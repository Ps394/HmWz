"""Lokalisierungsmodul für HmWz. 
Dieses Modul enthält Funktionen und Datenstrukturen, die für die Übersetzung von Texten in der Anwendung verwendet werden.
Es bietet eine zentrale Anlaufstelle für die Verwaltung von Übersetzungen, sowohl für statische Texte, die in den Befehlen verwendet werden, als auch für dynamische Nachrichten, die zur Laufzeit generiert werden.
"""
from __future__ import annotations
import logging
from discord import Locale, app_commands
from . import command, runtime

CommandLocalizations = command.translations
"""Alias für die Lokalisierungen von Befehlen. Diese Datenstruktur enthält Übersetzungen für Befehlsbeschreibungen und andere statische Texte, die in den Befehlen verwendet werden."""
RuntimeLocalizations = runtime.translations
"""Alias für die Lokalisierungen zur Laufzeit. Diese Datenstruktur enthält Übersetzungen für Nachrichten, die zur Laufzeit generiert werden."""

__all__ = ["t", "CommandTranslator", "CommandLocalizations", "RuntimeLocalizations"]

logger = logging.getLogger(__name__)

def get_user_language(interaction, default: str = "de") -> str:
    """Bestimmt die Sprache eines Benutzers anhand der Interaktion. 
    Zuerst wird versucht, die Sprache aus der `locale`-Eigenschaft der Interaktion zu holen. 
    Wenn das fehlschlägt, wird versucht, die Sprache aus der `guild_locale`-Eigenschaft der Interaktion zu holen. 
    Wenn beide Versuche fehlschlagen, wird die Standard-Sprache zurückgegeben."""
    try:
        locale = str(getattr(interaction, "locale", "") or "")
        if not locale:
            locale = str(getattr(interaction, "guild_locale", "") or "")
        language = locale.split("-")[0].lower() if locale else default
        return language if language in {"de", "en"} else default
    except Exception as e:
        logger.exception(f"Error determining user language: {e}")
        return default

def t(interaction, key: str, **kwargs) -> str:
    """Übersetzt einen Schlüssel basierend auf der Discord-Benutzersprache und formatiert Platzhalter."""
    try:
        language = get_user_language(interaction)
        catalog = RuntimeLocalizations.get(language, RuntimeLocalizations["de"])
        template = catalog.get(key) or RuntimeLocalizations["de"].get(key, key)
        return template.format(**kwargs)
    except Exception as e:
        logger.exception(f"Error in translation for key '{key}' with language '{language}': {e}")
        return key
    
class CommandTranslator(app_commands.Translator):
    """Übersetzer für Slash-Befehle und Gruppen-Metadaten."""

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        """"Übersetzt einen Schlüssel basierend auf der Discord-Benutzersprache."""
        try:
            key = string.extras.get("key")
            if not key:
                return None

            locale_name = str(locale)
            catalog = CommandLocalizations.get(locale_name)
            if catalog and key in catalog:
                return catalog[key]

            short_locale = locale_name.split("-")[0].lower()
            catalog = CommandLocalizations.get(short_locale)
            if catalog and key in catalog:
                return catalog[key]

            return CommandLocalizations.get("de", {}).get(key)
        except Exception as e:
            logger.exception(f"Error in command translation for key '{key}' with locale '{locale}': {e}")
            return None