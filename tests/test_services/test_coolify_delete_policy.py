"""Tests for the hardcoded delete-blocking policy on Coolify database commands.

Per project policy, destructive operations on remote Coolify-managed databases
must be refused unconditionally, regardless of --force flags or any other input.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# database delete — hard-blocked
# ---------------------------------------------------------------------------


class TestDeleteDatabasePolicy:
    POLICY_PHRASE = "not permitted to delete remote"

    def test_exit_nonzero_without_force(self, runner):
        """Command exits non-zero when invoked without --force."""
        result = runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid"])
        assert result.exit_code != 0

    def test_exit_nonzero_with_force(self, runner):
        """--force flag does not bypass the policy block."""
        result = runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid", "--force"])
        assert result.exit_code != 0

    def test_policy_message_in_output_without_force(self, runner):
        """Policy refusal phrase appears in output when no --force is given."""
        result = runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid"])
        assert self.POLICY_PHRASE in result.output

    def test_policy_message_in_output_with_force(self, runner):
        """Policy refusal phrase appears in output even when --force is passed."""
        result = runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid", "--force"])
        assert self.POLICY_PHRASE in result.output

    def test_client_delete_database_never_called(self, runner):
        """The underlying API method is never invoked."""
        mock_client = MagicMock()
        mock_client.delete_database = AsyncMock()

        with patch(
            "copilot_cli.services.coolify.main.State.get_client",
            return_value=mock_client,
        ):
            runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid", "--force"])

        mock_client.delete_database.assert_not_called()

    def test_client_delete_database_never_called_without_force(self, runner):
        """The underlying API method is never invoked even without --force."""
        mock_client = MagicMock()
        mock_client.delete_database = AsyncMock()

        with patch(
            "copilot_cli.services.coolify.main.State.get_client",
            return_value=mock_client,
        ):
            runner.invoke(app, ["coolify", "db", "delete", "some-db-uuid"])

        mock_client.delete_database.assert_not_called()


# ---------------------------------------------------------------------------
# backup delete — hard-blocked
# ---------------------------------------------------------------------------


class TestDeleteBackupPolicy:
    POLICY_PHRASE = "not permitted to delete backup"

    def test_exit_nonzero_without_force(self, runner):
        """Command exits non-zero when invoked without --force."""
        result = runner.invoke(
            app, ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid"]
        )
        assert result.exit_code != 0

    def test_exit_nonzero_with_force(self, runner):
        """--force flag does not bypass the policy block."""
        result = runner.invoke(
            app,
            ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid", "--force"],
        )
        assert result.exit_code != 0

    def test_policy_message_in_output_without_force(self, runner):
        """Policy refusal phrase appears in output when no --force is given."""
        result = runner.invoke(
            app, ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid"]
        )
        assert self.POLICY_PHRASE in result.output

    def test_policy_message_in_output_with_force(self, runner):
        """Policy refusal phrase appears in output even when --force is passed."""
        result = runner.invoke(
            app,
            ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid", "--force"],
        )
        assert self.POLICY_PHRASE in result.output

    def test_client_delete_backup_never_called(self, runner):
        """The underlying API method is never invoked."""
        mock_client = MagicMock()
        mock_client.delete_database_backup = AsyncMock()

        with patch(
            "copilot_cli.services.coolify.main.State.get_client",
            return_value=mock_client,
        ):
            runner.invoke(
                app,
                ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid", "--force"],
            )

        mock_client.delete_database_backup.assert_not_called()

    def test_client_delete_backup_never_called_without_force(self, runner):
        """The underlying API method is never invoked even without --force."""
        mock_client = MagicMock()
        mock_client.delete_database_backup = AsyncMock()

        with patch(
            "copilot_cli.services.coolify.main.State.get_client",
            return_value=mock_client,
        ):
            runner.invoke(
                app,
                ["coolify", "backup", "delete", "some-db-uuid", "some-backup-uuid"],
            )

        mock_client.delete_database_backup.assert_not_called()
