"""Render a summary of registration settings for setup views."""

from __future__ import annotations

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.modules.registration.module import RegistrationModule
from hmwz.ui.embeds import create_embed


async def configuration_message(
    module: RegistrationModule,
    interaction: discord.Interaction,
    channel_id: int,
) -> discord.Embed:
    """Summarize the current registration settings for the setup panel."""
    channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
    channel_mention = channel.mention if channel is not None else f"<#{channel_id}>"
    settings = await module.registration.get(guild=module.guild, channel_id=channel_id)
    roles = await module.roles.get(guild=module.guild, channel_id=channel_id)
    title = (
        settings.title
        if settings and settings.title
        else t(interaction, f"{module.module_key}.overview.default_title")
    )
    title_default = not settings or not settings.title
    description = (
        settings.description
        if settings and settings.description
        else t(interaction, f"{module.module_key}.overview.default_description")
    )
    description_default = not settings or not settings.description
    role_summary = []
    for role in roles or ():
        guild_role = module.guild.get_role(role.role)
        role_name = (
            guild_role.mention
            if guild_role is not None
            else t(
                interaction,
                "registration.setup.config.missing_role",
                role_id=role.role,
            )
        )
        permanence = (
            emojis.get(
                "perma_registration" if role.permanent else "normal_registration",
                interaction,
            )
        )
        role_summary.append(
            t(
                interaction,
                "registration.setup.config.role_summary",
                role=role_name,
                permanence=permanence,
            )
        )
    if not role_summary:
        role_summary.append(t(interaction, "registration.setup.config.no_roles"))

    export_channel_id = await module.registration_event_channel.get(guild=module.guild)
    export_channel = (
        module.guild.get_channel(export_channel_id)
        if export_channel_id is not None
        else None
    )
    if export_channel is not None:
        export_status = export_channel.mention
    elif export_channel_id is not None:
        export_status = t(
            interaction,
            "registration.setup.config.export_channel_unavailable",
            channel_id=export_channel_id,
        )
    else:
        export_status = t(interaction, "registration.setup.config.export_disabled")

    embed = create_embed(
        title=t(
            interaction,
            "registration.setup.config.panel",
            channel=channel_mention,
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.channel"),
        value=channel_mention,
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.title"),
        value=(
            f"**{title}**\n{t(interaction, 'registration.setup.config.default')}"
            if title_default
            else f"**{title}**"
        ),
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.description"),
        value=(
            f"{t(interaction, 'registration.setup.config.default')}\n"
            if description_default
            else ""
        )
        + f"{description[:947]}{'...' if len(description) > 950 else ''}",
        inline=False,
    )
    embed.add_field(
        name=t(
            interaction,
            "registration.setup.config.roles",
            count=len(roles or ()),
        ),
        value="\n".join(role_summary),
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.export_channel"),
        value=export_status,
        inline=False,
    )
    return embed
