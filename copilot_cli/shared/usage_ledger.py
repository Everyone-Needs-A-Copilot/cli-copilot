"""Opt-in, append-only usage ledger.

SOUL.md's statelessness stance ("The Stateful Store" anti-pattern) is about
*portability* -- the binary must work unchanged in any project -- not
privacy, and it is already breached in practice by uspto's local
session-capture state (a narrow, documented exception; the discord handoff
registry and Coolify's three-layer config were two more, but both now live
in the org-specific `-internal` tier, not this public foundation). This
ledger is the second, explicitly documented exception: it exists only to
answer "is this CLI actually used, and by which commands" (a
usage-frequency audit finding) and is OFF by default so the charter default
is preserved.

Enable with ``COPILOT_USAGE_LOG=1``. When enabled, every command
invocation appends one JSON line to ``~/.copilot-cli/usage.jsonl``
(override the path with ``COPILOT_USAGE_LOG_PATH``):

    {"ts": "2026-07-12T10:00:00.123456Z", "cmd": "git status",
     "exit_code": 0, "duration_ms": 12, "version": "1.4.5"}

PRIVACY INVARIANT: ``cmd`` is the resolved command *path* only (the group
and subcommand names Click/Typer dispatched through) -- never argument
values, option values, or environment contents.

RESILIENCE INVARIANT: any failure writing the ledger (missing directory,
permissions, full disk) is swallowed silently. The ledger must never
break or slow down the command it is observing.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from copilot_cli import __version__

_ENV_VAR = "COPILOT_USAGE_LOG"
_PATH_ENV_VAR = "COPILOT_USAGE_LOG_PATH"
_DEFAULT_LOG_PATH = "~/.copilot-cli/usage.jsonl"

_installed = False


def _enabled() -> bool:
    """Return True only when the ledger has been explicitly opted into."""
    try:
        return os.environ.get(_ENV_VAR) == "1"
    except Exception:
        return False


def _log_path() -> Path:
    override = os.environ.get(_PATH_ENV_VAR)
    return Path(override).expanduser() if override else Path(_DEFAULT_LOG_PATH).expanduser()


def _command_path(ctx: typer.Context) -> str:
    """Resolve the invoked command path, excluding the root program name.

    Walks the Click context's parent chain so nested groups (e.g.
    ``discord bridge run``) resolve correctly regardless of nesting depth.
    """
    names: list[str] = []
    node: Any = ctx
    while node is not None and node.parent is not None:
        names.append(node.info_name or "")
        node = node.parent
    return " ".join(reversed(names))


def record(cmd: str, exit_code: int, duration_ms: int) -> None:
    """Append one usage line to the ledger when enabled. Never raises.

    Args:
        cmd: Resolved command path only (e.g. ``"git status"``). Callers
            must never pass argument or option values.
        exit_code: The command's real exit code.
        duration_ms: Wall-clock duration of the command, in milliseconds.
    """
    if not _enabled():
        return
    try:
        entry = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "cmd": cmd,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "version": __version__,
        }
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        # RESILIENCE INVARIANT: a ledger failure must never break or slow
        # the command it is observing.
        pass


def install() -> None:
    """Patch ``TyperCommand.invoke`` once so every leaf command is timed.

    This is the single hook point for the ledger: every ``@app.command()``
    leaf -- in every nested ``add_typer`` group -- is built by Typer into a
    ``TyperCommand`` instance, so patching this one method covers all leaf
    commands without touching any service's command functions. Group
    dispatch (resolving ``copilot git status`` down to the ``status``
    leaf) is untouched, so nested command paths still resolve correctly.
    """
    global _installed
    if _installed:
        return

    from typer.core import TyperCommand

    original_invoke = TyperCommand.invoke

    def _invoke_with_ledger(self: TyperCommand, ctx: typer.Context) -> Any:
        if not _enabled():
            return original_invoke(self, ctx)

        start = time.monotonic()
        exit_code = 0
        try:
            return original_invoke(self, ctx)
        except typer.Exit as exc:
            exit_code = exc.exit_code if isinstance(exc.exit_code, int) else 1
            raise
        except SystemExit as exc:
            code = exc.code
            exit_code = code if isinstance(code, int) else (0 if code is None else 1)
            raise
        except Exception as exc:
            candidate = getattr(exc, "exit_code", 1)
            exit_code = candidate if isinstance(candidate, int) else 1
            raise
        except BaseException:
            exit_code = 1
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            record(_command_path(ctx), exit_code, duration_ms)

    TyperCommand.invoke = _invoke_with_ledger
    _installed = True
