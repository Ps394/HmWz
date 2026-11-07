"""Feature modules provided by the HS bot."""

from pathlib import Path

from hmwz.i18n import register_translations

register_translations(Path(__file__).parent / "i18n")

from . import account, wz 

__all__ = ["account", "wz"]
