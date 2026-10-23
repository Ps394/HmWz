from pathlib import Path

from hmwz.i18n import register_translations

from .module import QueueModule
from .repository import QueueConfiguration, QueueRepository, QueueRun

register_translations(Path(__file__).parent / "i18n")

__all__ = ["QueueConfiguration", "QueueModule", "QueueRepository", "QueueRun"]
