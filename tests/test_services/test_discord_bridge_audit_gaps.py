"""Regression tests for Discord bridge audit gaps."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.shared.output import print_json, set_json_mode


def test_titled_print_json_honors_global_json_mode() -> None:
    stream = io.StringIO()
    set_json_mode(True)
    try:
        with redirect_stdout(stream):
            print_json({"ok": True}, title="Titled Payload")
    finally:
        set_json_mode(False)

    assert json.loads(stream.getvalue()) == {"ok": True}


def test_discord_bridge_status_global_json_is_parseable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "copilot_cli.services.discord.bridge.bridge_status",
        lambda: {"handoffs": [], "queue": {}, "tmux_available": True},
    )

    try:
        result = CliRunner().invoke(app, ["--json", "discord", "bridge", "status"])
    finally:
        set_json_mode(False)

    assert result.exit_code == 0
    assert json.loads(result.output) == {"handoffs": [], "queue": {}, "tmux_available": True}


def test_discord_bridge_launch_global_json_is_single_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "copilot_cli.services.discord.commands._client",
        lambda: object(),
    )
    monkeypatch.setattr(
        "copilot_cli.services.discord.bridge.start_tmux_bridge_session",
        lambda *_args, **_kwargs: {
            "thread_id": "thread-1",
            "tmux_attach_command": "tmux attach -t session",
        },
    )

    try:
        result = CliRunner().invoke(app, ["--json", "discord", "bridge", "launch", "codex"])
    finally:
        set_json_mode(False)

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "thread_id": "thread-1",
        "tmux_attach_command": "tmux attach -t session",
    }


def test_discord_service_docs_describe_nonblocking_bridge_model() -> None:
    text = Path("docs/services/22-discord.md").read_text(encoding="utf-8")

    assert "Stop hook posts status to that thread, waits" not in text
    assert (
        "At the next stopping point, the `Stop` hook posts status in Discord and waits." not in text
    )
    assert "copilot discord bridge launch" in text
    assert "notify-only" in text
