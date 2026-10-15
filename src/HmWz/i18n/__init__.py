from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import discord

from . import command, runtime
from .loader import load_translations
from .type import Translations

CommandLocalizations: Translations = command.translations
RuntimeLocalizations: Translations = runtime.translations

__all__ = [
    "CommandLocalizations",
    "CommandTranslator",
    "RuntimeLocalizations",
    "register_translations",
    "t",
]


def register_translations(directory: Path) -> None:
    """Merge an extension's command and runtime catalogs into the bot catalogs."""
    for category, target in (
        ("command", CommandLocalizations),
        ("runtime", RuntimeLocalizations),
    ):
        catalogs = load_translations(directory / category)
        for language, translations in catalogs.items():
            destination = target.setdefault(language, {})
            duplicate_keys = destination.keys() & translations.keys()
            if duplicate_keys:
                duplicates = ", ".join(sorted(duplicate_keys))
                raise ValueError(
                    f"Duplicate {category} translation keys for {language}: {duplicates}"
                )
            destination.update(translations)


def get_user_language(
    context: discord.Interaction | discord.Guild, default: str = "de"
) -> str:
    """Resolve a language from an interaction or guild context."""
    locale = getattr(context, "locale", None)
    if not locale:
        locale = getattr(context, "guild_locale", None)
    if not locale:
        locale = getattr(context, "preferred_locale", None)

    language = str(locale).split("-")[0].lower() if locale else default
    return language if language in RuntimeLocalizations else default


def t(context: discord.Interaction | discord.Guild, key: str, **kwargs: object) -> str:
    """Translate a runtime key using the supplied interaction or guild context."""
    language = get_user_language(context)
    catalog = RuntimeLocalizations.get(language, {})
    template = catalog.get(key, RuntimeLocalizations.get("de", {}).get(key, key))
    return template.format(**kwargs)


class CommandTranslator(discord.app_commands.Translator):
    """Translate slash-command metadata from the merged JSON catalogs."""

    _context_prefixes: ClassVar[
        dict[discord.app_commands.TranslationContextLocation, tuple[str, str]]
    ] = {
        discord.app_commands.TranslationContextLocation.command_name: (
            "command.name",
            ".name",
        ),
        discord.app_commands.TranslationContextLocation.command_description: (
            "command.description",
            ".description",
        ),
        discord.app_commands.TranslationContextLocation.group_name: (
            "group.name",
            ".name",
        ),
        discord.app_commands.TranslationContextLocation.group_description: (
            "group.description",
            ".description",
        ),
        discord.app_commands.TranslationContextLocation.parameter_name: (
            "parameter.name",
            ".name",
        ),
        discord.app_commands.TranslationContextLocation.parameter_description: (
            "parameter.description",
            ".description",
        ),
        discord.app_commands.TranslationContextLocation.choice_name: (
            "choice.name",
            ".name",
        ),
    }

    async def translate(
        self,
        string: discord.app_commands.locale_str,
        locale: discord.Locale,
        context: discord.app_commands.TranslationContext[Any, Any],
    ) -> str | None:
        key = string.extras.get("key")
        key_context = self._context_prefixes.get(context.location)
        if not key or key_context is None:
            return None

        prefix, suffix = key_context
        normalized_key = key.removesuffix(suffix)
        contextual_key = f"{prefix}.{normalized_key}"

        language = str(locale).lower()
        languages = (language, language.split("-")[0], "de")

        for candidate in dict.fromkeys(languages):
            translated = CommandLocalizations.get(candidate, {}).get(contextual_key)
            if translated is not None:
                return translated
        return None
