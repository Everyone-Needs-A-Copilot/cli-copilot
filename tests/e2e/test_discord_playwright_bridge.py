"""Live Discord Web verification for send/receive bridge paths.

Usage:
    COPILOT_E2E_LIVE=1 pytest tests/e2e/test_discord_playwright_bridge.py -m e2e -q
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The live Discord server to run against is never hardcoded -- point
# DISCORD_GUILD_ID (via .env or the shell) at your own test server.
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("COPILOT_E2E_LIVE") != "1",
        reason="Live Discord E2E tests are disabled. Set COPILOT_E2E_LIVE=1 to run.",
    ),
    pytest.mark.skipif(
        not GUILD_ID,
        reason="DISCORD_GUILD_ID is not set. Point it at your own Discord server to run.",
    ),
]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("COPILOT_ENV_FILE", str(ROOT / ".env"))
    return env


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _create_thread(title: str, message: str) -> str:
    result = _run(
        [
            "copilot",
            "discord",
            "handoff",
            message,
            "--title",
            title,
            "--harness",
            "codex",
        ],
        timeout=90,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    match = re.search(r'"thread_id":\s*"(\d+)"', result.stdout)
    assert match, result.stdout
    return match.group(1)


def _thread_url(thread_id: str) -> str:
    return f"https://discord.com/channels/{GUILD_ID}/{thread_id}"


def test_discord_web_message_is_received_by_cli_listener() -> None:
    """Inbound: real Discord Web composer -> Gateway listener -> CLI output."""
    stamp = int(time.time())
    thread_id = _create_thread(
        title=f"Playwright inbound verification {stamp}",
        message="Playwright inbound verification thread.",
    )
    expected = f"playwright inbound verification {stamp}"

    listener = subprocess.Popen(
        [
            "copilot",
            "discord",
            "listen",
            thread_id,
            "--timeout",
            "180",
        ],
        cwd=ROOT,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    sender = _run(
        [
            "python3",
            "tests/e2e/discord_bridge_send.py",
            "--url",
            _thread_url(thread_id),
            "--message",
            expected,
            "--timeout",
            "180",
        ],
        timeout=240,
    )
    assert sender.returncode == 0, sender.stderr or sender.stdout

    stdout, _ = listener.communicate(timeout=240)
    assert listener.returncode == 0, stdout
    assert expected in stdout


def test_cli_notify_is_visible_in_discord_web_thread() -> None:
    """Outbound: CLI post -> real Discord Web thread visibility."""
    stamp = int(time.time())
    thread_id = _create_thread(
        title=f"Playwright outbound verification {stamp}",
        message="Playwright outbound verification thread.",
    )
    expected = f"playwright outbound verification {stamp}"

    notify = _run(
        [
            "copilot",
            "discord",
            "notify",
            expected,
            "--thread-id",
            thread_id,
            "--no-mention",
        ],
        timeout=90,
    )
    assert notify.returncode == 0, notify.stderr or notify.stdout

    visible = _run(
        [
            "python3",
            "tests/e2e/discord_bridge_send.py",
            "--url",
            _thread_url(thread_id),
            "--expect-text",
            expected,
            "--timeout",
            "180",
        ],
        timeout=240,
    )
    assert visible.returncode == 0, visible.stderr or visible.stdout
