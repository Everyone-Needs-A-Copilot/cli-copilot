"""Typer subcommand group for Discord handoffs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import sys
from contextlib import suppress
from pathlib import Path

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    is_json_mode,
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
    print_warning,
)

app = typer.Typer(no_args_is_help=True)
_await_app = typer.Typer(no_args_is_help=True, help="Manage Discord away/await mode.")
_bridge_app = typer.Typer(no_args_is_help=True, help="Manage the Discord tmux bridge.")


def _client():
    from copilot_cli.services.discord.client import DiscordClient

    return DiscordClient()


def _mention_user_ids(client, thread_id: str | None = None) -> list[str]:
    if thread_id:
        try:
            record = client.get_handoff(thread_id)
            values = record.get("allowed_user_ids") or []
            return [str(value).strip() for value in values if str(value).strip()]
        except CopilotError:
            pass
    return client.allowed_user_ids()


def _with_mentions(message: str, user_ids: list[str]) -> str:
    cleaned = [str(user_id).strip() for user_id in user_ids if str(user_id).strip()]
    if not cleaned:
        return message
    mentions = " ".join(f"<@{user_id}>" for user_id in cleaned)
    if any(f"<@{user_id}>" in message for user_id in cleaned):
        return message
    return f"{mentions} {message}"


def _notify_thread_for_cwd(client, cwd: str) -> str | None:
    """Return the only open handoff thread for cwd, preferring armed sessions."""
    with suppress(Exception):
        client.reap_stale_handoffs()
    records = [
        record
        for record in client.load_handoffs()
        if record.get("status") == "open" and record.get("cwd") == cwd
    ]
    armed = [record for record in records if record.get("await") is True]
    candidates = armed or records
    if len(candidates) == 1:
        return str(candidates[0].get("thread_id") or "") or None
    return None


# ---------------------------------------------------------------------- #
# handoff                                                                  #
# ---------------------------------------------------------------------- #


@app.command()
def handoff(
    message: str = typer.Argument(..., help="Initial message to post in the new thread."),
    title: str = typer.Option("Copilot handoff", "--title", "-t", help="Discord thread title."),
    harness: str | None = typer.Option(None, "--harness", help="codex, claude, or another label."),
    session_id: str | None = typer.Option(None, "--session-id", help="Local harness session id."),
    cwd: str = typer.Option("", "--cwd", help="Project working directory. Defaults to cwd."),
    channel_id: str | None = typer.Option(None, "--channel-id", help="Discord parent channel id."),
    agent_slug: str = typer.Option(
        "lead-cto", "--agent-slug", help="Agent slug for registry metadata."
    ),
    allowed_user_ids: str | None = typer.Option(
        None,
        "--allowed-user-ids",
        help="Comma-separated Discord user ids allowed to steer this handoff.",
    ),
    enable_await: bool = typer.Option(
        False,
        "--await/--no-await",
        help=(
            "Arm Discord away-mode on the new handoff. "
            "When armed, the Stop hook posts stopping points without blocking; "
            "full reply injection requires a tmux bridge session."
        ),
    ),
) -> None:
    """Create a new Discord thread for the current local session."""
    try:
        client = _client()
        allowed = client.allowed_user_ids(allowed_user_ids) if allowed_user_ids else None
        record = client.start_handoff(
            title=title,
            message=message,
            harness=harness,
            local_session_id=session_id,
            cwd=cwd or os.getcwd(),
            agent_slug=agent_slug,
            channel_id=channel_id,
            allowed_user_ids=allowed,
        )
        if enable_await:
            record = client.set_await(record["thread_id"], True)
            if not os.environ.get("TMUX"):
                launch_harness = (harness or "codex").strip().lower()
                if launch_harness not in {"codex", "claude"}:
                    launch_harness = "codex"
                print_warning(
                    "This terminal is not inside tmux, so Discord replies cannot be "
                    "injected back into this session automatically. The Stop hook will "
                    "still post updates to the thread without blocking. For a two-way "
                    "bridge, launch the session with "
                    f"`copilot discord bridge launch {launch_harness}`."
                )
        print_json(record, title="Discord Handoff")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# notify                                                                   #
# ---------------------------------------------------------------------- #


@app.command()
def notify(
    message: str = typer.Argument(..., help="Message to post to Discord."),
    thread_id: str | None = typer.Option(None, "--thread-id", help="Target Discord thread id."),
    channel_id: str | None = typer.Option(None, "--channel-id", help="Target Discord channel id."),
    mention: bool = typer.Option(
        True,
        "--mention/--no-mention",
        help="Mention configured allowed Discord users so the notification is visible.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Post even when away-mode is armed for the thread, bypassing the "
        "duplicate-mirror guard.",
    ),
) -> None:
    """Post an update to a registered handoff thread."""
    try:
        client = _client()
        if not thread_id:
            if channel_id:
                print_error(
                    "Refusing to post a Discord notification directly to a parent channel.",
                    hint=(
                        "Use `copilot discord handoff ...` to start a new thread, "
                        "or pass `--thread-id <thread_id>` to continue an existing one."
                    ),
                )
                raise typer.Exit(1)
            thread_id = _notify_thread_for_cwd(client, os.getcwd())
            if not thread_id:
                print_error(
                    "Refusing to post a Discord notification without a thread.",
                    hint=(
                        "Use `copilot discord handoff ...` to start a new thread, "
                        "or pass `--thread-id <thread_id>` to continue an existing one."
                    ),
                )
                raise typer.Exit(1)
        # Away-mode guard: while the Stop hook is mirroring a thread's turns, a
        # manual notify posts the same content a second time. Skip unless forced
        # so correctness never depends on an agent remembering not to notify.
        if thread_id and not force:
            with suppress(CopilotError):
                record = client.get_handoff(thread_id)
                if record.get("await") is True and record.get("status") == "open":
                    print_success(
                        "Away-mode is armed for this thread — the Stop hook already "
                        "mirrors each turn's final message. Skipped manual notify to "
                        "avoid a duplicate post (use --force to override)."
                    )
                    return
        mention_user_ids = _mention_user_ids(client, thread_id) if mention else []
        client.send_message(
            _with_mentions(message, mention_user_ids),
            channel_id=channel_id,
            thread_id=thread_id,
            mention_user_ids=mention_user_ids,
        )
        print_success("Discord message sent.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# wait                                                                     #
# ---------------------------------------------------------------------- #


@app.command()
def wait(
    thread_id: str = typer.Argument(..., help="Registered Discord thread id."),
    timeout: int = typer.Option(0, "--timeout", help="Seconds to wait. 0 waits forever."),
    poll_interval: float = typer.Option(
        5.0, "--poll-interval", help="Polling interval in seconds."
    ),
    after_message_id: str | None = typer.Option(
        None,
        "--after-message-id",
        help="Only consider messages after this Discord message id.",
    ),
    mark_seen: bool = typer.Option(True, "--mark-seen/--no-mark-seen"),
) -> None:
    """Wait for the next authorized reply in a handoff thread."""
    try:
        client = _client()
        record = client.get_handoff(thread_id)
        after = after_message_id or record.get("last_seen_message_id") or None
        reply = client.wait_for_reply(
            thread_id,
            after_message_id=after,
            allowed_user_ids=record.get("allowed_user_ids") or None,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        if mark_seen:
            client.mark_seen(thread_id, reply.message_id)
        print_json(reply.to_dict(), title="Discord Reply")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# listen                                                                   #
# ---------------------------------------------------------------------- #


@app.command()
def listen(
    thread_id: str = typer.Argument(..., help="Registered Discord thread id."),
    timeout: int = typer.Option(0, "--timeout", help="Seconds to listen. 0 listens forever."),
    after_message_id: str | None = typer.Option(
        None,
        "--after-message-id",
        help="Only consider messages after this Discord message id.",
    ),
    mark_seen: bool = typer.Option(True, "--mark-seen/--no-mark-seen"),
) -> None:
    """Listen for the next authorized reply using Discord Gateway events."""
    try:
        client = _client()
        record = client.get_handoff(thread_id)
        after = after_message_id or record.get("last_seen_message_id") or None
        reply = asyncio.run(
            client.listen_for_reply(
                thread_id,
                after_message_id=after,
                allowed_user_ids=record.get("allowed_user_ids") or None,
                timeout=timeout,
            )
        )
        if mark_seen:
            client.mark_seen(thread_id, reply.message_id)
        print_json(reply.to_dict(), title="Discord Reply")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# ack                                                                      #
# ---------------------------------------------------------------------- #


@app.command("ack")
def ack(
    thread_id: str = typer.Argument(..., help="Registered Discord thread id."),
    message_id: str = typer.Argument(..., help="Discord message id that has been handled."),
) -> None:
    """Mark a Discord reply as handled after the local session acts on it."""
    try:
        record = _client().mark_seen(thread_id, message_id)
        print_json(
            {
                "thread_id": record["thread_id"],
                "last_seen_message_id": record.get("last_seen_message_id", ""),
                "updated_at": record.get("updated_at", ""),
            },
            title="Discord Ack",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# list                                                                     #
# ---------------------------------------------------------------------- #


@app.command("list")
def list_handoffs(
    open_only: bool = typer.Option(False, "--open", help="Show only open handoffs."),
) -> None:
    """List registered Discord handoff threads."""
    try:
        client = _client()
        rows = client.open_handoffs() if open_only else client.load_handoffs()
        print_table(
            rows,
            title="Discord Handoffs",
            columns=["thread_id", "status", "harness", "cwd", "await", "title", "updated_at"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# attach                                                                   #
# ---------------------------------------------------------------------- #


@app.command()
def attach(
    thread_id: str = typer.Argument(..., help="Registered Discord handoff thread id."),
    tmux_pane: str | None = typer.Option(
        None,
        "--tmux-pane",
        help="tmux pane target. Defaults to $TMUX_PANE.",
    ),
    harness: str | None = typer.Option(
        None,
        "--harness",
        help="Harness label for routing metadata: claude, codex, or another label.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Local harness session id.",
    ),
    cwd: str = typer.Option("", "--cwd", help="Project working directory. Defaults to cwd."),
) -> None:
    """Attach an open handoff thread to the current tmux pane for bridge delivery."""
    try:
        from copilot_cli.services.discord.bridge import attach_record

        record = attach_record(
            _client(),
            thread_id=thread_id,
            tmux_pane=tmux_pane,
            harness=harness,
            session_id=session_id,
            cwd=cwd or os.getcwd(),
        )
        print_json(record, title="Discord Bridge Attached")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# doctor                                                                   #
# ---------------------------------------------------------------------- #


def _scan_shims() -> list[str]:
    """Warn about installed stop-hook shims that carry hardcoded paths."""
    warnings: list[str] = []
    candidates = [
        Path.home() / ".claude" / "hooks" / "discord-stop.sh",
        Path.home() / ".codex" / "hooks" / "discord-stop.sh",
        Path.cwd() / ".claude" / "hooks" / "discord-stop.sh",
        Path.cwd() / ".codex" / "hooks" / "discord-stop.sh",
    ]
    seen: set[Path] = set()
    for shim in candidates:
        if not shim.is_file():
            continue
        resolved = shim.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        text = shim.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?m)^\s*exec\s+/\S*copilot\b", text):
            warnings.append(
                f"{shim}: execs a hardcoded copilot path — re-run 'copilot discord install-hook'."
            )
        if re.search(r"(?m)^\s*(export\s+)?COPILOT_ENV_FILE=/", text):
            warnings.append(
                f"{shim}: bakes an absolute COPILOT_ENV_FILE — re-run 'copilot discord install-hook'."
            )
    return warnings


@app.command()
def doctor(
    fix: bool = typer.Option(
        False, "--fix", help="Close stale handoffs whose owning session is gone."
    ),
) -> None:
    """Report (and optionally --fix) stale away-mode handoffs and hook shims.

    A handoff is stale when its owning harness process is gone (killed terminal)
    or superseded by a new /clear or /new session. Live sessions — even ones
    parked for days on a Discord wait — are never touched.
    """
    from copilot_cli.services.discord.client import is_stale_await

    def _state(rec: dict) -> str:
        if is_stale_await(rec):
            return "STALE"
        if not (rec.get("bridge_enabled") or rec.get("tmux_pane")):
            return "NOT-BRIDGED"
        if not rec.get("owner_pid"):
            return "legacy?"  # pre-reaper record; liveness unknowable — close manually
        return "bridged"

    try:
        client = _client()
        handoffs = client.load_handoffs()
        open_await = [r for r in handoffs if r.get("status") == "open" and r.get("await")]
        states = {r["thread_id"]: _state(r) for r in open_await}
        counts = {
            s: sum(1 for v in states.values() if v == s)
            for s in ("bridged", "NOT-BRIDGED", "STALE", "legacy?")
        }

        print_table(
            [
                {
                    "thread_id": r.get("thread_id"),
                    "state": states[r["thread_id"]],
                    "mode": "bridge"
                    if (r.get("bridge_enabled") or r.get("tmux_pane"))
                    else "notify-only",
                    "owner_pid": r.get("owner_pid", "—"),
                    "harness": r.get("harness", ""),
                    "cwd": r.get("cwd", ""),
                    "updated_at": r.get("updated_at", ""),
                }
                for r in open_await
            ],
            title="Away-mode handoffs (open + await)",
            columns=["thread_id", "state", "mode", "owner_pid", "harness", "cwd", "updated_at"],
        )

        for warning in _scan_shims():
            typer.echo(f"⚠  {warning}")

        if fix:
            reaped = client.reap_stale_handoffs()
            print_success(
                f"Reaped {len(reaped)} stale handoff(s); "
                f"{counts['bridged']} bridged, {counts['NOT-BRIDGED']} not-bridged, "
                f"{counts['legacy?']} legacy remain."
            )
            if counts["legacy?"]:
                typer.echo(
                    "Note: 'legacy?' records predate liveness tracking and can't be "
                    "auto-verified. Close them with 'copilot discord close <thread_id>'."
                )
        else:
            hint = (
                " Run 'copilot discord doctor --fix' to close STALE ones."
                if counts["STALE"]
                else ""
            )
            print_success(
                f"{counts['bridged']} bridged, {counts['NOT-BRIDGED']} not-bridged, "
                f"{counts['STALE']} stale, {counts['legacy?']} legacy.{hint}"
            )
            if counts["NOT-BRIDGED"]:
                typer.echo(
                    "Warning: NOT-BRIDGED handoffs are notification-only (notify-only); Discord replies "
                    "will not reach Codex/Claude. Start controllable sessions with "
                    "'copilot discord bridge launch codex' or 'claude'."
                )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# close                                                                    #
# ---------------------------------------------------------------------- #


@app.command()
def close(
    thread_id: str = typer.Argument(..., help="Registered Discord thread id."),
    message: str | None = typer.Option(None, "--message", help="Optional closing message to post."),
) -> None:
    """Close a registered handoff (also ends the await loop)."""
    try:
        client = _client()
        if message:
            client.send_message(message, thread_id=thread_id)
        record = client.close_handoff(thread_id)
        print_json(record, title="Discord Handoff Closed")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# health                                                                   #
# ---------------------------------------------------------------------- #


@app.command()
def health() -> None:
    """Check Discord API connectivity."""
    try:
        result = _client().get_channel()
        print_health("discord", True)
        print_success(f"Discord channel reachable: {result.get('id', '?')}")
    except CopilotError as exc:
        print_health("discord", False, {"error": str(exc)})
        raise typer.Exit(1)


# ---------------------------------------------------------------------- #
# hook / stop-hook                                                         #
# ---------------------------------------------------------------------- #


def _read_hook_stdin(label: str) -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, Exception) as exc:
        sys.stderr.write(f"[discord {label}] malformed stdin: {exc}\n")
        raise typer.Exit(0) from exc


def _normalize_hook_event(event: str) -> str:
    normalized = event.strip().lower().replace("_", "-")
    aliases = {
        "prompt": "user-prompt-submit",
        "userpromptsubmit": "user-prompt-submit",
        "user-prompt-submit": "user-prompt-submit",
        "stop": "stop",
        "stophook": "stop",
        "stop-hook": "stop",
    }
    if normalized not in aliases:
        raise ValueError("event must be 'user-prompt-submit' or 'stop'")
    return aliases[normalized]


def _hook_debug_enabled() -> bool:
    return os.environ.get("COPILOT_DISCORD_HOOK_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _run_hook_event(event: str, harness: str, label: str) -> None:
    stdin_data = _read_hook_stdin(label)
    try:
        from copilot_cli.config.settings import get_settings
        from copilot_cli.services.discord.hook import run_prompt_hook, run_stop_hook

        client = _client()
        settings = get_settings()
        normalized = _normalize_hook_event(event)
        if normalized == "user-prompt-submit":
            prompt_result = run_prompt_hook(
                stdin_data,
                client=client,
                settings=settings,
                harness=harness,
            )
            if prompt_result.debug and _hook_debug_enabled():
                sys.stderr.write(f"[discord {label}] {prompt_result.debug}\n")
            if prompt_result.additional_context:
                sys.stdout.write(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "UserPromptSubmit",
                                "additionalContext": prompt_result.additional_context,
                            }
                        }
                    )
                )
            return

        stop_result = run_stop_hook(
            stdin_data,
            client=client,
            settings=settings,
            harness=harness,
        )
    except Exception as exc:
        sys.stderr.write(f"[discord {label}] error: {exc}\n")
        sys.exit(0)

    if stop_result.debug and _hook_debug_enabled():
        sys.stderr.write(f"[discord {label}] {stop_result.debug}\n")

    if stop_result.block:
        sys.stdout.write(json.dumps({"decision": "block", "reason": stop_result.reason}))
    # else: exit 0 with no output → allow stop


@app.command("hook")
def hook(
    event: str = typer.Argument(..., help="Hook event: user-prompt-submit or stop."),
    harness: str = typer.Option(
        "claude",
        "--harness",
        help="Harness label for thread routing: claude or codex.",
    ),
) -> None:
    """Read hook JSON from stdin and run the Discord away-mode bridge.

    All errors fail open so local assistant sessions are never trapped by
    Discord infrastructure failures.
    """
    try:
        _run_hook_event(event, harness, label=f"hook:{event}")
    except typer.Exit:
        raise
    except Exception as exc:
        sys.stderr.write(f"[discord hook:{event}] error: {exc}\n")
        sys.exit(0)


@app.command("stop-hook")
def stop_hook() -> None:
    """Backward-compatible alias for ``copilot discord hook stop --harness claude``."""
    _run_hook_event("stop", "claude", label="stop-hook")


# ---------------------------------------------------------------------- #
# await on / await off  (arm / disarm away-mode)                          #
# ---------------------------------------------------------------------- #


@_await_app.command("on")
def await_on(
    thread_id: str = typer.Argument(..., help="Thread id to arm."),
) -> None:
    """Arm Discord away-mode for a handoff thread."""
    try:
        record = _client().set_await(thread_id, True)
        print_json(record, title="Discord Await Armed")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_await_app.command("off")
def await_off(
    thread_id: str = typer.Argument(..., help="Thread id to disarm."),
) -> None:
    """Disarm Discord away-mode for a handoff thread."""
    try:
        record = _client().set_await(thread_id, False)
        print_json(record, title="Discord Await Disarmed")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


app.add_typer(_await_app, name="await", help="Arm or disarm Discord away-mode.")


# ---------------------------------------------------------------------- #
# bridge                                                                   #
# ---------------------------------------------------------------------- #


@_bridge_app.command("run")
def bridge_run() -> None:
    """Run the local Discord Gateway bridge worker in the foreground."""
    try:
        from copilot_cli.services.discord.bridge import DiscordBridgeWorker

        asyncio.run(DiscordBridgeWorker().run_forever())
    except KeyboardInterrupt:
        raise typer.Exit(0)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_bridge_app.command("launch")
def bridge_launch(
    harness: str = typer.Argument("codex", help="Assistant harness to launch: codex or claude."),
    command: str | None = typer.Option(
        None,
        "--command",
        help="Override command to run inside tmux, for example: 'codex --model gpt-5'.",
    ),
    session_name: str | None = typer.Option(
        None,
        "--session-name",
        help="tmux session name. Defaults to a project-based name.",
    ),
    cwd: str = typer.Option("", "--cwd", help="Project working directory. Defaults to cwd."),
    title: str = typer.Option(
        "",
        "--title",
        "-t",
        help="Discord thread title. Defaults to '<harness> bridge: <project>'.",
    ),
    message: str = typer.Option(
        "",
        "--message",
        "-m",
        help="Initial Discord message. Defaults to a bridge-ready status note.",
    ),
    channel_id: str | None = typer.Option(None, "--channel-id", help="Discord parent channel id."),
    allowed_user_ids: str | None = typer.Option(
        None,
        "--allowed-user-ids",
        help="Comma-separated Discord user ids allowed to steer this bridge.",
    ),
) -> None:
    """Launch a bridge-ready Claude Code or Codex session in detached tmux."""
    try:
        from copilot_cli.services.discord.bridge import start_tmux_bridge_session

        client = _client()
        working_dir = cwd or os.getcwd()
        project = Path(working_dir).expanduser().resolve().name or "session"
        normalized_harness = harness.strip().lower()
        allowed = client.allowed_user_ids(allowed_user_ids) if allowed_user_ids else None
        record = start_tmux_bridge_session(
            client,
            harness=normalized_harness,
            title=title or f"{normalized_harness} bridge: {project}",
            message=message
            or (
                f"Started a local {normalized_harness} session in tmux for {project}. "
                "Reply in this thread to continue that same local session."
            ),
            session_name=session_name,
            cwd=working_dir,
            command=shlex.split(command) if command else None,
            channel_id=channel_id,
            allowed_user_ids=allowed,
        )
        print_json(record, title="Discord Bridge Launched")
        if not is_json_mode():
            typer.echo(f"Attach locally with: {record['tmux_attach_command']}")
    except ValueError as exc:
        print_error(f"Invalid --command: {exc}")
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_bridge_app.command("status")
def bridge_status_command() -> None:
    """Show registered bridge sessions and queue counts."""
    try:
        from copilot_cli.services.discord.bridge import bridge_status

        print_json(bridge_status(), title="Discord Bridge Status")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_bridge_app.command("install")
def bridge_install(
    copilot_bin: str | None = typer.Option(
        None,
        "--copilot-bin",
        help="Optional copilot executable override for launchd.",
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help="Optional COPILOT_ENV_FILE override. Defaults to normal config discovery.",
    ),
    path_env: str | None = typer.Option(
        None,
        "--path-env",
        help="PATH for launchd. Defaults to discovered copilot/tmux dirs plus system PATH.",
    ),
) -> None:
    """Install the local launchd worker for the Discord bridge."""
    try:
        from copilot_cli.services.discord.bridge import install_launch_agent

        plist_path = install_launch_agent(
            copilot_bin=copilot_bin,
            env_file=env_file,
            path_env=path_env,
        )
        print_success(f"Discord bridge launch agent installed: {plist_path}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_bridge_app.command("start")
def bridge_start() -> None:
    """Start the installed Discord bridge launchd worker."""
    try:
        from copilot_cli.services.discord.bridge import launchctl

        result = launchctl("start")
        if result.returncode != 0:
            print_error(result.stderr or result.stdout or "Failed to start Discord bridge.")
            raise typer.Exit(1)
        print_success("Discord bridge started.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@_bridge_app.command("stop")
def bridge_stop() -> None:
    """Stop the installed Discord bridge launchd worker."""
    try:
        from copilot_cli.services.discord.bridge import launchctl

        result = launchctl("stop")
        if result.returncode != 0:
            print_error(result.stderr or result.stdout or "Failed to stop Discord bridge.")
            raise typer.Exit(1)
        print_success("Discord bridge stopped.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


app.add_typer(_bridge_app, name="bridge", help="Manage the Discord tmux bridge.")


# ---------------------------------------------------------------------- #
# install-hook / uninstall-hook                                            #
# ---------------------------------------------------------------------- #


@app.command("install-hook")
def install_hook(
    scope: str = typer.Option(
        "user",
        "--scope",
        help="project or user (default).",
    ),
    harness: str = typer.Option(
        "all",
        "--harness",
        help="claude, codex, or all.",
    ),
    target_dir: str = typer.Option(
        "",
        "--target-dir",
        help="Explicit project root (scope=project only). Defaults to cwd.",
    ),
) -> None:
    """Install Discord away-mode hooks for Claude Code and/or Codex.

    Idempotent: safe to run multiple times.

    \\b
    Scopes
    ------
    project  Writes project-local hook files under .claude/ and/or .codex/.
    user     Writes user-level hook files under ~/.claude/ and/or ~/.codex/.
    """
    from copilot_cli.services.discord.install import install_hooks

    valid_scopes = {"project", "user"}
    if scope not in valid_scopes:
        print_error(f"Invalid scope {scope!r}. Choose 'project' or 'user'.")
        raise typer.Exit(1)
    valid_harnesses = {"claude", "codex", "all"}
    if harness not in valid_harnesses:
        print_error(f"Invalid harness {harness!r}. Choose 'claude', 'codex', or 'all'.")
        raise typer.Exit(1)

    try:
        result = install_hooks(
            scope=scope,  # type: ignore[arg-type]
            target_dir=Path(target_dir) if target_dir else None,
            harness=harness,  # type: ignore[arg-type]
        )
        for name, installed in result.items():
            print_success(f"{name} prompt hook installed: {installed['prompt_shim']}")
            print_success(f"{name} stop hook installed: {installed['stop_shim']}")
            print_success(
                f"{name} registered in: {installed.get('settings') or installed.get('hooks')}"
            )
    except Exception as exc:
        print_error(f"Failed to install Discord hooks: {exc}")
        raise typer.Exit(1)


@app.command("uninstall-hook")
def uninstall_hook(
    scope: str = typer.Option("user", "--scope", help="project or user."),
    harness: str = typer.Option("all", "--harness", help="claude, codex, or all."),
    target_dir: str = typer.Option("", "--target-dir", help="Explicit project root."),
) -> None:
    """Remove Discord away-mode hook shims and settings entries."""
    from copilot_cli.services.discord.install import uninstall_hooks

    valid_scopes = {"project", "user"}
    if scope not in valid_scopes:
        print_error(f"Invalid scope {scope!r}. Choose 'project' or 'user'.")
        raise typer.Exit(1)
    valid_harnesses = {"claude", "codex", "all"}
    if harness not in valid_harnesses:
        print_error(f"Invalid harness {harness!r}. Choose 'claude', 'codex', or 'all'.")
        raise typer.Exit(1)

    try:
        result = uninstall_hooks(
            scope=scope,  # type: ignore[arg-type]
            target_dir=Path(target_dir) if target_dir else None,
            harness=harness,  # type: ignore[arg-type]
        )
        removed_any = False
        for name, removed in result.items():
            if (
                removed.get("prompt_shim_removed") == "True"
                or removed.get("stop_shim_removed") == "True"
            ):
                print_success(f"{name} shims removed.")
                removed_any = True
            if removed.get("entry_removed") == "True":
                print_success(
                    f"{name} settings entry removed from: "
                    f"{removed.get('settings') or removed.get('hooks')}"
                )
                removed_any = True
        if not removed_any:
            print_success("Nothing to remove (hook was not installed).")
    except Exception as exc:
        print_error(f"Failed to uninstall Discord hooks: {exc}")
        raise typer.Exit(1)
