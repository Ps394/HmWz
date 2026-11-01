"""Persistent automatic Qs notifications without offline start/end catch-up."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import aiosqlite
import discord
from discord.ext import tasks

from hmwz.utils.interactions import log_guild

from .models.constants import PHASE_GOAL

if TYPE_CHECKING:
    from .module import QsModule

_logger = logging.getLogger(__name__)


class QsNotifications:
    """Track connected time windows and persistent per-cycle notification flags."""

    def __init__(self, module: QsModule) -> None:
        self.module = module
        self.last_tick: float | None = None
        self.pending: set[tuple[int, int, str]] = set()

    def start(self) -> None:
        """Start the bounded-interval worker once the client is ready."""
        if not self.worker.is_running():
            self.last_tick = None
            self.pending.clear()
            self.worker.start()

    def stop(self) -> None:
        """Cancel notification delivery on client shutdown or guild removal."""
        self.worker.cancel()
        self.last_tick = None
        self.pending.clear()

    @tasks.loop(seconds=30)
    async def worker(self) -> None:
        """Deliver notifications only while Discord is connected."""
        if not self.module.client.is_ready():
            self.last_tick = None
            return
        now = time.time()
        previous = self.last_tick
        self.last_tick = now
        if previous is not None and now - previous > 90:
            previous = None
        try:
            await self.tick(now, previous)
        except (
            aiosqlite.Error,
            RuntimeError,
            discord.HTTPException,
            discord.RateLimited,
        ):
            _logger.exception(
                "%s Qs notification storage failed.", log_guild(self.module.guild)
            )

    async def tick(self, now: float, previous: float | None) -> None:
        """Skip offline deadlines; notify once for crossed online deadlines and goals."""
        module = self.module
        for configuration in await module.qs.all(module.guild.id):
            async with module._lock(configuration.channel_id):
                current = await module.qs.get(module.guild.id, configuration.channel_id)
                if current is None or current.state != "active":
                    continue
                for event, deadline, sent in (
                    ("start", current.eruption_start, current.start_notified),
                    ("end", current.eruption_end, current.end_notified),
                ):
                    if sent or deadline > now:
                        continue
                    key = (current.channel_id, current.eruption_start, event)
                    if previous is None or (
                        deadline <= previous and key not in self.pending
                    ):
                        if not await module.qs.notified(
                            module.guild.id, current.channel_id, event
                        ):
                            raise RuntimeError(
                                "Failed to persist skipped Qs notification."
                            )
                        self.pending.discard(key)
                    elif await module.ping(current.channel_id, event=event):
                        if not await module.qs.notified(
                            module.guild.id, current.channel_id, event
                        ):
                            raise RuntimeError("Failed to persist Qs notification.")
                        self.pending.discard(key)
                    else:
                        self.pending.add(key)
                await self.goals(current.channel_id)
                for phase in await module.qs.phases(
                    module.guild.id, current.channel_id
                ):
                    if phase.start_notified or phase.starts_at > now:
                        continue
                    key = (current.channel_id, phase.starts_at, f"phase:{phase.index}")
                    skipped = previous is None or (
                        phase.starts_at <= previous and key not in self.pending
                    )
                    try:
                        delivered = skipped or await module.ping_participants(
                            current.channel_id, phase
                        )
                    except (discord.HTTPException, discord.RateLimited, RuntimeError):
                        _logger.exception(
                            "%s Qs participant notification failed.",
                            log_guild(module.guild),
                        )
                        self.pending.add(key)
                        continue
                    if delivered:
                        if not await module.qs.notified(
                            module.guild.id,
                            current.channel_id,
                            "phase_start",
                            phase.index,
                        ):
                            raise RuntimeError(
                                "Failed to persist Qs phase-start notification."
                            )
                        self.pending.discard(key)
                    else:
                        self.pending.add(key)

    async def goals(self, channel_id: int) -> bool:
        """Send the target-completed ping once per phase after at least eight reports."""
        module = self.module
        reports = await module.qs.reports(module.guild.id, channel_id)
        success = True
        for phase in await module.qs.phases(module.guild.id, channel_id):
            if (
                phase.goal_notified
                or sum(report.phase_index == phase.index for report in reports)
                < PHASE_GOAL
            ):
                continue
            if not await module.ping(channel_id, event="goal", phase_index=phase.index):
                success = False
            elif not await module.qs.notified(
                module.guild.id, channel_id, "goal", phase.index
            ):
                success = False
        return success
