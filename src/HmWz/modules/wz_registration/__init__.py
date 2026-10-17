from pathlib import Path

from hmwz.i18n import register_translations

register_translations(Path(__file__).parent / "i18n")

from . import commands  # noqa: E402
from .module import WzRegistrationModule  # noqa: E402

__all__ = ["WzRegistrationModule", "commands"]
