"""Install and uninstall Discord away-mode hooks for Claude Code and Codex.

The installer writes small shell shims and registers both lifecycle events:

* ``UserPromptSubmit`` arms away-mode when the user asks for Discord follow-up.
* ``Stop`` posts the stopping-point status and releases the terminal.

Claude Code stores hooks in ``settings.json``. Codex can discover hooks from
``hooks.json`` next to its config layer, so this module uses that representation
instead of editing ``config.toml``.
"""

from __future__ import annotations

import json
import os
import shlex
import stat
from pathlib import Path
from typing import Any, Literal

Harness = Literal["claude", "codex"]
HarnessSelection = Literal["claude", "codex", "all"]
Scope = Literal["project", "user"]

PROMPT_EVENT = "UserPromptSubmit"
STOP_EVENT = "Stop"
PROMPT_SHIM_NAME = "discord-user-prompt-submit.sh"
STOP_SHIM_NAME = "discord-stop.sh"
STOP_TIMEOUT_SECONDS = 604800
PROMPT_TIMEOUT_SECONDS = 30


def install_stop_hook(
    scope: Scope = "project",
    target_dir: Path | None = None,
    harness: HarnessSelection = "claude",
) -> dict[str, Any]:
    """Backward-compatible wrapper that installs Discord away-mode hooks."""
    return install_hooks(scope=scope, target_dir=target_dir, harness=harness)


def uninstall_stop_hook(
    scope: Scope = "project",
    target_dir: Path | None = None,
    harness: HarnessSelection = "claude",
) -> dict[str, Any]:
    """Backward-compatible wrapper that removes Discord away-mode hooks."""
    return uninstall_hooks(scope=scope, target_dir=target_dir, harness=harness)


def install_hooks(
    scope: Scope = "project",
    target_dir: Path | None = None,
    harness: HarnessSelection = "all",
) -> dict[str, Any]:
    """Install Discord away-mode hooks for one harness or all supported harnesses."""
    results: dict[str, Any] = {}
    for selected in _selected_harnesses(harness):
        if selected == "claude":
            results[selected] = _install_claude_hooks(scope, target_dir)
        elif selected == "codex":
            results[selected] = _install_codex_hooks(scope, target_dir)
    return results


def uninstall_hooks(
    scope: Scope = "project",
    target_dir: Path | None = None,
    harness: HarnessSelection = "all",
) -> dict[str, Any]:
    """Remove Discord away-mode hooks for one harness or all supported harnesses."""
    results: dict[str, Any] = {}
    for selected in _selected_harnesses(harness):
        if selected == "claude":
            results[selected] = _uninstall_claude_hooks(scope, target_dir)
        elif selected == "codex":
            results[selected] = _uninstall_codex_hooks(scope, target_dir)
    return results


# ---------------------------------------------------------------------- #
# Claude Code                                                              #
# ---------------------------------------------------------------------- #


def _install_claude_hooks(scope: Scope, target_dir: Path | None) -> dict[str, str]:
    hooks_dir, settings_path = _claude_paths(scope, target_dir)
    prompt_shim = _write_shim(hooks_dir, PROMPT_SHIM_NAME, "user-prompt-submit", "claude")
    stop_shim = _write_shim(hooks_dir, STOP_SHIM_NAME, "stop", "claude")

    prompt_cmd = _register_command(prompt_shim, scope, target_dir)
    stop_cmd = _register_command(stop_shim, scope, target_dir)

    settings = _load_json(settings_path)
    settings.setdefault("hooks", {})
    _ensure_event_entry(settings["hooks"], PROMPT_EVENT, prompt_cmd, PROMPT_TIMEOUT_SECONDS)
    _ensure_event_entry(settings["hooks"], STOP_EVENT, stop_cmd, STOP_TIMEOUT_SECONDS)
    _save_json(settings_path, settings)

    return {
        "prompt_shim": str(prompt_shim),
        "stop_shim": str(stop_shim),
        "settings": str(settings_path),
    }


def _uninstall_claude_hooks(scope: Scope, target_dir: Path | None) -> dict[str, str]:
    hooks_dir, settings_path = _claude_paths(scope, target_dir)
    prompt_shim = hooks_dir / PROMPT_SHIM_NAME
    stop_shim = hooks_dir / STOP_SHIM_NAME

    removed_prompt = _unlink(prompt_shim)
    removed_stop = _unlink(stop_shim)
    removed_entries = False

    if settings_path.is_file():
        prompt_cmd = _register_command(prompt_shim, scope, target_dir)
        stop_cmd = _register_command(stop_shim, scope, target_dir)
        settings = _load_json(settings_path)
        hooks = settings.get("hooks", {})
        removed_entries = _remove_event_entry(hooks, PROMPT_EVENT, prompt_cmd)
        removed_entries = _remove_event_entry(hooks, STOP_EVENT, stop_cmd) or removed_entries
        _save_json(settings_path, settings)

    return {
        "prompt_shim_removed": str(removed_prompt),
        "stop_shim_removed": str(removed_stop),
        "entry_removed": str(removed_entries),
        "settings": str(settings_path),
    }


# ---------------------------------------------------------------------- #
# Codex                                                                    #
# ---------------------------------------------------------------------- #


def _install_codex_hooks(scope: Scope, target_dir: Path | None) -> dict[str, str]:
    hooks_dir, hooks_path = _codex_paths(scope, target_dir)
    prompt_shim = _write_shim(hooks_dir, PROMPT_SHIM_NAME, "user-prompt-submit", "codex")
    stop_shim = _write_shim(hooks_dir, STOP_SHIM_NAME, "stop", "codex")

    prompt_cmd = _register_command(prompt_shim, scope, target_dir)
    stop_cmd = _register_command(stop_shim, scope, target_dir)

    hooks_json = _load_json(hooks_path)
    hooks_json.setdefault("hooks", {})
    _ensure_event_entry(
        hooks_json["hooks"],
        PROMPT_EVENT,
        prompt_cmd,
        PROMPT_TIMEOUT_SECONDS,
        status_message="Arming Discord away-mode",
    )
    _ensure_event_entry(
        hooks_json["hooks"],
        STOP_EVENT,
        stop_cmd,
        STOP_TIMEOUT_SECONDS,
        status_message="Posting Discord stopping point",
    )
    _save_json(hooks_path, hooks_json)

    return {
        "prompt_shim": str(prompt_shim),
        "stop_shim": str(stop_shim),
        "hooks": str(hooks_path),
    }


def _uninstall_codex_hooks(scope: Scope, target_dir: Path | None) -> dict[str, str]:
    hooks_dir, hooks_path = _codex_paths(scope, target_dir)
    prompt_shim = hooks_dir / PROMPT_SHIM_NAME
    stop_shim = hooks_dir / STOP_SHIM_NAME

    removed_prompt = _unlink(prompt_shim)
    removed_stop = _unlink(stop_shim)
    removed_entries = False

    if hooks_path.is_file():
        prompt_cmd = _register_command(prompt_shim, scope, target_dir)
        stop_cmd = _register_command(stop_shim, scope, target_dir)
        hooks_json = _load_json(hooks_path)
        hooks = hooks_json.get("hooks", {})
        removed_entries = _remove_event_entry(hooks, PROMPT_EVENT, prompt_cmd)
        removed_entries = _remove_event_entry(hooks, STOP_EVENT, stop_cmd) or removed_entries
        _save_json(hooks_path, hooks_json)

    return {
        "prompt_shim_removed": str(removed_prompt),
        "stop_shim_removed": str(removed_stop),
        "entry_removed": str(removed_entries),
        "hooks": str(hooks_path),
    }


# ---------------------------------------------------------------------- #
# Shared helpers                                                           #
# ---------------------------------------------------------------------- #


def _selected_harnesses(harness: HarnessSelection) -> tuple[Harness, ...]:
    if harness == "all":
        return ("claude", "codex")
    if harness in {"claude", "codex"}:
        return (harness,)
    raise ValueError("harness must be 'claude', 'codex', or 'all'")


def _claude_paths(scope: Scope, target_dir: Path | None) -> tuple[Path, Path]:
    if scope == "user":
        base = Path("~/.claude").expanduser()
    else:
        base = Path(target_dir or os.getcwd()) / ".claude"
    return base / "hooks", base / "settings.json"


def _codex_paths(scope: Scope, target_dir: Path | None) -> tuple[Path, Path]:
    if scope == "user":
        base = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    else:
        base = Path(target_dir or os.getcwd()) / ".codex"
    return base / "hooks", base / "hooks.json"


def _write_shim(hooks_dir: Path, name: str, event: str, harness: Harness) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    shim_path = hooks_dir / name
    shim_path.write_text(_shim_content(event, harness), encoding="utf-8")
    mode = shim_path.stat().st_mode
    shim_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim_path


# Portable shim body: resolves the copilot binary and COPILOT_ENV_FILE at
# RUNTIME so generated shims carry no machine-specific absolute paths and are
# safe to commit. (Raw string to preserve bash ``$`` / ``\`` verbatim.)
_SHIM_PREAMBLE = r"""#!/usr/bin/env bash
set -euo pipefail

# copilot binary: honor COPILOT_BIN, else use PATH.
copilot_bin="${COPILOT_BIN:-}"
if [ -z "$copilot_bin" ]; then
  copilot_bin="$(command -v copilot 2>/dev/null || true)"
fi
if [ -z "$copilot_bin" ]; then
  echo "[discord-hook] copilot CLI not found on PATH; skipping" >&2
  exit 0
fi

# COPILOT_ENV_FILE (holds Discord config): honor an existing value, else
# discover it relative to this repo.
if [ -z "${COPILOT_ENV_FILE:-}" ]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
  repo_root="$(cd "$here/../.." >/dev/null 2>&1 && pwd)"
  for candidate in \
    "$repo_root/.codex/discord.env" \
    "$repo_root/.claude/discord.env" \
    "$repo_root/../cli-copilot/.env" \
    "$HOME/.config/copilot/.env"; do
    if [ -f "$candidate" ]; then export COPILOT_ENV_FILE="$candidate"; break; fi
  done
fi
"""


def _shim_content(event: str, harness: Harness) -> str:
    exec_line = (
        f'exec "$copilot_bin" discord hook {shlex.quote(event)} --harness {shlex.quote(harness)}\n'
    )
    return _SHIM_PREAMBLE + "\n" + exec_line


def _register_command(shim_path: Path, scope: Scope, target_dir: Path | None) -> str:
    """Command string to register in the hooks config.

    Project-scope config lives inside the repo and is typically committed, so
    register a repo-relative path (portable across checkouts). User-scope config
    lives outside any repo, so keep an absolute path.
    """
    if scope == "project":
        project_root = Path(target_dir) if target_dir is not None else Path(os.getcwd())
        try:
            return os.path.relpath(shim_path, project_root)
        except ValueError:  # pragma: no cover - different drives on Windows
            return str(shim_path)
    return str(shim_path)


def _ensure_event_entry(
    hooks: dict[str, Any],
    event: str,
    command: str,
    timeout: int,
    status_message: str | None = None,
) -> None:
    groups: list[Any] = hooks.setdefault(event, [])
    hook_config: dict[str, Any] = {
        "type": "command",
        "command": command,
        "timeout": timeout,
    }
    if status_message:
        hook_config["statusMessage"] = status_message
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            if isinstance(hook, dict) and hook.get("command") == command:
                hook.update(hook_config)
                return
    groups.append({"hooks": [hook_config]})


def _remove_event_entry(hooks: dict[str, Any], event: str, command: str) -> bool:
    groups = hooks.get(event, [])
    if not isinstance(groups, list):
        return False

    removed = False
    kept_groups: list[Any] = []
    for group in groups:
        if not isinstance(group, dict):
            kept_groups.append(group)
            continue
        old_handlers = group.get("hooks", [])
        new_handlers = [
            hook
            for hook in old_handlers
            if not (isinstance(hook, dict) and hook.get("command") == command)
        ]
        if len(new_handlers) != len(old_handlers):
            removed = True
        if new_handlers:
            new_group = dict(group)
            new_group["hooks"] = new_handlers
            kept_groups.append(new_group)

    hooks[event] = kept_groups
    return removed


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _unlink(path: Path) -> bool:
    if not path.is_file():
        return False
    path.unlink()
    return True
