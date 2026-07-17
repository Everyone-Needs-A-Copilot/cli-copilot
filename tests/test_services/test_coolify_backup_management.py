"""Tests for Coolify backup scheduling and structured-output safety."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.coolify.core.api_client import CoolifyClient
from copilot_cli.services.coolify.core.exceptions import APIError
from copilot_cli.services.coolify.monitoring.http_probes import public_probe_url
from copilot_cli.services.coolify.monitoring.log_analyzer import extract_log_text
from copilot_cli.services.coolify.output.json_out import redact_sensitive_data

DB_UUID = "a" * 24
BACKUP_UUID = "b" * 24


@pytest.mark.asyncio
async def test_backup_list_filters_polymorphic_id_collision() -> None:
    client = MagicMock(spec=CoolifyClient)
    client.get = AsyncMock(
        return_value=[
            {
                "uuid": "postgres-backup",
                "database_type": "App\\Models\\StandalonePostgresql",
            },
            {"uuid": "mysql-backup", "database_type": "App\\Models\\StandaloneMysql"},
        ]
    )
    client.get_database = AsyncMock(
        return_value={"database_type": "standalone-postgresql"}
    )

    result = await CoolifyClient.list_database_backups(client, DB_UUID)

    assert result == [
        {
            "uuid": "postgres-backup",
            "database_type": "App\\Models\\StandalonePostgresql",
        }
    ]


@pytest.mark.asyncio
async def test_backup_detail_uses_collection_endpoint() -> None:
    client = MagicMock(spec=CoolifyClient)
    client.list_database_backups = AsyncMock(
        return_value=[{"uuid": BACKUP_UUID, "frequency": "0 3 * * *"}]
    )

    result = await CoolifyClient.get_database_backup(client, DB_UUID, BACKUP_UUID)

    assert result["frequency"] == "0 3 * * *"


@pytest.mark.asyncio
async def test_backup_detail_raises_when_missing() -> None:
    client = MagicMock(spec=CoolifyClient)
    client.list_database_backups = AsyncMock(return_value=[])

    with pytest.raises(APIError, match="not found"):
        await CoolifyClient.get_database_backup(client, DB_UUID, BACKUP_UUID)


@pytest.mark.asyncio
async def test_execution_envelope_is_unwrapped() -> None:
    client = MagicMock(spec=CoolifyClient)
    client.get = AsyncMock(return_value={"executions": [{"uuid": "execution-1"}]})

    result = await CoolifyClient.list_backup_executions(client, DB_UUID, BACKUP_UUID)

    assert result == [{"uuid": "execution-1"}]


def test_create_backup_uses_bounded_local_retention() -> None:
    runner = CliRunner()
    client = MagicMock()
    client.create_database_backup = AsyncMock(return_value={"uuid": BACKUP_UUID})

    with patch("copilot_cli.services.coolify.main.State.get_client", return_value=client):
        result = runner.invoke(
            app,
            ["coolify", "backup", "create", DB_UUID, "0 3 * * *"],
        )

    assert result.exit_code == 0, result.output
    client.create_database_backup.assert_awaited_once_with(
        DB_UUID,
        {
            "frequency": "0 3 * * *",
            "enabled": True,
            "save_s3": False,
            "database_backup_retention_amount_locally": 7,
            "database_backup_retention_days_locally": 7,
            "database_backup_retention_max_storage_locally": 0,
            "backup_now": False,
            "timeout": 3600,
        },
    )


def test_update_backup_changes_only_requested_local_fields() -> None:
    runner = CliRunner()
    client = MagicMock()
    client.update_database_backup = AsyncMock(return_value={"message": "updated"})

    with patch("copilot_cli.services.coolify.main.State.get_client", return_value=client):
        result = runner.invoke(
            app,
            [
                "coolify",
                "backup",
                "update",
                DB_UUID,
                BACKUP_UUID,
                "--keep-local",
                "7",
                "--retention-days-local",
                "7",
            ],
        )

    assert result.exit_code == 0, result.output
    client.update_database_backup.assert_awaited_once_with(
        DB_UUID,
        BACKUP_UUID,
        {
            "database_backup_retention_amount_locally": 7,
            "database_backup_retention_days_locally": 7,
        },
    )


def test_structured_output_redacts_nested_server_secrets_without_mutating_input() -> None:
    data = {
        "settings": {
            "sentinel_token": "secret-token",
            "is_sentinel_enabled": True,
            "private_key_id": 3,
        },
        "servers": [
            {
                "logdrain_axiom_api_key": "axiom-secret",
                "manual_webhook_secret_github": "webhook-secret",
                "http_basic_auth_password": "password",
            }
        ],
    }

    redacted = redact_sensitive_data(data)

    assert redacted["settings"]["sentinel_token"] == "[REDACTED]"
    assert redacted["settings"]["private_key_id"] == 3
    assert redacted["servers"][0]["logdrain_axiom_api_key"] == "[REDACTED]"
    assert redacted["servers"][0]["manual_webhook_secret_github"] == "[REDACTED]"
    assert redacted["servers"][0]["http_basic_auth_password"] == "[REDACTED]"
    assert data["settings"]["sentinel_token"] == "secret-token"


def test_public_probe_url_strips_coolify_internal_port() -> None:
    assert (
        public_probe_url("https://staging.app.example.com:3000")
        == "https://staging.app.example.com"
    )
    assert public_probe_url("app.example.com:8080/path") == "https://app.example.com/path"


def test_extract_log_text_unwraps_coolify_log_response() -> None:
    logs = "line one\nERROR: line two"

    assert extract_log_text({"logs": logs}) == logs
    assert extract_log_text(["line one", "line two"]) == "line one\nline two"
