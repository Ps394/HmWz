"""Registry for all module classes.

The decorator registers modules centrally so the manager can create an
instance for each guild.
"""

from __future__ import annotations

from .protocols import ModuleType

REGISTRY: list[ModuleType] = []
"""Globale Liste aller registrierten Modulklassen."""


def register(cls: ModuleType) -> ModuleType:
    """Register a module class once in the global registry.

    Args:
        cls: Module class that can be instantiated by the manager.

    Returns:
        The unchanged class, allowing the decorator to be used transparently.
    """
    if cls not in REGISTRY:
        REGISTRY.append(cls)
    return cls
