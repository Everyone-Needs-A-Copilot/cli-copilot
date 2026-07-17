"""Persistent Discord bridge worker.

The worker listens to Discord once per machine, maps thread messages to local
handoff records, and delivers authorized replies into a registered tmux pane.
The existing Stop hook remains responsible for mirroring clean assistant output.
"""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import shlex
import shutil
import sqlite3
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import websockets

from copilot_cli.services.discord import tmux
from copilot_cli.services.discord.client import (
    DISCORD_GATEWAY_URL,
    DiscordClient,
    DiscordReply,
    close_gateway_for_resume,
    gateway_url_with_query,
    message_to_reply,
)
from copilot_cli.services.discord.hook import TERMINATOR_TOKENS
from copilot_cli.shared.errors import CopilotError, ValidationError

SERVICE = "discord"
LAUNCHD_LABEL = "com.copilot.discord-bridge"


@dataclass(frozen=True)
class BridgeDelivery:
    """Result of attempting to route one Discord message."""

    thread_id: str
    message_id: str
    delivered: bool
    detail: str = ""


class DiscordBridgeStore:
    """Small durable queue for Discord messages awaiting pane delivery."""

    def __init__(self, data_dir: Path):
        self.db_path = data_dir / "bridge.sqlite3"

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queued_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                error TEXT NOT NULL DEFAULT '',
                inserted_at TEXT NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
        return conn

    def enqueue(self, reply: DiscordReply) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO queued_messages (
                    thread_id, message_id, user_id, username, content,
                    created_at, inserted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reply.thread_id,
                    reply.message_id,
                    reply.user_id,
                    reply.username,
                    reply.content,
                    reply.created_at,
                    _now_iso(),
                ),
            )
            conn.commit()

    def queued(self, thread_id: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM queued_messages WHERE status = 'queued'"
        params: tuple[str, ...] = ()
        if thread_id:
            query += " AND thread_id = ?"
            params = (thread_id,)
        query += " ORDER BY id ASC"
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def mark_delivered(self, message_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE queued_messages
                SET status = 'delivered', delivered_at = ?, error = ''
                WHERE message_id = ?
                """,
                (_now_iso(), message_id),
            )
            conn.commit()

    def mark_failed(self, message_id: str, error: str, retry: bool = True) -> None:
        with self.connect() as conn:
            status = "queued" if retry else "failed"
            conn.execute(
                "UPDATE queued_messages SET status = ?, error = ? WHERE message_id = ?",
                (status, error[:500], message_id),
            )
            conn.commit()

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM queued_messages GROUP BY status"
            )
            return {str(row["status"]): int(row["count"]) for row in rows}


class DiscordBridgeWorker:
    """Route Discord Gateway messages to registered local tmux panes."""

    def __init__(
        self,
        client: DiscordClient | None = None,
        store: DiscordBridgeStore | None = None,
    ):
        self.client = client or DiscordClient()
        self.store = store or DiscordBridgeStore(self.client.data_dir)

    def handle_message(self, message: dict[str, Any]) -> BridgeDelivery | None:
        """Queue and deliver one Discord MESSAGE_CREATE payload when relevant."""
        thread_id = str(message.get("channel_id", ""))
        record = self._record_for_thread(thread_id)
        if record is None:
            return None

        reply = message_to_reply(
            message,
            thread_id=thread_id,
            allowed_user_ids=record.get("allowed_user_ids") or None,
            after_message_id=record.get("last_seen_message_id") or None,
        )
        if reply is None:
            return None
        if not reply.content:
            with suppress(Exception):
                full = self.client.get_message(thread_id, reply.message_id)
                reply = message_to_reply(
                    full,
                    thread_id=thread_id,
                    allowed_user_ids=record.get("allowed_user_ids") or None,
                    after_message_id=record.get("last_seen_message_id") or None,
                )
        if reply is None:
            return None

        self.store.enqueue(reply)
        self.client.mark_seen(thread_id, reply.message_id)
        return self.deliver_reply(record, reply)

    def deliver_pending(self) -> list[BridgeDelivery]:
        results: list[BridgeDelivery] = []
        for row in self.store.queued():
            record = self._record_for_thread(str(row["thread_id"]))
            if record is None:
                self.store.mark_failed(
                    str(row["message_id"]),
                    "no open bridge handoff",
                    retry=False,
                )
                continue
            reply = DiscordReply(
                message_id=str(row["message_id"]),
                thread_id=str(row["thread_id"]),
                user_id=str(row["user_id"]),
                username=str(row["username"]),
                content=str(row["content"]),
                created_at=str(row["created_at"]),
            )
            results.append(self.deliver_reply(record, reply))
        return results

    def catch_up_open_threads(self) -> list[BridgeDelivery]:
        """Poll open bridge/await threads for replies missed while offline."""
        results: list[BridgeDelivery] = []
        for record in self._bridge_records():
            thread_id = str(record.get("thread_id") or "")
            if not thread_id:
                continue
            try:
                replies = self.client.get_replies(
                    thread_id,
                    after_message_id=record.get("last_seen_message_id") or None,
                    allowed_user_ids=record.get("allowed_user_ids") or None,
                )
            except Exception:
                continue
            for reply in replies:
                self.store.enqueue(reply)
                self.client.mark_seen(thread_id, reply.message_id)
                record["last_seen_message_id"] = reply.message_id
                results.append(self.deliver_reply(record, reply))
        return results

    def deliver_reply(self, record: dict[str, Any], reply: DiscordReply) -> BridgeDelivery:
        """Deliver a queued reply into the handoff's pane, or retain it queued."""
        if reply.content.strip().lower() in TERMINATOR_TOKENS:
            record["bridge_enabled"] = False
            record["await"] = False
            record["updated_at"] = _now_iso()
            self.client.upsert_handoff(record)
            self.store.mark_delivered(reply.message_id)
            with suppress(Exception):
                self.client.send_message(
                    "Discord bridge ended. Control remains in the local terminal.",
                    thread_id=record["thread_id"],
                    prefer_webhook=False,
                )
            return BridgeDelivery(reply.thread_id, reply.message_id, True, "terminated")

        pane = str(record.get("tmux_pane") or "")
        if not pane:
            if record.get("bridge_enabled"):
                # Bridge is enabled but its pane isn't registered yet — keep the
                # reply queued so it delivers once the pane attaches.
                detail = "no tmux pane registered"
                self.store.mark_failed(reply.message_id, detail, retry=True)
                return BridgeDelivery(reply.thread_id, reply.message_id, False, detail)
            # Notify-only away thread: no bridge intent and no pane, so keystrokes
            # cannot be injected. Warn once instead of silently dropping the reply.
            self._notify_unbridged(record)
            detail = "notify-only: session not bridged (no tmux pane)"
            self.store.mark_failed(reply.message_id, detail, retry=False)
            return BridgeDelivery(reply.thread_id, reply.message_id, False, detail)

        try:
            tmux.inject_text(
                pane,
                _reply_frame(reply, record),
                submit_enters=_submit_enter_count(record),
            )
        except Exception as exc:
            detail = str(exc)
            self.store.mark_failed(reply.message_id, detail)
            return BridgeDelivery(reply.thread_id, reply.message_id, False, detail)

        self.store.mark_delivered(reply.message_id)
        return BridgeDelivery(reply.thread_id, reply.message_id, True, "delivered")

    async def run_forever(self) -> None:
        """Run the Gateway listener until interrupted."""
        self.client.require_bot_token()
        session_id: str | None = None
        resume_url: str | None = None
        seq: int | None = None
        backoff = 1.0
        fatal_close_codes = {4004, 4010, 4011, 4012, 4013, 4014}

        while True:
            can_resume = bool(session_id and resume_url)
            target_url = resume_url if can_resume else DISCORD_GATEWAY_URL
            heartbeat_task: asyncio.Task | None = None
            try:
                self.catch_up_open_threads()
                self.deliver_pending()
                async with websockets.connect(target_url, ping_interval=None) as ws:

                    async def heartbeat(interval_seconds: float) -> None:
                        while True:
                            await asyncio.sleep(interval_seconds)
                            await ws.send(json.dumps({"op": 1, "d": seq}))  # noqa: B023

                    while True:
                        raw = await ws.recv()
                        event = json.loads(raw)
                        if event.get("s") is not None:
                            seq = event["s"]
                        opcode = event.get("op")

                        if opcode == 10:
                            interval = event["d"]["heartbeat_interval"] / 1000
                            heartbeat_task = asyncio.create_task(heartbeat(interval))
                            if can_resume:
                                await ws.send(
                                    json.dumps(
                                        {
                                            "op": 6,
                                            "d": {
                                                "token": self.client.settings.discord_bot_token,
                                                "session_id": session_id,
                                                "seq": seq,
                                            },
                                        }
                                    )
                                )
                            else:
                                await ws.send(json.dumps(self.client._gateway_identify_payload()))
                            continue

                        if opcode == 1:
                            await ws.send(json.dumps({"op": 1, "d": seq}))
                            continue
                        if opcode == 11:
                            continue
                        if opcode == 7:
                            if session_id and resume_url:
                                await close_gateway_for_resume(ws)
                            break
                        if opcode == 9:
                            if bool(event.get("d")) and session_id and resume_url:
                                await close_gateway_for_resume(ws)
                            else:
                                session_id = None
                                resume_url = None
                            await asyncio.sleep(1.0)
                            break
                        if opcode != 0:
                            continue

                        event_type = event.get("t")
                        if event_type == "READY":
                            data = event.get("d") or {}
                            session_id = data.get("session_id")
                            raw_resume = data.get("resume_gateway_url")
                            resume_url = gateway_url_with_query(raw_resume) if raw_resume else None
                            backoff = 1.0
                            continue
                        if event_type == "RESUMED":
                            backoff = 1.0
                            continue
                        if event_type == "MESSAGE_CREATE":
                            self.handle_message(event.get("d") or {})
            except websockets.ConnectionClosed as exc:
                code = getattr(exc, "code", None)
                if code is None:
                    code = getattr(getattr(exc, "rcvd", None), "code", None)
                if code in fatal_close_codes:
                    raise CopilotError(
                        f"Discord Gateway closed with non-recoverable code {code}.",
                        service=SERVICE,
                    ) from exc
                if code in (4007, 4009):
                    session_id = None
                    resume_url = None
            except (websockets.WebSocketException, OSError):
                pass
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task

            await asyncio.sleep(min(backoff, 30.0))
            backoff = min(backoff * 2.0, 30.0)

    def _notify_unbridged(self, record: dict[str, Any]) -> None:
        """Warn once that replies to this un-bridged away thread can't be delivered."""
        if record.get("unbridged_notice_sent"):
            return
        with suppress(Exception):
            self.client.send_message(
                "⚠️ I got your reply, but this session is running outside tmux, so I "
                "can't inject it back into the session — Discord replies only reach "
                "sessions started under the bridge. Launch one with "
                "`copilot discord bridge launch claude` (or `codex`) and reply in that "
                "thread instead. This thread will keep posting stopping points, but "
                "replies here won't be delivered.",
                thread_id=record["thread_id"],
                prefer_webhook=False,
            )
        # Persist the flag on a freshly-loaded record so we don't clobber fields
        # updated earlier this turn (e.g. last_seen_message_id from mark_seen).
        record["unbridged_notice_sent"] = True
        with suppress(Exception):
            current = self.client.get_handoff(record["thread_id"])
            current["unbridged_notice_sent"] = True
            current["updated_at"] = _now_iso()
            self.client.upsert_handoff(current)

    def _record_for_thread(self, thread_id: str) -> dict[str, Any] | None:
        for record in self._bridge_records():
            if record.get("thread_id") == thread_id:
                return record
        return None

    def _bridge_records(self) -> list[dict[str, Any]]:
        # Watch bridged panes AND notify-only await threads. Including await
        # threads lets the worker answer a reply to an un-bridged away session
        # with a guidance notice instead of silently dropping it — the failure
        # mode that left messages unanswered with no feedback.
        return [
            record
            for record in self.client.load_handoffs()
            if record.get("status") == "open"
            and (record.get("bridge_enabled") or record.get("tmux_pane") or record.get("await"))
        ]


def attach_record(
    client: DiscordClient,
    thread_id: str,
    tmux_pane: str | None = None,
    harness: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
    owner_pid: int | None = None,
) -> dict[str, Any]:
    """Register a handoff thread for full-duplex bridge delivery."""
    target = tmux_pane or (tmux.current_target().pane if tmux.current_target() else "")
    if not target:
        raise ValidationError(
            "No tmux pane is available for Discord bridge attach.",
            service=SERVICE,
            hint="Start Claude Code or Codex inside tmux, then run this command again.",
        )
    record = client.get_handoff(thread_id)
    record["bridge_enabled"] = True
    record["tmux_pane"] = target
    record["harness"] = harness or record.get("harness") or ""
    record["local_session_id"] = session_id or record.get("local_session_id") or ""
    record["cwd"] = cwd or record.get("cwd") or os.getcwd()
    record["owner_pid"] = owner_pid or os.getppid()
    record["updated_at"] = _now_iso()
    client.upsert_handoff(record)
    return record


def start_tmux_bridge_session(
    client: DiscordClient,
    harness: str,
    title: str,
    message: str,
    session_name: str | None = None,
    cwd: str | None = None,
    command: list[str] | None = None,
    channel_id: str | None = None,
    allowed_user_ids: list[str] | None = None,
    initial_prompt: str | None = None,
    runner: tmux.Runner | None = None,
) -> dict[str, Any]:
    """Start Claude/Codex in tmux and register its Discord bridge thread."""
    normalized_harness = harness.strip().lower() or "codex"
    working_dir = str(Path(cwd or os.getcwd()).expanduser().resolve())
    launch_command = command or default_harness_command(normalized_harness)
    # Pre-trust the target dir so the launched harness boots straight to its
    # prompt instead of hanging on a first-run trust dialog — otherwise an
    # unattended away-session never sees injected Discord replies.
    ensure_project_trusted(normalized_harness, working_dir)
    tmux_session = tmux.start_session(
        session_name=session_name or default_tmux_session_name(normalized_harness, working_dir),
        cwd=working_dir,
        command=launch_command,
        runner=runner,
    )
    record = client.start_handoff(
        title=title,
        message=message,
        harness=normalized_harness,
        cwd=working_dir,
        channel_id=channel_id,
        allowed_user_ids=allowed_user_ids,
    )
    record["await"] = True
    record["bridge_enabled"] = True
    record["tmux_pane"] = tmux_session.pane
    record["tmux_session"] = tmux_session.name
    record["tmux_attach_command"] = tmux_session.attach_command
    record["local_session_id"] = record.get("local_session_id") or tmux_session.name
    if tmux_session.pane_pid is not None:
        record["owner_pid"] = tmux_session.pane_pid
    record["launch_command"] = shlex.join(launch_command)
    record["updated_at"] = _now_iso()
    client.upsert_handoff(record)
    if initial_prompt:
        try:
            tmux.inject_text(
                tmux_session.pane,
                initial_prompt,
                submit_enters=_submit_enter_count(record),
                runner=runner,
            )
            record["initial_prompt_delivered"] = True
        except Exception as exc:
            record["initial_prompt_delivered"] = False
            record["initial_prompt_error"] = str(exc)
        record["updated_at"] = _now_iso()
        client.upsert_handoff(record)
    return record


def ensure_project_trusted(harness: str, cwd: str) -> bool:
    """Pre-trust a project directory for the given harness.

    A freshly launched Claude/Codex session shows a first-run "do you trust this
    folder?" dialog. Under the bridge that dialog silently swallows the session:
    it never reaches its prompt, and an injected Discord reply can even land on
    the trust menu. Writing the trust flag ahead of launch makes the session boot
    straight to its prompt. Best-effort: returns False without raising if the
    harness is unknown or the config can't be written.
    """
    normalized = harness.strip().lower()
    path = str(Path(cwd).expanduser().resolve())
    if normalized in {"claude", "claude-code", "claude_code"}:
        return _trust_claude_project(path)
    if normalized == "codex":
        return _trust_codex_project(path)
    return False


def _trust_claude_project(path: str) -> bool:
    config = Path.home() / ".claude.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    projects = data.setdefault("projects", {})
    entry = projects.setdefault(path, {})
    if entry.get("hasTrustDialogAccepted") is True:
        return True
    entry["hasTrustDialogAccepted"] = True
    try:
        tmp = config.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(config)
        return True
    except OSError:
        return False


def _trust_codex_project(path: str) -> bool:
    import tomllib

    config = Path.home() / ".codex" / "config.toml"
    try:
        text = config.read_text(encoding="utf-8") if config.exists() else ""
        data = tomllib.loads(text) if text else {}
    except (OSError, ValueError):
        return False
    existing = data.get("projects", {}).get(path)
    if isinstance(existing, dict):
        # Respect an explicit setting the user already made; don't duplicate it.
        return existing.get("trust_level") == "trusted"
    # Append a new section rather than rewriting the file, so comments and
    # formatting in the user's config.toml are preserved.
    prefix = "" if text.endswith("\n") or not text else "\n"
    section = f'{prefix}\n[projects."{path}"]\ntrust_level = "trusted"\n'
    try:
        config.parent.mkdir(parents=True, exist_ok=True)
        with config.open("a", encoding="utf-8") as fh:
            fh.write(section)
        return True
    except OSError:
        return False


def default_harness_command(harness: str) -> list[str]:
    """Return the default local command for a supported assistant harness."""
    normalized = harness.strip().lower()
    if normalized == "codex":
        return ["codex"]
    if normalized in {"claude", "claude-code"}:
        return ["claude"]
    raise ValidationError(
        f"No default Discord bridge command is known for harness {harness!r}.",
        service=SERVICE,
        hint="Pass --command with the assistant command to launch inside tmux.",
    )


def default_tmux_session_name(harness: str, cwd: str) -> str:
    """Build a portable tmux session name from harness and project directory."""
    project = Path(cwd).name or "session"
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    raw = f"copilot-{harness}-{project}-{stamp}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")[:80] or "copilot-discord"


def bridge_status(client: DiscordClient | None = None) -> dict[str, Any]:
    """Return a machine-readable summary of bridge registrations and queue state."""
    client = client or DiscordClient()
    store = DiscordBridgeStore(client.data_dir)
    handoffs = [
        r
        for r in client.load_handoffs()
        if r.get("status") == "open"
        and (r.get("bridge_enabled") or r.get("tmux_pane") or r.get("await"))
    ]
    return {
        "handoffs": handoffs,
        "queue": store.counts(),
        "tmux_available": tmux.tmux_available(),
    }


def install_launch_agent(
    copilot_bin: str | None = None,
    env_file: str | None = None,
    path_env: str | None = None,
    plist_dir: Path | None = None,
) -> Path:
    """Write a launchd plist for the local bridge worker."""
    plist_dir = plist_dir or Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{LAUNCHD_LABEL}.plist"
    env: dict[str, str] = {
        "PATH": path_env or os.environ.get("COPILOT_BRIDGE_PATH") or _launch_path()
    }
    if copilot_bin:
        env["COPILOT_BRIDGE_COPILOT_BIN"] = copilot_bin
    if env_file:
        env["COPILOT_ENV_FILE"] = env_file

    payload: dict[str, Any] = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [
            "/bin/sh",
            "-lc",
            'exec "${COPILOT_BRIDGE_COPILOT_BIN:-copilot}" discord bridge run',
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "copilot-discord-bridge.log"),
        "StandardErrorPath": str(
            Path.home() / "Library" / "Logs" / "copilot-discord-bridge.err.log"
        ),
    }
    if env:
        payload["EnvironmentVariables"] = env
    with plist_path.open("wb") as fh:
        plistlib.dump(payload, fh)
    return plist_path


def launchctl(action: str, plist_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Start or stop the launchd bridge job."""
    uid = os.getuid()
    domain_target = f"gui/{uid}/{LAUNCHD_LABEL}"
    if action == "start":
        plist_path = (
            plist_path or Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        )
        if not plist_path.is_file():
            raise ValidationError(
                f"Launch agent is not installed: {plist_path}",
                service=SERVICE,
                hint="Run 'copilot discord bridge install' first.",
            )
        bootstrap = _run_launchctl(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)])
        if bootstrap.returncode != 0:
            probe = _run_launchctl(["launchctl", "print", domain_target])
            if probe.returncode != 0:
                return bootstrap
        return _run_launchctl(
            ["launchctl", "kickstart", "-k", domain_target],
        )
    if action == "stop":
        return _run_launchctl(["launchctl", "bootout", domain_target])
    raise ValueError("action must be 'start' or 'stop'")


def _run_launchctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "launchctl timed out",
        )


def _launch_path() -> str:
    """Build a small PATH for launchd from discovered tool locations."""
    dirs: list[str] = []
    for tool in ("copilot", "tmux"):
        found = shutil.which(tool)
        if found:
            directory = str(Path(found).parent)
            if directory not in dirs:
                dirs.append(directory)
    for directory in os.defpath.split(os.pathsep):
        if directory and directory not in dirs:
            dirs.append(directory)
    return os.pathsep.join(dirs)


def _reply_frame(reply: DiscordReply, record: dict[str, Any]) -> str:
    label = record.get("harness") or "local harness"
    return (
        f"[Discord bridge] Reply from @{reply.username} "
        f"(thread {reply.thread_id}; target {label}):\n\n"
        f"{reply.content.strip()}\n\n"
        "Continue this same local terminal session with the instruction above."
    )


def _submit_enter_count(record: dict[str, Any]) -> int:
    if str(record.get("harness") or "").strip().lower() == "codex":
        return 2
    return 1


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
