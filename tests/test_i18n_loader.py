from pathlib import Path

import pytest

from hmwz.i18n.loader import load_translation, load_translations


def test_load_translation_reads_utf8_and_normalizes_values(tmp_path: Path) -> None:
    translation_file = tmp_path / "de.json"
    translation_file.write_text(
        '{"greeting": "Grüß dich", "count": 2}', encoding="utf-8"
    )

    assert load_translation(translation_file) == {
        "greeting": "Grüß dich",
        "count": "2",
    }


@pytest.mark.parametrize("content", ['["not", "an", "object"]', "null", '"text"'])
def test_load_translation_rejects_non_object_json(tmp_path: Path, content: str) -> None:
    translation_file = tmp_path / "invalid.json"
    translation_file.write_text(content, encoding="utf-8")

    with pytest.raises(TypeError, match="must contain an object"):
        load_translation(translation_file)


def test_load_translations_loads_json_catalogs_in_filename_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "en.json").write_text('{"greeting": "Hello"}', encoding="utf-8")
    (tmp_path / "de.json").write_text('{"greeting": "Hallo"}', encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("not json", encoding="utf-8")

    assert load_translations(tmp_path) == {
        "de": {"greeting": "Hallo"},
        "en": {"greeting": "Hello"},
    }
