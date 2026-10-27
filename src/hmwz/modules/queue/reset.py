from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord

from hmwz.i18n import t
from hmwz.ui import EphemeralView

from .models import Eruption, QueueConfiguration
from .rules import phase_schedule
from .schedule_picker import SchedulePickerView

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .module import QueueModule


@dataclass(slots=True)
class QueueResetDraft:
    module: QueueModule
    configuration: QueueConfiguration
    eruption: Eruption
    owner_id: int
    start_date: str = ""
    start_time: str = "00:00"
    timezone_name: str = ""
    starts_at: float | None = None
    ends_at: float | None = None
    phases: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        self.timezone_name = self.configuration.timezone
        if self.configuration.next_start_at is not None:
            local = datetime.fromtimestamp(
                self.configuration.next_start_at, timezone.utc
            ).astimezone(ZoneInfo(self.timezone_name))
            self.start_date = local.date().isoformat()
            self.start_time = local.strftime("%H:%M")
        else:
            tomorrow = discord.utils.utcnow().astimezone(
                ZoneInfo(self.timezone_name)
            ).date() + timedelta(days=1)
            self.start_date = tomorrow.isoformat()


class QueueResetView(EphemeralView):
    def __init__(self, draft: QueueResetDraft, confirm: bool = False) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        if confirm:
            self.add_item(QueueResetButton(self, True))
            self.add_item(QueueResetButton(self, False))
        else:
            self.add_item(QueueResetButton(self, None))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            permissions = getattr(interaction.user, "guild_permissions", None)
            if (
                permissions is not None
                and permissions.manage_channels
                and permissions.manage_roles
            ):
                return True
        await interaction.response.send_message(
            t(interaction, "queue.reset.moderator_only"), ephemeral=True
        )
        return False


class QueueResetButton(discord.ui.Button):
    def __init__(self, view: QueueResetView, confirm: bool | None) -> None:
        label = (
            "queue.reset.confirm"
            if confirm is True
            else "queue.reset.cancel"
            if confirm is False
            else "queue.reset.set_start"
        )
        super().__init__(
            label=t(view.draft.module.guild, label),
            style=discord.ButtonStyle.danger
            if confirm is True
            else discord.ButtonStyle.secondary,
            custom_id=f"queue:reset:{label}",
        )
        self.reset_view = view
        self.confirm = confirm

    async def callback(self, interaction: discord.Interaction) -> None:
        draft = self.reset_view.draft
        if self.confirm is None:

            async def finish_schedule(
                picker_interaction: discord.Interaction,
            ) -> None:
                try:
                    schedule = phase_schedule(
                        draft.start_date,
                        draft.timezone_name,
                        draft.configuration.phase_hours,
                        draft.start_time,
                    )
                except ValueError:
                    schedule = None
                if schedule is None:
                    if picker_interaction.message is not None:
                        await picker_interaction.message.edit(
                            content=t(
                                picker_interaction,
                                "queue.reset.invalid_start",
                            ),
                            view=SchedulePickerView(draft, on_done=finish_schedule),
                        )
                    return
                draft.starts_at, draft.ends_at, draft.phases = schedule
                local_start = datetime.fromtimestamp(
                    draft.starts_at, timezone.utc
                ).astimezone(ZoneInfo(draft.timezone_name))
                if picker_interaction.message is not None:
                    await picker_interaction.message.edit(
                        content=t(
                            picker_interaction,
                            "queue.reset.confirmation",
                            start=local_start.strftime("%Y-%m-%d %H:%M"),
                            timezone=draft.timezone_name,
                            discord_time=discord.utils.format_dt(
                                datetime.fromtimestamp(draft.starts_at, timezone.utc),
                                style="F",
                            ),
                            role_removal=t(
                                picker_interaction,
                                "queue.reset.enabled"
                                if draft.configuration.remove_role_on_reset
                                else "queue.reset.disabled",
                            ),
                        ),
                        view=QueueResetView(draft, confirm=True),
                    )

            picker = SchedulePickerView(draft, on_done=finish_schedule)
            await interaction.response.send_message(
                content=picker.summary(interaction),
                view=picker,
                ephemeral=True,
            )
            return
        if self.confirm is False:
            await interaction.response.edit_message(
                content=t(interaction, "queue.reset.cancelled"), view=None
            )
            return
        if draft.starts_at is None or draft.ends_at is None:
            await interaction.response.send_message(
                t(interaction, "queue.reset.invalid_start"), ephemeral=True
            )
            return
        try:
            result = await draft.module.reset_queue(
                draft.configuration,
                draft.eruption,
                draft.starts_at,
                draft.ends_at,
                draft.phases,
                draft.timezone_name,
            )
        except Exception:
            _logger.exception(
                "QS reset failed unexpectedly for guild %s, channel %s, eruption %s.",
                draft.module.guild.id,
                draft.configuration.channel_id,
                draft.eruption.id,
            )
            result = "failed"
        await interaction.response.edit_message(
            content=t(interaction, f"queue.reset.{result}"),
            view=self.reset_view if result == "failed" else None,
        )
