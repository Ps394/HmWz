from __future__ import annotations

from ..repository import QueueMode
from .continuous import ContinuousQueueMode
from .protocol import QueueModeProtocol
from .seasons import SeasonQueueMode
from .stages import StagedQueueMode


def create_queue_modes() -> dict[QueueMode, QueueModeProtocol]:
    """Create the supported queue mode strategies."""
    modes: tuple[QueueModeProtocol, ...] = (
        ContinuousQueueMode(),
        StagedQueueMode(),
        SeasonQueueMode(),
    )
    return {mode.mode: mode for mode in modes}


__all__ = ["QueueModeProtocol", "create_queue_modes"]
