from __future__ import annotations

import discord
from discord import app_commands
from discord.app_commands import locale_str

from hmwz.i18n import t
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.setup_views import (
    DonationSetupKindSelect,
    DonationSetupKindView,
    DonationSetupView,
    donation_setup_panel,
)


@app_commands.command(
    name="setup",
    description=locale_str("Configure donations and their overview in this channel"),
)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
)
async def setup(interaction: discord.Interaction) -> None:
    """Open the guided configuration menu for the current text channel."""
    guild = interaction.guild
    channel = interaction.channel
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or manager is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            t(interaction, "donation.error.text_channel_only"),
            ephemeral=True,
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    if not await module.sync():
        await interaction.response.send_message(
            t(interaction, "donation.error.setup_save"), ephemeral=True
        )
        return

    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel.id
    )
    donation_type = await module.donations.get_type(guild=guild, channel_id=channel.id)
    if donation_type is not None:
        kind_select = DonationSetupKindSelect(
            module,
            channel.id,
            interaction.user.id,
            configuration,
            donation_type,
        )
        draft = kind_select.create_draft(donation_type.kind, interaction)
        await interaction.response.send_message(
            content=donation_setup_panel(draft, interaction),
            view=DonationSetupView(draft),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        t(interaction, "donation.setup.choose_kind"),
        view=DonationSetupKindView(
            module,
            channel.id,
            interaction.user.id,
            configuration,
            donation_type,
        ),
        ephemeral=True,
    )
