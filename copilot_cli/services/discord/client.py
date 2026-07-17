"""Discord client and foreground handoff registry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import websockets

from copilot_cli.config.settings import Settings, get_settings
from copilot_cli.shared.errors import (
    ConfigError,
    ConnectionError,
    ValidationError,
)
from copilot_cli.shared.errors import (
    TimeoutError as CopilotTimeoutError,
)
from copilot_cli.shared.http_client import api_request, create_client, handle_response

SERVICE = "discord"
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
DISCORD_GATEWAY_QUERY = {"v": "10", "encoding": "json"}
MAX_DISCORD_CONTENT = 1900
GATEWAY_INTENTS = 1 | (1 << 9) | (1 << 15)


@dataclass(frozen=True)
class DiscordReply:
    """A user reply received from a registered Discord handoff thread."""

    message_id: str
    thread_id: str
    user_id: str
    username: str
    content: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "username": self.username,
            "content": self.content,
            "created_at": self.created_at,
        }


class DiscordClient:
    """Small Discord API client for active-session handoffs."""

    def __init__(self, settings: Settings | None = None, data_dir: Path | None = None):
        self.settings = settings or get_settings()
        self._client = create_client(
            DISCORD_API_BASE,
            headers={"Authorization": f"Bot {self.settings.discord_bot_token}"},
            timeout=30.0,
        )
        self.data_dir = (
            data_dir
            or Path(
                os.environ.get("COPILOT_DISCORD_DATA_DIR", "~/.copilot-cli/discord")
            ).expanduser()
        )
        self.registry_path = self.data_dir / "handoffs.json"

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def require_bot_token(self) -> None:
        if not self.settings.discord_bot_token:
            raise ConfigError(
                "DISCORD_BOT_TOKEN is required for Discord handoffs.",
                service=SERVICE,
                hint="Set DISCORD_BOT_TOKEN in your .env.",
            )

    def channel_id(self, override: str | None = None) -> str:
        channel_id = override or self.settings.discord_channel_id
        if not channel_id:
            raise ConfigError(
                "DISCORD_CHANNEL_ID is required.",
                service=SERVICE,
                hint="Set DISCORD_CHANNEL_ID or pass --channel-id.",
            )
        return channel_id

    def allowed_user_ids(self, override: str | None = None) -> list[str]:
        raw = override or self.settings.discord_allowed_user_ids
        return [value.strip() for value in raw.split(",") if value.strip()]

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check Discord API connectivity.

        Confirms a bot token is configured, then pings the Discord API
        using the bot's own identity endpoint -- no channel required.

        Returns:
            Dict with ``healthy`` boolean and additional details.
        """
        if not self.settings.discord_bot_token:
            return {
                "healthy": False,
                "error": "DISCORD_BOT_TOKEN is not configured.",
            }
        try:
            me = api_request(self._client, "GET", "/users/@me", service=SERVICE)
            return {"healthy": True, "username": me.get("username", "")}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Discord API
    # ------------------------------------------------------------------

    def get_channel(self, channel_id: str | None = None) -> dict[str, Any]:
        self.require_bot_token()
        return api_request(
            self._client,
            "GET",
            f"/channels/{self.channel_id(channel_id)}",
            service=SERVICE,
        )

    def create_thread(
        self,
        title: str,
        channel_id: str | None = None,
        auto_archive_duration: int = 1440,
    ) -> dict[str, Any]:
        self.require_bot_token()
        payload = {
            "name": title[:100],
            "type": 11,
            "auto_archive_duration": auto_archive_duration,
        }
        return api_request(
            self._client,
            "POST",
            f"/channels/{self.channel_id(channel_id)}/threads",
            service=SERVICE,
            json=payload,
        )

    def create_thread_from_message(
        self,
        title: str,
        message_id: str,
        channel_id: str | None = None,
        auto_archive_duration: int = 1440,
    ) -> dict[str, Any]:
        self.require_bot_token()
        payload = {
            "name": title[:100],
            "auto_archive_duration": auto_archive_duration,
        }
        return api_request(
            self._client,
            "POST",
            f"/channels/{self.channel_id(channel_id)}/messages/{message_id}/threads",
            service=SERVICE,
            json=payload,
        )

    def add_thread_member(self, thread_id: str, user_id: str) -> None:
        self.require_bot_token()
        api_request(
            self._client,
            "PUT",
            f"/channels/{thread_id}/thread-members/{user_id}",
            service=SERVICE,
        )

    def send_message(
        self,
        content: str,
        channel_id: str | None = None,
        thread_id: str | None = None,
        prefer_webhook: bool = True,
        mention_user_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        target_id = thread_id or self.channel_id(channel_id)
        messages: list[dict[str, Any]] = []
        for chunk in split_discord_content(content):
            if prefer_webhook and self.settings.discord_webhook_url:
                try:
                    messages.append(
                        self._send_webhook(
                            chunk,
                            thread_id=thread_id,
                            mention_user_ids=mention_user_ids,
                        )
                    )
                    continue
                except Exception:
                    # Fall back to bot messages when the webhook cannot post to
                    # the target. The command output still reflects success/fail.
                    pass
            self.require_bot_token()
            messages.append(
                api_request(
                    self._client,
                    "POST",
                    f"/channels/{target_id}/messages",
                    service=SERVICE,
                    json={
                        "content": chunk,
                        "allowed_mentions": _allowed_mentions(mention_user_ids),
                    },
                )
            )
        return messages

    def send_bot_message(
        self,
        content: str,
        channel_id: str | None = None,
        thread_id: str | None = None,
        mention_user_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Send a message with the bot token instead of the configured webhook."""
        target_id = thread_id or self.channel_id(channel_id)
        messages: list[dict[str, Any]] = []
        for chunk in split_discord_content(content):
            self.require_bot_token()
            messages.append(
                api_request(
                    self._client,
                    "POST",
                    f"/channels/{target_id}/messages",
                    service=SERVICE,
                    json={
                        "content": chunk,
                        "allowed_mentions": _allowed_mentions(mention_user_ids),
                    },
                )
            )
        return messages

    def _send_webhook(
        self,
        content: str,
        thread_id: str | None = None,
        mention_user_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"wait": "true"}
        if thread_id:
            params["thread_id"] = thread_id
        payload: dict[str, Any] = {
            "content": content,
            "allowed_mentions": _allowed_mentions(mention_user_ids),
        }
        if self.settings.discord_webhook_username:
            payload["username"] = self.settings.discord_webhook_username
        if self.settings.discord_webhook_avatar_url:
            payload["avatar_url"] = self.settings.discord_webhook_avatar_url

        response = httpx.post(
            self.settings.discord_webhook_url,
            params=params,
            json=payload,
            timeout=30.0,
        )
        return handle_response(response, service=SERVICE)

    def list_thread_messages(
        self,
        thread_id: str,
        after_message_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.require_bot_token()
        params: dict[str, Any] = {"limit": limit}
        if after_message_id:
            params["after"] = after_message_id
        messages = api_request(
            self._client,
            "GET",
            f"/channels/{thread_id}/messages",
            service=SERVICE,
            params=params,
        )
        return sorted(messages, key=lambda msg: int(msg.get("id", "0")))

    def get_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        self.require_bot_token()
        return api_request(
            self._client,
            "GET",
            f"/channels/{channel_id}/messages/{message_id}",
            service=SERVICE,
        )

    def get_replies(
        self,
        thread_id: str,
        after_message_id: str | None = None,
        allowed_user_ids: list[str] | None = None,
    ) -> list[DiscordReply]:
        allowed = set(allowed_user_ids or self.allowed_user_ids())
        replies: list[DiscordReply] = []
        for msg in self.list_thread_messages(thread_id, after_message_id=after_message_id):
            author = msg.get("author") or {}
            user_id = str(author.get("id", ""))
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if author.get("bot"):
                continue
            if allowed and user_id not in allowed:
                continue
            replies.append(
                DiscordReply(
                    message_id=str(msg.get("id", "")),
                    thread_id=thread_id,
                    user_id=user_id,
                    username=str(author.get("username", "")),
                    content=content,
                    created_at=str(msg.get("timestamp", "")),
                )
            )
        return replies

    def wait_for_reply(
        self,
        thread_id: str,
        after_message_id: str | None = None,
        allowed_user_ids: list[str] | None = None,
        timeout: int = 0,
        poll_interval: float = 5.0,
    ) -> DiscordReply:
        started = time.monotonic()
        while True:
            replies = self.get_replies(
                thread_id,
                after_message_id=after_message_id,
                allowed_user_ids=allowed_user_ids,
            )
            if replies:
                return replies[0]
            if timeout and time.monotonic() - started >= timeout:
                raise CopilotTimeoutError(
                    f"No authorized Discord reply received within {timeout}s.",
                    service=SERVICE,
                )
            time.sleep(poll_interval)

    async def listen_for_reply(
        self,
        thread_id: str,
        after_message_id: str | None = None,
        allowed_user_ids: list[str] | None = None,
        timeout: int = 0,
    ) -> DiscordReply:
        """Listen for the next authorized reply through Discord Gateway events.

        Holds a persistent connection across Discord's routine control frames
        instead of exiting on each one: on Op 7 (Reconnect) it reconnects and
        RESUMEs the session, and on Op 9 (Invalid Session) it re-identifies
        after a short backoff. Transient socket drops are retried with
        exponential backoff (resuming when possible). Non-recoverable gateway
        close codes (e.g. authentication failure) are raised, not retried.
        """
        self.require_bot_token()
        allowed = allowed_user_ids or self.allowed_user_ids()

        # Fatal gateway close codes that must not be retried.
        fatal_close_codes = {4004, 4010, 4011, 4012, 4013, 4014}

        session_id: str | None = None
        resume_url: str | None = None
        seq: int | None = None

        async def run() -> DiscordReply:
            nonlocal session_id, resume_url, seq
            backoff = 1.0

            while True:
                can_resume = bool(session_id and resume_url)
                target_url = resume_url if can_resume else DISCORD_GATEWAY_URL
                heartbeat_task: asyncio.Task | None = None
                try:
                    async with websockets.connect(target_url, ping_interval=None) as ws:

                        async def heartbeat(interval_seconds: float) -> None:
                            while True:
                                await asyncio.sleep(interval_seconds)
                                # Intentional late binding: always send the latest seq.
                                await ws.send(json.dumps({"op": 1, "d": seq}))  # noqa: B023

                        while True:
                            raw = await ws.recv()
                            event = json.loads(raw)
                            if event.get("s") is not None:
                                seq = event["s"]
                            opcode = event.get("op")

                            if opcode == 10:  # Hello -> resume or identify
                                interval = event["d"]["heartbeat_interval"] / 1000
                                heartbeat_task = asyncio.create_task(heartbeat(interval))
                                if can_resume:
                                    await ws.send(
                                        json.dumps(
                                            {
                                                "op": 6,  # Resume
                                                "d": {
                                                    "token": self.settings.discord_bot_token,
                                                    "session_id": session_id,
                                                    "seq": seq,
                                                },
                                            }
                                        )
                                    )
                                else:
                                    await ws.send(json.dumps(self._gateway_identify_payload()))
                                continue

                            if opcode == 1:  # Server-requested heartbeat
                                await ws.send(json.dumps({"op": 1, "d": seq}))
                                continue

                            if opcode == 11:  # Heartbeat ACK
                                continue

                            if opcode == 7:  # Reconnect -> resume on a fresh socket
                                if session_id and resume_url:
                                    await close_gateway_for_resume(ws)
                                break

                            if opcode == 9:  # Invalid Session
                                if bool(event.get("d")) and session_id and resume_url:
                                    await close_gateway_for_resume(ws)
                                else:  # not resumable
                                    session_id = None
                                    resume_url = None
                                await asyncio.sleep(random.uniform(1.0, 5.0))
                                break

                            if opcode != 0:
                                continue

                            event_type = event.get("t")
                            if event_type == "READY":
                                data = event.get("d") or {}
                                session_id = data.get("session_id")
                                raw_resume = data.get("resume_gateway_url")
                                if raw_resume:
                                    resume_url = gateway_url_with_query(raw_resume)
                                backoff = 1.0
                                continue
                            if event_type == "RESUMED":
                                backoff = 1.0
                                continue
                            if event_type != "MESSAGE_CREATE":
                                continue

                            message = event.get("d") or {}
                            reply = message_to_reply(
                                message,
                                thread_id=thread_id,
                                allowed_user_ids=allowed,
                                after_message_id=after_message_id,
                            )
                            if reply:
                                if not reply.content:
                                    message = self.get_message(thread_id, reply.message_id)
                                    reply = message_to_reply(
                                        message,
                                        thread_id=thread_id,
                                        allowed_user_ids=allowed,
                                        after_message_id=after_message_id,
                                    )
                                if reply:
                                    return reply
                except websockets.ConnectionClosed as exc:
                    code = getattr(exc, "code", None)
                    if code is None:
                        code = getattr(getattr(exc, "rcvd", None), "code", None)
                    if code in fatal_close_codes:
                        raise ConnectionError(
                            f"Discord Gateway closed with non-recoverable code {code}.",
                            service=SERVICE,
                        ) from exc
                    if code in (4007, 4009):  # bad seq / session timed out -> fresh session
                        session_id = None
                        resume_url = None
                    await asyncio.sleep(min(backoff, 30.0))
                    backoff = min(backoff * 2.0, 30.0)
                except (websockets.WebSocketException, OSError):
                    await asyncio.sleep(min(backoff, 30.0))
                    backoff = min(backoff * 2.0, 30.0)
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await heartbeat_task

        try:
            if timeout:
                return await asyncio.wait_for(run(), timeout=timeout)
            return await run()
        except TimeoutError as exc:
            raise CopilotTimeoutError(
                f"No authorized Discord reply received within {timeout}s.",
                service=SERVICE,
            ) from exc

    def _gateway_identify_payload(self) -> dict[str, Any]:
        return {
            "op": 2,
            "d": {
                "token": self.settings.discord_bot_token,
                "intents": GATEWAY_INTENTS,
                "properties": {
                    "os": "macos",
                    "browser": "cli-copilot",
                    "device": "cli-copilot",
                },
            },
        }

    # ------------------------------------------------------------------
    # Handoff registry
    # ------------------------------------------------------------------

    def start_handoff(
        self,
        title: str,
        message: str,
        harness: str | None = None,
        local_session_id: str | None = None,
        cwd: str | None = None,
        agent_slug: str = "lead-cto",
        channel_id: str | None = None,
        allowed_user_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        starter_messages = self.send_bot_message(message, channel_id=channel_id)
        starter_message_id = str(starter_messages[-1].get("id", "")) if starter_messages else ""
        thread = self.create_thread_from_message(
            title=title,
            message_id=starter_message_id,
            channel_id=channel_id,
        )
        thread_id = str(thread["id"])
        allowed = allowed_user_ids or self.allowed_user_ids()
        member_add_errors: list[dict[str, str]] = []
        for user_id in allowed:
            try:
                self.add_thread_member(thread_id, user_id)
            except Exception as exc:
                member_add_errors.append({"user_id": user_id, "error": str(exc)})
        record = {
            "thread_id": thread_id,
            "channel_id": self.channel_id(channel_id),
            "starter_message_id": starter_message_id,
            "title": title,
            "harness": harness or "",
            "local_session_id": local_session_id or "",
            "cwd": cwd or os.getcwd(),
            "agent_slug": agent_slug,
            "allowed_user_ids": allowed,
            "member_add_errors": member_add_errors,
            "status": "open",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "last_seen_message_id": starter_message_id,
        }
        self.upsert_handoff(record)
        return record

    def load_handoffs(self) -> list[dict[str, Any]]:
        if not self.registry_path.is_file():
            return []
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"Discord handoff registry is not valid JSON: {self.registry_path}",
                service=SERVICE,
            ) from exc
        return data.get("handoffs", [])

    def save_handoffs(self, handoffs: list[dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {"handoffs": handoffs}
        tmp = self.registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.registry_path)

    def upsert_handoff(self, record: dict[str, Any]) -> None:
        handoffs = self.load_handoffs()
        thread_id = record["thread_id"]
        updated = False
        for index, existing in enumerate(handoffs):
            if existing.get("thread_id") == thread_id:
                handoffs[index] = record
                updated = True
                break
        if not updated:
            handoffs.append(record)
        self.save_handoffs(handoffs)

    def get_handoff(self, thread_id: str) -> dict[str, Any]:
        for record in self.load_handoffs():
            if record.get("thread_id") == thread_id:
                return record
        raise ValidationError(
            f"No Discord handoff is registered for thread {thread_id}.",
            service=SERVICE,
        )

    def claim_stop_notification(self, thread_id: str, key: str) -> bool:
        """Atomically claim the right to post one stopping-point notification.

        Returns ``True`` for exactly one caller per ``(thread_id, key)`` even
        across concurrent processes, and ``False`` for every later caller. Uses
        an ``O_EXCL`` file create as a cross-process lock so duplicate Stop-hook
        registrations (e.g. the same hook installed at both user and project
        scope, which the harness runs together) can never double-post — the
        record-based ``last_notified_stop_key`` check races and cannot.
        """
        digest = hashlib.sha256(f"{thread_id}:{key}".encode()).hexdigest()[:32]
        lock_dir = self.data_dir / "stop-locks"
        marker = lock_dir / f"{digest}.lock"
        try:
            lock_dir.mkdir(parents=True, exist_ok=True)
            self._prune_stop_locks(lock_dir)
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        except OSError:
            # Filesystem unavailable — fail open so a real turn is never silenced.
            return True
        os.close(fd)
        return True

    @staticmethod
    def _prune_stop_locks(lock_dir: Path, max_age_seconds: int = 21600) -> None:
        """Remove stale stop-notification lock files (older than 6h)."""
        cutoff = time.time() - max_age_seconds
        with suppress(OSError):
            for marker in lock_dir.glob("*.lock"):
                with suppress(OSError):
                    if marker.stat().st_mtime < cutoff:
                        marker.unlink()

    def mark_seen(self, thread_id: str, message_id: str) -> dict[str, Any]:
        record = self.get_handoff(thread_id)
        record["last_seen_message_id"] = message_id
        record["updated_at"] = now_iso()
        self.upsert_handoff(record)
        return record

    def close_handoff(self, thread_id: str) -> dict[str, Any]:
        record = self.get_handoff(thread_id)
        record["status"] = "closed"
        record["await"] = False
        record["updated_at"] = now_iso()
        self.upsert_handoff(record)
        return record

    def reap_stale_handoffs(
        self, exclude_thread_ids: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """Close open await-handoffs whose owning session is gone.

        Runs opportunistically from the hooks (no daemon). Returns the records
        that were reaped. ``exclude_thread_ids`` protects the caller's own live
        handoff from a between-turns false positive.
        """
        exclude = exclude_thread_ids or set()
        handoffs = self.load_handoffs()
        reaped: list[dict[str, Any]] = []
        for record in handoffs:
            if record.get("thread_id") in exclude:
                continue
            if is_stale_await(record):
                record["status"] = "closed"
                record["await"] = False
                record["closed_reason"] = "stale-owner"
                record["updated_at"] = now_iso()
                reaped.append(record)
        if reaped:
            self.save_handoffs(handoffs)
        return reaped

    def open_handoffs(self) -> list[dict[str, Any]]:
        return [record for record in self.load_handoffs() if record.get("status") == "open"]

    def set_await(self, thread_id: str, on: bool) -> dict[str, Any]:
        """Set the ``await`` flag on a handoff record."""
        record = self.get_handoff(thread_id)
        record["await"] = on
        record["updated_at"] = now_iso()
        self.upsert_handoff(record)
        return record

    def clear_await(self, thread_id: str) -> dict[str, Any]:
        """Clear the ``await`` flag on a handoff record."""
        return self.set_await(thread_id, False)

    def active_await_for_cwd(
        self,
        cwd: str,
        session_id: str | None = None,
        harness: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the first open handoff with ``await=True`` whose ``cwd`` matches.

        When ``session_id`` is given, prefers an exact ``local_session_id``
        match.  Returns ``None`` when no matching await-handoff is found.
        """
        candidates = [
            r
            for r in self.load_handoffs()
            if r.get("await") is True
            and r.get("status") == "open"
            and r.get("cwd") == cwd
            and (not harness or r.get("harness") == harness)
        ]
        if not candidates:
            return None
        if session_id:
            exact = [r for r in candidates if r.get("local_session_id") == session_id]
            if exact:
                return exact[0]
            # Remaining threads for this cwd belong to other live sessions —
            # never adopt another session's handoff. Only fall through for
            # legacy records that carry no session id at all.
            if any(r.get("local_session_id") for r in candidates):
                return None
        return candidates[0]

    def open_handoff_for_cwd(
        self,
        cwd: str,
        session_id: str | None = None,
        harness: str | None = None,
    ) -> dict[str, Any] | None:
        """Return an open handoff for this cwd/session/harness, if one exists."""
        candidates = [
            r
            for r in self.load_handoffs()
            if r.get("status") == "open"
            and r.get("cwd") == cwd
            and (not harness or r.get("harness") == harness)
        ]
        if not candidates:
            return None
        if session_id:
            exact = [r for r in candidates if r.get("local_session_id") == session_id]
            if exact:
                return exact[-1]
            # Other live sessions own the remaining threads for this cwd; do not
            # reuse them. Legacy session-less records still fall through.
            if any(r.get("local_session_id") for r in candidates):
                return None
        return candidates[-1]


def gateway_url_with_query(raw_url: str) -> str:
    """Attach the pinned Gateway query params to a Discord Gateway URL."""
    parts = urlsplit(raw_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(DISCORD_GATEWAY_QUERY)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )


async def close_gateway_for_resume(ws: Any) -> None:
    """Close without invalidating the resumable Discord Gateway session."""
    await ws.close(code=4000, reason="resume")


def split_discord_content(content: str) -> list[str]:
    """Split content into Discord-safe message chunks."""
    text = content or " "
    if len(text) <= MAX_DISCORD_CONTENT:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        chunk = remaining[:MAX_DISCORD_CONTENT]
        split_at = max(chunk.rfind("\n"), chunk.rfind(" "))
        if split_at > 400:
            chunk = chunk[:split_at]
        chunks.append(chunk)
        remaining = remaining[len(chunk) :].lstrip()
    return chunks


def _allowed_mentions(user_ids: list[str] | None = None) -> dict[str, Any]:
    cleaned = [str(user_id).strip() for user_id in user_ids or [] if str(user_id).strip()]
    if not cleaned:
        return {"parse": []}
    return {"users": cleaned}


def message_to_reply(
    message: dict[str, Any],
    thread_id: str,
    allowed_user_ids: list[str] | None = None,
    after_message_id: str | None = None,
) -> DiscordReply | None:
    """Convert a Discord message payload to an authorized handoff reply."""
    if str(message.get("channel_id", "")) != str(thread_id):
        return None
    message_id = str(message.get("id", ""))
    if after_message_id and int(message_id or "0") <= int(after_message_id):
        return None

    author = message.get("author") or {}
    user_id = str(author.get("id", ""))
    if author.get("bot"):
        return None
    if allowed_user_ids and user_id not in set(allowed_user_ids):
        return None

    content = str(message.get("content", "")).strip()
    return DiscordReply(
        message_id=message_id,
        thread_id=str(thread_id),
        user_id=user_id,
        username=str(author.get("username", "")),
        content=content,
        created_at=str(message.get("timestamp", "")),
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
# Staleness reaping                                                            #
# --------------------------------------------------------------------------- #
# A live away-session's Stop hook refreshes ``owner_pid`` + ``updated_at`` every
# turn and keeps its owner process alive while parked on the Gateway wait. So a
# record is reaped only when its owner process is gone AND it has been idle past
# a short grace window (covers the brief between-turns gap where the previous
# hook wrapper has exited but the session is mid-turn). Records with no
# ``owner_pid`` (legacy / pre-reaper) fall back to a long idle backstop equal to
# the Stop-hook timeout, so a genuine weekend-long wait is never reaped.
STALE_GRACE_SECONDS = 900  # 15 min
PIDLESS_BACKSTOP_SECONDS = 604800  # 7 days (matches install STOP_TIMEOUT_SECONDS)


def _pid_alive(pid: int) -> bool:
    """Best-effort POSIX liveness check for a process id."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but is owned by another user
    except OSError:
        return False
    return True


def _age_seconds(iso_ts: str | None) -> float:
    """Seconds since an ISO-8601 timestamp; ``inf`` when missing/unparseable."""
    if not iso_ts:
        return float("inf")
    try:
        ts = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds()


def is_stale_await(record: dict[str, Any]) -> bool:
    """True when an open await-handoff's owning session is gone.

    Liveness, not idleness: an alive owner process (even one parked on a
    multi-day Gateway wait) is never stale. Only a dead owner past the grace
    window, or a legacy pid-less record past the long backstop, is reaped.
    """
    if record.get("status") != "open" or not record.get("await"):
        return False
    owner_pid = record.get("owner_pid")
    age = _age_seconds(record.get("updated_at"))
    if owner_pid:
        if _pid_alive(int(owner_pid)):
            return False
        return age > STALE_GRACE_SECONDS
    return age > PIDLESS_BACKSTOP_SECONDS
