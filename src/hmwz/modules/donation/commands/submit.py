from __future__ import annotations

import discord
from discord import app_commands

from hmwz.i18n import t
from hmwz.modules.donation.module import DonationModule


@app_commands.command(
    name="eintragen",
    description="Eine Spende in diesem Kanal eintragen",
)
async def submit(interaction: discord.Interaction) -> None:
    """Open the donation type selector in the current configured channel."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "donation.error.not_configured"), ephemeral=True
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    if channel_id not in await module.donations.get_channels(guild=guild):
        await interaction.response.send_message(
            t(interaction, "donation.error.not_configured"), ephemeral=True
        )
        return
    await module.show_donation_type_selection(interaction, channel_id)
