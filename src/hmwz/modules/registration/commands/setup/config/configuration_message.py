"""Render a summary of registration settings for setup views."""

from __future__ import annotations

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.modules.registration.module import RegistrationModule
from hmwz.ui.embeds import create_embed

from .draft import RegistrationSetupDraft


async def configuration_message(
    module: RegistrationModule,
    interaction: discord.Interaction,
    channel_id: int,
    draft: RegistrationSetupDraft | None = None,
) -> discord.Embed:
    """Summarize the current registration settings for the setup panel."""
    channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
    channel_mention = channel.mention if channel is not None else f"<#{channel_id}>"
    settings = (
        None
        if draft is not None
        else await module.registration.get(guild=module.guild, channel_id=channel_id)
    )
    roles = (
        None
        if draft is not None
        else await module.roles.get(guild=module.guild, channel_id=channel_id)
    )
    configured_title = (
        draft.title
        if draft is not None
        else settings.title
        if settings and settings.title
        else ""
    )
    title_default = not configured_title
    title = configured_title or t(
        interaction, f"{module.module_key}.overview.default_title"
    )
    configured_description = (
        draft.description
        if draft is not None
        else settings.description
        if settings and settings.description
        else ""
    )
    description_default = not configured_description
    description = configured_description or t(
        interaction, f"{module.module_key}.overview.default_description"
    )
    role_summary = []
    role_items = (
        draft.roles.items()
        if draft is not None
        else ((role.role, role.permanent) for role in roles or ())
    )
    for role_id, permanent in role_items:
        guild_role = module.guild.get_role(role_id)
        role_name = (
            guild_role.mention
            if guild_role is not None
            else t(
                interaction,
                "registration.setup.config.missing_role",
                role_id=role_id,
            )
        )
        permanence = emojis.get(
            "perma_registration" if permanent else "normal_registration",
            interaction,
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
    role_count = len(draft.roles) if draft is not None else len(roles or ())

    export_channel_id = (
        draft.export_channel_id
        if draft is not None
        else await module.registration_event_channel.get(guild=module.guild)
    )
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
        description=(
            t(interaction, "registration.setup.config.pending")
            if draft is not None
            else None
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
            count=role_count,
        ),
        value="\n".join(role_summary),
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.export_channel"),
        value=export_status,
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "registration.setup.config.lock_emojis"),
        value=t(
            interaction,
            "registration.setup.config.lock_emojis_enabled"
            if (
                draft.show_lock_emojis
                if draft is not None
                else settings is None or settings.show_lock_emojis
            )
            else "registration.setup.config.lock_emojis_disabled",
        ),
        inline=False,
    )
    return embed
