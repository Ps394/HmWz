"""Feature modules provided by the HS bot."""

from pathlib import Path

from hmwz.i18n import register_translations

from . import account, wz

register_translations(Path(__file__).parent / "i18n")

__all__ = ["account", "wz"]
