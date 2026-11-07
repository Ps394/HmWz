"""Set the timezone used by guild modules."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from importlib.resources import files
from typing import Protocol, cast

from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import Interaction, app_commands
from discord.app_commands import command, describe, locale_str

from hmwz.configuration import MODERATOR_ROLES
from hmwz.ui.messages import send_initial_response
from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.timezones import DEFAULT_GUILD_TIMEZONE, validate_iana_timezone

_logger = logging.getLogger(__name__)
_PREFERRED_TIMEZONE_ALIASES = {"UTC": "Etc/UTC", "GMT": "Etc/GMT"}
_timezone_data = files("tzdata.zoneinfo").joinpath("tzdata.zi").read_text(
    encoding="utf-8"
)
_TIMEZONE_ALIASES = {
    fields[2]
    for line in _timezone_data.splitlines()
    if line.startswith("L ") and len(fields := line.split()) >= 3
}
_TIMEZONE_NAMES = tuple(
    sorted(
        (
            available_timezones()
            - _TIMEZONE_ALIASES
            - set(_PREFERRED_TIMEZONE_ALIASES.values())
        )
        | set(_PREFERRED_TIMEZONE_ALIASES),
        key=lambda timezone_name: (
            timezone_name != DEFAULT_GUILD_TIMEZONE,
            timezone_name.casefold(),
        ),
    )
)
_PREFERRED_TIMEZONES_BY_OFFSET = {
    -12: ("Etc/GMT+12",),
    -11: ("Pacific/Pago_Pago", "Pacific/Niue", "Etc/GMT+11"),
    -10: ("Pacific/Honolulu", "America/Adak", "Etc/GMT+10"),
    -9: ("America/Anchorage", "Etc/GMT+9"),
    -8: ("America/Los_Angeles", "Etc/GMT+8"),
    -7: ("America/Denver", "Etc/GMT+7"),
    -6: ("America/Chicago", "Etc/GMT+6"),
    -5: ("America/New_York", "Etc/GMT+5"),
    -4: ("America/Halifax", "America/Santo_Domingo", "Etc/GMT+4"),
    -3: ("America/Sao_Paulo", "America/Argentina/Buenos_Aires", "Etc/GMT+3"),
    -2: ("America/Noronha", "Etc/GMT+2"),
    -1: ("Atlantic/Cape_Verde", "Etc/GMT+1"),
    0: ("UTC", "Etc/GMT"),
    1: ("Europe/Berlin", "Africa/Lagos", "Etc/GMT-1"),
    2: ("Europe/Berlin", "Africa/Johannesburg", "Etc/GMT-2"),
    3: ("Europe/Moscow", "Asia/Riyadh", "Etc/GMT-3"),
    4: ("Asia/Dubai", "Etc/GMT-4"),
    5: ("Asia/Karachi", "Etc/GMT-5"),
    6: ("Asia/Dhaka", "Etc/GMT-6"),
    7: ("Asia/Bangkok", "Etc/GMT-7"),
    8: ("Asia/Shanghai", "Etc/GMT-8"),
    9: ("Asia/Tokyo", "Etc/GMT-9"),
    10: ("Australia/Brisbane", "Etc/GMT-10"),
    11: ("Australia/Sydney", "Pacific/Noumea", "Etc/GMT-11"),
    12: ("Pacific/Auckland", "Pacific/Fiji", "Etc/GMT-12"),
    13: ("Pacific/Auckland", "Pacific/Apia", "Etc/GMT-13"),
    14: ("Pacific/Kiritimati", "Etc/GMT-14"),
}
_FRACTIONAL_TIMEZONES = (
    "America/St_Johns",
    "America/Caracas",
    "Pacific/Marquesas",
    "Asia/Kabul",
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Asia/Yangon",
    "Australia/Adelaide",
    "Pacific/Chatham",
)
_POPULAR_TIMEZONE_ORDER = (
    DEFAULT_GUILD_TIMEZONE,
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "Europe/London",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Australia/Sydney",
    "Europe/Paris",
    "Asia/Dubai",
    "America/Toronto",
    "America/Vancouver",
    "America/Sao_Paulo",
    "Asia/Singapore",
    "Pacific/Auckland",
)
_TIMEZONE_PRIORITY = {
    timezone_name: index
    for index, timezone_name in enumerate(_POPULAR_TIMEZONE_ORDER)
}


def _format_utc_offset(offset_minutes: int) -> str:
    """Format an offset in minutes as a UTC label."""
    sign = "+" if offset_minutes >= 0 else "-"
    hours, minutes = divmod(abs(offset_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _suggested_timezones(now: datetime) -> list[tuple[str, int]]:
    """Return one preferred timezone per whole-hour offset and common fractions."""
    offset_by_timezone: dict[str, int] = {}
    for timezone_name in _TIMEZONE_NAMES:
        offset = now.astimezone(ZoneInfo(timezone_name)).utcoffset()
        if offset is not None:
            offset_by_timezone[timezone_name] = int(offset.total_seconds() // 60)
    timezones_by_offset: dict[int, list[str]] = {}
    for timezone_name, offset_minutes in offset_by_timezone.items():
        if offset_minutes % 60 == 0:
            timezones_by_offset.setdefault(offset_minutes // 60, []).append(
                timezone_name
            )

    suggestions: dict[str, int] = {}
    for hour_offset in range(-12, 15):
        candidates = timezones_by_offset.get(hour_offset, [])
        preferred = _PREFERRED_TIMEZONES_BY_OFFSET[hour_offset]
        selected_timezone = next(
            (name for name in preferred if name in candidates),
            None,
        )
        if selected_timezone is None and candidates:
            selected_timezone = min(
                candidates,
                key=lambda name: (
                    _TIMEZONE_PRIORITY.get(name, len(_TIMEZONE_PRIORITY)),
                    name.casefold(),
                ),
            )
        if selected_timezone is not None:
            suggestions[selected_timezone] = hour_offset * 60

    for timezone_name in _FRACTIONAL_TIMEZONES:
        fractional_offset_minutes = offset_by_timezone.get(timezone_name)
        if (
            fractional_offset_minutes is not None
            and fractional_offset_minutes % 60
        ):
            suggestions[timezone_name] = fractional_offset_minutes

    return sorted(
        suggestions.items(),
        key=lambda item: (
            _TIMEZONE_PRIORITY.get(item[0], len(_TIMEZONE_PRIORITY)),
            item[1],
            item[0].casefold(),
        ),
    )


async def timezone_autocomplete(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest common IANA timezones with their current UTC offsets."""
    query = current.casefold()
    matches = []
    for timezone_name, offset_minutes in _suggested_timezones(datetime.now(UTC)):
        offset_label = _format_utc_offset(offset_minutes)
        display_name = f"{timezone_name} ({offset_label})"
        if (
            query not in timezone_name.casefold()
            and query not in display_name.casefold()
        ):
            continue
        matches.append(app_commands.Choice(name=display_name, value=timezone_name))
    return matches[:25]


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
            "Choose a timezone; search UTC- or UTC+ for common zones by UTC hour",
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
