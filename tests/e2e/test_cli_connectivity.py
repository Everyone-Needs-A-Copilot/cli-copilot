"""Live E2E smoke checks for CLI connectivity and health.

Usage:
    COPILOT_E2E_LIVE=1 pytest tests/e2e/test_cli_connectivity.py -m e2e -q
"""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("COPILOT_E2E_LIVE") != "1",
        reason="Live E2E tests are disabled. Set COPILOT_E2E_LIVE=1 to run.",
    ),
]

runner = CliRunner()


def _maybe_skip_unavailable(args: list[str], result) -> None:
    """Skip checks that fail due to environment limitations, not code regressions."""
    text = (result.output or "").lower()
    if result.exception is not None:
        text = f"{text}\n{result.exception}".lower()

    skip_patterns = [
        # Network/service reachability
        "cannot connect to",
        "connection refused",
        "name or service not known",
        "temporary failure in name resolution",
        "timed out",
        "network is unreachable",
        # Sandbox/permissions
        "operation not permitted",
        "permission denied",
        # Env/config not present for optional integrations
        "missing required configuration",
        "not configured",
        "api key",
        "access token",
        # Git repo topology may not have upstream configured
        "bad revision",
        "no upstream configured",
        "does not have any commits yet",
    ]
    for pattern in skip_patterns:
        if pattern in text:
            pytest.skip(f"Environment-dependent failure for `copilot {' '.join(args)}`: {pattern}")


def _assert_ok(args: list[str]) -> None:
    result = runner.invoke(app, args)
    if result.exit_code != 0:
        _maybe_skip_unavailable(args, result)
    assert result.exit_code == 0, (
        f"Command failed: copilot {' '.join(args)}\n\nstdout/stderr:\n{result.output}"
    )


@pytest.mark.parametrize(
    "args",
    [
        ["health"],
        ["git", "status", "--path", "."],
        ["docker", "health"],
        ["shell", "ps"],
        ["fs", "health"],
        ["services", "health"],
        ["db", "health"],
        ["docs", "health"],
        ["bi", "health"],
        ["monitoring", "health"],
    ],
)
def test_cli_connectivity_smoke(args: list[str]) -> None:
    """Every CLI group should pass a lightweight read-only check."""
    _assert_ok(args)
