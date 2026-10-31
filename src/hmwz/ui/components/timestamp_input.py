"""Local date/time inputs that produce timezone-independent Discord timestamps."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from hmwz.i18n import t


def resolve_timezone(name: str) -> tzinfo:
    """Resolve IANA zones and stored whole-hour UTC offsets."""
    match = re.fullmatch(r"UTC([+-])(\d{1,2})", name)
    if match is not None:
        hours = int(match.group(2)) * (-1 if match.group(1) == "-" else 1)
        if not -12 <= hours <= 14 or (hours == 0 and match.group(1) == "-"):
            raise ValueError("UTC offset must be between UTC-12 and UTC+14.")
        return timezone(timedelta(hours=hours), name=name)
    if name == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Select a valid timezone.") from error


def parse_timestamp(raw: str) -> datetime:
    """Parse Discord tokens or Unix seconds without any local timezone conversion."""
    value = raw.strip()
    match = re.fullmatch(r"<t:(-?\d+)(?::[tTdDfFR])?>", value)
    if match is not None:
        value = match.group(1)
    elif re.fullmatch(r"-?\d+", value) is None:
        raise ValueError("Enter a Discord timestamp or integer Unix seconds.")
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError(
            "The timestamp is outside the supported date range."
        ) from error


def parse_local_datetime(raw: str, timezone_name: str) -> datetime:
    """Parse local calendar input or an absolute timestamp, rejecting DST ambiguity."""
    value = raw.strip()
    if value.startswith("<t:") or re.fullmatch(r"-?\d+", value):
        return parse_timestamp(value)
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})[ T](\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)",
        value,
    )
    if match is None:
        raise ValueError("Enter YYYY-MM-DD HH:MM or DD.MM.YYYY HH:MM.")
    date_value = match.group(1)
    if "." in date_value:
        day, month, year = date_value.split(".")
        date_value = f"{year}-{month}-{day}"
    clock = match.group(2)
    parts = [int(part) for part in clock.split(".")[0].split(":")]
    if parts[0] > 23 or parts[1] > 59 or (len(parts) == 3 and parts[2] > 59):
        raise ValueError(
            "Enter an hour from 00 to 23 and minutes/seconds from 00 to 59."
        )
    local = datetime.fromisoformat(f"{date_value}T{clock}")
    zone = resolve_timezone(timezone_name)
    aware = local.replace(tzinfo=zone)
    try:
        result = aware.astimezone(UTC)
        if result.astimezone(zone).replace(tzinfo=None) != local:
            raise ValueError(
                "This local time does not exist due to daylight saving time."
            )
        if aware.replace(fold=1).utcoffset() != aware.utcoffset():
            raise ValueError(
                "This local time occurs twice; enter a Discord or Unix timestamp instead."
            )
    except (OverflowError, OSError) as error:
        raise ValueError(
            "The timestamp is outside the supported date range."
        ) from error
    return result


class TimestampInput(discord.ui.TextInput):
    """Enter a local date/time comfortably and expose its generated Discord token."""

    def __init__(
        self,
        context: discord.Guild | discord.Interaction,
        *,
        label: str,
        timezone_name: str,
        value: datetime | None = None,
        required: bool = True,
    ) -> None:
        zone = resolve_timezone(timezone_name)
        if value is not None and value.utcoffset() is None:
            raise ValueError("The initial timestamp must be timezone-aware.")
        self.timezone_name = timezone_name
        # Keep the full instant, including seconds/microseconds, on unchanged submission.
        self._initial_value = value
        local = value.astimezone(zone) if value is not None else None
        self._initial_text = (
            local.strftime(
                "%Y-%m-%d %H:%M:%S.%f"
                if local.microsecond
                else "%Y-%m-%d %H:%M:%S"
                if local.second
                else "%Y-%m-%d %H:%M"
            )
            if local
            else None
        )
        if (
            value is not None
            and local is not None
            and local.replace(fold=1).utcoffset() != local.replace(fold=0).utcoffset()
        ):
            self._initial_text = discord.utils.format_dt(value, "F")
        super().__init__(
            label=f"{label[: max(1, 42 - len(timezone_name))]} ({timezone_name})"[:45],
            placeholder=t(context, "ui.timestamp.placeholder")[:100],
            default=self._initial_text,
            required=required,
            max_length=64,
        )

    def parse(self) -> datetime | None:
        """Return the chosen UTC instant, or None for an empty optional input."""
        if not self.value.strip():
            if self.required:
                raise ValueError("A timestamp is required.")
            return None
        if self.value == self._initial_text and self._initial_value is not None:
            return self._initial_value.astimezone(UTC)
        return parse_local_datetime(self.value, self.timezone_name)

    def discord_timestamp(self) -> str | None:
        """Generate a full Discord timestamp such as <t:1793403130:F>."""
        value = self.parse()
        return discord.utils.format_dt(value, "F") if value is not None else None
