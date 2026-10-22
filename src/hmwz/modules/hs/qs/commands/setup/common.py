from __future__ import annotations

from dataclasses import dataclass

import discord

from hmwz.configuration import registration_defaults
from hmwz.i18n import t

from hmwz.modules.registrations.qs import QsRegistrationModule


@dataclass(frozen=True)
class SetupContext:
    guild: discord.Guild
    channel_id: int
    module: QsRegistrationModule


async def get_setup_context(
    interaction: discord.Interaction,
) -> SetupContext | None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
        return None

    module: QsRegistrationModule = await manager.get_module(guild, QsRegistrationModule)
    return SetupContext(guild=guild, channel_id=channel_id, module=module)


async def add_registration_role(
    interaction: discord.Interaction,
    context: SetupContext,
    role: discord.Role,
) -> bool:
    if context.guild.me and role >= context.guild.me.top_role:
        await interaction.followup.send(
            t(interaction, "qs.setup.role_hierarchy"), ephemeral=True
        )
        return False

    max_roles = min(
        4, int(registration_defaults("qs").get("max_registration_roles", 4))
    )
    existing_count = await context.module.roles.count(
        guild=context.guild,
        roles=[role.id],
        channel_id=context.channel_id,
    )
    role_count = await context.module.roles.count(
        guild=context.guild, channel_id=context.channel_id
    )
    if existing_count == 0 and role_count >= max_roles:
        await interaction.followup.send(
            t(interaction, "qs.setup.max_roles", max_roles=max_roles),
            ephemeral=True,
        )
        return False

    if not await context.module.registration.upsert(
        guild=context.guild, channel_id=context.channel_id
    ):
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
        return False
    if not await context.module.roles.add(
        guild=context.guild,
        role=role.id,
        permanent=False,
        score=1,
        channel_id=context.channel_id,
    ):
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
        return False
    if not await context.module.compose_registration_overview(
        force=True, channel_id=context.channel_id
    ):
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
        return False
    return True
