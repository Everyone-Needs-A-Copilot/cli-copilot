"""Discord hook bridge for active local sessions.

Called by the hook shims (``copilot discord hook ...``).  The prompt hook
registers the local session when the user asks to be notified in Discord. The
stop hook mirrors the stopping-point status and then releases the terminal;
Discord input is handled by the background bridge worker, never by parking the
harness.

Design goals
------------
* Pure-ish: legacy ``wait_fn`` is injected so unit tests run without real I/O.
* Harness-neutral: Claude Code and Codex adapters call the same command.
* Graceful on every failure: infra errors → allow stop, never trap terminal.

Termination flow
----------------
No await-handoff for cwd     → allow stop (guard for active terminal sessions)
COPILOT_DISCORD_LOOP=off     → allow stop (escape hatch)
COPILOT_SAFETY=off           → allow stop (umbrella escape hatch)
Bridge mode / await active   → post stopping point, allow stop
Legacy blocking wait enabled → old Stop-hook wait/continue behavior
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shlex
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVICE = "discord"

# Tokens a user can post to end away-mode and return control to the terminal.
TERMINATOR_TOKENS: frozenset[str] = frozenset({"/return", "/resume-local", "/stop"})

# Template for the reason string injected back into the harness as the next turn
# only when explicitly running the legacy blocking Stop-hook mode.
_REPLY_FRAME = (
    "[Discord away-mode] Reply from @{username}"
    " (Discord thread {thread_id}; this continues the current session;"
    " the Discord hook bridge remains armed):\n\n"
    "{content}\n\n"
    "Continue with this instruction in the same local session. After each turn "
    "the Stop hook posts your next stopping point to this thread and waits for "
    "your reply. Reply /return to end away-mode."
)

_PROMPT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\blet\s+me\s+know\s+(?:on|in)\s+discord\b", re.I),
    re.compile(r"\bnotify\s+me\s+(?:on|in)\s+discord\b", re.I),
    re.compile(r"\bhit\s+me\s+(?:on|in)\s+discord\b", re.I),
    re.compile(r"\btell\s+me\b.*\bdiscord\b", re.I | re.S),
    re.compile(r"\bdiscord\b.*\bwhen\s+(?:you'?re|you\s+are)\s+done\b", re.I | re.S),
    re.compile(r"\bwhen\s+(?:you'?re|you\s+are)\s+done\b.*\bdiscord\b", re.I | re.S),
    re.compile(r"\bi'?m\s+stepping\s+away\b", re.I),
    re.compile(r"\bi\s+am\s+stepping\s+away\b", re.I),
)


@dataclass(frozen=True)
class PromptHookResult:
    """Outcome of the prompt-hook evaluation."""

    armed: bool
    """True when Discord away-mode was armed or reused."""

    additional_context: str = ""
    """Model-visible context emitted by the command layer when non-empty."""

    thread_id: str = ""
    """Discord thread id for the armed handoff."""

    debug: str = ""
    """Logged to stderr; never written to stdout."""


@dataclass(frozen=True)
class StopHookResult:
    """Outcome of the stop-hook evaluation."""

    block: bool
    """True → emit {\"decision\":\"block\",\"reason\":...}; False → exit 0."""

    reason: str = ""
    """Populated only when ``block=True``."""

    debug: str = ""
    """Logged to stderr; never written to stdout."""


def run_prompt_hook(
    stdin_data: dict[str, Any],
    client: Any,
    settings: Any,
    env: dict[str, str] | None = None,
    harness: str | None = None,
) -> PromptHookResult:
    """Arm Discord away-mode when the submitted prompt asks for Discord follow-up."""
    del settings  # Kept for the same command-layer shape as ``run_stop_hook``.
    env = env if env is not None else dict(os.environ)
    harness = _normalize_harness(harness or stdin_data.get("harness") or "")

    if env.get("COPILOT_DISCORD_LOOP", "").lower() == "off":
        return PromptHookResult(armed=False, debug="COPILOT_DISCORD_LOOP=off")
    if env.get("COPILOT_SAFETY", "").lower() == "off":
        return PromptHookResult(armed=False, debug="COPILOT_SAFETY=off")

    prompt = _prompt_from_payload(stdin_data)
    hook_cwd = _hook_cwd(stdin_data)
    hook_session_id = _hook_session_id(stdin_data)

    if not should_arm_discord(prompt):
        # Already in away-mode for this cwd? Re-assert the operating contract on
        # every turn so it survives context summarization and arming that did not
        # come through this hook (e.g. a manual `discord handoff`). The bridge —
        # not any project doc — is the single source of truth for how to behave
        # while away-mode is active.
        with suppress(Exception):
            existing = client.active_await_for_cwd(
                hook_cwd, session_id=hook_session_id, harness=harness
            )
            if existing is None:
                existing = _legacy_await_for_cwd(
                    client,
                    cwd=hook_cwd,
                )
            if existing is not None:
                return PromptHookResult(
                    armed=True,
                    additional_context=_armed_context(
                        thread_id=existing["thread_id"],
                        harness=harness,
                        cwd=hook_cwd,
                        created=False,
                        bridge_enabled=bool(
                            existing.get("bridge_enabled") or existing.get("tmux_pane")
                        ),
                    ),
                    thread_id=existing["thread_id"],
                    debug=(
                        f"Discord away-mode context re-asserted for thread={existing['thread_id']}"
                    ),
                )
        return PromptHookResult(armed=False, debug="No Discord away-mode trigger in prompt")

    if _should_auto_start_bridge(env, harness):
        try:
            record = _existing_auto_bridge_for_source(
                client,
                cwd=hook_cwd,
                harness=harness,
                source_session_id=hook_session_id,
            )
            if record is not None and not _inject_bridge_continuation_prompt(record, prompt):
                record = None
            if record is None:
                record = _start_bridge_continuation(
                    client,
                    cwd=hook_cwd,
                    harness=harness,
                    source_session_id=hook_session_id,
                    prompt=prompt,
                )
        except Exception:
            record = None
        if record is not None:
            return PromptHookResult(
                armed=True,
                additional_context=_bridge_continuation_context(record, harness, hook_cwd),
                thread_id=record["thread_id"],
                debug=(f"Discord bridge continuation launched for thread={record['thread_id']}"),
            )

    try:
        record = client.open_handoff_for_cwd(
            hook_cwd,
            session_id=hook_session_id,
            harness=harness,
        )
        # Opportunistic self-healing: close handoffs whose owning session is
        # gone (killed terminal / superseded by /clear), never our own record.
        with suppress(Exception):
            mine = {record["thread_id"]} if record else set()
            client.reap_stale_handoffs(exclude_thread_ids=mine)
        if record is None:
            record = client.start_handoff(
                title=_handoff_title(harness, hook_cwd),
                message=_initial_handoff_message(harness, hook_cwd),
                harness=harness,
                local_session_id=hook_session_id,
                cwd=hook_cwd,
            )
            created = True
        else:
            created = False
            if not record.get("await"):
                _send_best_effort(
                    client,
                    record["thread_id"],
                    _rearm_handoff_message(harness, hook_cwd),
                )
        record = client.set_await(record["thread_id"], True)
        _stamp_bridge_target(record, env)
        client.upsert_handoff(record)
    except Exception as exc:
        return PromptHookResult(
            armed=False,
            debug=f"Failed to arm Discord away-mode: {exc}",
        )

    context = _armed_context(
        thread_id=record["thread_id"],
        harness=harness,
        cwd=hook_cwd,
        created=created,
        bridge_enabled=bool(record.get("bridge_enabled") or record.get("tmux_pane")),
    )
    return PromptHookResult(
        armed=True,
        additional_context=context,
        thread_id=record["thread_id"],
        debug=f"Discord away-mode armed for thread={record['thread_id']}",
    )


def should_arm_discord(prompt: str) -> bool:
    """Return True when a prompt asks the local session to hand off to Discord."""
    if not prompt.strip():
        return False
    return any(pattern.search(prompt) for pattern in _PROMPT_PATTERNS)


def run_stop_hook(
    stdin_data: dict[str, Any],
    client: Any,
    settings: Any,
    env: dict[str, str] | None = None,
    wait_fn: Callable[..., Any] | None = None,
    harness: str | None = None,
) -> StopHookResult:
    """Evaluate the Stop-hook payload and return a continuation decision.

    Parameters
    ----------
    stdin_data:
        The Stop-hook JSON payload parsed from Claude Code stdin.
    client:
        A :class:`~copilot_cli.services.discord.client.DiscordClient` instance.
    settings:
        A settings object with ``discord_wait_timeout: int`` attribute.
    env:
        Environment mapping (defaults to ``os.environ``).  Inject in tests.
    wait_fn:
        ``wait_fn(thread_id, after_msg_id, allowed, timeout) -> DiscordReply``
        Used only when legacy blocking mode is explicitly enabled.
    """
    env = env if env is not None else dict(os.environ)

    # ------------------------------------------------------------------ #
    # 1. Escape hatches — immediate allow-stop                             #
    # ------------------------------------------------------------------ #
    if env.get("COPILOT_DISCORD_LOOP", "").lower() == "off":
        return StopHookResult(block=False, debug="COPILOT_DISCORD_LOOP=off")
    if env.get("COPILOT_SAFETY", "").lower() == "off":
        return StopHookResult(block=False, debug="COPILOT_SAFETY=off")

    # ------------------------------------------------------------------ #
    # 2. Find an active await-handoff for this cwd                         #
    # ------------------------------------------------------------------ #
    hook_cwd = _hook_cwd(stdin_data)
    hook_session_id = _hook_session_id(stdin_data)
    harness = _normalize_harness(harness or stdin_data.get("harness") or "")

    record = client.active_await_for_cwd(
        hook_cwd,
        session_id=hook_session_id,
        harness=harness,
    )
    if record is None:
        record = _active_bridge_for_tmux_pane(client, hook_cwd, harness, env)
    if record is None:
        record = _legacy_await_for_cwd(
            client,
            cwd=hook_cwd,
        )
    if record is None:
        return StopHookResult(
            block=False,
            debug=f"No active await-handoff for cwd={hook_cwd!r}",
        )

    thread_id: str = record["thread_id"]
    after_msg_id: str | None = record.get("last_seen_message_id") or None
    allowed: list[str] | None = record.get("allowed_user_ids") or None

    # Stamp this session live on the in-memory record (fresh owner_pid + stamp)
    # so later upserts in this turn preserve it and the reaper never closes our
    # own handoff. os.getppid() is the harness process that owns this
    # away-session; when the terminal is killed it dies and the record becomes
    # reapable. Then sweep other dead sessions.
    record["owner_pid"] = os.getppid()
    record["updated_at"] = _now_iso()
    _stamp_bridge_target(record, env)
    with suppress(Exception):
        client.upsert_handoff(record)
    with suppress(Exception):
        client.reap_stale_handoffs(exclude_thread_ids={thread_id})

    has_bridge_target = bool(record.get("bridge_enabled") or record.get("tmux_pane"))
    _notify_stopping_point(client, record, stdin_data, harness=harness)

    # Non-blocking by default: never hold the terminal. When a tmux bridge target
    # exists the background worker delivers replies out-of-band (injected into the
    # pane); otherwise this is notify-only — stopping points are posted but replies
    # are not injected. Blocking the Stop event to wait in-process for a reply is
    # opt-in via COPILOT_DISCORD_LEGACY_BLOCKING_WAIT for sessions that want
    # two-way delivery without tmux and accept the held terminal.
    if not _legacy_blocking_wait_enabled(env):
        mode = "bridge" if has_bridge_target else "notify-only"
        return StopHookResult(
            block=False,
            debug=f"Discord {mode} released stop for thread={thread_id}",
        )

    # ------------------------------------------------------------------ #
    # 3. Resolve timeout (env var overrides settings)                      #
    # ------------------------------------------------------------------ #
    timeout_raw = env.get("COPILOT_DISCORD_WAIT_TIMEOUT")
    if timeout_raw is not None:
        try:
            timeout = int(timeout_raw)
        except ValueError:
            timeout = settings.discord_wait_timeout
    else:
        timeout = settings.discord_wait_timeout
    # Default to a 30-minute idle release so an unattended away-session never
    # blocks the Stop event forever waiting for a reply that will not come.
    if timeout <= 0:
        timeout = 1800

    # ------------------------------------------------------------------ #
    # 4. Wait for a Discord reply                                          #
    # ------------------------------------------------------------------ #
    if wait_fn is None:
        wait_fn = _make_default_wait_fn(client)

    try:
        reply = wait_fn(thread_id, after_msg_id, allowed, timeout)
    except Exception:
        _release(client, thread_id)
        return StopHookResult(
            block=False,
            debug=f"Timeout or infra failure for thread={thread_id}",
        )

    # ------------------------------------------------------------------ #
    # 5. Classify the reply                                                #
    # ------------------------------------------------------------------ #
    content_stripped = (reply.content or "").strip()
    client.mark_seen(thread_id, reply.message_id)

    if content_stripped.lower() in TERMINATOR_TOKENS:
        client.clear_await(thread_id)
        _ack_terminator(client, thread_id)
        return StopHookResult(
            block=False,
            debug=f"Terminator token received: {content_stripped!r}",
        )

    framed = _REPLY_FRAME.format(
        username=reply.username,
        thread_id=thread_id,
        content=content_stripped,
    )
    return StopHookResult(block=True, reason=framed)


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #


def _make_default_wait_fn(client: Any) -> Callable[..., Any]:
    """Return a sync callable: Gateway listen with polling fallback."""

    def _wait(
        thread_id: str,
        after_msg_id: str | None,
        allowed: list[str] | None,
        timeout: int,
    ) -> Any:
        try:
            return asyncio.run(
                client.listen_for_reply(
                    thread_id,
                    after_message_id=after_msg_id,
                    allowed_user_ids=allowed,
                    timeout=timeout or 0,
                )
            )
        except Exception:
            # Gateway unavailable — fall back to HTTP polling.
            return client.wait_for_reply(
                thread_id,
                after_message_id=after_msg_id,
                allowed_user_ids=allowed,
                timeout=timeout or 0,
            )

    return _wait


def _legacy_blocking_wait_enabled(env: dict[str, str]) -> bool:
    """Return True only for the opt-in legacy Stop-hook wait loop."""
    return env.get("COPILOT_DISCORD_LEGACY_BLOCKING_WAIT", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _release(client: Any, thread_id: str) -> None:
    """Clear await flag and post an idle notice — best-effort."""
    try:
        client.clear_await(thread_id)
    except Exception:
        pass
    try:
        client.send_message(
            "Session idle — away-mode released. Send a new handoff to resume.",
            thread_id=thread_id,
            prefer_webhook=False,
        )
    except Exception:
        pass


def _ack_terminator(client: Any, thread_id: str) -> None:
    """Post a terminator acknowledgement — best-effort."""
    try:
        client.send_message(
            "Away-mode ended. Control returned to local terminal.",
            thread_id=thread_id,
            prefer_webhook=False,
        )
    except Exception:
        pass


def _notify_stopping_point(
    client: Any,
    record: dict[str, Any],
    stdin_data: dict[str, Any],
    harness: str,
) -> None:
    """Post the latest stopping-point summary once per turn — best-effort."""
    key = _stop_notification_key(stdin_data)
    if record.get("last_notified_stop_key") == key:
        return
    # Cross-process claim: when the same Stop hook is registered at more than one
    # scope (user + project) the harness runs both, and the record-based check
    # above races. Only the process that wins the atomic claim posts.
    claim = getattr(client, "claim_stop_notification", None)
    if callable(claim) and not claim(record["thread_id"], key):
        return
    try:
        # Bot-only: system/control messages must never take the webhook->bot
        # fallback path, which can re-post an identical body when a delivered
        # webhook send is misclassified as an error (429/5xx/read-timeout).
        mentions = _record_mention_user_ids(record)
        message = _stopping_point_message(
            stdin_data,
            harness=harness,
            bridge_enabled=bool(record.get("bridge_enabled") or record.get("tmux_pane")),
        )
        client.send_message(
            _with_mentions(message, mentions),
            thread_id=record["thread_id"],
            prefer_webhook=False,
            mention_user_ids=mentions,
        )
        record["last_notified_stop_key"] = key
        record["updated_at"] = _now_iso()
        client.upsert_handoff(record)
    except Exception:
        pass


def _stop_notification_key(stdin_data: dict[str, Any]) -> str:
    if stdin_data.get("turn_id"):
        return f"turn:{stdin_data['turn_id']}"
    session_id = _hook_session_id(stdin_data) or "no-session"
    message = _assistant_summary(stdin_data, limit=1200)
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
    return f"{session_id}:{digest}"


def _stopping_point_message(stdin_data: dict[str, Any], harness: str, bridge_enabled: bool) -> str:
    label = _harness_label(harness)
    summary = _assistant_summary(stdin_data)
    if not bridge_enabled:
        return (
            f"Local {label} session reached a stopping point (NOT BRIDGED).\n\n"
            f"{summary}\n\n"
            "This thread is notification-only: replies here will NOT reach the "
            f"local {label} terminal. For Discord-controllable work, start a "
            f"bridge session with `{_bridge_launch_command(harness, stdin_data)}`."
        )
    return (
        f"Local {label} session reached a stopping point.\n\n"
        f"{summary}\n\n"
        "Reply here to continue. If this session is attached to tmux, the "
        "background Discord bridge will deliver your reply without blocking "
        "the terminal. Reply /return to end the bridge."
    )


def _record_mention_user_ids(record: dict[str, Any]) -> list[str]:
    values = record.get("allowed_user_ids") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _with_mentions(message: str, user_ids: list[str]) -> str:
    if not user_ids:
        return message
    mentions = " ".join(f"<@{user_id}>" for user_id in user_ids)
    if any(f"<@{user_id}>" in message for user_id in user_ids):
        return message
    return f"{mentions} {message}"


def _assistant_summary(stdin_data: dict[str, Any], limit: int = 1500) -> str:
    raw = (
        stdin_data.get("last_assistant_message")
        or stdin_data.get("last_response")
        or stdin_data.get("message")
        or ""
    )
    text = str(raw).strip()
    if not text:
        return "The local session is waiting for your next instruction."
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n\n[truncated]"


def _prompt_from_payload(stdin_data: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "message", "input"):
        value = stdin_data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _hook_cwd(stdin_data: dict[str, Any]) -> str:
    return str(stdin_data.get("cwd") or os.getcwd())


def _hook_session_id(stdin_data: dict[str, Any]) -> str | None:
    for key in ("session_id", "conversation_id", "thread_id"):
        value = stdin_data.get(key)
        if value:
            return str(value)
    return None


def _stamp_bridge_target(record: dict[str, Any], env: dict[str, str]) -> None:
    """Capture the tmux pane when hooks are running inside tmux."""
    tmux_pane = (env.get("TMUX_PANE") or "").strip()
    if not tmux_pane:
        return
    record["bridge_enabled"] = True
    record["tmux_pane"] = tmux_pane
    record["owner_pid"] = os.getppid()
    record["updated_at"] = _now_iso()


def _should_auto_start_bridge(env: dict[str, str], harness: str) -> bool:
    if env.get("COPILOT_DISCORD_AUTO_BRIDGE", "").lower() == "off":
        return False
    if (env.get("TMUX_PANE") or "").strip():
        return False
    return _normalize_harness(harness) in {"codex", "claude"}


def _existing_auto_bridge_for_source(
    client: Any,
    cwd: str,
    harness: str,
    source_session_id: str | None,
) -> dict[str, Any] | None:
    if not source_session_id:
        return None
    for record in reversed(client.load_handoffs()):
        if (
            record.get("status") == "open"
            and record.get("await") is True
            and record.get("cwd") == cwd
            and record.get("harness") == harness
            and record.get("source_session_id") == source_session_id
            and (record.get("bridge_enabled") or record.get("tmux_pane"))
        ):
            return record
    return None


def _start_bridge_continuation(
    client: Any,
    cwd: str,
    harness: str,
    source_session_id: str | None,
    prompt: str,
) -> dict[str, Any]:
    from copilot_cli.services.discord.bridge import start_tmux_bridge_session

    record = start_tmux_bridge_session(
        client,
        harness=harness,
        title=_bridge_continuation_title(harness, cwd),
        message=_bridge_continuation_message(harness, cwd),
        cwd=cwd,
        initial_prompt=_bridge_continuation_prompt(harness, cwd, prompt),
    )
    if record.get("initial_prompt_delivered") is False:
        with suppress(Exception):
            client.close_handoff(record["thread_id"])
        raise RuntimeError(record.get("initial_prompt_error") or "initial prompt was not delivered")
    record["auto_bridge_continuation"] = True
    record["source_session_id"] = source_session_id or ""
    record["source_cwd"] = cwd
    record["updated_at"] = _now_iso()
    client.upsert_handoff(record)
    return record


def _inject_bridge_continuation_prompt(record: dict[str, Any], prompt: str) -> bool:
    pane = str(record.get("tmux_pane") or "")
    if not pane:
        return False
    try:
        from copilot_cli.services.discord import tmux

        submit_enters = 2 if _normalize_harness(str(record.get("harness") or "")) == "codex" else 1
        tmux.inject_text(
            pane,
            _bridge_continuation_prompt(
                str(record.get("harness") or ""),
                str(record.get("cwd") or os.getcwd()),
                prompt,
            ),
            submit_enters=submit_enters,
        )
        record["last_continuation_injected_at"] = _now_iso()
        return True
    except Exception:
        return False


def _active_bridge_for_tmux_pane(
    client: Any,
    cwd: str,
    harness: str,
    env: dict[str, str],
) -> dict[str, Any] | None:
    tmux_pane = (env.get("TMUX_PANE") or "").strip()
    if not tmux_pane:
        return None
    for record in reversed(client.load_handoffs()):
        if (
            record.get("status") == "open"
            and record.get("await") is True
            and record.get("cwd") == cwd
            and record.get("tmux_pane") == tmux_pane
            and (not harness or record.get("harness") == harness)
        ):
            return record
    return None


def _legacy_await_for_cwd(
    client: Any,
    cwd: str,
) -> dict[str, Any] | None:
    """Return one legacy await thread for cwd when strict lookup cannot.

    Older handoffs, and some handoffs created before harness-specific fixes,
    may have an empty local_session_id or the wrong harness label. Adopting
    exactly one such record keeps existing sessions posting to their thread
    without letting concurrent sessions steal each other.
    """
    candidates = [
        record
        for record in client.load_handoffs()
        if record.get("status") == "open"
        and record.get("await") is True
        and record.get("cwd") == cwd
        and not record.get("local_session_id")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _normalize_harness(harness: str) -> str:
    value = (harness or "").strip().lower()
    if value in {"claude-code", "claude_code"}:
        return "claude"
    if value in {"", "unknown"}:
        return ""
    return value


def _harness_label(harness: str) -> str:
    if harness == "codex":
        return "Codex"
    if harness == "claude":
        return "Claude Code"
    return harness or "assistant"


def _handoff_title(harness: str, cwd: str) -> str:
    project = Path(cwd).name or "session"
    return f"{_harness_label(harness)} away-mode: {project}"[:100]


def _bridge_continuation_title(harness: str, cwd: str) -> str:
    project = Path(cwd).name or "session"
    return f"{_harness_label(harness)} bridge: {project}"[:100]


def _bridge_continuation_message(harness: str, cwd: str) -> str:
    return (
        f"Discord-controllable {_harness_label(harness)} continuation started.\n\n"
        f"Project: `{cwd}`\n\n"
        "Reply in this thread to steer the tmux-backed local session. The "
        "original terminal only launched this continuation; this thread is the "
        "one that can receive replies."
    )


def _bridge_continuation_prompt(harness: str, cwd: str, prompt: str) -> str:
    return (
        f"You are a Discord-controllable {_harness_label(harness)} continuation "
        f"for the local project at {cwd}.\n\n"
        "The user asked from a normal terminal session that cannot receive "
        "Discord replies, so the hook launched this tmux-backed continuation "
        "and delivered the user's instruction here.\n\n"
        f"User instruction:\n{prompt.strip()}\n\n"
        "Continue the work in this bridged session. When you reach a stopping "
        "point, the Stop hook will post status to Discord, and replies in that "
        "thread will be injected back into this session."
    )


def _initial_handoff_message(harness: str, cwd: str) -> str:
    return (
        f"Discord notification-only thread created for this {_harness_label(harness)} session.\n\n"
        f"Project: `{cwd}`\n\n"
        "This terminal was not launched under the tmux bridge, so I can post "
        "stopping points here but Discord replies will NOT reach the local "
        "session. For Discord-controllable work, start with "
        f"`{_bridge_launch_command(harness, {'cwd': cwd})}`."
    )


def _rearm_handoff_message(harness: str, cwd: str) -> str:
    return (
        f"Discord bridge re-armed for this {_harness_label(harness)} session.\n\nProject: `{cwd}`"
    )


def _armed_context(
    thread_id: str,
    harness: str,
    cwd: str,
    created: bool,
    bridge_enabled: bool,
) -> str:
    state = "created" if created else "reused"
    if not bridge_enabled:
        command = _bridge_launch_command(harness, {"cwd": cwd})
        return (
            f"Discord NOT-BRIDGED notification thread {thread_id} is {state} for "
            f"this {_harness_label(harness)} session. The Stop hook will post "
            "updates there, but Discord replies will NOT reach this terminal. "
            "Do not run Discord listen/wait commands. For two-way Discord "
            f"control, start a bridged session with `{command}`."
        )
    return (
        f"Discord bridge is armed ({state} thread {thread_id}) for this "
        f"{_harness_label(harness)} session in {cwd}. Continue the user's task "
        "normally. Do not manually run Discord notify/listen commands. The "
        "Stop hook will post stopping-point status and immediately release the "
        "terminal; the background Discord bridge handles replies."
    )


def _bridge_continuation_context(record: dict[str, Any], harness: str, cwd: str) -> str:
    attach = str(record.get("tmux_attach_command") or "").strip()
    attach_text = f" Local attach command: `{attach}`." if attach else ""
    delivered = (
        "received"
        if record.get("initial_prompt_delivered") is not False
        else "may not have received"
    )
    return (
        f"A Discord-controllable bridge continuation is ready in thread "
        f"{record['thread_id']} for this {_harness_label(harness)} project at {cwd}. "
        f"The user's prompt was {delivered} by the tmux-backed continuation."
        f"{attach_text} This current terminal is only the launcher and is not "
        "the Discord-controllable session. Do not continue the long-running work "
        "here; answer briefly that the bridged continuation is taking over."
    )


def _send_best_effort(client: Any, thread_id: str, message: str) -> None:
    try:
        client.send_message(message, thread_id=thread_id, prefer_webhook=False)
    except Exception:
        pass


def _bridge_launch_command(harness: str, stdin_data: dict[str, Any]) -> str:
    label = _normalize_harness(harness) or "codex"
    if label not in {"codex", "claude"}:
        label = "codex"
    cwd = _hook_cwd(stdin_data)
    return f"copilot discord bridge launch {label} --cwd {shlex.quote(cwd)}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
