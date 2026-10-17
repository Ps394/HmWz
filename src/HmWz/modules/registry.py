"""Registry fuer alle Modulklassen.

Dieses Modul bietet einen kleinen Dekorator, mit dem Module zentral
registriert werden koennen. Der Manager instanziiert spaeter pro Guild
alle hier registrierten Module.
"""

from __future__ import annotations

from .instance import ModuleType

REGISTRY: list[ModuleType] = []
"""Globale Liste aller registrierten Modulklassen."""


def register(cls: ModuleType) -> ModuleType:
    """Registriert eine Modulklasse in der globalen Registry.

    Parameter:
    - cls: Modulklasse, die spaeter vom Manager erstellt werden kann.

    Rueckgabe:
    - Die unveraenderte Klasse, damit der Dekorator transparent bleibt.
    """
    if cls not in REGISTRY:
        REGISTRY.append(cls)
    return cls
