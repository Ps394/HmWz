from pathlib import Path

from hmwz.i18n import register_translations

from .module import DonationModule

register_translations(Path(__file__).parent / "i18n")

__all__ = ["DonationModule"]
