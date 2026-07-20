"""Shared test fixtures for Copilot CLI tests."""

from __future__ import annotations

import os

# Isolate the tier manifest for the test session BEFORE anything imports
# `copilot_cli.main` (which discovers services via the loader at import time).
# A developer with a live org overlay + ~/.config/copilot/copilot.layers.yml
# installed must still see the FOUNDATION's own services under test, not the
# composed org+foundation chain -- otherwise soul-conformance discovers the
# overlay's org-only services and fails on their absent foundation docs/tests.
# In clean CI no manifest exists, so this is a no-op there. Tests that exercise
# tiering set COPILOT_LAYERS_FILE explicitly (monkeypatch) and override this.
os.environ.setdefault("COPILOT_LAYERS_FILE", "/nonexistent/tier-isolation-for-tests.yml")

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app


@pytest.fixture
def runner():
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli(runner):
    """Invoke the CLI app."""

    def invoke(*args):
        return runner.invoke(app, list(args))

    return invoke


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Provide deterministic settings for all tests.

    This patches get_settings() globally so no test accidentally reads
    the real .env file or connects to live services.
    """
    if os.environ.get("COPILOT_E2E_LIVE") == "1":
        # Live E2E mode: use the real environment and real services.
        return None

    from copilot_cli.config.settings import Settings

    fake = Settings(
        git_user_name="test-user",
        git_user_email="test@example.com",
        docker_socket="/var/run/docker.sock",
        shell_scripts_path="/tmp/test-scripts",
        shell_timeout=30,
        database_url="postgresql://test:test@localhost:5432/main",
        nocodb_database_url="postgresql://test:test@localhost:5432/nocodb",
        n8n_database_url="postgresql://test:test@localhost:5432/n8n",
        formbricks_database_url="",
        allowed_volumes="/tmp,/Volumes/Dev",
        max_file_size_mb=10,
        cpu_alert_threshold=80,
        memory_alert_threshold=85,
        disk_alert_threshold=90,
        skill_paths="",
        log_level="debug",
    )
    monkeypatch.setattr("copilot_cli.config.settings.get_settings", lambda: fake)
    return fake
