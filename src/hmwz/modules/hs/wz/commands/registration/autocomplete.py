from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz.i18n import t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)
DISPLAY_NAME_ACCOUNT_VALUE = "__discord_display_name__"


async def _module_for(
    interaction: Interaction,
) -> tuple[discord.Guild, discord.Member, WzRegistrationModule] | None:
    guild = interaction.guild
    member = interaction.user
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or not isinstance(member, discord.Member) or manager is None:
        return None
    module: WzRegistrationModule = await manager.get_module(guild, WzRegistrationModule)
    return guild, member, module


async def linked_accounts(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest the invoking member's linked in-game accounts."""
    try:
        context = await _module_for(interaction)
        if context is None:
            return []
        guild, member, module = context
        accounts = await module.game_accounts.get(guild=guild, member=member.id)
        display_name = member.display_name
        choices = [
            app_commands.Choice(
                name=f"{record.account} ({display_name})"[:100],
                value=record.account,
            )
            for record in accounts or ()
            if current.casefold() in record.account.casefold()
            or current.casefold() in display_name.casefold()
        ]
        if current.casefold() in display_name.casefold():
            choices.insert(
                0,
                app_commands.Choice(
                    name=t(
                        interaction,
                        "wz.registration.account.display_name_choice",
                        display_name=display_name,
                    )[:100],
                    value=DISPLAY_NAME_ACCOUNT_VALUE,
                ),
            )
        return choices[:25]
    except Exception:
        logger.exception("Failed to autocomplete linked game accounts.")
        return []


async def registered_accounts(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest linked accounts that currently have a registration."""
    try:
        context = await _module_for(interaction)
        if context is None:
            return []
        guild, member, module = context
        accounts = await module.game_accounts.get(guild=guild, member=member.id)
        registrations = await module.registrations.get(
            guild=guild,
            member=member.id,
            channel_id=interaction.channel_id,
        )
        registrations_by_name = {
            record.account.casefold(): record for record in registrations or ()
        }
        display_name = member.display_name
        choices = [
            app_commands.Choice(
                name=f"{record.account} ({display_name})"[:100],
                value=record.account,
            )
            for record in accounts or ()
            if record.account.casefold() in registrations_by_name
            and (
                current.casefold() in record.account.casefold()
                or current.casefold() in display_name.casefold()
            )
        ]
        if (
            "" in registrations_by_name
            and current.casefold() in display_name.casefold()
        ):
            choices.insert(
                0,
                app_commands.Choice(
                    name=t(
                        interaction,
                        "wz.registration.account.display_name_choice",
                        display_name=display_name,
                    )[:100],
                    value=DISPLAY_NAME_ACCOUNT_VALUE,
                ),
            )
        return choices[:25]
    except Exception:
        logger.exception("Failed to autocomplete registered game accounts.")
        return []


async def registration_roles(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest configured registration roles for the current guild."""
    try:
        context = await _module_for(interaction)
        if context is None:
            return []
        guild, _, module = context
        configured_roles = await module.roles.get(
            guild=guild, channel_id=interaction.channel_id
        )
        if not configured_roles:
            return []
        choices: list[app_commands.Choice[str]] = []
        for configured in configured_roles:
            role = guild.get_role(configured.role)
            if role is not None and current.casefold() in role.name.casefold():
                choices.append(app_commands.Choice(name=role.name, value=str(role.id)))
        return choices[:25]
    except Exception:
        logger.exception("Failed to autocomplete WZ registration roles.")
        return []
