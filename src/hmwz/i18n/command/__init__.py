from pathlib import Path

from ..loader import load_translations
from ..type import Translations

translations: Translations = load_translations(Path(__file__).parent)
