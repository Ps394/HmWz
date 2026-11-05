"""Mutable configuration collected by the guided setup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ....models import DonationKind
from hmwz.utils.timezones import DEFAULT_GUILD_TIMEZONE

if TYPE_CHECKING:
    from ....module import DonationModule


@dataclass(slots=True)
class DonationSetupDraft:
    """Mutable settings collected by the donation setup menu."""

    module: DonationModule
    channel_id: int
    owner_id: int
    kind: DonationKind
    title: str
    description: str
    unit: str
    choices: tuple[str, ...]
    time_reductions: tuple[str, ...]
    goal_hours: int | None
    recent_limit: int
    show_ranking: bool
    rush_start_at: datetime | None
    timezone_name: str = DEFAULT_GUILD_TIMEZONE
    show_donations: bool = True
    donations_enabled: bool = True
    export_channel_id: int | None = None
    accelerated_hours: int = 0
    target_at: datetime | None = None
