"""tmux helpers for the Discord bridge.

The bridge drives Claude Code, Codex, or another terminal harness below the
harness layer by writing to a tmux pane. That keeps the input path
harness-neutral: the only contract is "this pane accepts typed text".
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from copilot_cli.shared.errors import CopilotError, ValidationError

SERVICE = "discord"
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class TmuxTarget:
    """A tmux pane target captured from the local harness environment."""

    pane: str

    def to_record(self) -> dict[str, str]:
        return {"tmux_pane": self.pane}


@dataclass(frozen=True)
class TmuxSession:
    """A detached tmux session prepared for Discord bridge delivery."""

    name: str
    pane: str
    pane_pid: int | None = None

    @property
    def attach_command(self) -> str:
        return f"tmux attach -t {shlex.quote(self.name)}"


def current_target(env: Mapping[str, str] | None = None) -> TmuxTarget | None:
    """Return the current tmux pane from ``$TMUX_PANE`` when available."""
    value = (env or os.environ).get("TMUX_PANE", "").strip()
    if not value:
        return None
    return TmuxTarget(pane=value)


def tmux_available() -> bool:
    """Return True when the tmux executable is on PATH."""
    return shutil.which("tmux") is not None


def pane_exists(target: str, runner: Runner | None = None) -> bool:
    """Return True when tmux can resolve ``target`` as a live pane."""
    runner = runner or subprocess.run
    result = runner(
        ["tmux", "display-message", "-p", "-t", target, "#{pane_id}"],
        capture_output=True,
        text=True,
        timeout=3,
    )
    return result.returncode == 0


def start_session(
    session_name: str,
    cwd: str,
    command: list[str],
    runner: Runner | None = None,
) -> TmuxSession:
    """Start a detached tmux session and return its first pane target."""
    if not session_name.strip():
        raise ValidationError("tmux session name is required.", service=SERVICE)
    if not command:
        raise ValidationError("A command is required to start a tmux session.", service=SERVICE)
    if not tmux_available():
        raise ValidationError(
            "tmux is not installed or not on PATH.",
            service=SERVICE,
            hint="Install tmux, then run this command again.",
        )

    runner = runner or subprocess.run
    _run_tmux(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name,
            "-c",
            cwd,
            shlex.join(command),
        ],
        runner=runner,
    )
    pane = _run_tmux(
        ["tmux", "display-message", "-p", "-t", f"{session_name}:0.0", "#{pane_id}"],
        runner=runner,
    ).stdout.strip()
    if not pane:
        raise CopilotError(
            f"tmux session {session_name!r} started but no pane id was returned.",
            service=SERVICE,
        )
    pane_pid = _optional_int(
        _run_tmux(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_pid}"],
            runner=runner,
        ).stdout.strip()
    )
    return TmuxSession(name=session_name, pane=pane, pane_pid=pane_pid)


def inject_text(
    target: str,
    text: str,
    runner: Runner | None = None,
    submit_enters: int = 1,
) -> None:
    """Paste text into a tmux pane and press Enter.

    ``load-buffer -`` avoids shell quoting bugs and preserves newlines. The
    buffer name is stable so repeated deliveries replace prior content instead
    of accumulating local state.
    """
    if not target:
        raise ValidationError(
            "No tmux pane is registered for this Discord handoff.",
            service=SERVICE,
            hint="Run the harness inside tmux and register it with 'copilot discord attach'.",
        )
    if not tmux_available():
        raise ValidationError(
            "tmux is not installed or not on PATH.",
            service=SERVICE,
            hint="Install tmux, then start Claude Code or Codex inside a tmux pane.",
        )

    runner = runner or subprocess.run
    buffer_name = "copilot-discord-bridge"
    _run_tmux(
        ["tmux", "load-buffer", "-b", buffer_name, "-"],
        runner=runner,
        input=text,
    )
    _run_tmux(
        ["tmux", "paste-buffer", "-b", buffer_name, "-t", target],
        runner=runner,
    )
    for _ in range(max(1, submit_enters)):
        _run_tmux(["tmux", "send-keys", "-t", target, "Enter"], runner=runner)


def _run_tmux(
    args: list[str],
    runner: Runner,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = runner(
        args,
        input=input,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "tmux command failed").strip()
        raise CopilotError(
            detail,
            service=SERVICE,
            hint="Check that the registered tmux pane is still alive.",
        )
    return result


def _optional_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
