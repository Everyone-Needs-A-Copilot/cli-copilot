"""Tests for the opt-in usage ledger (COPILOT_USAGE_LOG).

Covers:
- record(): disabled by default, enabled writes a valid JSONL line, write
  failure never raises (resilience invariant).
- End-to-end via CliRunner: real command paths are captured (including
  nested groups), argument/option values are never recorded (privacy
  invariant), and a ledger write failure never changes the command's own
  exit code or output.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli import __version__
from copilot_cli.main import app
from copilot_cli.shared import usage_ledger

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


def _fake_ctx(info_name: str, parent: SimpleNamespace | None) -> SimpleNamespace:
    return SimpleNamespace(info_name=info_name, parent=parent)


# ------------------------------------------------------------------ #
# _command_path
# ------------------------------------------------------------------ #


class TestCommandPath:
    """_command_path resolves the leaf's chain, excluding the root program name."""

    def test_top_level_command(self):
        root = _fake_ctx("copilot", parent=None)
        leaf = _fake_ctx("health", parent=root)

        assert usage_ledger._command_path(leaf) == "health"

    def test_nested_group_command(self):
        root = _fake_ctx("copilot", parent=None)
        group = _fake_ctx("git", parent=root)
        leaf = _fake_ctx("status", parent=group)

        assert usage_ledger._command_path(leaf) == "git status"

    def test_deeply_nested_command(self):
        root = _fake_ctx("copilot", parent=None)
        group = _fake_ctx("uspto", parent=root)
        subgroup = _fake_ctx("auth", parent=group)
        leaf = _fake_ctx("show", parent=subgroup)

        assert usage_ledger._command_path(leaf) == "uspto auth show"


# ------------------------------------------------------------------ #
# record()
# ------------------------------------------------------------------ #


class TestRecord:
    def test_disabled_by_default_writes_nothing(self, tmp_path, monkeypatch):
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.delenv("COPILOT_USAGE_LOG", raising=False)
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        usage_ledger.record("git status", 0, 12)

        assert not log_path.exists()

    def test_enabled_writes_a_valid_jsonl_line(self, tmp_path, monkeypatch):
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        usage_ledger.record("git status", 0, 12)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry == {
            "ts": entry["ts"],
            "cmd": "git status",
            "exit_code": 0,
            "duration_ms": 12,
            "version": __version__,
        }
        assert entry["ts"].endswith("Z")

    def test_enabled_appends_multiple_lines(self, tmp_path, monkeypatch):
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        usage_ledger.record("git status", 0, 12)
        usage_ledger.record("docker ps", 1, 5)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["cmd"] == "git status"
        assert json.loads(lines[1])["cmd"] == "docker ps"
        assert json.loads(lines[1])["exit_code"] == 1

    def test_write_failure_never_raises(self, tmp_path, monkeypatch):
        """A ledger write failure (e.g. parent path is a file) is silent."""
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("occupied")
        log_path = blocker / "usage.jsonl"

        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        # Must not raise even though `blocker` cannot be mkdir'd into.
        usage_ledger.record("git status", 0, 12)

    def test_disabled_check_itself_never_raises(self, monkeypatch):
        class ExplodingEnviron:
            def get(self, key, default=None):
                raise RuntimeError("boom")

        monkeypatch.setattr(usage_ledger, "os", SimpleNamespace(environ=ExplodingEnviron()))

        assert usage_ledger._enabled() is False


# ------------------------------------------------------------------ #
# End-to-end via CliRunner -- real command paths, real exit codes
# ------------------------------------------------------------------ #


class TestLedgerEndToEnd:
    def test_disabled_by_default_no_ledger_file(self, runner, tmp_path, monkeypatch):
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.delenv("COPILOT_USAGE_LOG", raising=False)
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        mock_client = MagicMock()
        mock_client.system_info.return_value = {
            "containers": 0,
            "running": 0,
            "paused": 0,
            "stopped": 0,
            "images": 0,
            "version": "24.0.7",
            "cpus": 1,
            "memory_gb": 1.0,
            "os": "test",
        }
        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "info"])

        assert result.exit_code == 0
        assert not log_path.exists()

    def test_enabled_records_successful_command(self, runner, tmp_path, monkeypatch):
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        mock_client = MagicMock()
        mock_client.container_list.return_value = []
        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "ps"])

        assert result.exit_code == 0
        entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["cmd"] == "docker ps"
        assert entry["exit_code"] == 0
        assert isinstance(entry["duration_ms"], int)

    def test_enabled_records_real_exit_code_on_failure(self, runner, tmp_path, monkeypatch):
        from copilot_cli.shared.errors import NotFoundError

        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        mock_client = MagicMock()
        mock_client.container_start.side_effect = NotFoundError(
            "Container not found: ghost", service="docker"
        )
        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "start", "ghost"])

        assert result.exit_code == 1
        entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["cmd"] == "docker start"
        assert entry["exit_code"] == 1

    def test_argument_values_are_never_recorded(self, runner, tmp_path, monkeypatch):
        """PRIVACY INVARIANT: only the command path is recorded, never argv values."""
        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        secret = "super-secret-value-123"
        mock_client = MagicMock()
        mock_client.execute.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", f"echo {secret}"])

        assert result.exit_code == 0
        raw_log = log_path.read_text(encoding="utf-8")
        entry = json.loads(raw_log.strip().splitlines()[-1])
        assert entry["cmd"] == "shell exec"
        assert secret not in raw_log

    def test_nested_command_path_resolves_and_hides_argument(self, runner, tmp_path, monkeypatch):
        """A 3-level nested command (uspto auth show <artifact_id>) records the
        full group chain and never the artifact id argument."""
        from copilot_cli.shared.errors import CopilotError

        log_path = tmp_path / "usage.jsonl"
        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        artifact_id = "artifact-should-not-leak-999"
        mock_client = MagicMock()
        mock_client.auth_instructions.side_effect = CopilotError(
            f"Unknown auth artifact {artifact_id}.",
            service="uspto",
        )
        with patch(
            "copilot_cli.services.uspto.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["uspto", "auth", "show", artifact_id])

        assert result.exit_code == 1
        raw_log = log_path.read_text(encoding="utf-8")
        entry = json.loads(raw_log.strip().splitlines()[-1])
        assert entry["cmd"] == "uspto auth show"
        assert entry["exit_code"] == 1
        assert artifact_id not in entry["cmd"]

    def test_ledger_write_failure_does_not_break_command(self, runner, tmp_path, monkeypatch):
        """RESILIENCE INVARIANT: an unwritable ledger path never fails the command."""
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("occupied")
        log_path = blocker / "usage.jsonl"

        monkeypatch.setenv("COPILOT_USAGE_LOG", "1")
        monkeypatch.setenv("COPILOT_USAGE_LOG_PATH", str(log_path))

        mock_client = MagicMock()
        mock_client.container_list.return_value = []
        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "ps"])

        assert result.exit_code == 0
