"""Load translation catalogs from JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from .type import Translation, Translations


def load_translation(file_path: Path) -> Translation:
    """Load one translation catalog from a JSON file.

    Args:
        file_path: Path to the catalog file.

    Returns:
        A mapping of translation keys to text.

    Raises:
        TypeError: If the JSON document is not an object.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError(f"Translation file must contain an object: {file_path}")

    return {str(key): str(value) for key, value in data.items()}


def load_translations(directory: Path) -> Translations:
    """Load all JSON translation catalogs in a directory.

    Args:
        directory: Directory containing one JSON file per language.

    Returns:
        Catalogs keyed by each file's stem.
    """
    translations: Translations = {}

    for file_path in sorted(directory.glob("*.json")):
        translations[file_path.stem] = load_translation(file_path)

    return translations
