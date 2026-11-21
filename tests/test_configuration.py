from pathlib import Path

import pytest

from hmwz.configuration import _default_config, _load_configuration


@pytest.mark.parametrize("content", ["{invalid", '["not", "an", "object"]'])
def test_load_configuration_uses_defaults_for_invalid_json(
    tmp_path: Path, content: str
) -> None:
    configuration_file = tmp_path / "configuration.json"
    configuration_file.write_text(content, encoding="utf-8")

    loaded = _load_configuration(str(configuration_file))

    assert loaded == _default_config()
    assert configuration_file.read_text(encoding="utf-8") == content


def test_load_configuration_creates_defaults_when_file_is_missing(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "configuration.json"

    loaded = _load_configuration(str(configuration_file))

    assert loaded == _default_config()
    assert configuration_file.exists()
