from __future__ import annotations

from . import de
from ..type import Translations
from . import en

translations : Translations = {
    "de": de.translation,
    "en": en.translation,
}
"""Enthält alle statischen Texte, die in den Befehlen verwendet werden. 
Die Texte sind in verschiedenen Sprachen organisiert, um die Lokalisierung zu unterstützen.
Die `CommandLocalizations`-Datenstruktur enthält Übersetzungen für Befehlsbeschreibungen und andere statische Texte, während die `RuntimeMessages`-Datenstruktur Übersetzungen für Nachrichten enthält, die zur Laufzeit generiert werden.
"""