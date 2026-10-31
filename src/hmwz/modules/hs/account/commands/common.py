from __future__ import annotations

import discord
from discord import Interaction, app_commands

from hmwz.i18n import CommandLocalizations

from hmwz.modules.registration import RegistrationModule


def command_description(key: str, fallback: str) -> app_commands.locale_str:
    return app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(key, fallback),
        key=f"{key.removeprefix('command.description.')}.description",
    )


async def get_member_context(
    interaction: Interaction,
) -> tuple[discord.Guild, discord.Member, RegistrationModule] | None:
    guild = interaction.guild
    member = interaction.user
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or not isinstance(member, discord.Member) or manager is None:
        return None
    module: RegistrationModule = await manager.get_module(guild, RegistrationModule)
    return guild, member, module
