from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.validation import (
    donation_timezone,
    donation_timezone_translation_key,
    parse_rush_start,
)
from ..responses import send_temporary_response as _send_temporary_response


@app_commands.command(
    name="reset",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.donation.reset",
            "Start a new donation cycle in this channel",
        ),
        key="donation.reset.description",
    ),
)
@app_commands.checks.has_permissions(manage_channels=True)
async def reset(interaction: discord.Interaction) -> None:
    """Reset current-cycle views while retaining the channel's all-time ranking."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel_id
    )
    donation_type = await module.donations.get_type(guild=guild, channel_id=channel_id)
    if configuration is None or donation_type is None:
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    if donation_type.kind == "time_reduction":
        await interaction.response.send_modal(
            DonationRushResetModal(
                module,
                channel_id,
                interaction.user.id,
                configuration.timezone_name,
            )
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
        await _send_temporary_response(
            interaction, t(interaction, "donation.setup.owner_only")
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
        reset_done, messages_updated, export_failed = await self.module.reset_cycle(
            self.channel_id, rush_start_at=None
        )
        result_key = _reset_result_key(
            reset_done, messages_updated, export_failed=export_failed
        )
        self.stop()
        await interaction.delete_original_response()
        result = await interaction.followup.send(
            t(interaction, result_key), ephemeral=True, wait=True
        )
        await result.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_reset_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer(ephemeral=True)
        await interaction.delete_original_response()


class DonationRushResetModal(discord.ui.Modal):
    """Set the next Rush start using the channel's configured timezone."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
        timezone_name: str,
    ) -> None:
        super().__init__(title=t(module.guild, "donation.reset.start_modal_title")[:45])
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.timezone_name = timezone_name
        current_time = datetime.now(donation_timezone(timezone_name))
        self.date_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(
                module.guild,
                "donation.setup.start_date",
                timezone=t(
                    module.guild, donation_timezone_translation_key(timezone_name)
                ),
            )[:45],
            placeholder="YYYY-MM-DD",
            default=current_time.strftime("%Y-%m-%d"),
            max_length=10,
        )
        self.time_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(
                module.guild,
                "donation.setup.start_time",
                timezone=t(
                    module.guild, donation_timezone_translation_key(timezone_name)
                ),
            )[:45],
            placeholder="HH:MM",
            default=current_time.strftime("%H:%M"),
            max_length=5,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await _send_temporary_response(
                interaction, t(interaction, "donation.setup.owner_only")
            )
            return
        try:
            rush_start_at = parse_rush_start(
                self.date_input.value,
                self.time_input.value,
                self.timezone_name,
            )
        except ValueError:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_rush_start")
            )
            return
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated, export_failed = await self.module.reset_cycle(
            self.channel_id, rush_start_at=rush_start_at
        )
        result = await interaction.followup.send(
            t(
                interaction,
                _reset_result_key(
                    reset_done, messages_updated, export_failed=export_failed
                ),
            ),
            ephemeral=True,
            wait=True,
        )
        await result.delete(delay=5)


def _reset_result_key(
    reset_done: bool, messages_updated: bool, *, export_failed: bool = False
) -> str:
    if export_failed:
        return "donation.error.reset_export"
    if not reset_done:
        return "donation.error.reset"
    if messages_updated:
        return "donation.success.reset"
    return "donation.success.reset_overview_failed"
