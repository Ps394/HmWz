from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("systemd-analyze") is None,
    reason="Requires Bash and systemd-analyze",
)
@pytest.mark.parametrize("directory", ["bot", "bot with spaces", 'bot%with"quotes\\'])
@pytest.mark.parametrize("with_token_file", [False, True])
def test_generated_systemd_unit(
    tmp_path: Path, directory: str, with_token_file: bool
) -> None:
    project = tmp_path / directory
    scripts = project / "scripts" / "linux"
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "scripts" / "linux"
    for name in ("install_service.bash", "service_config.bash"):
        shutil.copy2(source / name, scripts / name)
    python = project / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    (project / "src").mkdir()
    (project / "src" / "bot.py").touch()

    commands = tmp_path / "commands"
    commands.mkdir()
    unit_file = tmp_path / "discordbot.service"
    for name, content in {
        "id": (
            '#!/bin/bash\ncase "$1" in\n'
            "  -u) echo 1000;;\n"
            "  -un|-gn) echo nobody;;\n"
            "  *) exit 1;;\nesac\n"
        ),
        "systemctl": "#!/bin/bash\nexit 0\n",
        "sudo": (
            '#!/bin/bash\nif [[ "$1" == install ]]; then\n'
            '  exec /usr/bin/install -m 0644 "$4" "$TEST_UNIT_FILE"\n'
            "fi\n"
            'exec "$@"\n'
        ),
    }.items():
        command = commands / name
        command.write_text(content)
        command.chmod(0o755)

    env = os.environ.copy()
    env.update(
        PATH=f"{commands}:{env['PATH']}",
        HOME=str(tmp_path / "home"),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        HMWZ_SERVICE_NAME="discordbot",
        TEST_UNIT_FILE=str(unit_file),
    )
    env.pop("HMWZ_TOKEN_FILE", None)
    token_file = project / "token file.env"
    if with_token_file:
        token_file.write_text("WZ_BOT_TOKEN=test\n")
        env["HMWZ_TOKEN_FILE"] = str(token_file)

    subprocess.run(
        ["bash", str(scripts / "install_service.bash")],
        env=env,
        stdin=subprocess.DEVNULL,
        check=True,
        capture_output=True,
        text=True,
    )
    unit = unit_file.read_text()
    assert f"WorkingDirectory={str(project).replace('%', '%%')}\n" in unit
    if with_token_file:
        assert f"EnvironmentFile={str(token_file).replace('%', '%%')}\n" in unit
    else:
        assert "EnvironmentFile=" not in unit
    result = subprocess.run(
        ["systemd-analyze", "verify", str(unit_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "not absolute" not in result.stderr
