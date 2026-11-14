"""Validation of phase durations inside a fixed eruption window."""

from .constants import ERUPTION_SECONDS, PHASE_COUNT


def validate_schedule(
    eruption_start: int, starts: tuple[int, ...], durations: tuple[int, ...]
) -> None:
    """Reject invalid phase counts, durations or intervals outside the eruption.

    Raises:
        ValueError: If the schedule does not fit the 24-hour event window.
    """
    if len(starts) != PHASE_COUNT or len(durations) != PHASE_COUNT:
        raise ValueError("Qs requires exactly five phases.")
    if any(duration not in (1, 2, 3) for duration in durations):
        raise ValueError("Phase durations must be between one and three hours.")
    if any(
        start < eruption_start
        or start + duration * 3600 > eruption_start + ERUPTION_SECONDS
        for start, duration in zip(starts, durations, strict=True)
    ):
        raise ValueError("All phases must fit inside the 24-hour eruption.")
