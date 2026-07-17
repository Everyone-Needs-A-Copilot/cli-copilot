"""Shared test fixtures for Copilot CLI tests."""

from __future__ import annotations

import os
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
        n8n_base_url="http://localhost:5678",
        n8n_api_key="test-n8n-key",
        git_user_name="test-user",
        git_user_email="test@example.com",
        docker_socket="/var/run/docker.sock",
        shell_scripts_path="/tmp/test-scripts",
        shell_timeout=30,
        nocodb_url="http://localhost:8080",
        nocodb_api_key="test-nocodb-key",
        nocodb_base_id="test-base-id",
        database_url="postgresql://test:test@localhost:5432/main",
        nocodb_database_url="postgresql://test:test@localhost:5432/nocodb",
        n8n_database_url="postgresql://test:test@localhost:5432/n8n",
        formbricks_database_url="",
        brevo_api_key="dGVzdC1icmV2by1rZXk=",
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
