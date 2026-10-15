from __future__ import annotations

import json
from pathlib import Path

from .type import Translation, Translations


def load_translation(file_path: Path) -> Translation:
    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError(f"Translation file must contain an object: {file_path}")

    return {str(key): str(value) for key, value in data.items()}


def load_translations(directory: Path) -> Translations:
    translations: Translations = {}

    for file_path in sorted(directory.glob("*.json")):
        translations[file_path.stem] = load_translation(file_path)

    return translations
