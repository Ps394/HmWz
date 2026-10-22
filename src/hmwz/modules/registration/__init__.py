"""Reusable registration functionality shared by bot features."""

from pathlib import Path

from hmwz.i18n import register_translations

from .base import RegistrationModuleBase
from .overview import RegistrationOverview

register_translations(Path(__file__).parent / "i18n")

__all__ = ["RegistrationModuleBase", "RegistrationOverview"]
