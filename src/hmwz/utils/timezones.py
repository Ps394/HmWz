"""Helpers for validating guild-wide IANA timezones."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_GUILD_TIMEZONE = "Europe/Berlin"


def validate_iana_timezone(timezone_name: str) -> str:
    """Return a valid IANA timezone name.

    Args:
        timezone_name: IANA timezone identifier.

    Returns:
        The trimmed timezone name.

    Raises:
        ValueError: If the name is not a valid IANA timezone.
    """
    normalized_name = timezone_name.strip()
    if not normalized_name:
        raise ValueError("Timezone name must not be empty.")
    try:
        ZoneInfo(normalized_name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError(f"Unknown IANA timezone: {normalized_name}") from error
    return normalized_name
