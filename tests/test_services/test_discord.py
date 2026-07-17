"""Unit tests for Discord handoff integration."""

from __future__ import annotations

import json
import os
import plistlib
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import copilot_cli.services.discord.client as discord_client_module
from copilot_cli.services.discord import tmux as discord_tmux
from copilot_cli.services.discord.bridge import (
    DiscordBridgeStore,
    DiscordBridgeWorker,
    attach_record,
    bridge_status,
    default_harness_command,
    install_launch_agent,
    start_tmux_bridge_session,
)
from copilot_cli.services.discord.client import (
    DISCORD_GATEWAY_URL,
    PIDLESS_BACKSTOP_SECONDS,
    STALE_GRACE_SECONDS,
    DiscordClient,
    DiscordReply,
    gateway_url_with_query,
    is_stale_await,
    message_to_reply,
    split_discord_content,
)
from copilot_cli.services.discord.commands import app as discord_app
from copilot_cli.services.discord.hook import (
    TERMINATOR_TOKENS,
    StopHookResult,
    run_prompt_hook,
    run_stop_hook,
    should_arm_discord,
)
from copilot_cli.services.discord.install import (
    install_hooks,
    install_stop_hook,
    uninstall_hooks,
    uninstall_stop_hook,
)

# ---------------------------------------------------------------------- #
# Shared helpers                                                           #
# ---------------------------------------------------------------------- #


def _settings(**overrides):
    defaults = {
        "discord_bot_token": "bot-token",
        "discord_webhook_url": "",
        "discord_channel_id": "200000000000000002",
        "discord_allowed_user_ids": "100000000000000001",
        "discord_webhook_username": "",
        "discord_webhook_avatar_url": "",
        "discord_wait_timeout": 30,
        "discord_await_default": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _json_response(status_code: int, payload):
    response = MagicMock()
    response.is_success = 200 <= status_code < 300
    response.status_code = status_code
    response.headers = {"content-type": "application/json"}
    response.json.return_value = payload
    response.text = ""
    return response


def _fake_reply(content="ship it", message_id="101", username="testuser", thread_id="thread-1"):
    """Return a DiscordReply-like SimpleNamespace."""
    return SimpleNamespace(
        content=content,
        message_id=message_id,
        thread_id=thread_id,
        username=username,
        user_id="100000000000000001",
        created_at="2026-06-29T10:00:00Z",
    )


@pytest.fixture
def discord(tmp_path):
    client = DiscordClient(settings=_settings(), data_dir=tmp_path)
    client._client = MagicMock()
    return client


@pytest.fixture
def discord_with_await(tmp_path):
    """DiscordClient with an active await-handoff pre-seeded."""
    client = DiscordClient(settings=_settings(), data_dir=tmp_path)
    client._client = MagicMock()
    client.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Test session",
                "harness": "claude",
                "local_session_id": "sess-abc",
                "cwd": "/tmp/project",
                "agent_slug": "lead-cto",
                "allowed_user_ids": ["100000000000000001"],
                "member_add_errors": [],
                "status": "open",
                "await": True,
                "last_seen_message_id": "100",
                "created_at": "2026-06-29T10:00:00Z",
                "updated_at": "2026-06-29T10:00:00Z",
            }
        ]
    )
    return client


# ---------------------------------------------------------------------- #
# Existing tests (preserved)                                               #
# ---------------------------------------------------------------------- #


def test_start_handoff_creates_thread_posts_message_and_records_mapping(discord):
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "I will report back here."}),
        _json_response(200, {"id": "200", "name": "Session thread"}),
        _json_response(204, ""),
    ]

    record = discord.start_handoff(
        title="Session thread",
        message="I will report back here.",
        harness="codex",
        local_session_id="codex-1",
        cwd="/tmp/project",
    )

    assert record["thread_id"] == "200"
    assert record["channel_id"] == "200000000000000002"
    assert record["starter_message_id"] == "100"
    assert record["harness"] == "codex"
    assert record["local_session_id"] == "codex-1"
    assert record["allowed_user_ids"] == ["100000000000000001"]
    assert record["member_add_errors"] == []
    assert record["last_seen_message_id"] == "100"
    assert discord.get_handoff("200")["cwd"] == "/tmp/project"

    calls = discord._client.request.call_args_list
    assert calls[0].args[:2] == ("POST", "/channels/200000000000000002/messages")
    assert calls[1].args[:2] == (
        "POST",
        "/channels/200000000000000002/messages/100/threads",
    )
    assert calls[2].args[:2] == (
        "PUT",
        "/channels/200/thread-members/100000000000000001",
    )


def test_send_message_can_explicitly_mention_allowed_user(discord):
    discord._client.request.return_value = _json_response(200, {"id": "999"})

    discord.send_message(
        "Done <@100000000000000001>",
        thread_id="thread-1",
        prefer_webhook=False,
        mention_user_ids=["100000000000000001"],
    )

    call = discord._client.request.call_args
    assert call.args[:2] == ("POST", "/channels/thread-1/messages")
    assert call.kwargs["json"]["allowed_mentions"] == {"users": ["100000000000000001"]}


def test_notify_cli_mentions_allowed_user_by_default(discord, monkeypatch):
    discord._client.request.return_value = _json_response(200, {"id": "999"})
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["notify", "Done", "--thread-id", "thread-1"])

    assert result.exit_code == 0
    payload = discord._client.request.call_args.kwargs["json"]
    assert payload["content"].startswith("<@100000000000000001> Done")
    assert payload["allowed_mentions"] == {"users": ["100000000000000001"]}


def test_notify_cli_can_suppress_mentions(discord, monkeypatch):
    discord._client.request.return_value = _json_response(200, {"id": "999"})
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(
        discord_app,
        ["notify", "Done", "--thread-id", "thread-1", "--no-mention"],
    )

    assert result.exit_code == 0
    payload = discord._client.request.call_args.kwargs["json"]
    assert payload["content"] == "Done"
    assert payload["allowed_mentions"] == {"parse": []}


def test_notify_cli_without_thread_refuses_parent_channel_post(discord, monkeypatch):
    discord._client.request.return_value = _json_response(200, {"id": "999"})
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["notify", "Done"])

    assert result.exit_code == 1
    assert "Refusing to post a Discord notification without a thread" in result.output
    assert "copilot discord handoff" in result.output
    discord._client.request.assert_not_called()


def test_notify_cli_without_thread_reuses_only_open_handoff_for_cwd(
    discord,
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Existing session",
                "harness": "claude",
                "local_session_id": "sess-abc",
                "cwd": str(tmp_path),
                "status": "open",
                "await": False,
                "allowed_user_ids": ["100000000000000001"],
            }
        ]
    )
    discord._client.request.return_value = _json_response(200, {"id": "999"})
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["notify", "Done", "--no-mention"])

    assert result.exit_code == 0
    assert discord._client.request.call_args.args[:2] == ("POST", "/channels/thread-1/messages")


def test_notify_cli_without_thread_refuses_ambiguous_handoffs_for_cwd(
    discord,
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "cwd": str(tmp_path),
                "status": "open",
                "await": False,
            },
            {
                "thread_id": "thread-2",
                "cwd": str(tmp_path),
                "status": "open",
                "await": False,
            },
        ]
    )
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["notify", "Done"])

    assert result.exit_code == 1
    assert "without a thread" in result.output
    discord._client.request.assert_not_called()


def test_notify_cli_refuses_explicit_channel_without_thread(discord, monkeypatch):
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(
        discord_app,
        ["notify", "Done", "--channel-id", "200000000000000002"],
    )

    assert result.exit_code == 1
    assert "directly to a parent channel" in result.output
    discord._client.request.assert_not_called()


def _armed_handoff(thread_id: str = "thread-1") -> dict:
    return {
        "thread_id": thread_id,
        "channel_id": "200000000000000002",
        "starter_message_id": "100",
        "title": "Away session",
        "harness": "claude",
        "local_session_id": "sess-abc",
        "cwd": "/tmp/project",
        "status": "open",
        "await": True,
        "last_seen_message_id": "100",
    }


def test_notify_skips_when_away_mode_armed(discord, monkeypatch):
    discord.save_handoffs([_armed_handoff()])
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["notify", "Update", "--thread-id", "thread-1"])

    # The Stop hook already mirrors each turn, so a manual notify is refused to
    # prevent a duplicate post — nothing hits the Discord API.
    assert result.exit_code == 0
    discord._client.request.assert_not_called()


def test_notify_force_posts_even_when_away_mode_armed(discord, monkeypatch):
    discord.save_handoffs([_armed_handoff()])
    discord._client.request.return_value = _json_response(200, {"id": "999"})
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(
        discord_app,
        ["notify", "Update", "--thread-id", "thread-1", "--no-mention", "--force"],
    )

    assert result.exit_code == 0
    assert discord._client.request.call_args.args[:2] == ("POST", "/channels/thread-1/messages")


def test_get_replies_filters_to_allowed_human_users_and_sorts(discord):
    discord._client.request.return_value = _json_response(
        200,
        [
            {
                "id": "12",
                "content": "bot note",
                "timestamp": "2026-06-27T12:00:02Z",
                "author": {"id": "bot", "username": "CTO", "bot": True},
            },
            {
                "id": "10",
                "content": "push to GitHub",
                "timestamp": "2026-06-27T12:00:00Z",
                "author": {"id": "100000000000000001", "username": "testuser"},
            },
            {
                "id": "11",
                "content": "ignore me",
                "timestamp": "2026-06-27T12:00:01Z",
                "author": {"id": "someone-else", "username": "other"},
            },
        ],
    )

    replies = discord.get_replies("200", allowed_user_ids=["100000000000000001"])

    assert [reply.message_id for reply in replies] == ["10"]
    assert replies[0].content == "push to GitHub"
    assert replies[0].user_id == "100000000000000001"


def test_mark_seen_updates_only_the_matching_thread(discord):
    discord.save_handoffs(
        [
            {"thread_id": "a", "last_seen_message_id": "1", "status": "open"},
            {"thread_id": "b", "last_seen_message_id": "2", "status": "open"},
        ]
    )

    discord.mark_seen("b", "99")

    assert discord.get_handoff("a")["last_seen_message_id"] == "1"
    assert discord.get_handoff("b")["last_seen_message_id"] == "99"


def test_ack_command_marks_reply_seen(monkeypatch, discord):
    discord.save_handoffs(
        [{"thread_id": "thread-1", "last_seen_message_id": "100", "status": "open"}]
    )
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["ack", "thread-1", "123"])

    assert result.exit_code == 0
    assert discord.get_handoff("thread-1")["last_seen_message_id"] == "123"
    assert "123" in result.output


def test_hook_command_outputs_prompt_additional_context(monkeypatch, discord):
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Away mode armed"}),
        _json_response(200, {"id": "200", "name": "Codex away-mode"}),
        _json_response(204, ""),
    ]
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(
        discord_app,
        ["hook", "user-prompt-submit", "--harness", "codex"],
        input=json.dumps(
            {
                "cwd": "/tmp/project",
                "session_id": "sess-1",
                "prompt": "Let me know on Discord when this is done.",
            }
        ),
    )

    assert result.exit_code == 0
    payload, _ = json.JSONDecoder().raw_decode(result.output)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "thread 200" in payload["hookSpecificOutput"]["additionalContext"]


def test_split_discord_content_keeps_chunks_under_limit():
    chunks = split_discord_content("x" * 4500)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1900 for chunk in chunks)


def test_message_to_reply_accepts_authorized_thread_message_after_seen_id():
    reply = message_to_reply(
        {
            "id": "101",
            "channel_id": "thread-1",
            "content": "push to GitHub",
            "timestamp": "2026-06-27T12:00:00Z",
            "author": {"id": "100000000000000001", "username": "testuser"},
        },
        thread_id="thread-1",
        allowed_user_ids=["100000000000000001"],
        after_message_id="100",
    )

    assert reply is not None
    assert reply.content == "push to GitHub"
    assert reply.message_id == "101"


@pytest.mark.parametrize(
    ("message", "allowed", "after"),
    [
        (
            {
                "id": "101",
                "channel_id": "other-thread",
                "content": "wrong place",
                "author": {"id": "100000000000000001"},
            },
            ["100000000000000001"],
            "100",
        ),
        (
            {
                "id": "101",
                "channel_id": "thread-1",
                "content": "wrong user",
                "author": {"id": "someone-else"},
            },
            ["100000000000000001"],
            "100",
        ),
        (
            {
                "id": "101",
                "channel_id": "thread-1",
                "content": "bot",
                "author": {"id": "bot", "bot": True},
            },
            ["100000000000000001"],
            "100",
        ),
        (
            {
                "id": "99",
                "channel_id": "thread-1",
                "content": "old",
                "author": {"id": "100000000000000001"},
            },
            ["100000000000000001"],
            "100",
        ),
    ],
)
def test_message_to_reply_filters_non_matching_gateway_messages(message, allowed, after):
    assert (
        message_to_reply(
            message,
            thread_id="thread-1",
            allowed_user_ids=allowed,
            after_message_id=after,
        )
        is None
    )


class FakeGatewaySocket:
    def __init__(self, events):
        self.events = list(events)
        self.sent = []
        self.close_calls = []

    async def recv(self):
        if not self.events:
            raise AssertionError("No fake Gateway events left")
        return json.dumps(self.events.pop(0))

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def close(self, code=1000, reason=""):
        self.close_calls.append({"code": code, "reason": reason})


class FakeGatewayConnect:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc_value, traceback):
        if not self.socket.close_calls:
            await self.socket.close()


@pytest.mark.asyncio
async def test_listen_resumes_after_gateway_reconnect_without_normal_close(discord, monkeypatch):
    resume_base = "wss://resume.discord.example"
    resume_url = gateway_url_with_query(resume_base)
    first_socket = FakeGatewaySocket(
        [
            {"op": 10, "d": {"heartbeat_interval": 999999}},
            {
                "op": 0,
                "t": "READY",
                "s": 41,
                "d": {
                    "session_id": "session-1",
                    "resume_gateway_url": resume_base,
                },
            },
            {"op": 7, "d": None},
        ]
    )
    second_socket = FakeGatewaySocket(
        [
            {"op": 10, "d": {"heartbeat_interval": 999999}},
            {"op": 0, "t": "RESUMED", "s": 42, "d": {}},
            {
                "op": 0,
                "t": "MESSAGE_CREATE",
                "s": 43,
                "d": {
                    "id": "101",
                    "channel_id": "thread-1",
                    "content": "ship it",
                    "timestamp": "2026-06-28T12:00:00Z",
                    "author": {"id": "100000000000000001", "username": "testuser"},
                },
            },
        ]
    )
    sockets = [first_socket, second_socket]
    urls = []

    def fake_connect(url, ping_interval=None):
        urls.append(url)
        assert ping_interval is None
        return FakeGatewayConnect(sockets.pop(0))

    monkeypatch.setattr(discord_client_module.websockets, "connect", fake_connect)

    reply = await discord.listen_for_reply(
        "thread-1",
        after_message_id="100",
        allowed_user_ids=["100000000000000001"],
        timeout=1,
    )

    assert reply.content == "ship it"
    assert urls == [DISCORD_GATEWAY_URL, resume_url]
    assert first_socket.close_calls == [{"code": 4000, "reason": "resume"}]
    assert second_socket.sent[0]["op"] == 6
    assert second_socket.sent[0]["d"] == {
        "token": "bot-token",
        "session_id": "session-1",
        "seq": 41,
    }


# ---------------------------------------------------------------------- #
# Client registry helpers — set_await / clear_await / active_await_for_cwd
# ---------------------------------------------------------------------- #


def test_set_await_marks_record(discord):
    discord.save_handoffs(
        [{"thread_id": "t1", "status": "open", "cwd": "/proj", "last_seen_message_id": "50"}]
    )

    record = discord.set_await("t1", True)

    assert record["await"] is True
    assert discord.get_handoff("t1")["await"] is True


def test_clear_await_removes_flag(discord):
    discord.save_handoffs([{"thread_id": "t1", "status": "open", "cwd": "/proj", "await": True}])

    record = discord.clear_await("t1")

    assert record["await"] is False
    assert discord.get_handoff("t1")["await"] is False


def test_active_await_for_cwd_returns_matching_record(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "t1",
                "status": "open",
                "cwd": "/proj",
                "await": True,
                "local_session_id": "",
            }
        ]
    )

    record = discord.active_await_for_cwd("/proj")

    assert record is not None
    assert record["thread_id"] == "t1"


def test_active_await_for_cwd_returns_none_when_no_match(discord):
    discord.save_handoffs([{"thread_id": "t1", "status": "open", "cwd": "/other", "await": True}])

    assert discord.active_await_for_cwd("/proj") is None


def test_active_await_for_cwd_ignores_closed_handoffs(discord):
    discord.save_handoffs([{"thread_id": "t1", "status": "closed", "cwd": "/proj", "await": True}])

    assert discord.active_await_for_cwd("/proj") is None


def test_active_await_for_cwd_ignores_non_await_handoffs(discord):
    discord.save_handoffs([{"thread_id": "t1", "status": "open", "cwd": "/proj", "await": False}])

    assert discord.active_await_for_cwd("/proj") is None


def test_active_await_for_cwd_prefers_session_id_match(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "t1",
                "status": "open",
                "cwd": "/proj",
                "await": True,
                "local_session_id": "other-sess",
            },
            {
                "thread_id": "t2",
                "status": "open",
                "cwd": "/proj",
                "await": True,
                "local_session_id": "my-sess",
            },
        ]
    )

    record = discord.active_await_for_cwd("/proj", session_id="my-sess")

    assert record["thread_id"] == "t2"


def test_active_await_for_cwd_can_filter_by_harness(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "claude-thread",
                "status": "open",
                "cwd": "/proj",
                "await": True,
                "harness": "claude",
            },
            {
                "thread_id": "codex-thread",
                "status": "open",
                "cwd": "/proj",
                "await": True,
                "harness": "codex",
            },
        ]
    )

    record = discord.active_await_for_cwd("/proj", harness="codex")

    assert record["thread_id"] == "codex-thread"


def test_open_handoff_for_cwd_finds_reusable_session_thread(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "old-thread",
                "status": "open",
                "cwd": "/proj",
                "harness": "codex",
                "local_session_id": "old",
            },
            {
                "thread_id": "session-thread",
                "status": "open",
                "cwd": "/proj",
                "harness": "codex",
                "local_session_id": "sess-1",
            },
        ]
    )

    record = discord.open_handoff_for_cwd("/proj", session_id="sess-1", harness="codex")

    assert record["thread_id"] == "session-thread"


# ---------------------------------------------------------------------- #
# run_prompt_hook — arm Discord away-mode                                  #
# ---------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt",
    [
        "Let me know on Discord when this is done.",
        "notify me in Discord",
        "hit me on Discord",
        "I'm stepping away for the day.",
        "When you're done, tell me in Discord.",
    ],
)
def test_should_arm_discord_detects_handoff_phrases(prompt):
    assert should_arm_discord(prompt) is True


def test_should_arm_discord_ignores_unrelated_prompt():
    assert should_arm_discord("Run the focused tests and summarize here.") is False


def test_prompt_hook_auto_launches_bridge_continuation_outside_tmux(discord, monkeypatch):
    captured: dict[str, str] = {}

    def _start_bridge(client, **kwargs):
        captured.update(
            {
                "harness": kwargs["harness"],
                "title": kwargs["title"],
                "message": kwargs["message"],
                "cwd": kwargs["cwd"],
                "initial_prompt": kwargs["initial_prompt"],
            }
        )
        record = {
            "thread_id": "bridge-thread",
            "channel_id": "200000000000000002",
            "starter_message_id": "100",
            "title": kwargs["title"],
            "harness": kwargs["harness"],
            "local_session_id": "copilot-codex-project",
            "cwd": kwargs["cwd"],
            "status": "open",
            "await": True,
            "bridge_enabled": True,
            "tmux_pane": "%42",
            "tmux_attach_command": "tmux attach -t copilot-codex-project",
            "initial_prompt_delivered": True,
        }
        client.upsert_handoff(record)
        return record

    monkeypatch.setattr(
        "copilot_cli.services.discord.bridge.start_tmux_bridge_session",
        _start_bridge,
    )

    result = run_prompt_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "codex-sess",
            "prompt": "Please finish this and let me know on Discord.",
        },
        client=discord,
        settings=_settings(),
        env={},
        harness="codex",
    )

    assert result.armed is True
    assert result.thread_id == "bridge-thread"
    assert "Discord-controllable bridge continuation is ready" in result.additional_context
    assert "tmux attach -t copilot-codex-project" in result.additional_context
    assert "only the launcher" in result.additional_context
    assert captured["harness"] == "codex"
    assert captured["cwd"] == "/tmp/project"
    assert "Codex bridge: project" == captured["title"]
    assert "Please finish this and let me know on Discord." in captured["initial_prompt"]
    assert "tmux-backed continuation" in captured["initial_prompt"]
    assert discord._client.request.call_count == 0

    stored = discord.get_handoff("bridge-thread")
    assert stored["auto_bridge_continuation"] is True
    assert stored["source_session_id"] == "codex-sess"
    assert stored["bridge_enabled"] is True
    assert stored["tmux_pane"] == "%42"


def test_prompt_hook_falls_back_to_notify_only_when_auto_bridge_fails(discord, monkeypatch):
    def _bridge_unavailable(*_args, **_kwargs):
        raise RuntimeError("tmux unavailable")

    monkeypatch.setattr(
        "copilot_cli.services.discord.bridge.start_tmux_bridge_session",
        _bridge_unavailable,
    )
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Away mode armed"}),
        _json_response(200, {"id": "200", "name": "Codex away-mode"}),
        _json_response(204, ""),
    ]

    result = run_prompt_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "codex-sess",
            "prompt": "Please finish this and let me know on Discord.",
        },
        client=discord,
        settings=_settings(),
        env={},
        harness="codex",
    )

    assert result.armed is True
    assert result.thread_id == "200"
    assert "Discord NOT-BRIDGED notification thread 200 is created" in result.additional_context
    assert "Discord replies will NOT reach this terminal" in result.additional_context
    assert "Do not run Discord listen/wait commands" in result.additional_context
    assert "copilot discord bridge launch codex --cwd /tmp/project" in result.additional_context
    assert "bridge launch claude" not in result.additional_context

    stored = discord.get_handoff("200")
    assert stored["await"] is True
    assert stored["harness"] == "codex"
    assert stored["local_session_id"] == "codex-sess"
    assert stored.get("bridge_enabled") is not True
    assert not stored.get("tmux_pane")


def test_prompt_hook_reuses_open_handoff_for_same_session(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Existing session",
                "harness": "claude",
                "local_session_id": "sess-abc",
                "cwd": "/tmp/project",
                "status": "open",
                "await": False,
                "last_seen_message_id": "100",
            }
        ]
    )
    discord._client.request.return_value = _json_response(200, {"id": "999"})

    result = run_prompt_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "prompt": "I'm stepping away. Please tell me in Discord.",
        },
        client=discord,
        settings=_settings(),
        env={"COPILOT_DISCORD_AUTO_BRIDGE": "off"},
        harness="claude",
    )

    assert result.armed is True
    assert result.thread_id == "thread-1"
    assert discord.get_handoff("thread-1")["await"] is True
    assert discord._client.request.call_args.args[:2] == ("POST", "/channels/thread-1/messages")


def test_prompt_hook_allows_when_no_trigger(discord):
    result = run_prompt_hook(
        {"cwd": "/tmp/project", "prompt": "Keep going and report here."},
        client=discord,
        settings=_settings(),
        env={},
        harness="codex",
    )

    assert result.armed is False
    assert discord.load_handoffs() == []


def test_prompt_hook_reasserts_context_while_armed_without_trigger(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Existing session",
                "harness": "claude",
                "local_session_id": "sess-abc",
                "cwd": "/tmp/project",
                "status": "open",
                "await": True,
                "last_seen_message_id": "100",
            }
        ]
    )

    result = run_prompt_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "prompt": "Keep going and add the tests.",
        },
        client=discord,
        settings=_settings(),
        env={},
        harness="claude",
    )

    # No trigger phrase, but away-mode is armed → the contract is re-asserted so
    # it stays in-window every turn, and nothing is posted to Discord.
    assert result.armed is True
    assert result.thread_id == "thread-1"
    assert "Discord NOT-BRIDGED notification thread thread-1 is reused" in result.additional_context
    assert "Do not run Discord listen/wait commands" in result.additional_context
    discord._client.request.assert_not_called()


def test_prompt_hook_reasserts_single_legacy_await_even_when_harness_label_differs(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "legacy-thread",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Legacy session",
                "harness": "codex",
                "local_session_id": "",
                "cwd": "/tmp/project",
                "status": "open",
                "await": True,
                "last_seen_message_id": "100",
            }
        ]
    )

    result = run_prompt_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "claude-sess",
            "prompt": "Keep going and finish the review.",
        },
        client=discord,
        settings=_settings(),
        env={},
        harness="claude",
    )

    assert result.armed is True
    assert result.thread_id == "legacy-thread"
    assert "Discord NOT-BRIDGED notification thread legacy-thread is reused" in (
        result.additional_context
    )
    discord._client.request.assert_not_called()


# ---------------------------------------------------------------------- #
# run_stop_hook — core loop brain                                          #
# ---------------------------------------------------------------------- #


def test_stop_hook_without_bridge_is_non_blocking_notify_only(discord_with_await):
    """Non-tmux away-mode never blocks the terminal by default.

    The Stop hook posts one stopping-point mirror and releases; it does not wait
    for or inject replies (that is the tmux bridge's job). Blocking is opt-in.
    """
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

    def _must_not_wait(*_):
        raise AssertionError("default Stop hook must not block waiting for a reply")

    result = run_stop_hook(
        {"cwd": "/tmp/project", "session_id": "sess-abc", "last_assistant_message": "Done."},
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=_must_not_wait,
    )

    assert result.block is False
    assert "notify-only released" in result.debug

    # Exactly one stopping-point mirror is posted (no duplicate tmux nag).
    posts = [
        call
        for call in discord_with_await._client.request.call_args_list
        if call.args[:2] == ("POST", "/channels/thread-1/messages")
    ]
    assert len(posts) == 1
    assert posts[0].kwargs["json"]["content"].startswith("<@100000000000000001>")


def test_stop_hook_posts_to_single_legacy_await_even_when_harness_label_differs(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "legacy-thread",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Legacy session",
                "harness": "codex",
                "local_session_id": "",
                "cwd": "/tmp/project",
                "status": "open",
                "await": True,
                "last_seen_message_id": "100",
                "allowed_user_ids": ["100000000000000001"],
            }
        ]
    )
    discord._client.request.return_value = _json_response(200, {"id": "999"})

    result = run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "claude-sess",
            "turn_id": "turn-legacy",
            "last_assistant_message": "Done from Claude.",
        },
        client=discord,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )

    assert result.block is False
    assert "notify-only released" in result.debug
    call = discord._client.request.call_args
    assert call.args[:2] == ("POST", "/channels/legacy-thread/messages")
    assert "Local Claude Code session reached a stopping point" in call.kwargs["json"]["content"]
    assert "Done from Claude." in call.kwargs["json"]["content"]


def test_stop_hook_does_not_adopt_ambiguous_legacy_awaits(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "legacy-one",
                "cwd": "/tmp/project",
                "status": "open",
                "await": True,
                "local_session_id": "",
            },
            {
                "thread_id": "legacy-two",
                "cwd": "/tmp/project",
                "status": "open",
                "await": True,
                "local_session_id": "",
            },
        ]
    )

    result = run_stop_hook(
        {"cwd": "/tmp/project", "session_id": "claude-sess", "last_assistant_message": "Done."},
        client=discord,
        settings=_settings(),
        env={},
        harness="claude",
    )

    assert result.block is False
    assert "No active await-handoff" in result.debug
    discord._client.request.assert_not_called()


def test_claim_stop_notification_is_exclusive(discord):
    """The atomic claim returns True once per (thread, key), False thereafter."""
    assert discord.claim_stop_notification("thread-1", "turn-1") is True
    assert discord.claim_stop_notification("thread-1", "turn-1") is False
    # A different turn or thread is independently claimable.
    assert discord.claim_stop_notification("thread-1", "turn-2") is True
    assert discord.claim_stop_notification("thread-2", "turn-1") is True


def test_stop_hook_claim_prevents_duplicate_posts_across_processes(discord_with_await):
    """Two Stop-hook invocations for the same turn post the mirror only once.

    Simulates the same hook installed at user + project scope both firing: the
    atomic claim lets exactly one of them post.
    """
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})
    payload = {
        "cwd": "/tmp/project",
        "session_id": "sess-abc",
        "turn_id": "turn-xyz",
        "last_assistant_message": "Same turn output.",
    }
    reply = _fake_reply(content="ok", thread_id="thread-1")

    for _ in range(2):
        discord_with_await.set_await("thread-1", True)
        run_stop_hook(
            payload,
            client=discord_with_await,
            settings=_settings(),
            env={},
            wait_fn=lambda *_: reply,
        )

    posts = [
        call
        for call in discord_with_await._client.request.call_args_list
        if call.args[:2] == ("POST", "/channels/thread-1/messages")
    ]
    assert len(posts) == 1


def test_stop_hook_legacy_blocking_wait_is_explicit_opt_in(discord_with_await):
    """The old parked Stop-hook loop exists only behind an explicit env flag."""
    reply = _fake_reply(content="push to staging", username="testuser", thread_id="thread-1")
    wait_fn = lambda *_: reply  # noqa: E731

    result = run_stop_hook(
        {"cwd": "/tmp/project", "session_id": "sess-abc"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on"},
        wait_fn=wait_fn,
    )

    assert result.block is True
    assert "@testuser" in result.reason
    assert "push to staging" in result.reason
    assert "thread-1" in result.reason


def test_stop_hook_allows_stop_when_no_await_handoff(discord):
    """No await-handoff for this cwd → allow stop (core guard)."""
    result = run_stop_hook(
        {"cwd": "/no/such/project"},
        client=discord,
        settings=_settings(),
        env={},
    )

    assert result.block is False


def test_stop_hook_terminator_token_clears_await_and_allows_stop(discord_with_await):
    """Reply is /return → clear await, allow stop."""
    for token in TERMINATOR_TOKENS:
        # Reset await flag for each token
        discord_with_await.set_await("thread-1", True)
        # Suppress the send_message call (no HTTP mock)
        discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

        reply = _fake_reply(content=token, thread_id="thread-1")
        wait_fn = lambda *_, _r=reply: _r  # noqa: E731

        result = run_stop_hook(
            {"cwd": "/tmp/project"},
            client=discord_with_await,
            settings=_settings(),
            env={"COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on"},
            wait_fn=wait_fn,
        )

        assert result.block is False, f"Expected allow-stop for token {token!r}"
        assert discord_with_await.get_handoff("thread-1")["await"] is False


def test_stop_hook_timeout_releases_gracefully(discord_with_await):
    """Wait timeout → clear await, post idle notice, allow stop."""
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

    def _timeout_wait(*_):
        from copilot_cli.shared.errors import TimeoutError as CopilotTimeoutError

        raise CopilotTimeoutError("timed out", service="discord")

    result = run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on"},
        wait_fn=_timeout_wait,
    )

    assert result.block is False
    assert discord_with_await.get_handoff("thread-1")["await"] is False


def test_stop_hook_escape_hatch_discord_loop_off(discord_with_await):
    """COPILOT_DISCORD_LOOP=off → immediate allow-stop, wait_fn never called."""
    called = []

    def _should_not_be_called(*_):
        called.append(True)
        raise AssertionError("wait_fn must not be called when loop is off")

    result = run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_DISCORD_LOOP": "off"},
        wait_fn=_should_not_be_called,
    )

    assert result.block is False
    assert not called


def test_stop_hook_escape_hatch_safety_off(discord_with_await):
    """COPILOT_SAFETY=off → immediate allow-stop."""
    result = run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_SAFETY": "off"},
    )

    assert result.block is False


def test_stop_hook_env_timeout_override(discord_with_await):
    """COPILOT_DISCORD_WAIT_TIMEOUT env var overrides settings.discord_wait_timeout."""
    captured_timeout = []

    def _capture_timeout(thread_id, after_msg_id, allowed, timeout):
        captured_timeout.append(timeout)
        return _fake_reply()

    run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(discord_wait_timeout=1800),
        env={
            "COPILOT_DISCORD_WAIT_TIMEOUT": "120",
            "COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on",
        },
        wait_fn=_capture_timeout,
    )

    assert captured_timeout == [120]


def test_stop_hook_infra_failure_allows_stop(discord_with_await):
    """Any exception from wait_fn → release and allow stop."""
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

    def _boom(*_):
        raise ConnectionError("network down")

    result = run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on"},
        wait_fn=_boom,
    )

    assert result.block is False


def test_stop_hook_legacy_wait_marks_message_seen_on_normal_reply(discord_with_await):
    """After delivering a reply, last_seen_message_id is updated."""
    reply = _fake_reply(content="do the thing", message_id="202")
    wait_fn = lambda *_: reply  # noqa: E731

    run_stop_hook(
        {"cwd": "/tmp/project"},
        client=discord_with_await,
        settings=_settings(),
        env={"COPILOT_DISCORD_LEGACY_BLOCKING_WAIT": "on"},
        wait_fn=wait_fn,
    )

    assert discord_with_await.get_handoff("thread-1")["last_seen_message_id"] == "202"


def test_stop_hook_posts_stopping_point_before_releasing(discord_with_await):
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})
    run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "turn_id": "turn-1",
            "last_assistant_message": "Done with tests. Two files changed.",
        },
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )

    call = discord_with_await._client.request.call_args_list[0]
    assert call.args[:2] == ("POST", "/channels/thread-1/messages")
    content = call.kwargs["json"]["content"]
    assert "Local Claude Code session reached a stopping point (NOT BRIDGED)." in content
    assert "Done with tests. Two files changed." in content


def test_stop_hook_labels_notify_only_stopping_point_as_not_bridged(discord_with_await):
    record = discord_with_await.get_handoff("thread-1")
    record["harness"] = "codex"
    discord_with_await.upsert_handoff(record)
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

    run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "turn_id": "turn-not-bridged",
            "last_assistant_message": "Done.",
        },
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="codex",
    )

    content = discord_with_await._client.request.call_args_list[0].kwargs["json"]["content"]
    assert "Local Codex session reached a stopping point (NOT BRIDGED)." in content
    assert "replies here will NOT reach the local Codex terminal" in content
    assert "copilot discord bridge launch codex --cwd /tmp/project" in content


def test_doctor_flags_live_await_without_bridge_as_not_bridged(discord, monkeypatch):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "await": True,
                "owner_pid": os.getpid(),
                "harness": "codex",
                "cwd": "/tmp/project",
                "updated_at": "2026-07-02T10:00:00Z",
            }
        ]
    )
    monkeypatch.setattr("copilot_cli.services.discord.commands._client", lambda: discord)

    result = CliRunner().invoke(discord_app, ["doctor"])

    assert result.exit_code == 0
    assert "NOT-BRIDGED" in result.output
    assert "notify-only" in result.output
    assert "0 bridged, 1 not-bridged" in result.output
    assert "Discord replies will not reach Codex/Claude" in result.output


def test_stop_hook_does_not_duplicate_stopping_point_for_same_turn(discord_with_await):
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})
    payload = {
        "cwd": "/tmp/project",
        "session_id": "sess-abc",
        "turn_id": "turn-1",
        "last_assistant_message": "Done.",
    }

    run_stop_hook(
        payload,
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )
    discord_with_await._client.request.reset_mock()

    run_stop_hook(
        payload,
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )

    discord_with_await._client.request.assert_not_called()


def test_stop_hook_stopping_point_is_bot_only_even_with_webhook_configured(tmp_path, monkeypatch):
    """Regression (double-post): the stopping-point message must never use the
    webhook->bot fallback in send_message. With a webhook configured, a delivered
    webhook send that is misclassified as an error (429/5xx/read-timeout) would
    be re-posted verbatim via the bot. System/control messages go bot-only.
    """
    settings = _settings(discord_webhook_url="https://discord.test/webhook")
    client = DiscordClient(settings=settings, data_dir=tmp_path)
    client._client = MagicMock()
    client._client.request.return_value = _json_response(200, {"id": "999"})
    client.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "channel_id": "200000000000000002",
                "starter_message_id": "100",
                "title": "Test session",
                "harness": "claude",
                "local_session_id": "sess-abc",
                "cwd": "/tmp/project",
                "allowed_user_ids": ["100000000000000001"],
                "status": "open",
                "await": True,
                "last_seen_message_id": "100",
                "created_at": "2026-06-29T10:00:00Z",
                "updated_at": "2026-06-29T10:00:00Z",
            }
        ]
    )

    webhook_calls: list = []
    monkeypatch.setattr(
        discord_client_module.httpx,
        "post",
        lambda *a, **k: webhook_calls.append((a, k)) or _json_response(200, {"id": "wh"}),
    )

    run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "turn_id": "turn-1",
            "last_assistant_message": "Done.",
        },
        client=client,
        settings=settings,
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )

    # The webhook must never be used for the system stopping-point message.
    assert webhook_calls == []
    # And the stopping-point body is posted exactly once via the bot endpoint.
    stop_posts = [
        call
        for call in client._client.request.call_args_list
        if call.args[:2] == ("POST", "/channels/thread-1/messages")
        and "reached a stopping point" in call.kwargs["json"]["content"]
    ]
    assert len(stop_posts) == 1


# ---------------------------------------------------------------------- #
# staleness reaping (liveness, not idleness)                               #
# ---------------------------------------------------------------------- #

_DEAD_PID = 2_000_000_000  # a pid that will not be alive on this machine


def _iso_ago(seconds: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def test_live_owner_is_never_stale_even_after_days_of_waiting():
    # The whole point of away-mode: a session parked for a weekend on a Discord
    # wait keeps its owner process alive, so it must never be reaped.
    rec = {
        "status": "open",
        "await": True,
        "owner_pid": os.getpid(),
        "updated_at": _iso_ago(3 * 24 * 3600),
    }
    assert is_stale_await(rec) is False


def test_dead_owner_past_grace_is_stale():
    rec = {
        "status": "open",
        "await": True,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(STALE_GRACE_SECONDS + 60),
    }
    assert is_stale_await(rec) is True


def test_dead_owner_within_grace_is_not_stale():
    # Between-turns window: previous hook wrapper exited but the session is
    # mid-turn; a fresh timestamp protects it from a false reap.
    rec = {
        "status": "open",
        "await": True,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(10),
    }
    assert is_stale_await(rec) is False


def test_pidless_record_uses_long_backstop():
    recent = {"status": "open", "await": True, "updated_at": _iso_ago(3600)}
    ancient = {
        "status": "open",
        "await": True,
        "updated_at": _iso_ago(PIDLESS_BACKSTOP_SECONDS + 3600),
    }
    assert is_stale_await(recent) is False
    assert is_stale_await(ancient) is True


def test_closed_or_non_await_records_are_never_stale():
    closed = {
        "status": "closed",
        "await": True,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(1e6),
    }
    not_await = {
        "status": "open",
        "await": False,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(1e6),
    }
    assert is_stale_await(closed) is False
    assert is_stale_await(not_await) is False


def test_reap_closes_dead_sessions_and_respects_exclude(discord):
    dead = {
        "thread_id": "t-dead",
        "status": "open",
        "await": True,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(STALE_GRACE_SECONDS + 60),
        "cwd": "/a",
    }
    live = {
        "thread_id": "t-live",
        "status": "open",
        "await": True,
        "owner_pid": os.getpid(),
        "updated_at": _iso_ago(1e6),
        "cwd": "/b",
    }
    mine = {
        "thread_id": "t-mine",
        "status": "open",
        "await": True,
        "owner_pid": _DEAD_PID,
        "updated_at": _iso_ago(STALE_GRACE_SECONDS + 60),
        "cwd": "/c",
    }
    discord.save_handoffs([dead, live, mine])

    reaped = discord.reap_stale_handoffs(exclude_thread_ids={"t-mine"})

    assert {r["thread_id"] for r in reaped} == {"t-dead"}
    after = {r["thread_id"]: r for r in discord.load_handoffs()}
    assert after["t-dead"]["status"] == "closed"
    assert after["t-dead"]["await"] is False
    assert after["t-dead"]["closed_reason"] == "stale-owner"
    assert after["t-live"]["status"] == "open"  # alive owner untouched
    assert after["t-mine"]["status"] == "open"  # excluded (caller's own record)


def test_active_await_uses_strict_session_scoping(discord):
    # Three concurrent sessions on the SAME codebase each own a distinct thread.
    a = {
        "thread_id": "t-a",
        "status": "open",
        "await": True,
        "cwd": "/repo",
        "harness": "claude",
        "local_session_id": "sess-A",
        "updated_at": _iso_ago(1),
    }
    b = {
        "thread_id": "t-b",
        "status": "open",
        "await": True,
        "cwd": "/repo",
        "harness": "claude",
        "local_session_id": "sess-B",
        "updated_at": _iso_ago(1),
    }
    discord.save_handoffs([a, b])

    # Each session sees only its own thread...
    assert (
        discord.active_await_for_cwd("/repo", session_id="sess-A", harness="claude")["thread_id"]
        == "t-a"
    )
    assert (
        discord.active_await_for_cwd("/repo", session_id="sess-B", harness="claude")["thread_id"]
        == "t-b"
    )
    # ...and a brand-new session never steals a sibling's thread (forces new handoff).
    assert discord.active_await_for_cwd("/repo", session_id="sess-NEW", harness="claude") is None


def test_stop_hook_stamps_owner_pid(discord_with_await):
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})
    run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "turn_id": "turn-x",
            "last_assistant_message": "Done.",
        },
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="claude",
    )
    rec = discord_with_await.get_handoff("thread-1")
    assert rec.get("owner_pid") == os.getppid()


# ---------------------------------------------------------------------- #
# bridge mode (non-blocking tmux delivery)                                #
# ---------------------------------------------------------------------- #


def test_tmux_inject_text_can_send_multiple_submit_enters(monkeypatch):
    monkeypatch.setattr("copilot_cli.services.discord.tmux.tmux_available", lambda: True)
    calls: list[tuple[list[str], str | None]] = []

    def _runner(args, input=None, **_kwargs):
        calls.append((args, input))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    discord_tmux.inject_text("%7", "hello", runner=_runner, submit_enters=2)

    assert calls[0] == (["tmux", "load-buffer", "-b", "copilot-discord-bridge", "-"], "hello")
    assert calls[1] == (["tmux", "paste-buffer", "-b", "copilot-discord-bridge", "-t", "%7"], None)
    assert calls[2:] == [
        (["tmux", "send-keys", "-t", "%7", "Enter"], None),
        (["tmux", "send-keys", "-t", "%7", "Enter"], None),
    ]


def test_prompt_hook_inside_tmux_registers_bridge_target(discord):
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Starting"}),
        _json_response(200, {"id": "200", "name": "Session"}),
        _json_response(204, ""),
        _json_response(200, {"id": "999"}),
    ]

    result = run_prompt_hook(
        {"cwd": "/tmp/project", "session_id": "sess-abc", "prompt": "let me know on Discord"},
        client=discord,
        settings=_settings(),
        env={"TMUX_PANE": "%7"},
        harness="claude",
    )

    assert result.armed is True
    stored = discord.get_handoff("200")
    assert stored["bridge_enabled"] is True
    assert stored["tmux_pane"] == "%7"
    assert stored["harness"] == "claude"


def test_stop_hook_releases_terminal_when_bridge_target_registered(discord_with_await):
    record = discord_with_await.get_handoff("thread-1")
    record["bridge_enabled"] = True
    record["tmux_pane"] = "%7"
    discord_with_await.upsert_handoff(record)
    discord_with_await._client.request.return_value = _json_response(200, {"id": "999"})

    def _should_not_wait(*_):
        raise AssertionError("bridge mode must not block on Discord wait")

    result = run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "sess-abc",
            "turn_id": "turn-bridge",
            "last_assistant_message": "Done.",
        },
        client=discord_with_await,
        settings=_settings(),
        env={},
        wait_fn=_should_not_wait,
        harness="claude",
    )

    assert result.block is False
    assert "released stop" in result.debug
    stop_posts = [
        call
        for call in discord_with_await._client.request.call_args_list
        if call.args[:2] == ("POST", "/channels/thread-1/messages")
    ]
    assert stop_posts, "bridge mode still mirrors the stopping point"


def test_stop_hook_matches_bridge_record_by_tmux_pane_when_session_id_differs(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "await": True,
                "bridge_enabled": True,
                "tmux_pane": "%7",
                "harness": "codex",
                "cwd": "/tmp/project",
                "local_session_id": "copilot-codex-project-20260701184338",
                "allowed_user_ids": ["100000000000000001"],
                "last_seen_message_id": "100",
            }
        ]
    )
    discord._client.request.return_value = _json_response(200, {"id": "999"})

    result = run_stop_hook(
        {
            "cwd": "/tmp/project",
            "session_id": "inherited-codex-thread-id",
            "turn_id": "turn-bridge-pane",
            "last_assistant_message": "Yep, I see this one too.",
        },
        client=discord,
        settings=_settings(),
        env={"TMUX_PANE": "%7"},
        wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("must not wait")),
        harness="codex",
    )

    assert result.block is False
    assert "released stop" in result.debug
    stop_posts = [
        call
        for call in discord._client.request.call_args_list
        if call.args[:2] == ("POST", "/channels/thread-1/messages")
    ]
    assert stop_posts
    assert "Yep, I see this one too." in stop_posts[0].kwargs["json"]["content"]
    stored = discord.get_handoff("thread-1")
    assert stored["last_notified_stop_key"] == "turn:turn-bridge-pane"
    assert stored["local_session_id"] == "copilot-codex-project-20260701184338"


def test_bridge_worker_delivers_authorized_reply_to_tmux(discord, tmp_path, monkeypatch):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "bridge_enabled": True,
                "tmux_pane": "%7",
                "harness": "claude",
                "cwd": "/tmp/project",
                "allowed_user_ids": ["100000000000000001"],
                "last_seen_message_id": "100",
            }
        ]
    )
    injected: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "copilot_cli.services.discord.tmux.inject_text",
        lambda target, text, submit_enters=1: injected.append((target, text, submit_enters)),
    )

    worker = DiscordBridgeWorker(discord, DiscordBridgeStore(tmp_path))
    result = worker.handle_message(
        {
            "id": "200",
            "channel_id": "thread-1",
            "content": "ship it",
            "timestamp": "2026-06-29T10:00:00Z",
            "author": {
                "id": "100000000000000001",
                "username": "testuser",
                "bot": False,
            },
        }
    )

    assert result is not None
    assert result.delivered is True
    assert injected[0][0] == "%7"
    assert "ship it" in injected[0][1]
    assert injected[0][2] == 1
    assert discord.get_handoff("thread-1")["last_seen_message_id"] == "200"
    assert worker.store.counts() == {"delivered": 1}


def test_bridge_worker_uses_double_enter_for_codex_tmux_delivery(discord, tmp_path, monkeypatch):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "bridge_enabled": True,
                "tmux_pane": "%7",
                "harness": "codex",
                "cwd": "/tmp/project",
                "allowed_user_ids": ["100000000000000001"],
                "last_seen_message_id": "100",
            }
        ]
    )
    injected: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "copilot_cli.services.discord.tmux.inject_text",
        lambda target, text, submit_enters=1: injected.append((target, text, submit_enters)),
    )

    worker = DiscordBridgeWorker(discord, DiscordBridgeStore(tmp_path))
    result = worker.handle_message(
        {
            "id": "200",
            "channel_id": "thread-1",
            "content": "Can you see this?",
            "timestamp": "2026-06-29T10:00:00Z",
            "author": {
                "id": "100000000000000001",
                "username": "testuser",
                "bot": False,
            },
        }
    )

    assert result is not None
    assert result.delivered is True
    assert injected[0][0] == "%7"
    assert injected[0][2] == 2


def test_bridge_worker_warns_once_on_notify_only_await_without_pane(discord, tmp_path, monkeypatch):
    """A reply to an un-bridged away thread is answered with a warning, not dropped."""
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "await": True,
                "harness": "claude",
                "cwd": "/tmp/project",
                "allowed_user_ids": ["100000000000000001"],
                "last_seen_message_id": "100",
            }
        ]
    )
    discord._client.request.return_value = _json_response(200, {"id": "999"})

    def _must_not_inject(*_):
        raise AssertionError("no pane is registered, so injection cannot run")

    monkeypatch.setattr("copilot_cli.services.discord.tmux.inject_text", _must_not_inject)

    worker = DiscordBridgeWorker(discord, DiscordBridgeStore(tmp_path))

    def _msg(mid, content):
        return {
            "id": mid,
            "channel_id": "thread-1",
            "content": content,
            "timestamp": "2026-06-29T10:00:00Z",
            "author": {"id": "100000000000000001", "username": "testuser", "bot": False},
        }

    result = worker.handle_message(_msg("200", "queue me"))

    # Handled, not silently dropped: failed delivery + exactly one warning posted.
    assert result is not None
    assert result.delivered is False
    assert worker.store.counts() == {"failed": 1}
    stored = discord.get_handoff("thread-1")
    assert stored["unbridged_notice_sent"] is True
    assert stored["last_seen_message_id"] == "200"

    def _warnings():
        return [
            c
            for c in discord._client.request.call_args_list
            if c.args[:2] == ("POST", "/channels/thread-1/messages")
        ]

    warnings = _warnings()
    assert len(warnings) == 1
    assert "bridge launch" in warnings[0].kwargs["json"]["content"]

    # A second reply must NOT re-warn — one notice per thread.
    worker.handle_message(_msg("201", "again"))
    assert len(_warnings()) == 1


def test_bridge_worker_queues_bridge_reply_without_tmux_pane(discord, tmp_path, monkeypatch):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "bridge_enabled": True,
                "harness": "codex",
                "cwd": "/tmp/project",
                "allowed_user_ids": ["100000000000000001"],
                "last_seen_message_id": "100",
            }
        ]
    )
    discord._client.request.return_value = _json_response(
        200,
        [
            {
                "id": "200",
                "channel_id": "thread-1",
                "content": "Can you see this?",
                "timestamp": "2026-07-01T18:00:20.630000+00:00",
                "author": {
                    "id": "100000000000000001",
                    "username": "life.of.testuser",
                    "bot": False,
                },
            }
        ],
    )

    def _must_not_inject(*_):
        raise AssertionError("no pane is registered, so injection cannot run")

    monkeypatch.setattr("copilot_cli.services.discord.tmux.inject_text", _must_not_inject)

    worker = DiscordBridgeWorker(discord, DiscordBridgeStore(tmp_path))
    results = worker.catch_up_open_threads()

    assert len(results) == 1
    assert results[0].delivered is False
    assert results[0].detail == "no tmux pane registered"
    assert worker.store.counts() == {"queued": 1}
    assert discord.get_handoff("thread-1")["last_seen_message_id"] == "200"


def test_bridge_worker_dead_letters_queued_reply_without_bridge_record(discord, tmp_path):
    # Open handoff with no bridge intent (no await, no pane) → not watched at all.
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "await": False,
                "harness": "codex",
                "cwd": "/tmp/project",
            }
        ]
    )
    store = DiscordBridgeStore(tmp_path)
    store.enqueue(
        DiscordReply(
            message_id="200",
            thread_id="thread-1",
            user_id="100000000000000001",
            username="testuser",
            content="Can you see this?",
            created_at="2026-07-01T18:00:20.630000+00:00",
        )
    )

    results = DiscordBridgeWorker(discord, store).deliver_pending()

    assert results == []
    assert store.counts() == {"failed": 1}


def test_ensure_project_trusted_claude_writes_flag(tmp_path, monkeypatch):
    from copilot_cli.services.discord.bridge import ensure_project_trusted

    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    proj.mkdir()

    assert ensure_project_trusted("claude", str(proj)) is True

    data = json.loads((tmp_path / ".claude.json").read_text())
    key = str(proj.resolve())
    assert data["projects"][key]["hasTrustDialogAccepted"] is True
    # Idempotent.
    assert ensure_project_trusted("claude", str(proj)) is True


def test_ensure_project_trusted_claude_preserves_existing_config(tmp_path, monkeypatch):
    from copilot_cli.services.discord.bridge import ensure_project_trusted

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(
        json.dumps({"userID": "abc", "projects": {"/other": {"hasTrustDialogAccepted": True}}})
    )
    proj = tmp_path / "proj"
    proj.mkdir()

    ensure_project_trusted("claude", str(proj))

    data = json.loads((tmp_path / ".claude.json").read_text())
    assert data["userID"] == "abc"
    assert data["projects"]["/other"]["hasTrustDialogAccepted"] is True
    assert data["projects"][str(proj.resolve())]["hasTrustDialogAccepted"] is True


def test_ensure_project_trusted_codex_appends_without_rewrite(tmp_path, monkeypatch):
    import tomllib

    from copilot_cli.services.discord.bridge import ensure_project_trusted

    monkeypatch.setenv("HOME", str(tmp_path))
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "config.toml").write_text(
        '# my config\nmodel = "gpt-5"\n\n[projects."/existing"]\ntrust_level = "trusted"\n'
    )
    proj = tmp_path / "proj"
    proj.mkdir()

    assert ensure_project_trusted("codex", str(proj)) is True

    text = (codex / "config.toml").read_text()
    assert "# my config" in text  # comments/formatting preserved
    data = tomllib.loads(text)
    assert data["projects"][str(proj.resolve())]["trust_level"] == "trusted"
    assert data["projects"]["/existing"]["trust_level"] == "trusted"

    # Idempotent — an existing section is respected, not duplicated.
    assert ensure_project_trusted("codex", str(proj)) is True
    assert text.count(f'[projects."{proj.resolve()}"]') == 1


def test_ensure_project_trusted_unknown_harness_is_noop(tmp_path, monkeypatch):
    from copilot_cli.services.discord.bridge import ensure_project_trusted

    monkeypatch.setenv("HOME", str(tmp_path))
    assert ensure_project_trusted("weird", str(tmp_path)) is False


def test_bridge_status_includes_open_await_handoffs(discord, tmp_path):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "await": True,
                "harness": "codex",
                "cwd": "/tmp/project",
            }
        ]
    )

    result = bridge_status(client=discord)

    assert [record["thread_id"] for record in result["handoffs"]] == ["thread-1"]


def test_attach_record_enables_bridge_for_open_thread(discord):
    discord.save_handoffs(
        [
            {
                "thread_id": "thread-1",
                "status": "open",
                "harness": "claude",
                "cwd": "/tmp/project",
            }
        ]
    )

    record = attach_record(
        discord,
        "thread-1",
        tmux_pane="%7",
        harness="codex",
        session_id="sess-bridge",
        cwd="/tmp/project",
        owner_pid=123,
    )

    assert record["bridge_enabled"] is True
    assert record["tmux_pane"] == "%7"
    assert record["harness"] == "codex"
    assert record["local_session_id"] == "sess-bridge"
    assert record["owner_pid"] == 123


def test_start_tmux_bridge_session_launches_and_registers_bridge(discord, tmp_path, monkeypatch):
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Starting"}),
        _json_response(200, {"id": "200", "name": "Bridge"}),
        _json_response(204, ""),
    ]
    monkeypatch.setattr("copilot_cli.services.discord.tmux.tmux_available", lambda: True)
    calls: list[list[str]] = []

    def _runner(args, **_kwargs):
        calls.append(args)
        if args[:2] == ["tmux", "display-message"] and args[-1] == "#{pane_id}":
            return subprocess.CompletedProcess(args, 0, stdout="%42\n", stderr="")
        if args[:2] == ["tmux", "display-message"] and args[-1] == "#{pane_pid}":
            return subprocess.CompletedProcess(args, 0, stdout="4242\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    record = start_tmux_bridge_session(
        discord,
        harness="codex",
        title="Codex bridge",
        message="Starting bridge",
        session_name="copilot-codex-test",
        cwd=str(tmp_path),
        command=["codex", "--model", "gpt-5"],
        runner=_runner,
    )

    assert calls[0] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "copilot-codex-test",
        "-c",
        str(tmp_path),
        "codex --model gpt-5",
    ]
    assert record["thread_id"] == "200"
    assert record["await"] is True
    assert record["bridge_enabled"] is True
    assert record["tmux_pane"] == "%42"
    assert record["tmux_session"] == "copilot-codex-test"
    assert record["tmux_attach_command"] == "tmux attach -t copilot-codex-test"
    assert record["owner_pid"] == 4242
    assert record["launch_command"] == "codex --model gpt-5"


def test_start_tmux_bridge_session_injects_initial_prompt(discord, tmp_path, monkeypatch):
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Starting"}),
        _json_response(200, {"id": "200", "name": "Bridge"}),
        _json_response(204, ""),
    ]
    monkeypatch.setattr("copilot_cli.services.discord.tmux.tmux_available", lambda: True)
    calls: list[tuple[list[str], str | None]] = []

    def _runner(args, **kwargs):
        calls.append((args, kwargs.get("input")))
        if args[:2] == ["tmux", "display-message"] and args[-1] == "#{pane_id}":
            return subprocess.CompletedProcess(args, 0, stdout="%42\n", stderr="")
        if args[:2] == ["tmux", "display-message"] and args[-1] == "#{pane_pid}":
            return subprocess.CompletedProcess(args, 0, stdout="4242\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    record = start_tmux_bridge_session(
        discord,
        harness="codex",
        title="Codex bridge",
        message="Starting bridge",
        session_name="copilot-codex-test",
        cwd=str(tmp_path),
        command=["codex"],
        initial_prompt="Continue this bridged task.",
        runner=_runner,
    )

    load_buffer = next(call for call in calls if call[0][:3] == ["tmux", "load-buffer", "-b"])
    send_enters = [
        call for call in calls if call[0][:2] == ["tmux", "send-keys"] and call[0][-1] == "Enter"
    ]
    assert load_buffer[1] == "Continue this bridged task."
    assert len(send_enters) == 2
    assert record["initial_prompt_delivered"] is True


def test_default_harness_command_supports_claude_code_alias():
    assert default_harness_command("claude-code") == ["claude"]


def test_install_launch_agent_default_plist_uses_configurable_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_BRIDGE_PATH", "/custom/bin:/usr/bin:/bin")

    plist_path = install_launch_agent(plist_dir=tmp_path)

    payload = plistlib.loads(plist_path.read_bytes())
    assert payload["Label"] == "com.copilot.discord-bridge"
    assert payload["ProgramArguments"] == [
        "/bin/sh",
        "-lc",
        'exec "${COPILOT_BRIDGE_COPILOT_BIN:-copilot}" discord bridge run',
    ]
    assert payload["EnvironmentVariables"] == {"PATH": "/custom/bin:/usr/bin:/bin"}
    assert "COPILOT_ENV_FILE" not in payload["EnvironmentVariables"]


def test_install_launch_agent_supports_explicit_overrides(tmp_path):
    plist_path = install_launch_agent(
        copilot_bin="/custom/bin/copilot",
        env_file="/tmp/copilot.env",
        path_env="/custom/bin:/usr/bin:/bin",
        plist_dir=tmp_path,
    )

    payload = plistlib.loads(plist_path.read_bytes())
    assert payload["EnvironmentVariables"]["COPILOT_BRIDGE_COPILOT_BIN"] == "/custom/bin/copilot"
    assert payload["EnvironmentVariables"]["COPILOT_ENV_FILE"] == "/tmp/copilot.env"
    assert payload["EnvironmentVariables"]["PATH"] == "/custom/bin:/usr/bin:/bin"


# ---------------------------------------------------------------------- #
# install_hooks / uninstall_hooks                                          #
# ---------------------------------------------------------------------- #


def test_install_claude_hooks_writes_executable_shims_and_merges_settings(tmp_path):
    result = install_stop_hook(scope="project", target_dir=tmp_path, harness="claude")

    installed = result["claude"]
    prompt_shim = Path(installed["prompt_shim"])
    stop_shim = Path(installed["stop_shim"])
    settings_path = Path(installed["settings"])

    assert prompt_shim.is_file(), "prompt shim must be written"
    assert stop_shim.is_file(), "stop shim must be written"
    assert prompt_shim.stat().st_mode & stat.S_IXUSR, "prompt shim must be executable"
    assert stop_shim.stat().st_mode & stat.S_IXUSR, "stop shim must be executable"
    prompt_text = prompt_shim.read_text()
    assert "discord hook user-prompt-submit --harness claude" in prompt_text
    assert "discord hook stop --harness claude" in stop_shim.read_text()
    # Portable: binary + env file resolved at runtime, no baked absolute paths.
    assert "command -v copilot" in prompt_text
    assert "COPILOT_BIN" in prompt_text
    assert "COPILOT_ENV_FILE" in prompt_text
    assert "/opt/homebrew/bin/copilot" not in prompt_text
    assert "/usr/local/bin/copilot" not in prompt_text
    assert str(tmp_path) not in prompt_text

    settings = json.loads(settings_path.read_text())
    prompts = settings["hooks"]["UserPromptSubmit"]
    stops = settings["hooks"]["Stop"]
    # Project-scope commands are registered repo-relative (portable when committed).
    prompt_cmd = os.path.relpath(prompt_shim, tmp_path)
    stop_cmd = os.path.relpath(stop_shim, tmp_path)
    assert not os.path.isabs(prompt_cmd)
    assert any(h.get("command") == prompt_cmd for entry in prompts for h in entry.get("hooks", []))
    assert any(h.get("command") == stop_cmd for entry in stops for h in entry.get("hooks", []))


def test_install_claude_hooks_is_idempotent(tmp_path):
    """Running install twice must not duplicate hook entries."""
    install_stop_hook(scope="project", target_dir=tmp_path, harness="claude")
    install_stop_hook(scope="project", target_dir=tmp_path, harness="claude")

    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    prompts = settings["hooks"]["UserPromptSubmit"]
    stops = settings["hooks"]["Stop"]

    prompt_shim = tmp_path / ".claude" / "hooks" / "discord-user-prompt-submit.sh"
    shim_path = tmp_path / ".claude" / "hooks" / "discord-stop.sh"
    prompt_cmd = os.path.relpath(prompt_shim, tmp_path)
    stop_cmd = os.path.relpath(shim_path, tmp_path)
    prompt_matching = [
        entry
        for entry in prompts
        if any(h.get("command") == prompt_cmd for h in entry.get("hooks", []))
    ]
    matching = [
        entry
        for entry in stops
        if any(h.get("command") == stop_cmd for h in entry.get("hooks", []))
    ]
    assert len(prompt_matching) == 1, "must have one UserPromptSubmit entry after two installs"
    assert len(matching) == 1, "must have exactly one hooks.Stop entry after two installs"


def test_install_claude_hooks_merges_with_existing_entries(tmp_path):
    """Existing Claude hook entries must be preserved."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "/other/hook.sh"}]}]}}
        )
    )

    install_stop_hook(scope="project", target_dir=tmp_path, harness="claude")

    settings = json.loads(settings_path.read_text())
    commands = [h["command"] for entry in settings["hooks"]["Stop"] for h in entry.get("hooks", [])]
    assert "/other/hook.sh" in commands, "pre-existing hook must not be removed"
    assert any("discord-stop.sh" in c for c in commands)


def test_install_codex_hooks_writes_hooks_json(tmp_path):
    result = install_hooks(scope="project", target_dir=tmp_path, harness="codex")

    installed = result["codex"]
    prompt_shim = Path(installed["prompt_shim"])
    stop_shim = Path(installed["stop_shim"])
    hooks_path = Path(installed["hooks"])

    assert prompt_shim.is_file()
    assert stop_shim.is_file()
    prompt_text = prompt_shim.read_text()
    assert "discord hook user-prompt-submit --harness codex" in prompt_text
    assert "discord hook stop --harness codex" in stop_shim.read_text()
    # Portable: no baked absolute paths.
    assert "command -v copilot" in prompt_text
    assert str(tmp_path) not in prompt_text

    hooks_json = json.loads(hooks_path.read_text())
    prompt_handlers = hooks_json["hooks"]["UserPromptSubmit"][0]["hooks"]
    stop_handlers = hooks_json["hooks"]["Stop"][0]["hooks"]
    # Project-scope commands registered repo-relative.
    assert prompt_handlers[0]["command"] == os.path.relpath(prompt_shim, tmp_path)
    assert stop_handlers[0]["command"] == os.path.relpath(stop_shim, tmp_path)
    assert stop_handlers[0]["timeout"] == 604800


def test_install_all_hooks_installs_claude_and_codex(tmp_path):
    result = install_hooks(scope="project", target_dir=tmp_path, harness="all")

    assert set(result) == {"claude", "codex"}
    assert Path(result["claude"]["settings"]).is_file()
    assert Path(result["codex"]["hooks"]).is_file()


def test_uninstall_claude_hooks_removes_shims_and_settings_entries(tmp_path):
    install_stop_hook(scope="project", target_dir=tmp_path, harness="claude")
    result = uninstall_stop_hook(scope="project", target_dir=tmp_path, harness="claude")

    removed = result["claude"]

    prompt_path = tmp_path / ".claude" / "hooks" / "discord-user-prompt-submit.sh"
    shim_path = tmp_path / ".claude" / "hooks" / "discord-stop.sh"
    assert not prompt_path.exists(), "prompt shim must be removed"
    assert not shim_path.exists(), "shim must be removed"
    assert removed["prompt_shim_removed"] == "True"
    assert removed["stop_shim_removed"] == "True"
    assert removed["entry_removed"] == "True"

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    prompts = settings.get("hooks", {}).get("UserPromptSubmit", [])
    stops = settings.get("hooks", {}).get("Stop", [])
    assert not any(
        h.get("command", "").endswith("discord-user-prompt-submit.sh")
        for entry in prompts
        for h in entry.get("hooks", [])
    )
    assert not any(
        h.get("command", "").endswith("discord-stop.sh")
        for entry in stops
        for h in entry.get("hooks", [])
    )


def test_uninstall_codex_hooks_removes_shims_and_hooks_json_entries(tmp_path):
    install_hooks(scope="project", target_dir=tmp_path, harness="codex")
    result = uninstall_hooks(scope="project", target_dir=tmp_path, harness="codex")

    removed = result["codex"]
    prompt_path = tmp_path / ".codex" / "hooks" / "discord-user-prompt-submit.sh"
    stop_path = tmp_path / ".codex" / "hooks" / "discord-stop.sh"

    assert not prompt_path.exists()
    assert not stop_path.exists()
    assert removed["entry_removed"] == "True"

    hooks_json = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert hooks_json["hooks"]["UserPromptSubmit"] == []
    assert hooks_json["hooks"]["Stop"] == []


def test_uninstall_hooks_when_not_installed_is_safe(tmp_path):
    """Uninstalling when nothing was installed must not raise."""
    result = uninstall_stop_hook(scope="project", target_dir=tmp_path, harness="claude")

    removed = result["claude"]
    assert removed["prompt_shim_removed"] == "False"
    assert removed["stop_shim_removed"] == "False"
    assert removed["entry_removed"] == "False"


# ---------------------------------------------------------------------- #
# handoff --await CLI flag                                                 #
# ---------------------------------------------------------------------- #


def test_handoff_with_await_flag_sets_await_on_record(discord, tmp_path, monkeypatch):
    """``copilot discord handoff --await`` must persist await=True on the record."""
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Starting"}),
        _json_response(200, {"id": "200", "name": "Session"}),
        _json_response(204, ""),
    ]

    # Exercise the client path directly (mirrors what the command does).
    record = discord.start_handoff(
        title="Session",
        message="Starting",
        harness="claude",
        local_session_id="sess-1",
        cwd="/tmp/project",
    )
    record = discord.set_await(record["thread_id"], True)

    assert record["await"] is True
    assert discord.get_handoff(record["thread_id"])["await"] is True


def test_handoff_without_await_flag_does_not_arm(discord):
    """Default (--no-await) must leave await unset / falsy."""
    discord._client.request.side_effect = [
        _json_response(200, {"id": "100", "content": "Starting"}),
        _json_response(200, {"id": "200", "name": "Session"}),
        _json_response(204, ""),
    ]

    record = discord.start_handoff(
        title="Session",
        message="Starting",
        harness="claude",
        local_session_id="sess-2",
        cwd="/tmp/project",
    )

    # No set_await called — await key should be absent or False.
    stored = discord.get_handoff(record["thread_id"])
    assert not stored.get("await")


# ---------------------------------------------------------------------- #
# health                                                                    #
# ---------------------------------------------------------------------- #


def test_health_pings_own_identity_when_token_present(discord):
    """health() pings /users/@me and reports healthy when the API answers."""
    discord._client.request.return_value = _json_response(
        200, {"id": "1", "username": "copilot-bot"}
    )

    result = discord.health()

    assert result["healthy"] is True
    assert result["username"] == "copilot-bot"
    assert discord._client.request.call_args.args[:2] == ("GET", "/users/@me")


def test_health_unhealthy_when_token_missing(tmp_path):
    """health() reports unhealthy without ever calling the API when unconfigured."""
    client = DiscordClient(settings=_settings(discord_bot_token=""), data_dir=tmp_path)
    client._client = MagicMock()

    result = client.health()

    assert result["healthy"] is False
    assert "DISCORD_BOT_TOKEN" in result["error"]
    client._client.request.assert_not_called()


def test_health_unhealthy_on_api_error(discord):
    """health() reports unhealthy and the error when the API call fails."""
    discord._client.request.return_value = _json_response(401, {"message": "Unauthorized"})

    result = discord.health()

    assert result["healthy"] is False
    assert "error" in result
