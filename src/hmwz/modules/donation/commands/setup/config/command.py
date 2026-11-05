from __future__ import annotations

import discord
from discord import app_commands
from discord.app_commands import locale_str

from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.donation.module import DonationModule
from hmwz.ui.messages import send_temporary_response as _send_temporary_response
from hmwz.ui.embeds import create_embed
from .view import (
    DonationSetupKindSelect,
    DonationSetupKindView,
    DonationSetupView,
)
from .configuration_message import donation_setup_panel


@app_commands.command(
    name="setup",
    description=locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.donation.setup",
            "Configure donations and their overview in this channel",
        ),
        key="donation.setup.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "offiziere", "Moderator", "moderator", "officier", "Officier")

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
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.text_channel_only")
        )
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    if not await module.sync():
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.setup_save")
        )
        return

    configuration = await module.donations.get_channel(
        guild=guild, channel_id=channel.id
    )
    donation_type = await module.donations.get_type(guild=guild, channel_id=channel.id)
    timezone_name = await module.client.get_guild_timezone(guild.id)
    if donation_type is not None:
        kind_select = DonationSetupKindSelect(
            module,
            channel.id,
            interaction.user.id,
            configuration,
            donation_type,
            timezone_name,
        )
        draft = kind_select.create_draft(donation_type.kind, interaction)
        summary = await module.donations.get_summary(
            guild=guild,
            channel_id=channel.id,
            cycle=configuration.current_cycle if configuration is not None else None,
        )
        if summary is None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.setup_save")
            )
            return
        draft.accelerated_hours = summary.time_reduction_hours
        await interaction.response.send_message(
            embed=donation_setup_panel(draft, interaction),
            view=DonationSetupView(draft),
            ephemeral=True,
        )
        return

    embed = create_embed(
        title=t(interaction, "donation.setup.title"),
        description=t(interaction, "donation.setup.choose_kind"),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=t(interaction, "donation.setup.channel"),
        value=channel.mention,
        inline=False,
    )
    await interaction.response.send_message(
        embed=embed,
        view=DonationSetupKindView(
            module,
            channel.id,
            interaction.user.id,
            configuration,
            donation_type,
            timezone_name,
        ),
        ephemeral=True,
    )
