from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

import copilot_cli.services.infisical.commands.access as access
from copilot_cli.config.broker_auth import AccessGrant, BrokerConfig
from copilot_cli.services.infisical.core.exceptions import AuthenticationError


class _Client:
    negative_result = "denied"

    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def list_secrets(self, project, env, path):
        del project, env
        if path == "/shared":
            return [{"secretKey": "A", "secretValue": "must-not-leak"}]
        if self.negative_result == "denied":
            raise AuthenticationError("Access denied — check identity permissions")
        if self.negative_result == "filtered":
            return []
        return [{"secretKey": "CANARY", "secretValue": "must-not-leak"}]

    async def close(self):
        pass


@pytest.fixture
def installed(monkeypatch):
    reports = []
    settings = SimpleNamespace(broker_url="https://access.example.test", base_url="https://x")
    monkeypatch.setattr(access, "load_settings", lambda: settings)
    monkeypatch.setattr(
        access,
        "broker_config",
        lambda value: BrokerConfig(
            broker_url=value.broker_url,
            issuer=value.broker_url,
            audience=value.base_url,
            organization="Example-Org",
            scope="shared",
            infisical_url=value.base_url,
            public_key_path=Path("/unused"),
            auth_root=Path("/unused"),
        ),
    )

    async def _grant(_config):
        return AccessGrant("short-lived", "identity", 9_999_999_999)

    monkeypatch.setattr(access, "acquire_access_grant", _grant)
    monkeypatch.setattr(access, "InfisicalClient", _Client)
    monkeypatch.setattr(access, "_render", reports.append)
    return reports


def test_verify_proves_positive_read_and_negative_denial_without_secret_data(installed):
    _Client.negative_result = "denied"
    access.verify("workspace", "prod", "/shared", "/denied", "shared")

    assert installed == [
        {
            "schema_version": "1.0",
            "result": "ready",
            "detail": "Shared access is ready and limited to the approved path.",
            "auth_mode": "github-broker",
            "positive_read": True,
            "negative_denied": True,
            "secret_count": 1,
            "read_only": True,
        }
    ]
    assert "must-not-leak" not in str(installed)


def test_verify_fails_when_negative_path_is_readable(installed):
    _Client.negative_result = "readable"
    with pytest.raises(typer.Exit):
        access.verify("workspace", "prod", "/shared", "/denied", "shared")
    assert installed[0]["result"] == "unsafe"
    assert installed[0]["read_only"] is False


def test_verify_accepts_infisical_filtered_empty_canary_response(installed):
    _Client.negative_result = "filtered"

    access.verify("workspace", "prod", "/shared", "/denied", "shared")

    assert installed[0]["result"] == "ready"
    assert installed[0]["negative_denied"] is True
    assert installed[0]["read_only"] is True


def test_verify_refuses_unprovable_root_scope(installed):
    _Client.negative_result = "denied"
    with pytest.raises(typer.Exit):
        access.verify("workspace", "prod", "/", "/denied", "shared")
    assert installed[0]["result"] == "invalid-config"
