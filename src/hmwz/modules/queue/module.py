from __future__ import annotations

import asyncio
import logging
import time

import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .overview import QueueOverview
from .repository import QueueConfiguration, QueueRepository, QueueRun
from .views import QueueOverviewView, RunConfirmationView

_logger = logging.getLogger(__name__)


@register
class QueueModule(BasicModule):
    """Guild-scoped, channel-specific queues and run confirmations."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("Queue module requires a database.")
        self.queues = QueueRepository(self.database)
        self._queue_locks: dict[int, asyncio.Lock] = {}
        self._overview_messages: dict[int, discord.Message] = {}
        self._registered_views: set[tuple[int, int]] = set()
        self._maintenance_task: asyncio.Task[None] | None = None

    async def sync(self, startup: bool = False) -> bool:
        return await self.queues.ensure_schema()

    async def ensure(self) -> bool:
        if not await self.queues.ensure_schema():
            return False
        success = True
        configurations = await self.queues.get_all(guild=self.guild)
        for configuration in configurations:
            members = await self.queues.get_members(
                guild=self.guild, channel_id=configuration.channel_id
            )
            while len(members) >= configuration.max_players:
                if not await self._start_run(configuration, members):
                    success = False
                    break
                members = await self.queues.get_members(
                    guild=self.guild, channel_id=configuration.channel_id
                )
            if not await self.compose_overview(configuration.channel_id):
                success = False
        for run in await self.queues.get_active_runs(guild=self.guild):
            await self._register_confirmation_view(run)
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        return success

    async def configure(
        self,
        *,
        channel_id: int,
        name: str,
        min_players: int,
        max_players: int,
        confirmation_delay_minutes: int,
        reminder_interval_minutes: int,
    ) -> bool:
        if not await self.queues.configure(
            guild=self.guild,
            channel_id=channel_id,
            name=name,
            min_players=min_players,
            max_players=max_players,
            confirmation_delay_minutes=confirmation_delay_minutes,
            reminder_interval_minutes=reminder_interval_minutes,
        ):
            return False
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            if configuration is None:
                return False
            members = await self.queues.get_members(
                guild=self.guild, channel_id=channel_id
            )
            while len(members) >= configuration.max_players:
                if not await self._start_run(configuration, members):
                    return False
                members = await self.queues.get_members(
                    guild=self.guild, channel_id=channel_id
                )
        if not await self.compose_overview(channel_id):
            return False
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        return True

    async def remove_queue(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            return False
        if any(
            run.channel_id == channel_id
            for run in await self.queues.get_active_runs(guild=self.guild)
        ):
            return False
        if not await self.queues.remove(guild=self.guild, channel_id=channel_id):
            return False
        message = self._overview_messages.pop(channel_id, None)
        if message is None and configuration.message_id is not None:
            channel = self.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(configuration.message_id)
                except discord.NotFound:
                    message = None
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to fetch removed queue overview in channel %s.",
                        self.guild.name,
                        channel_id,
                    )
        if message is not None:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to delete removed queue overview in channel %s.",
                    self.guild.name,
                    channel_id,
                )
        return True

    async def compose_overview(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            return False
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "%s Queue channel %s is unavailable or not a text channel.",
                self.guild.name,
                channel_id,
            )
            return False

        view = QueueOverviewView(self, channel_id)
        embed = await QueueOverview.create_embed(self.guild, configuration, self.queues)
        message = self._overview_messages.get(channel_id)
        if message is None and configuration.message_id is not None:
            try:
                message = await channel.fetch_message(configuration.message_id)
            except discord.NotFound:
                message = None
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch queue overview in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                return False

        try:
            if message is None:
                message = await channel.send(embed=embed, view=view)
                if not await self.queues.set_message(
                    guild=self.guild,
                    channel_id=channel_id,
                    message_id=message.id,
                ):
                    _logger.error(
                        "%s Failed to save queue overview message %s.",
                        self.guild.name,
                        message.id,
                    )
                    return False
            else:
                await message.edit(embed=embed, view=view)
            self._overview_messages[channel_id] = message
            self._register_view(view, message.id)
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to publish queue overview in channel %s.",
                self.guild.name,
                channel_id,
            )
            return False

    async def handle_queue_action(
        self, interaction: discord.Interaction, channel_id: int, action: str
    ) -> None:
        guild = interaction.guild
        if (
            guild is None
            or guild.id != self.guild.id
            or not isinstance(interaction.user, discord.Member)
            or interaction.channel_id != channel_id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            if configuration is None:
                await interaction.followup.send(
                    t(interaction, "queue.error.not_configured"), ephemeral=True
                )
                return
            members = await self.queues.get_members(
                guild=self.guild, channel_id=channel_id
            )
            member_id = interaction.user.id
            if action == "join" and len(members) >= configuration.max_players:
                if not await self._start_run(configuration, members):
                    await interaction.followup.send(
                        t(interaction, "queue.error.run_start_failed"),
                        ephemeral=True,
                    )
                    return
                response = t(interaction, "queue.action.run_started")
                await interaction.followup.send(response, ephemeral=True)
                await self.compose_overview(channel_id)
                return
            if action == "leave":
                if member_id not in members or not await self.queues.leave(
                    guild=self.guild, channel_id=channel_id, member_id=member_id
                ):
                    await interaction.followup.send(
                        t(interaction, "queue.error.not_waiting"), ephemeral=True
                    )
                    return
                response = t(interaction, "queue.action.left")
            else:
                if member_id in members:
                    await interaction.followup.send(
                        t(interaction, "queue.error.already_waiting"), ephemeral=True
                    )
                    return
                if len(members) >= configuration.max_players:
                    await interaction.followup.send(
                        t(interaction, "queue.error.full"), ephemeral=True
                    )
                    return
                if not await self.queues.join(
                    guild=self.guild,
                    channel_id=channel_id,
                    member_id=member_id,
                    joined_at=time.time(),
                ):
                    await interaction.followup.send(
                        t(interaction, "queue.error.join_failed"), ephemeral=True
                    )
                    return
                response = t(interaction, "queue.action.joined")
                members = (*members, member_id)
                if len(members) >= configuration.max_players:
                    if not await self._start_run(configuration, members):
                        await interaction.followup.send(
                            t(interaction, "queue.error.run_start_failed"),
                            ephemeral=True,
                        )
                        await self.compose_overview(channel_id)
                        return
                    response = t(interaction, "queue.action.run_started")

        await interaction.followup.send(response, ephemeral=True)
        await self.compose_overview(channel_id)

    async def _start_run(
        self, configuration: QueueConfiguration, members: tuple[int, ...]
    ) -> bool:
        if len(members) < configuration.max_players:
            return False
        channel = self.guild.get_channel(configuration.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        thread: discord.Thread | None = None
        try:
            thread = await channel.create_thread(
                name=f"{configuration.name[:90]} - Run",
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=1440,
            )
            run_members: list[discord.Member] = []
            for member_id in members[: configuration.max_players]:
                member = self.guild.get_member(member_id)
                if member is None:
                    member = await self.guild.fetch_member(member_id)
                await thread.add_user(member)
                run_members.append(member)

            now = time.time()
            available_at = now + configuration.confirmation_delay_minutes * 60
            content = t(
                self.guild,
                "queue.run.started",
                members=", ".join(member.mention for member in run_members),
                minutes=configuration.confirmation_delay_minutes,
            )
            message = await thread.send(
                content,
                view=RunConfirmationView(
                    self,
                    run_id=0,
                    enabled=False,
                    completed=False,
                ),
            )
            run_id = await self.queues.create_run(
                guild=self.guild,
                channel_id=configuration.channel_id,
                thread_id=thread.id,
                message_id=message.id,
                members=tuple(member.id for member in run_members),
                started_at=now,
                confirmation_available_at=available_at,
            )
            if run_id is None:
                await thread.edit(archived=True)
                return False

            # Replace the placeholder control with a run-specific persistent view.
            try:
                await message.edit(
                    view=RunConfirmationView(
                        self,
                        run_id=run_id,
                        enabled=available_at <= time.time(),
                        completed=False,
                    )
                )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to update confirmation controls for run %s.",
                    self.guild.name,
                    run_id,
                )
            run = await self.queues.get_run(run_id)
            if run is not None:
                await self._register_confirmation_view(run)
            if available_at <= time.time():
                await self._process_due_confirmations()
            return True
        except (discord.HTTPException, discord.NotFound):
            _logger.exception(
                "%s Failed to start queue run in channel %s.",
                self.guild.name,
                configuration.channel_id,
            )
            if thread is not None:
                try:
                    await thread.edit(archived=True)
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to archive incomplete queue thread %s.",
                        self.guild.name,
                        thread.id,
                    )
            return False

    async def confirm_run(self, interaction: discord.Interaction, run_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        run = await self.queues.get_run(run_id)
        if (
            run is None
            or run.guild_id != self.guild.id
            or run.status != "active"
            or interaction.guild_id != self.guild.id
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.run_unavailable"), ephemeral=True
            )
            return
        if time.time() < run.confirmation_available_at:
            await interaction.followup.send(
                t(interaction, "queue.error.confirmation_too_early"),
                ephemeral=True,
            )
            return
        participants = await self.queues.get_run_participants(run_id)
        participant = next(
            (item for item in participants if item.member_id == interaction.user.id),
            None,
        )
        if participant is None:
            await interaction.followup.send(
                t(interaction, "queue.error.not_run_member"), ephemeral=True
            )
            return
        if participant.confirmed_at is not None:
            await interaction.followup.send(
                t(interaction, "queue.error.already_confirmed"), ephemeral=True
            )
            return
        if not await self.queues.confirm(
            run_id=run_id, member_id=interaction.user.id, confirmed_at=time.time()
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.confirm_failed"), ephemeral=True
            )
            return

        participants = await self.queues.get_run_participants(run_id)
        all_confirmed = bool(participants) and all(
            item.confirmed_at is not None for item in participants
        )
        if all_confirmed:
            if not await self.queues.complete_run(run_id):
                await interaction.followup.send(
                    t(interaction, "queue.error.confirm_failed"), ephemeral=True
                )
                return
            response_key = "queue.confirmation.completed"
        else:
            response_key = "queue.confirmation.saved"
        await interaction.followup.send(t(interaction, response_key), ephemeral=True)
        await self._refresh_run_message(run_id)
        if all_confirmed:
            await self.compose_overview(run.channel_id)

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                await self._process_due_confirmations()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("%s Queue maintenance failed.", self.guild.name)
            await asyncio.sleep(30)

    async def _process_due_confirmations(self) -> None:
        now = time.time()
        for run in await self.queues.get_active_runs(guild=self.guild):
            if now < run.confirmation_available_at:
                continue
            configuration = await self.queues.get(
                guild=self.guild, channel_id=run.channel_id
            )
            if configuration is None:
                continue
            participants = await self.queues.get_run_participants(run.id)
            if not participants:
                _logger.error(
                    "%s Active queue run %s has no participants.",
                    self.guild.name,
                    run.id,
                )
                continue
            if all(item.confirmed_at is not None for item in participants):
                if await self.queues.complete_run(run.id):
                    await self.compose_overview(run.channel_id)
                continue
            overdue = tuple(
                item
                for item in participants
                if item.confirmed_at is None
                and (
                    item.last_reminded_at is None
                    or now - item.last_reminded_at
                    >= configuration.reminder_interval_minutes * 60
                )
            )
            if not overdue:
                continue
            thread = await self._fetch_thread(run.thread_id)
            if thread is None:
                continue
            await self._refresh_run_message(run.id)
            if thread.archived:
                try:
                    await thread.edit(archived=False)
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to reopen queue run thread %s.",
                        self.guild.name,
                        thread.id,
                    )
                    continue
            mentions = " ".join(f"<@{item.member_id}>" for item in overdue)
            try:
                await thread.send(
                    t(
                        self.guild,
                        "queue.run.reminder",
                        members=mentions,
                    ),
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=item.member_id) for item in overdue]
                    ),
                )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to send confirmation reminder for run %s.",
                    self.guild.name,
                    run.id,
                )
                continue
            for participant in overdue:
                if not await self.queues.mark_reminded(
                    run_id=run.id,
                    member_id=participant.member_id,
                    reminded_at=now,
                ):
                    _logger.error(
                        "%s Failed to record confirmation reminder for member %s "
                        "in run %s.",
                        self.guild.name,
                        participant.member_id,
                        run.id,
                    )

    async def _refresh_run_message(self, run_id: int) -> None:
        run = await self.queues.get_run(run_id)
        if run is None:
            return
        participants = await self.queues.get_run_participants(run_id)
        completed = run.status == "completed"
        confirmed_count = sum(item.confirmed_at is not None for item in participants)
        thread = await self._fetch_thread(run.thread_id)
        if thread is None:
            return
        try:
            message = await thread.fetch_message(run.message_id)
            await message.edit(
                content=t(
                    self.guild,
                    "queue.run.confirmation_status",
                    confirmed=confirmed_count,
                    total=len(participants),
                ),
                view=RunConfirmationView(
                    self,
                    run_id,
                    enabled=time.time() >= run.confirmation_available_at,
                    completed=completed,
                ),
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to update confirmation message for run %s.",
                self.guild.name,
                run_id,
            )

    async def _register_confirmation_view(self, run: QueueRun) -> None:
        key = (run.id, run.message_id)
        if key in self._registered_views:
            return
        view = RunConfirmationView(
            self,
            run.id,
            enabled=time.time() >= run.confirmation_available_at,
            completed=run.status == "completed",
        )
        self.client.add_view(view, message_id=run.message_id)
        self._registered_views.add(key)

    def _register_view(self, view: discord.ui.View, message_id: int) -> None:
        key = (0, message_id)
        if key in self._registered_views:
            return
        self.client.add_view(view, message_id=message_id)
        self._registered_views.add(key)

    async def _fetch_thread(self, thread_id: int) -> discord.Thread | None:
        channel = self.guild.get_channel_or_thread(thread_id)
        if isinstance(channel, discord.Thread):
            return channel
        try:
            fetched = await self.client.fetch_channel(thread_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to fetch queue run thread %s.",
                self.guild.name,
                thread_id,
            )
            return None
        return fetched if isinstance(fetched, discord.Thread) else None

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        if guild.id != self.guild.id:
            return False
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            self._maintenance_task = None
        return True

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        if channel.guild.id != self.guild.id:
            return False
        if await self.queues.get(guild=self.guild, channel_id=channel.id) is None:
            return True
        return await self.remove_queue(channel.id)

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id or payload.channel_id is None:
            return False
        configuration = await self.queues.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None or configuration.message_id != payload.message_id:
            return True
        self._overview_messages.pop(payload.channel_id, None)
        if not await self.queues.set_message(
            guild=self.guild, channel_id=payload.channel_id, message_id=0
        ):
            return False
        return await self.compose_overview(payload.channel_id)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id:
            return False
        configuration = await self.queues.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None or configuration.message_id not in payload.message_ids:
            return True
        self._overview_messages.pop(payload.channel_id, None)
        if not await self.queues.set_message(
            guild=self.guild, channel_id=payload.channel_id, message_id=0
        ):
            return False
        return await self.compose_overview(payload.channel_id)
