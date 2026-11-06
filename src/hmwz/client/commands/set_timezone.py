"""Set the timezone used by guild modules."""

from __future__ import annotations

import logging
from typing import Protocol, cast

from zoneinfo import available_timezones

import discord
from discord import Interaction, app_commands
from discord.app_commands import command, describe, locale_str

from hmwz.configuration import MODERATOR_ROLES
from hmwz.ui.messages import send_initial_response
from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.timezones import DEFAULT_GUILD_TIMEZONE, validate_iana_timezone

_logger = logging.getLogger(__name__)
_TIMEZONE_NAMES = tuple(
    sorted(
        available_timezones(),
        key=lambda timezone_name: (
            timezone_name != DEFAULT_GUILD_TIMEZONE,
            timezone_name.casefold(),
        ),
    )
)


async def timezone_autocomplete(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest available IANA timezones matching the user's input."""
    query = current.casefold()
    return [
        app_commands.Choice(name=timezone_name, value=timezone_name)
        for timezone_name in _TIMEZONE_NAMES
        if query in timezone_name.casefold()
    ][:25]


class _TimezoneClient(Protocol):
    async def set_guild_timezone(
        self, guild: discord.Guild, timezone_name: str
    ) -> bool: ...

    async def on_guild_timezone_update(self, guild: discord.Guild) -> bool: ...


@app_commands.checks.has_any_role(*MODERATOR_ROLES)
@app_commands.guild_only()
@command(
    name="set-timezone",
    description=locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.set_timezone",
            "Set the timezone used by this server",
        ),
        key="wz.set_timezone.description",
    ),
)
@describe(
    timezone=locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.set_timezone.timezone",
            "Choose an IANA timezone, for example Europe/Berlin",
        ),
        key="wz.set_timezone.timezone.description",
    )
)
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def SetTimezone(interaction: Interaction, timezone: str) -> None:
    """Set the IANA timezone shared by all modules in this guild.

    Args:
        interaction: Interaction that invoked the command.
        timezone: IANA timezone identifier such as ``Europe/Berlin``.
    """
    guild = interaction.guild
    if guild is None:
        await send_initial_response(
            interaction, t(interaction, "timezone.error.guild_only"), ephemeral=True
        )
        return

    try:
        timezone_name = validate_iana_timezone(timezone)
    except ValueError:
        await send_initial_response(
            interaction, t(interaction, "timezone.error.invalid"), ephemeral=True
        )
        return

    client = cast(_TimezoneClient, interaction.client)
    if not await client.set_guild_timezone(guild, timezone_name):
        await send_initial_response(
            interaction, t(interaction, "timezone.error.save_failed"), ephemeral=True
        )
        return
    if not await client.on_guild_timezone_update(guild):
        _logger.warning(
            "%s Saved timezone %s, but a module failed to refresh.",
            guild.name,
            timezone_name,
        )
        await send_initial_response(
            interaction,
            t(interaction, "timezone.saved_refresh_failed", timezone=timezone_name),
            ephemeral=True,
        )
        return
    await send_initial_response(
        interaction,
        t(interaction, "timezone.saved", timezone=timezone_name),
        ephemeral=True,
    )
