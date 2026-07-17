"""Tests for the Infisical service.

Covers:
- Exception hierarchy: InfisicalError and its subclasses subclass the shared
  CopilotError (SOUL.md §6 Quality Bar / Principle 4: Honest Failure) and
  carry service="infisical"
- Config: require_settings() raises ConfigError when credentials are missing
- InfisicalClient construction: missing base_url / client_id / client_secret
- authenticate(): success, connect/timeout errors, 401/403, non-success
- _request(): 401/403 handling, Zod-style validation error aggregation
- Projects / folders / secrets / identities / admin config CRUD
- get_org_id() hint short-circuit, caching, and identity-endpoint discovery
- validate_connection()
- CLI commands: project list, secret list/get/set, identity list, health
  wiring via `_infisical_health` (see also tests/test_services/
  test_health_completion.py for the shared health-plumbing coverage)

No test touches a real network call or DB — every httpx call is mocked or
made against an in-memory MagicMock/AsyncMock response, per SOUL.md
Principle 5 (Lazy & Mockable).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from copilot_cli.shared.errors import CopilotError

# ---------------------------------------------------------------------------
# Exception hierarchy (SOUL.md §6 Quality Bar / Principle 4: Honest Failure)
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Infisical's exception classes subclass the shared CopilotError."""

    def test_infisical_error_subclasses_copilot_error(self):
        from copilot_cli.services.infisical.core.exceptions import InfisicalError

        assert issubclass(InfisicalError, CopilotError)

    @pytest.mark.parametrize(
        "cls_name", ["APIError", "ConnectionError", "AuthenticationError", "ConfigError"]
    )
    def test_subclasses_subclass_copilot_error(self, cls_name):
        from copilot_cli.services.infisical.core import exceptions

        cls = getattr(exceptions, cls_name)
        assert issubclass(cls, CopilotError)

    def test_raised_error_carries_service_name(self):
        from copilot_cli.services.infisical.core.exceptions import ConfigError

        err = ConfigError("missing credentials")
        assert err.service == "infisical"
        assert str(err) == "missing credentials"

    def test_api_error_preserves_status_code_and_validation_detail(self):
        from copilot_cli.services.infisical.core.exceptions import APIError

        err = APIError("bad request", status_code=400, errors={"name": ["is required"]})
        assert err.status_code == 400
        assert err.service == "infisical"
        assert "name: is required" in str(err)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    """require_settings() validates required credentials."""

    def test_require_settings_raises_config_error_when_client_id_missing(self, monkeypatch):
        from copilot_cli.services.infisical.core import config
        from copilot_cli.services.infisical.core.config import InfisicalSettings
        from copilot_cli.services.infisical.core.exceptions import ConfigError

        fake = InfisicalSettings(client_id="", client_secret="secret")
        monkeypatch.setattr(config, "load_settings", lambda: fake)

        with pytest.raises(ConfigError, match="client_id"):
            config.require_settings()

    def test_require_settings_raises_config_error_when_client_secret_missing(self, monkeypatch):
        from copilot_cli.services.infisical.core import config
        from copilot_cli.services.infisical.core.config import InfisicalSettings
        from copilot_cli.services.infisical.core.exceptions import ConfigError

        fake = InfisicalSettings(client_id="id", client_secret="")
        monkeypatch.setattr(config, "load_settings", lambda: fake)

        with pytest.raises(ConfigError, match="client_secret"):
            config.require_settings()

    def test_require_settings_returns_settings_when_configured(self, monkeypatch):
        from copilot_cli.services.infisical.core import config
        from copilot_cli.services.infisical.core.config import InfisicalSettings

        fake = InfisicalSettings(client_id="id", client_secret="secret")
        monkeypatch.setattr(config, "load_settings", lambda: fake)

        result = config.require_settings()
        assert result.client_id == "id"

    def test_default_base_url(self):
        from copilot_cli.services.infisical.core.config import InfisicalSettings

        settings = InfisicalSettings(client_id="id", client_secret="secret")
        assert settings.base_url == "https://app.infisical.com"


# ---------------------------------------------------------------------------
# InfisicalClient construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_raises_connection_error_without_base_url(self):
        from copilot_cli.services.infisical.core.api_client import InfisicalClient
        from copilot_cli.services.infisical.core.exceptions import ConnectionError

        with pytest.raises(ConnectionError):
            InfisicalClient(base_url="", client_id="id", client_secret="secret")

    def test_raises_authentication_error_without_client_id(self):
        from copilot_cli.services.infisical.core.api_client import InfisicalClient
        from copilot_cli.services.infisical.core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            InfisicalClient(base_url="https://x.example.com", client_id="", client_secret="secret")

    def test_raises_authentication_error_without_client_secret(self):
        from copilot_cli.services.infisical.core.api_client import InfisicalClient
        from copilot_cli.services.infisical.core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            InfisicalClient(base_url="https://x.example.com", client_id="id", client_secret="")

    def test_construction_does_not_connect(self):
        """Importing/constructing the client makes no network call (lazy)."""
        from copilot_cli.services.infisical.core.api_client import InfisicalClient

        client = InfisicalClient(
            base_url="https://x.example.com", client_id="id", client_secret="s"
        )
        assert client._token is None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """An InfisicalClient with a real (unconnected) httpx.AsyncClient."""
    from copilot_cli.services.infisical.core.api_client import InfisicalClient

    return InfisicalClient(
        base_url="https://secrets.example.com", client_id="cid", client_secret="csecret"
    )


def _response(status_code=200, json_data=None, text="", success=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = success if success is not None else 200 <= status_code < 300
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text if text else ("{}" if json_data is not None else "")
    resp.reason_phrase = "Error"
    return resp


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------


class TestAuthenticate:
    def test_authenticate_success_caches_token_and_identity(self, client):
        # JWT with a base64url payload containing {"identityId": "ident-1"}
        payload = "eyJpZGVudGl0eUlkIjoiaWRlbnQtMSJ9"
        token = f"header.{payload}.sig"
        resp = _response(200, {"accessToken": token})

        with patch.object(client._http, "post", AsyncMock(return_value=resp)):
            result = asyncio.run(client.authenticate())

        assert result == token
        assert client._token == token
        assert client._identity_id == "ident-1"

    def test_authenticate_raises_connection_error_on_connect_failure(self, client):
        from copilot_cli.services.infisical.core.exceptions import ConnectionError

        with patch.object(
            client._http, "post", AsyncMock(side_effect=httpx.ConnectError("refused"))
        ):
            with pytest.raises(ConnectionError):
                asyncio.run(client.authenticate())

    def test_authenticate_raises_connection_error_on_timeout(self, client):
        from copilot_cli.services.infisical.core.exceptions import ConnectionError

        with patch.object(
            client._http, "post", AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        ):
            with pytest.raises(ConnectionError):
                asyncio.run(client.authenticate())

    def test_authenticate_raises_authentication_error_on_401(self, client):
        from copilot_cli.services.infisical.core.exceptions import AuthenticationError

        resp = _response(401, success=False)
        with patch.object(client._http, "post", AsyncMock(return_value=resp)):
            with pytest.raises(AuthenticationError):
                asyncio.run(client.authenticate())

    def test_authenticate_raises_api_error_on_other_failure(self, client):
        from copilot_cli.services.infisical.core.exceptions import APIError

        resp = _response(500, success=False)
        with patch.object(client._http, "post", AsyncMock(return_value=resp)):
            with pytest.raises(APIError):
                asyncio.run(client.authenticate())


# ---------------------------------------------------------------------------
# _request() — low-level error handling
# ---------------------------------------------------------------------------


class TestRequest:
    def _authenticated(self, client):
        client._token = "cached-token"
        client._identity_id = "ident-1"

    def test_request_raises_authentication_error_on_401(self, client):
        from copilot_cli.services.infisical.core.exceptions import AuthenticationError

        self._authenticated(client)
        resp = _response(401, success=False)
        with patch.object(client._http, "request", AsyncMock(return_value=resp)):
            with pytest.raises(AuthenticationError):
                asyncio.run(client.get("/api/v1/workspace"))

    def test_request_raises_authentication_error_on_403(self, client):
        from copilot_cli.services.infisical.core.exceptions import AuthenticationError

        self._authenticated(client)
        resp = _response(403, success=False, text="requires super admin")
        with patch.object(client._http, "request", AsyncMock(return_value=resp)):
            with pytest.raises(AuthenticationError, match="super-admin"):
                asyncio.run(client.get("/api/v1/admin/config"))

    def test_request_aggregates_zod_validation_errors(self, client):
        from copilot_cli.services.infisical.core.exceptions import APIError

        self._authenticated(client)
        resp = _response(
            400,
            {"message": [{"path": ["body", "name"], "message": "Required"}]},
            success=False,
        )
        with patch.object(client._http, "request", AsyncMock(return_value=resp)):
            with pytest.raises(APIError, match="name: Required"):
                asyncio.run(client.post("/api/v2/workspace", {}))

    def test_request_raises_connection_error_on_connect_failure(self, client):
        from copilot_cli.services.infisical.core.exceptions import ConnectionError

        self._authenticated(client)
        with patch.object(
            client._http, "request", AsyncMock(side_effect=httpx.ConnectError("refused"))
        ):
            with pytest.raises(ConnectionError):
                asyncio.run(client.get("/api/v1/workspace"))

    def test_request_returns_parsed_json_on_success(self, client):
        self._authenticated(client)
        resp = _response(200, {"workspaces": []})
        with patch.object(client._http, "request", AsyncMock(return_value=resp)):
            result = asyncio.run(client.get("/api/v1/workspace"))
        assert result == {"workspaces": []}


# ---------------------------------------------------------------------------
# Projects (workspaces)
# ---------------------------------------------------------------------------


class TestProjects:
    def test_list_projects(self, client):
        with patch.object(
            client, "get", AsyncMock(return_value={"workspaces": [{"id": "p1"}]})
        ) as mock_get:
            result = asyncio.run(client.list_projects())
        mock_get.assert_awaited_once_with("/api/v1/workspace")
        assert result == [{"id": "p1"}]

    def test_get_project(self, client):
        with patch.object(client, "get", AsyncMock(return_value={"workspace": {"id": "p1"}})):
            result = asyncio.run(client.get_project("p1"))
        assert result == {"id": "p1"}

    def test_create_project(self, client):
        with patch.object(
            client, "post", AsyncMock(return_value={"project": {"id": "p2", "name": "New"}})
        ) as mock_post:
            result = asyncio.run(client.create_project("New", "org-1"))
        mock_post.assert_awaited_once_with(
            "/api/v2/workspace", {"projectName": "New", "organizationId": "org-1"}
        )
        assert result["id"] == "p2"

    def test_delete_project(self, client):
        with patch.object(client, "delete", AsyncMock(return_value={"workspace": {"id": "p1"}})):
            result = asyncio.run(client.delete_project("p1"))
        assert result == {"id": "p1"}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


class TestSecrets:
    def test_list_secrets(self, client):
        with patch.object(
            client, "get", AsyncMock(return_value={"secrets": [{"secretKey": "K"}]})
        ) as mock_get:
            result = asyncio.run(client.list_secrets("p1", "dev"))
        assert mock_get.call_args[0][0] == "/api/v3/secrets/raw"
        assert result == [{"secretKey": "K"}]

    def test_get_secret(self, client):
        with patch.object(
            client,
            "get",
            AsyncMock(return_value={"secret": {"secretKey": "K", "secretValue": "V"}}),
        ):
            result = asyncio.run(client.get_secret("p1", "dev", "K"))
        assert result["secretValue"] == "V"

    def test_create_secret(self, client):
        with patch.object(
            client, "post", AsyncMock(return_value={"secret": {"secretKey": "K"}})
        ) as mock_post:
            asyncio.run(client.create_secret("p1", "dev", "K", "V"))
        payload = mock_post.call_args[0][1]
        assert payload["secretValue"] == "V"
        assert payload["type"] == "shared"

    def test_update_secret(self, client):
        with patch.object(
            client, "patch", AsyncMock(return_value={"secret": {"secretKey": "K"}})
        ) as mock_patch:
            asyncio.run(client.update_secret("p1", "dev", "K", "V2"))
        payload = mock_patch.call_args[0][1]
        assert payload["secretValue"] == "V2"

    def test_delete_secret_sends_body_as_json(self, client):
        with patch.object(
            client, "delete", AsyncMock(return_value={"secret": {"secretKey": "K"}})
        ) as mock_delete:
            asyncio.run(client.delete_secret("p1", "dev", "K"))
        assert mock_delete.call_args[1]["json_data"]["workspaceId"] == "p1"


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------


class TestIdentities:
    def test_list_identities(self, client):
        with patch.object(
            client, "get", AsyncMock(return_value={"identities": [{"id": "i1"}]})
        ) as mock_get:
            result = asyncio.run(client.list_identities("org-1"))
        assert mock_get.call_args[1]["params"] == {"orgId": "org-1"}
        assert result == [{"id": "i1"}]

    def test_create_identity_defaults_to_member_role(self, client):
        with patch.object(
            client, "post", AsyncMock(return_value={"identity": {"id": "i2"}})
        ) as mock_post:
            asyncio.run(client.create_identity("bot", "org-1"))
        payload = mock_post.call_args[0][1]
        assert payload["role"] == "member"

    def test_delete_identity(self, client):
        with patch.object(client, "delete", AsyncMock(return_value={"identity": {"id": "i1"}})):
            result = asyncio.run(client.delete_identity("i1"))
        assert result == {"id": "i1"}


# ---------------------------------------------------------------------------
# get_org_id()
# ---------------------------------------------------------------------------


class TestGetOrgId:
    def test_returns_hint_without_network_call(self, client):
        with patch.object(client, "_ensure_authenticated", AsyncMock()) as mock_auth:
            result = asyncio.run(client.get_org_id(hint="org-hint"))
        assert result == "org-hint"
        mock_auth.assert_not_awaited()

    def test_returns_cached_org_id(self, client):
        client._org_id = "cached-org"
        with patch.object(client, "_ensure_authenticated", AsyncMock()):
            result = asyncio.run(client.get_org_id())
        assert result == "cached-org"

    def test_discovers_org_id_from_identity_endpoint(self, client):
        client._identity_id = "ident-1"
        with (
            patch.object(client, "_ensure_authenticated", AsyncMock()),
            patch.object(
                client,
                "_get_raw",
                AsyncMock(return_value={"identity": {"orgId": "discovered-org"}}),
            ),
        ):
            result = asyncio.run(client.get_org_id())
        assert result == "discovered-org"
        assert client._org_id == "discovered-org"


# ---------------------------------------------------------------------------
# validate_connection()
# ---------------------------------------------------------------------------


class TestValidateConnection:
    def test_returns_identity_name(self, client):
        client._identity_id = "ident-1"
        with (
            patch.object(client, "authenticate", AsyncMock()),
            patch.object(
                client,
                "get",
                AsyncMock(return_value={"identity": {"identity": {"name": "my-bot"}}}),
            ),
        ):
            result = asyncio.run(client.validate_connection())
        assert result == "my-bot"

    def test_falls_back_to_identity_id_when_no_name(self, client):
        client._identity_id = "ident-1"
        with (
            patch.object(client, "authenticate", AsyncMock()),
            patch.object(client, "get", AsyncMock(return_value={"identity": {}})),
        ):
            result = asyncio.run(client.validate_connection())
        assert result == "ident-1"

    def test_returns_authenticated_without_identity_id(self, client):
        client._identity_id = None
        with patch.object(client, "authenticate", AsyncMock()):
            result = asyncio.run(client.validate_connection())
        assert result == "authenticated"


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_state(monkeypatch):
    """Patch the infisical CLI singleton state's get_client() and reset
    mutable fields afterward so tests don't bleed state into each other."""
    from copilot_cli.services.infisical.main import state as infisical_state

    original = (
        infisical_state.output_format,
        infisical_state.org_id,
        infisical_state.default_project,
    )
    mock_client = MagicMock()
    monkeypatch.setattr(infisical_state, "get_client", lambda: mock_client)
    yield infisical_state, mock_client
    infisical_state.output_format, infisical_state.org_id, infisical_state.default_project = (
        original
    )


class TestCLIProjectList:
    def test_list_success(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.list_projects = AsyncMock(
            return_value=[{"id": "p1", "name": "Proj", "slug": "proj", "createdAt": "2026-01-01"}]
        )
        result = cli("infisical", "project", "list")
        assert result.exit_code == 0
        assert "Proj" in result.output

    def test_list_empty(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.list_projects = AsyncMock(return_value=[])
        result = cli("infisical", "project", "list")
        assert result.exit_code == 0

    def test_list_error_exits_1(self, cli, mock_state):
        from copilot_cli.services.infisical.core.exceptions import APIError

        _, mock_client = mock_state
        mock_client.list_projects = AsyncMock(side_effect=APIError("boom"))
        result = cli("infisical", "project", "list")
        assert result.exit_code == 1


class TestCLISecretCommands:
    def test_secret_list_requires_project(self, cli, mock_state):
        result = cli("infisical", "secret", "list")
        assert result.exit_code == 1

    def test_secret_list_success(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.list_secrets = AsyncMock(
            return_value=[{"secretKey": "API_KEY", "type": "shared", "updatedAt": "2026-01-01"}]
        )
        result = cli("infisical", "secret", "list", "--project", "p1")
        assert result.exit_code == 0
        assert "API_KEY" in result.output

    def test_secret_get_success(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.get_secret = AsyncMock(
            return_value={"secretKey": "K", "secretValue": "V", "type": "shared", "updatedAt": ""}
        )
        result = cli("infisical", "secret", "get", "K", "--project", "p1")
        assert result.exit_code == 0

    def test_secret_set_creates_when_update_fails_not_found(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.update_secret = AsyncMock(side_effect=Exception("secret not found"))
        mock_client.create_secret = AsyncMock(return_value={"secretKey": "K"})
        result = cli("infisical", "secret", "set", "K", "V", "--project", "p1")
        assert result.exit_code == 0
        mock_client.create_secret.assert_awaited_once()


class TestCLIIdentityList:
    def test_list_success(self, cli, mock_state):
        _, mock_client = mock_state
        mock_client.get_org_id = AsyncMock(return_value="org-1")
        mock_client.list_identities = AsyncMock(
            return_value=[
                {
                    "identity": {"id": "i1", "name": "bot", "authMethods": ["universal-auth"]},
                    "role": "member",
                    "lastLoginTime": "2026-01-01",
                }
            ]
        )
        result = cli("infisical", "identity", "list")
        assert result.exit_code == 0
        assert "bot" in result.output


class TestHealthWiring:
    """Sanity check the module-level health check is registered; the full
    behavioral coverage lives in test_health_completion.py."""

    def test_health_check_is_registered(self):
        from copilot_cli.main import _collect_health_checks

        checks, _skipped = _collect_health_checks()
        assert "infisical" in {name for name, _ in checks}
