"""Owner-bound confirmations for removing or resetting the Qs tool."""

from __future__ import annotations

import logging
from typing import Literal

import aiosqlite
import discord

from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.messages import send_followup, defer_interaction
from hmwz.ui.components.localized import localize_buttons
from hmwz.utils.interactions import log_guild

from ..module import QsModule
from ..setup import can_manage

_logger = logging.getLogger(__name__)


class QsMaintenanceConfirmation(EphemeralView):
    """Require explicit confirmation and recheck the moderator's permissions."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        owner_id: int,
        *,
        action: Literal["remove", "reset"],
        date: str = "",
        hours: tuple[int, ...] = (),
        timezone: str = "UTC",
        eruption_start: int = 0,
        durations: tuple[int, ...] = (),
    ) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.action = action
        self.date, self.hours, self.timezone = date, hours, timezone
        self.eruption_start, self.durations = eruption_start, durations
        self.running = False
        localize_buttons(
            self,
            module.guild,
            {
                "qs_admin_confirm": "qs.admin.confirm",
                "qs_admin_cancel": "qs.admin.cancel",
            },
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Reject foreign users, lost privileges and duplicate executions."""
        if (
            not self.running
            and interaction.user.id == self.owner_id
            and interaction.guild_id == self.module.guild.id
            and can_manage(interaction.user)
            and isinstance(interaction.user, discord.Member)
            and interaction.permissions.manage_messages
            and interaction.app_permissions.manage_threads
            and interaction.app_permissions.manage_messages
        ):
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.admin.denied")
        )
        return False

    @discord.ui.button(
        label="Confirm", style=discord.ButtonStyle.danger, custom_id="qs_admin_confirm"
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Perform destructive operations only after revalidating the confirmation."""
        if not await self.interaction_check(interaction):
            return
        self.running = True
        await defer_interaction(interaction, thinking=True)
        try:
            if self.action == "remove":
                success = await self.module.remove_tool(self.channel_id)
            else:
                success = await self.module.reset_tool(
                    self.channel_id,
                    self.date,
                    self.hours,
                    self.timezone,
                    eruption_start=self.eruption_start,
                    durations=self.durations,
                )
        except (ValueError, aiosqlite.Error, discord.HTTPException):
            _logger.exception(
                "%s Qs %s failed.", log_guild(self.module.guild), self.action
            )
            success = False
        if success:
            await self.finish(
                interaction, t(interaction, f"qs.admin.{self.action}_success")
            )
        else:
            self.running = False
            await send_followup(
                interaction, t(interaction, "qs.admin.maintenance_failed")
            )

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="qs_admin_cancel"
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Cancel without changing messages, threads or data."""
        if not await self.interaction_check(interaction):
            return
        await self.dismiss(interaction)
