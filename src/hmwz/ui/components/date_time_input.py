"""Separate local date and time inputs that produce one UTC instant."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import discord

from hmwz.i18n import t

from .timestamp_input import parse_local_datetime, resolve_timezone

DATE_PATTERN = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}\.\d{4}")
TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}")


class DateTimeInput:
    """Paired date and time text inputs sharing one timezone."""

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
        self.required = required
        # Keep the full instant, including seconds/microseconds, on unchanged submission.
        self._initial_value = value
        local = value.astimezone(zone) if value is not None else None
        self._initial_date = local.strftime("%Y-%m-%d") if local is not None else None
        self._initial_time = local.strftime("%H:%M") if local is not None else None
        self.date_input: discord.ui.TextInput = discord.ui.TextInput(
            label=f"{label} – {t(context, 'ui.datetime.date')}"[:45],
            placeholder=t(context, "ui.datetime.date_placeholder")[:100],
            default=self._initial_date,
            required=required,
            max_length=10,
        )
        self.time_input: discord.ui.TextInput = discord.ui.TextInput(
            label=f"{label} – {t(context, 'ui.datetime.time')}"[:45],
            placeholder=t(
                context, "ui.datetime.time_placeholder", timezone=timezone_name
            )[:100],
            default=self._initial_time,
            required=required,
            max_length=5,
        )

    @property
    def items(self) -> tuple[discord.ui.TextInput, discord.ui.TextInput]:
        """Return both text inputs in display order."""
        return (self.date_input, self.time_input)

    def parse(self) -> datetime | None:
        """Return the chosen UTC instant, or None for empty optional inputs."""
        date_text = self.date_input.value.strip()
        time_text = self.time_input.value.strip()
        if not date_text and not time_text:
            if self.required:
                raise ValueError("A date and time are required.")
            return None
        if not date_text or not time_text:
            raise ValueError("Enter both a date and a time.")
        if (
            self._initial_value is not None
            and date_text == self._initial_date
            and time_text == self._initial_time
        ):
            return self._initial_value.astimezone(UTC)
        if DATE_PATTERN.fullmatch(date_text) is None:
            raise ValueError("Enter the date as YYYY-MM-DD or DD.MM.YYYY.")
        if TIME_PATTERN.fullmatch(time_text) is None:
            raise ValueError("Enter the time as HH:MM.")
        return parse_local_datetime(
            f"{date_text} {time_text.zfill(5)}", self.timezone_name
        )
