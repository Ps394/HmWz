from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord import app_commands

from hmwz.i18n import t
from hmwz.modules.donation.validation import parse_rush_start

if TYPE_CHECKING:
    from hmwz.modules.donation.module import DonationModule


@app_commands.command(
    name="reset",
    description="Start a new donation cycle in this channel",
)
@app_commands.checks.has_permissions(manage_channels=True)
async def reset(interaction: discord.Interaction) -> None:
    """Reset current-cycle views while retaining the channel's all-time ranking."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "donation.error.not_configured"), ephemeral=True
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel_id
    )
    donation_type = await module.donations.get_type(guild=guild, channel_id=channel_id)
    if configuration is None or donation_type is None:
        await interaction.response.send_message(
            t(interaction, "donation.error.not_configured"), ephemeral=True
        )
        return

    if donation_type.kind == "time_reduction":
        await interaction.response.send_modal(
            DonationRushResetModal(module, channel_id, interaction.user.id)
        )
        return

    await interaction.response.send_message(
        t(interaction, "donation.reset.simple_prompt"),
        view=DonationCycleResetView(module, channel_id, interaction.user.id),
        ephemeral=True,
    )


class DonationCycleResetView(discord.ui.View):
    """Confirm a simple-donation cycle reset without deleting its history."""

    def __init__(self, module: DonationModule, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=120)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    module.guild,
                    "donation.reset.confirm"
                    if item.custom_id == "donation_reset_confirm"
                    else "donation.delete.cancel",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.setup.owner_only"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Start new cycle",
        style=discord.ButtonStyle.danger,
        custom_id="donation_reset_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated = await self.module.reset_cycle(
            self.channel_id, rush_start_at=None
        )
        result_key = _reset_result_key(reset_done, messages_updated)
        self.stop()
        await interaction.followup.send(t(interaction, result_key), ephemeral=True)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_reset_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=t(interaction, "donation.reset.cancelled"), view=None
        )


class DonationRushResetModal(discord.ui.Modal):
    """Set the next Rush cycle's Berlin-local start date and time."""

    def __init__(self, module: DonationModule, channel_id: int, owner_id: int) -> None:
        super().__init__(title=t(module.guild, "donation.reset.start_modal_title")[:45])
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        current_time = datetime.now(ZoneInfo("Europe/Berlin"))
        self.date_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "donation.setup.start_date")[:45],
            placeholder="YYYY-MM-DD",
            default=current_time.strftime("%Y-%m-%d"),
            max_length=10,
        )
        self.time_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "donation.setup.start_time")[:45],
            placeholder="HH:MM",
            default=current_time.strftime("%H:%M"),
            max_length=5,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                t(interaction, "donation.setup.owner_only"), ephemeral=True
            )
            return
        try:
            rush_start_at = parse_rush_start(
                self.date_input.value, self.time_input.value
            )
        except ValueError:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_rush_start"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated = await self.module.reset_cycle(
            self.channel_id, rush_start_at=rush_start_at
        )
        await interaction.followup.send(
            t(interaction, _reset_result_key(reset_done, messages_updated)),
            ephemeral=True,
        )


def _reset_result_key(reset_done: bool, messages_updated: bool) -> str:
    if not reset_done:
        return "donation.error.reset"
    if messages_updated:
        return "donation.success.reset"
    return "donation.success.reset_overview_failed"
