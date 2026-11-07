"""Validate timezones used by persisted Rush donation settings."""

from __future__ import annotations

from datetime import tzinfo

from hmwz.ui.components.timestamp_input import (
    resolve_timezone,
)


def donation_timezone(timezone_name: str) -> tzinfo:
    """Resolve a stored fixed UTC offset or a legacy IANA timezone."""
    return resolve_timezone(timezone_name)
