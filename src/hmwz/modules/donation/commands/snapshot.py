"""Explicit export of the active donation cycle."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_followup, send_temporary_response

from ..module import DonationModule


@app_commands.command(
    name="snapshot",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.donation.snapshot",
            "Export a JSON snapshot of the current donation cycle",
        ),
        key="donation.snapshot.description",
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def snapshot(interaction: discord.Interaction) -> None:
    """Export all current-cycle donations without resetting the cycle."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    await interaction.response.defer(ephemeral=True)
    module: DonationModule = await manager.get_module(guild, DonationModule)
    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel_id
    )
    if configuration is None:
        result_key = "donation.error.not_configured"
    elif configuration.export_channel_id is None:
        result_key = "donation.error.snapshot_destination"
    elif await module.export_donation_snapshot(channel_id):
        result_key = "donation.success.snapshot"
    else:
        result_key = "donation.error.snapshot"
    await send_temporary_followup(interaction, t(interaction, result_key))
