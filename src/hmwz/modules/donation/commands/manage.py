from __future__ import annotations

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.views import DonationDeleteConfirmationView
from ..responses import send_temporary_response as _send_temporary_response


@app_commands.command(
    name="remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.donation.remove",
            "Permanently remove all donations and setup from this channel",
        ),
        key="donation.remove.description",
    ),
)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def remove(interaction: discord.Interaction) -> None:
    """Permanently remove all donation data from the current channel."""
    await _prompt_delete(interaction)


async def _prompt_delete(interaction: discord.Interaction) -> None:
    """Ask the invoking administrator to confirm permanent channel deletion."""
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
    if configuration is None:
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    view = DonationDeleteConfirmationView(
        module=module,
        channel_id=channel_id,
        owner_id=interaction.user.id,
        context=interaction,
    )
    await interaction.response.send_message(
        t(interaction, "donation.delete.prompt"),
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()
