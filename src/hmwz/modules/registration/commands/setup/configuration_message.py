from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.modules.hs.wz.module import WzRegistrationModule


async def configuration_message(
    module: WzRegistrationModule,
    interaction: discord.Interaction,
    channel_id: int,
) -> str:
    """Summarize the current registration settings for the setup panel."""
    channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
    channel_name = channel.mention if channel is not None else f"<#{channel_id}>"
    settings = await module.registration.get(guild=module.guild, channel_id=channel_id)
    roles = await module.roles.get(guild=module.guild, channel_id=channel_id)
    title = (
        settings.title
        if settings and settings.title
        else t(interaction, "wz.overview.default_title")
    )
    text_status = (
        t(interaction, "wz.setup.config.custom_value")
        if settings and settings.description
        else t(interaction, "wz.setup.config.default_value")
    )
    role_summary = [
        t(
            interaction,
            "wz.setup.config.role_status",
            role_name=(
                guild_role.name
                if (guild_role := module.guild.get_role(role.role)) is not None
                else str(role.role)
            ),
            permanence=t(
                interaction,
                (
                    "wz.setup.config.role_permanent"
                    if role.permanent
                    else "wz.setup.config.role_non_permanent"
                ),
            ),
        )
        for role in roles or ()
    ]
    if not role_summary:
        role_summary.append(t(interaction, "wz.setup.config.no_roles"))

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
            "wz.setup.config.export_channel_unavailable",
            channel_id=export_channel_id,
        )
    else:
        export_status = t(interaction, "wz.setup.config.export_disabled")

    return "\n".join(
        (
            t(interaction, "wz.setup.config.panel", channel_name=channel_name),
            t(interaction, "wz.setup.config.title_status", title=title),
            t(interaction, "wz.setup.config.text_status", status=text_status),
            t(
                interaction,
                "wz.setup.config.roles_status",
                roles=", ".join(role_summary),
            ),
            t(
                interaction,
                "wz.setup.config.export_channel_status",
                channel=export_status,
            ),
        )
    )
