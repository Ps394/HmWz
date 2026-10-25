from __future__ import annotations

import discord
from discord import app_commands

from hmwz.i18n import t
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.views import DonationDeleteConfirmationView


@app_commands.command(
    name="remove",
    description="Permanently remove all donations and setup from this channel",
)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def remove(interaction: discord.Interaction) -> None:
    """Permanently remove all donation data from the current channel."""
    await _prompt_delete(interaction)


@app_commands.command(
    name="delete",
    description="Permanently delete this channel's donation setup and history",
)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def delete(interaction: discord.Interaction) -> None:
    """Permanently delete all donation data from the current channel."""
    await _prompt_delete(interaction)


async def _prompt_delete(interaction: discord.Interaction) -> None:
    """Ask the invoking administrator to confirm permanent channel deletion."""
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
    if configuration is None:
        await interaction.response.send_message(
            t(interaction, "donation.error.not_configured"), ephemeral=True
        )
        return

    await interaction.response.send_message(
        t(interaction, "donation.delete.prompt"),
        view=DonationDeleteConfirmationView(
            module=module,
            channel_id=channel_id,
            owner_id=interaction.user.id,
            context=interaction,
        ),
        ephemeral=True,
    )
