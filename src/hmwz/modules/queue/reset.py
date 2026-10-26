from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord

from hmwz.i18n import t
from hmwz.ui import EphemeralView

from .models import Eruption, QueueConfiguration
from .rules import phase_schedule

if TYPE_CHECKING:
    from .module import QueueModule


@dataclass(slots=True)
class QueueResetDraft:
    module: QueueModule
    configuration: QueueConfiguration
    eruption: Eruption
    owner_id: int
    starts_at: float | None = None
    ends_at: float | None = None
    phases: tuple[tuple[float, float], ...] = ()


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
            await interaction.response.send_modal(QueueNextStartModal(draft))
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
        result = await draft.module.reset_queue(
            draft.configuration,
            draft.eruption,
            draft.starts_at,
            draft.ends_at,
            draft.phases,
        )
        await interaction.response.edit_message(
            content=t(interaction, f"queue.reset.{result}"),
            view=self.reset_view if result == "failed" else None,
        )


class QueueNextStartModal(discord.ui.Modal):
    def __init__(self, draft: QueueResetDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.reset.start_title"), timeout=300
        )
        self.draft = draft
        self.start: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.reset.start_label"),
            placeholder="YYYY-MM-DD HH:MM",
            max_length=16,
        )
        self.add_item(self.start)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            date_text, time_text = self.start.value.strip().split(" ", 1)
            schedule = phase_schedule(
                date_text,
                self.draft.configuration.timezone,
                self.draft.configuration.phase_hours,
                time_text,
            )
        except ValueError:
            schedule = None
        if schedule is None:
            await interaction.response.send_message(
                t(interaction, "queue.reset.invalid_start"), ephemeral=True
            )
            return
        starts_at, ends_at, phases = schedule
        if starts_at <= discord.utils.utcnow().timestamp():
            await interaction.response.send_message(
                t(interaction, "queue.reset.past_start"), ephemeral=True
            )
            return
        self.draft.starts_at = starts_at
        self.draft.ends_at = ends_at
        self.draft.phases = phases
        local = datetime.fromtimestamp(starts_at, timezone.utc).astimezone(
            ZoneInfo(self.draft.configuration.timezone)
        )
        view = QueueResetView(self.draft, confirm=True)
        await interaction.response.send_message(
            content=t(
                interaction,
                "queue.reset.confirmation",
                start=local.strftime("%Y-%m-%d %H:%M"),
                timezone=self.draft.configuration.timezone,
                role_removal=t(
                    interaction,
                    "queue.reset.enabled"
                    if self.draft.configuration.remove_role_on_reset
                    else "queue.reset.disabled",
                ),
            ),
            view=view,
            ephemeral=True,
        )
