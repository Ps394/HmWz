from pathlib import Path

from hmwz.i18n import register_translations

from .module import QueueModule
from .models import Eruption, QueueConfiguration, QueuePhase
from .repositories import QueueRepository

register_translations(Path(__file__).parent / "i18n")

__all__ = [
    "Eruption",
    "QueueConfiguration",
    "QueueModule",
    "QueuePhase",
    "QueueRepository",
]
