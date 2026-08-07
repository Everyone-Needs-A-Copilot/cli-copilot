"""Integration tests: the safety guard is wired through PostgreSQLClient.

These pin down the contract that ``query``, ``transaction``, ``batch_query``,
and ``analyze_query(analyze=True)`` all refuse destructive SQL on non-local
connections and gate destructive SQL on local connections behind a matching
confirm-token. The unit-level coverage of the guard itself lives in
``test_postgresql_safety.py``; this file proves the wire-up.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.postgresql.client import PostgreSQLClient
from copilot_cli.services.postgresql.safety import PolicyViolation


def _make_mock_conn():
    conn = MagicMock()
    conn.closed = False
    conn.autocommit = True
    cur = MagicMock()
    cur.description = None
    cur.rowcount = 0
    cur.fetchall.return_value = []
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


@pytest.fixture
def remote_client(monkeypatch):
    """A PostgreSQLClient configured with one local and one remote DB."""
    from copilot_cli.config.settings import Settings

    fake = Settings(
        database_url="postgresql://u:p@db.example.com:5432/prod",  # remote
        nocodb_database_url="postgresql://u:p@localhost:5432/nocodb",  # local
    )
    monkeypatch.setattr("copilot_cli.services.postgresql.client.get_settings", lambda: fake)
    client = PostgreSQLClient()
    return client


class TestQueryGuard:
    def test_select_on_remote_allowed(self, remote_client):
        with patch.object(remote_client, "_get_connection", return_value=_make_mock_conn()):
            remote_client.query("main", "SELECT 1")  # no raise

    def test_drop_on_remote_refused(self, remote_client):
        with pytest.raises(PolicyViolation, match="direct-remote"):
            remote_client.query("main", "DROP TABLE users")

    def test_drop_on_local_without_token_refused(self, remote_client):
        with pytest.raises(PolicyViolation, match="confirmation token"):
            remote_client.query("nocodb", "DROP TABLE users")

    def test_drop_on_local_with_matching_token_allowed(self, remote_client):
        with patch.object(remote_client, "_get_connection", return_value=_make_mock_conn()):
            remote_client.query("nocodb", "DROP TABLE users", confirm_token="nocodb")  # no raise

    def test_drop_on_local_with_wrong_token_refused(self, remote_client):
        with pytest.raises(PolicyViolation, match="confirmation token"):
            remote_client.query("nocodb", "DROP TABLE users", confirm_token="main")

    def test_unknown_db_still_raises_config_error_not_keyerror(self, remote_client):
        from copilot_cli.shared.errors import ConfigError

        with pytest.raises(ConfigError):
            remote_client.query("does-not-exist", "SELECT 1")


class TestTransactionGuard:
    def test_destructive_in_transaction_on_remote_refused(self, remote_client):
        ops = [{"query": "SELECT 1"}, {"query": "DROP TABLE x"}]
        with pytest.raises(PolicyViolation, match="direct-remote"):
            remote_client.transaction("main", ops)

    def test_destructive_in_transaction_on_local_needs_token(self, remote_client):
        ops = [{"query": "INSERT INTO t VALUES (1)"}, {"query": "DROP TABLE x"}]
        with pytest.raises(PolicyViolation, match="confirmation token"):
            remote_client.transaction("nocodb", ops)

    def test_local_destructive_with_token_proceeds_to_db(self, remote_client):
        ops = [{"query": "DROP TABLE x"}]
        # Make psycopg2 calls succeed.
        with patch.object(remote_client, "_get_connection", return_value=_make_mock_conn()):
            remote_client.transaction("nocodb", ops, confirm_token="nocodb")


class TestBatchQueryGuard:
    def test_returns_error_dict_for_blocked_destructive(self, remote_client):
        # batch_query catches CopilotError per query and stores it; PolicyViolation
        # is a CopilotError subclass, so destructive on remote becomes an error entry.
        results = remote_client.batch_query("main", ["SELECT 1", "DROP TABLE x"])
        assert len(results) == 2
        assert "error" in results[1]
        assert "direct-remote" in results[1]["error"]


class TestAnalyzeQueryGuard:
    def test_explain_without_analyze_not_gated(self, remote_client):
        """Plain EXPLAIN is read-only; destructive-looking SQL is fine to plan."""
        with patch.object(remote_client, "_get_connection", return_value=_make_mock_conn()):
            remote_client.analyze_query("main", "DROP TABLE x", analyze=False)

    def test_explain_analyze_destructive_on_remote_refused(self, remote_client):
        with pytest.raises(PolicyViolation, match="direct-remote"):
            remote_client.analyze_query("main", "DROP TABLE x", analyze=True)

    def test_explain_analyze_destructive_on_local_needs_token(self, remote_client):
        with pytest.raises(PolicyViolation, match="confirmation token"):
            remote_client.analyze_query("nocodb", "DROP TABLE x", analyze=True)


class TestCliQueryConfirmToken:
    """CLI-layer test: --confirm-token flag is plumbed through correctly."""

    def test_destructive_on_local_with_token_runs(self):
        from copilot_cli.services.postgresql import commands as cmd_mod

        runner = CliRunner()
        mock_client = MagicMock()
        mock_client.query.return_value = {"rows": [], "row_count": 0, "columns": []}
        with patch.object(cmd_mod, "_client", return_value=mock_client):
            result = runner.invoke(
                app,
                ["db", "query", "nocodb", "DROP TABLE x", "--confirm-token", "nocodb"],
            )
        assert result.exit_code == 0
        mock_client.query.assert_called_once()
        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["confirm_token"] == "nocodb"

    def test_destructive_without_token_defaults_to_none_not_empty_string(self):
        """An unset --confirm-token must become None, not ''."""
        from copilot_cli.services.postgresql import commands as cmd_mod

        runner = CliRunner()
        mock_client = MagicMock()
        mock_client.query.return_value = {"rows": [], "row_count": 0, "columns": []}
        with patch.object(cmd_mod, "_client", return_value=mock_client):
            runner.invoke(app, ["db", "query", "nocodb", "SELECT 1"])
        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["confirm_token"] is None
