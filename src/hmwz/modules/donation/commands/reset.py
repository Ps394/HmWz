"""Route the cycle reset command to the configured donation type."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_response

from ..module import DonationModule
from ..type.credit.reset import DonationCycleResetView
from ..type.rush.reset import DonationRushResetModal


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
@app_commands.checks.has_any_role("Offiziere", "offiziere", "Moderator", "moderator", "officier", "Officier")

async def reset(interaction: discord.Interaction) -> None:
    """Reset current-cycle views while retaining the channel's all-time ranking."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel_id
    )
    donation_type = await module.donations.get_type(guild=guild, channel_id=channel_id)
    if configuration is None or donation_type is None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return

    if donation_type.kind == "time_reduction":
        await interaction.response.send_modal(
            DonationRushResetModal(
                module,
                channel_id,
                interaction.user.id,
                timezone_name=configuration.timezone_name,
            )
        )
        return
    await interaction.response.send_message(
        t(interaction, "donation.reset.simple_prompt"),
        view=DonationCycleResetView(module, channel_id, interaction.user.id),
        ephemeral=True,
    )
