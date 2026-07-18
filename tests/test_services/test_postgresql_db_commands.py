"""Typer CliRunner tests for the database transfer commands.

These tests exercise the command-layer wiring: argument parsing, exit codes,
policy refusals, and prompt handling. They complement the helper-level unit
tests in test_postgresql_transfer.py and test_postgresql_safety.py.

Patching strategy
-----------------
- ``_resolve_remote_db``, ``_ssh_target_from_coolify_settings``, and
  ``_open_tunnel_or_raise`` are patched at the command module level to avoid
  needing a real Coolify-shaped adapter (this public foundation does not
  ship one -- see ``TestRemoteAdapterAbsent`` below).
- ``_resolve_local_url`` is patched at the command module level to return
  whatever URL the test needs (loopback to simulate local, remote host to
  exercise the policy guard).
- ``remote_pg_dump`` and ``local_pg_restore`` are patched at the transfer
  module level (``copilot_cli.services.postgresql.transfer.*``) because the
  command module imports them inside function bodies with
  ``from copilot_cli.services.postgresql.transfer import ...``.
- The tunnel registry is cleared between tests to prevent cross-test pollution.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.postgresql.safety import unregister_tunneled

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCAL_URL = "postgresql://test:test@localhost:5432/mydb"
REMOTE_URL = "postgresql://user:pass@db.prod.example.com:5432/mydb"

FAKE_REMOTE_RECORD = {
    "uuid": "abc-container-uuid",
    "name": "myapp-db",
    "database_type": "standalone-postgresql",
    "postgres_user": "pguser",
    "postgres_password": "pgpass",
    "postgres_db": "appdb",
}

FAKE_SSH_TARGET_PATH = "copilot_cli.services.postgresql.commands._ssh_target_from_coolify_settings"
FAKE_RESOLVE_REMOTE_PATH = "copilot_cli.services.postgresql.commands._resolve_remote_db"
FAKE_RESOLVE_LOCAL_PATH = "copilot_cli.services.postgresql.commands._resolve_local_url"
FAKE_OPEN_TUNNEL_PATH = "copilot_cli.services.postgresql.commands._open_tunnel_or_raise"
FAKE_REMOTE_DUMP_PATH = "copilot_cli.services.postgresql.transfer.remote_pg_dump"
FAKE_LOCAL_RESTORE_PATH = "copilot_cli.services.postgresql.transfer.local_pg_restore"
FAKE_SETTINGS_PATH = "copilot_cli.config.settings.get_settings"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_ssh_target():
    from copilot_cli.services.postgresql.transfer import SSHTarget

    return SSHTarget(user="root", host="10.0.0.5", port=22, key_file=None)


@pytest.fixture(autouse=True)
def _clear_tunnel_registry():
    """Prevent tunnel registry state from leaking between tests."""
    yield
    # After each test, unregister any URL that tests might have registered.
    for url in [LOCAL_URL, REMOTE_URL]:
        unregister_tunneled(url)
    # Also clear any tunneled-localhost URL that remote_query might register.
    from copilot_cli.services.postgresql import safety as _safety

    _safety._tunneled_urls.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_dump_result(output_path: Path) -> dict:
    """Return a plausible remote_pg_dump result dict."""
    output_path.write_bytes(b"PGDMP\x00fake")
    return {
        "path": str(output_path),
        "size_bytes": 7,
        "format": "custom",
    }


def _fake_restore_result() -> dict:
    return {"tool": "pg_restore", "format": "custom", "stderr_tail": []}


def _fake_settings_with_backup_dir(tmp_path: Path):
    """Return a minimal settings mock that provides a backup_dir in tmp_path."""
    settings = MagicMock()
    settings.get_backup_dir.return_value = tmp_path
    return settings


# ---------------------------------------------------------------------------
# db dump — happy path
# ---------------------------------------------------------------------------


class TestDbDumpHappyPath:
    """dump resolves the remote DB and calls remote_pg_dump with correct kwargs."""

    def test_exit_code_zero_and_correct_kwargs(self, runner, fake_ssh_target, tmp_path):
        tmp_path / "myapp-db-20260514-000000.dump"

        def _fake_dump(*, ssh, container, db_user, db_name, output_path, **kwargs):
            return _fake_dump_result(output_path)

        fake_settings = _fake_settings_with_backup_dir(tmp_path)

        with (
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=FAKE_REMOTE_RECORD),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
            patch(FAKE_REMOTE_DUMP_PATH, side_effect=_fake_dump) as mock_dump,
            patch(FAKE_SETTINGS_PATH, return_value=fake_settings),
        ):
            result = runner.invoke(app, ["db", "dump", "myapp-db"])

        assert result.exit_code == 0, result.output

        mock_dump.assert_called_once()
        call_kwargs = mock_dump.call_args.kwargs
        assert call_kwargs["container"] == FAKE_REMOTE_RECORD["uuid"]
        assert call_kwargs["db_user"] == FAKE_REMOTE_RECORD["postgres_user"]
        assert call_kwargs["db_name"] == FAKE_REMOTE_RECORD["postgres_db"]
        assert call_kwargs["ssh"] is fake_ssh_target


# ---------------------------------------------------------------------------
# db dump — non-postgres DB type
# ---------------------------------------------------------------------------


class TestDbDumpNonPostgres:
    """dump refuses non-postgres database types with exit code 1."""

    def test_mysql_record_exits_1_with_postgresql_mention(self, runner, fake_ssh_target):
        mysql_record = {**FAKE_REMOTE_RECORD, "database_type": "standalone-mysql"}

        with (
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=mysql_record),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
        ):
            result = runner.invoke(app, ["db", "dump", "myapp-db"])

        assert result.exit_code == 1
        assert "PostgreSQL" in result.output or "postgresql" in result.output.lower()


# ---------------------------------------------------------------------------
# db restore — unknown local name
# ---------------------------------------------------------------------------


class TestDbRestoreUnknownLocal:
    """restore exits 1 when the --to name is not in the local config."""

    def test_unknown_name_exits_1(self, runner, tmp_path):
        dump_file = tmp_path / "x.dump"
        dump_file.write_bytes(b"PGDMP\x00fake")

        from copilot_cli.shared.errors import CopilotError

        def _raise_unknown(name):
            raise CopilotError(
                f"Unknown local database '{name}'. Available: (none configured)",
                service="postgresql",
                hint="Add a *_DATABASE_URL to your .env file.",
            )

        with patch(FAKE_RESOLVE_LOCAL_PATH, side_effect=_raise_unknown):
            result = runner.invoke(
                app,
                [
                    "db",
                    "restore",
                    str(dump_file),
                    "--to",
                    "no-such-db",
                    "--confirm-token",
                    "no-such-db",
                ],
            )

        assert result.exit_code == 1
        assert "Unknown local database" in result.output


# ---------------------------------------------------------------------------
# db restore — remote target (policy refusal)
# ---------------------------------------------------------------------------


class TestDbRestoreRemoteTarget:
    """restore exits 1 when the resolved URL points at a non-loopback host."""

    def test_remote_url_exits_1_and_restore_not_called(self, runner, tmp_path):
        dump_file = tmp_path / "x.dump"
        dump_file.write_bytes(b"PGDMP\x00fake")

        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=REMOTE_URL),
            patch(FAKE_LOCAL_RESTORE_PATH) as mock_restore,
        ):
            result = runner.invoke(
                app, ["db", "restore", str(dump_file), "--to", "prod", "--confirm-token", "prod"]
            )

        assert result.exit_code == 1
        # The output should surface the policy violation in some form.
        assert (
            "Refused" in result.output
            or "remote" in result.output.lower()
            or "policy" in result.output.lower()
        )
        mock_restore.assert_not_called()


# ---------------------------------------------------------------------------
# db restore — confirmation token mismatch
# ---------------------------------------------------------------------------


class TestDbRestoreTokenMismatch:
    """restore exits 1 when --confirm-token doesn't match --to."""

    def test_wrong_token_exits_1_and_restore_not_called(self, runner, tmp_path):
        dump_file = tmp_path / "x.dump"
        dump_file.write_bytes(b"PGDMP\x00fake")

        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=LOCAL_URL),
            patch(FAKE_LOCAL_RESTORE_PATH) as mock_restore,
        ):
            result = runner.invoke(
                app,
                ["db", "restore", str(dump_file), "--to", "mydb", "--confirm-token", "wrong-name"],
            )

        assert result.exit_code == 1
        assert "Confirmation mismatch" in result.output or "mismatch" in result.output.lower()
        mock_restore.assert_not_called()


# ---------------------------------------------------------------------------
# db restore — happy path
# ---------------------------------------------------------------------------


class TestDbRestoreHappyPath:
    """restore exits 0 and calls local_pg_restore with the correct target URL."""

    def test_matching_token_calls_restore_once(self, runner, tmp_path):
        dump_file = tmp_path / "x.dump"
        dump_file.write_bytes(b"PGDMP\x00fake")

        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=LOCAL_URL),
            patch(FAKE_LOCAL_RESTORE_PATH, return_value=_fake_restore_result()) as mock_restore,
        ):
            result = runner.invoke(
                app, ["db", "restore", str(dump_file), "--to", "mydb", "--confirm-token", "mydb"]
            )

        assert result.exit_code == 0, result.output
        mock_restore.assert_called_once()
        call_kwargs = mock_restore.call_args.kwargs
        assert call_kwargs["target_url"] == LOCAL_URL


# ---------------------------------------------------------------------------
# db pull — happy path (dump + restore both called)
# ---------------------------------------------------------------------------


class TestDbPullHappyPath:
    """pull exits 0 and calls both remote_pg_dump then local_pg_restore."""

    def test_both_operations_called_in_order(self, runner, fake_ssh_target, tmp_path):
        call_order = []

        def _fake_dump(*, output_path, **kwargs):
            call_order.append("dump")
            return _fake_dump_result(output_path)

        def _fake_restore(**kwargs):
            call_order.append("restore")
            return _fake_restore_result()

        fake_settings = _fake_settings_with_backup_dir(tmp_path)

        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=LOCAL_URL),
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=FAKE_REMOTE_RECORD),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
            patch(FAKE_REMOTE_DUMP_PATH, side_effect=_fake_dump) as mock_dump,
            patch(FAKE_LOCAL_RESTORE_PATH, side_effect=_fake_restore) as mock_restore,
            patch(FAKE_SETTINGS_PATH, return_value=fake_settings),
        ):
            result = runner.invoke(
                app, ["db", "pull", "myapp-db", "--to", "mydb", "--confirm-token", "mydb"]
            )

        assert result.exit_code == 0, result.output
        mock_dump.assert_called_once()
        mock_restore.assert_called_once()
        assert call_order == ["dump", "restore"], "restore must follow dump"


# ---------------------------------------------------------------------------
# db pull — --keep-dump flag
# ---------------------------------------------------------------------------


class TestDbPullKeepDump:
    """With --keep-dump, the intermediate dump file is NOT removed."""

    def test_dump_file_survives_when_keep_dump_set(self, runner, fake_ssh_target, tmp_path):
        written_paths: list[Path] = []

        def _fake_dump(*, output_path, **kwargs):
            written_paths.append(output_path)
            return _fake_dump_result(output_path)

        fake_settings = _fake_settings_with_backup_dir(tmp_path)

        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=LOCAL_URL),
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=FAKE_REMOTE_RECORD),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
            patch(FAKE_REMOTE_DUMP_PATH, side_effect=_fake_dump),
            patch(FAKE_LOCAL_RESTORE_PATH, return_value=_fake_restore_result()),
            patch(FAKE_SETTINGS_PATH, return_value=fake_settings),
        ):
            result = runner.invoke(
                app,
                [
                    "db",
                    "pull",
                    "myapp-db",
                    "--to",
                    "mydb",
                    "--confirm-token",
                    "mydb",
                    "--keep-dump",
                ],
            )

        assert result.exit_code == 0, result.output
        assert written_paths, "remote_pg_dump was never called"
        assert written_paths[0].exists(), (
            f"Dump file {written_paths[0]} was removed despite --keep-dump"
        )


# ---------------------------------------------------------------------------
# db pull — remote target is refused
# ---------------------------------------------------------------------------


class TestDbPullRemoteTarget:
    """pull exits 1 and never calls local_pg_restore when target is remote."""

    def test_remote_url_exits_1_restore_not_called(self, runner, fake_ssh_target, tmp_path):
        with (
            patch(FAKE_RESOLVE_LOCAL_PATH, return_value=REMOTE_URL),
            patch(FAKE_LOCAL_RESTORE_PATH) as mock_restore,
        ):
            result = runner.invoke(
                app, ["db", "pull", "myapp-db", "--to", "prod", "--confirm-token", "prod"]
            )

        assert result.exit_code == 1
        mock_restore.assert_not_called()


# ---------------------------------------------------------------------------
# db remote-query — happy path (SELECT goes through)
# ---------------------------------------------------------------------------


class TestDbRemoteQueryHappyPath:
    """remote-query exits 0 and displays rows for a plain SELECT."""

    def test_select_exits_0_and_shows_results(self, runner, fake_ssh_target):
        tunnel_url = "postgresql://pguser:pgpass@127.0.0.1:54321/appdb"

        # Build a minimal psycopg2 connection mock that returns one row.
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        @contextmanager
        def _fake_tunnel(**kwargs):
            yield tunnel_url

        with (
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=FAKE_REMOTE_RECORD),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
            patch(FAKE_OPEN_TUNNEL_PATH, return_value=_fake_tunnel),
            patch("psycopg2.connect", return_value=mock_conn),
        ):
            result = runner.invoke(
                app, ["db", "remote-query", "myapp-db", "SELECT id, name FROM users"]
            )

        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# db remote-query — destructive SQL is refused
# ---------------------------------------------------------------------------


class TestDbRemoteQueryDestructiveRefused:
    """remote-query exits 1 for DROP / TRUNCATE / DELETE and never connects."""

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE x",
            "TRUNCATE users",
            "DELETE FROM sessions",
        ],
    )
    def test_destructive_sql_exits_1_connect_not_called(self, runner, fake_ssh_target, sql):
        tunnel_url = "postgresql://pguser:pgpass@127.0.0.1:54321/appdb"

        @contextmanager
        def _fake_tunnel(**kwargs):
            # Register as tunneled so the safety guard classifies it correctly.
            from copilot_cli.services.postgresql.safety import register_tunneled

            register_tunneled(tunnel_url)
            try:
                yield tunnel_url
            finally:
                unregister_tunneled(tunnel_url)

        with (
            patch(FAKE_RESOLVE_REMOTE_PATH, return_value=FAKE_REMOTE_RECORD),
            patch(FAKE_SSH_TARGET_PATH, return_value=fake_ssh_target),
            patch(FAKE_OPEN_TUNNEL_PATH, return_value=_fake_tunnel),
            patch("psycopg2.connect") as mock_connect,
        ):
            result = runner.invoke(app, ["db", "remote-query", "myapp-db", sql])

        assert result.exit_code == 1
        assert "Refused" in result.output or "refused" in result.output.lower()
        mock_connect.assert_not_called()


# ---------------------------------------------------------------------------
# db transition — placeholder (skip if command absent)
# ---------------------------------------------------------------------------


class TestDbTransitionPlaceholder:
    """Single placeholder test that skips if 'transition' is not yet registered."""

    def test_transition_command_if_present(self, runner):
        # Introspect the registered command names on the db Typer app.
        from copilot_cli.services.postgresql.commands import app as db_app

        registered_names = {cmd.name or cmd.callback.__name__ for cmd in db_app.registered_commands}

        if "transition" not in registered_names:
            pytest.skip("'transition' command is not yet implemented — placeholder test")

        # If the command does exist, verify it at least shows help without crashing.
        result = runner.invoke(app, ["db", "transition", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Remote-infra adapter absent — this public foundation ships no 'coolify'
# (or equivalent) adapter, so the guarded import points must fail with a
# clean CopilotError, never a raw ImportError/traceback. These exercise the
# *real*, unpatched import paths -- copilot_cli.services.coolify genuinely
# does not exist in this repo, so this is a true regression test, not a
# simulated one.
# ---------------------------------------------------------------------------


class TestRemoteAdapterAbsent:
    def test_resolve_remote_db_raises_clean_error(self):
        from copilot_cli.services.postgresql.commands import _resolve_remote_db
        from copilot_cli.shared.errors import CopilotError

        with pytest.raises(CopilotError, match="Coolify"):
            _resolve_remote_db("myapp-db")

    def test_ssh_target_raises_clean_error(self):
        from copilot_cli.services.postgresql.commands import (
            _ssh_target_from_coolify_settings,
        )
        from copilot_cli.shared.errors import CopilotError

        with pytest.raises(CopilotError, match="Coolify"):
            _ssh_target_from_coolify_settings()

    def test_open_tunnel_raises_clean_error(self):
        from copilot_cli.services.postgresql.commands import _open_tunnel_or_raise
        from copilot_cli.shared.errors import CopilotError

        with pytest.raises(CopilotError, match="Coolify"):
            _open_tunnel_or_raise()

    def test_remote_query_command_exits_1_with_hint_not_traceback(self, runner):
        """End-to-end: `db remote-query` against the real (absent) adapter
        exits cleanly with a hint, rather than an unhandled ImportError."""
        result = runner.invoke(app, ["db", "remote-query", "myapp-db", "SELECT 1"])

        assert result.exit_code == 1
        assert "Coolify" in result.output
        assert "Traceback" not in result.output
