"""Ensure interaction messages use the shared Discord message helpers."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from hmwz.modules.hs.account.commands import add as account_commands
from hmwz.ui import messages


@pytest.mark.asyncio
async def test_account_error_uses_shared_followup_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    translate = Mock(return_value="Warning")
    render = Mock(return_value="Rendered warning")
    monkeypatch.setattr(account_commands, "t", translate)
    monkeypatch.setattr(messages.emojis, "render", render)

    await account_commands.account_add.callback(interaction, " ")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    render.assert_called_once_with("Warning", interaction)
    interaction.followup.send.assert_awaited_once_with(
        "Rendered warning", ephemeral=True, wait=True
    )


def test_interaction_messages_use_shared_helpers() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "hmwz"
    helper = source / "ui" / "messages.py"
    violations: list[str] = []
    for path in source.rglob("*.py"):
        if path == helper:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            receiver = node.func.value
            if not isinstance(receiver, ast.Attribute):
                continue
            if (receiver.attr, node.func.attr) in {
                ("response", "send_message"),
                ("followup", "send"),
            }:
                violations.append(f"{path.relative_to(source)}:{node.lineno}")
    assert not violations, f"Direct interaction message sends: {', '.join(violations)}"
