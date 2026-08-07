"""Tests for the top-level `copilot health` command and its check registry.

Covers the health-completion work (git, shell, infisical -- and, historically,
discord -- were the groups missing from `copilot health`; discord has since
moved to the org-specific `-internal` tier). The registry itself
(`_collect_health_checks`) is tested without executing any check, so this
file makes zero real network/subprocess/filesystem calls -- consistent
with SOUL.md's "Lazy & Mockable" principle.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import _collect_health_checks, app
from copilot_cli.shared.output import set_json_mode

EXPECTED_SERVICES = {
    "docker",
    "filesystem",
    "system_services",
    "postgresql",
    "document",
    "bi",
    "monitoring",
    "skill",
    "uspto",
    "git",
    "shell",
    "infisical",
}


@pytest.fixture
def runner():
    return CliRunner()


# ------------------------------------------------------------------ #
# Registry -- structural coverage, zero execution
# ------------------------------------------------------------------ #


class TestHealthRegistry:
    """Every group must be registered; nothing here executes a check."""

    def test_all_12_groups_are_registered(self):
        checks, skipped = _collect_health_checks()
        names = {name for name, _ in checks} | set(skipped)
        assert names == EXPECTED_SERVICES

    def test_the_completed_groups_are_checked_not_skipped(self):
        checks, skipped = _collect_health_checks()
        checked_names = {name for name, _ in checks}
        for name in ("git", "shell", "infisical"):
            assert name in checked_names
            assert name not in skipped


class TestGitAndShellHealthWiring:
    """The registered git/shell checks are the real client.health() functions."""

    def test_git_check_is_client_health(self):
        from copilot_cli.services.git.client import health as git_health

        checks, _ = _collect_health_checks()
        assert dict(checks)["git"] is git_health

    def test_shell_check_is_client_health(self):
        from copilot_cli.services.shell.client import health as shell_health

        checks, _ = _collect_health_checks()
        assert dict(checks)["shell"] is shell_health


class TestInfisicalHealthWiring:
    """The registered infisical check authenticates via InfisicalClient."""

    def test_infisical_check_reports_unhealthy_without_credentials(self):
        fake_settings = MagicMock(client_id="", client_secret="", base_url="https://x")

        with patch(
            "copilot_cli.services.infisical.core.config.load_settings",
            return_value=fake_settings,
        ):
            checks, _ = _collect_health_checks()
            result = dict(checks)["infisical"]()

        assert result["healthy"] is False
        assert "INFISICAL_CLIENT_ID" in result["error"]

    def test_infisical_check_reports_healthy_with_valid_credentials(self):
        fake_settings = MagicMock(
            client_id="id", client_secret="secret", base_url="https://secrets.example.com"
        )
        fake_client = MagicMock()
        fake_client.validate_connection = AsyncMock(return_value="my-identity")
        fake_client.close = AsyncMock()

        with (
            patch(
                "copilot_cli.services.infisical.core.config.load_settings",
                return_value=fake_settings,
            ),
            patch(
                "copilot_cli.services.infisical.core.api_client.InfisicalClient",
                return_value=fake_client,
            ),
        ):
            checks, _ = _collect_health_checks()
            result = dict(checks)["infisical"]()

        assert result == {"healthy": True, "identity": "my-identity"}
        fake_client.close.assert_awaited_once()

    def test_infisical_check_reports_unhealthy_on_auth_failure(self):
        fake_settings = MagicMock(
            client_id="id", client_secret="secret", base_url="https://secrets.example.com"
        )
        fake_client = MagicMock()
        fake_client.validate_connection = AsyncMock(side_effect=RuntimeError("auth failed"))
        fake_client.close = AsyncMock()

        with (
            patch(
                "copilot_cli.services.infisical.core.config.load_settings",
                return_value=fake_settings,
            ),
            patch(
                "copilot_cli.services.infisical.core.api_client.InfisicalClient",
                return_value=fake_client,
            ),
        ):
            checks, _ = _collect_health_checks()
            infisical_check = dict(checks)["infisical"]
            with pytest.raises(RuntimeError, match="auth failed"):
                infisical_check()

        # The top-level `health` command's own try/except is what turns
        # this into an "unhealthy" line -- verified end to end below.
        fake_client.close.assert_awaited_once()


# ------------------------------------------------------------------ #
# CLI -- `copilot --json health` prints one line per registered group
# ------------------------------------------------------------------ #


class TestHealthCommandOutputsAllGroups:
    def test_json_health_lists_all_12_services(self, runner):
        """`copilot --json health` reports one line per registered group.

        Every check function is stubbed so this exercises only the CLI's
        own collect -> iterate -> print_health wiring, not any live
        integration.
        """
        stub_checks = [(name, lambda: {"healthy": True}) for name in EXPECTED_SERVICES]

        try:
            with patch(
                "copilot_cli.main._collect_health_checks",
                return_value=(stub_checks, []),
            ):
                result = runner.invoke(app, ["--json", "health"])
        finally:
            # The global --json flag is process-wide state (see main.py's
            # eager callback); reset it so later tests get table output.
            set_json_mode(False)

        assert result.exit_code == 0
        services = set()
        for line in result.output.strip().splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            data = json.loads(line)
            services.add(data["service"])
            assert data["status"] == "healthy"

        assert services == EXPECTED_SERVICES

    def test_json_health_reports_infisical_auth_failure_as_unhealthy(self, runner):
        """A raised exception from a check is caught and printed as unhealthy."""

        def _raise():
            raise RuntimeError("auth failed")

        try:
            with patch(
                "copilot_cli.main._collect_health_checks",
                return_value=([("infisical", _raise)], []),
            ):
                result = runner.invoke(app, ["--json", "health"])
        finally:
            set_json_mode(False)

        assert result.exit_code == 0
        line = next(ln for ln in result.output.strip().splitlines() if ln.strip().startswith("{"))
        data = json.loads(line)
        assert data == {
            "service": "infisical",
            "status": "unhealthy",
            "details": {"error": "auth failed"},
        }
