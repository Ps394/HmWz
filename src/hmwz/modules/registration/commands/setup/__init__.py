"""Setup commands for registration configurations."""

from .config.command import setup
from .remove import remove

__all__ = ["remove", "setup"]
