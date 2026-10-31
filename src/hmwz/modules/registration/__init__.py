"""Standalone guild module for managing independent registrations."""

from pathlib import Path

from hmwz.i18n import register_translations

from .module import RegistrationModule
from .overview import RegistrationOverview

register_translations(Path(__file__).parent / "i18n")

__all__ = ["RegistrationModule", "RegistrationOverview"]
