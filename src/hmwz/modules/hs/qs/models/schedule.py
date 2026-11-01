"""Validation of phase durations inside a fixed eruption window."""

from .constants import ERUPTION_SECONDS, MIN_PHASE_COUNT, PHASE_COUNT


def validate_schedule(
    eruption_start: int, starts: tuple[int, ...], durations: tuple[int, ...]
) -> None:
    """Reject invalid phase counts, durations or intervals outside the eruption.

    Raises:
        ValueError: If the schedule does not fit the 24-hour event window.
    """
    if not MIN_PHASE_COUNT <= len(starts) <= PHASE_COUNT or len(starts) != len(
        durations
    ):
        raise ValueError("Choose four or five phases.")
    if any(duration not in (1, 2, 3) for duration in durations):
        raise ValueError("Phase durations must be between one and three hours.")
    if any(
        start < eruption_start
        or start + duration * 3600 > eruption_start + ERUPTION_SECONDS
        for start, duration in zip(starts, durations, strict=True)
    ):
        raise ValueError("All phases must fit inside the 24-hour eruption.")
