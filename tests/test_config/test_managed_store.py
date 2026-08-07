"""Unit tests for `config/managed_store.py` -- rung 1's Infisical backend.

Covers the contract `secrets_ladder._rung_managed_store` depends on: dormant
(no network) until a tier declares a store, recursion-safe on bootstrap names,
resolves a named secret from the store, and falls through cleanly on every miss
(absent name, unreachable endpoint, missing bootstrap creds). No test touches
the network -- `InfisicalClient` is replaced with a fake.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import copilot_cli.config.managed_store as ms
from copilot_cli.config.layers import CliLayer
from copilot_cli.config.managed_store import StoreUnavailable, resolve_from_store
from copilot_cli.services.infisical.core.exceptions import (
    AuthenticationError,
)
from copilot_cli.services.infisical.core.exceptions import (
    ConnectionError as InfisicalConnectionError,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    ms._SECRET_CACHE.clear()
    yield
    ms._SECRET_CACHE.clear()


@pytest.fixture(autouse=True)
def _isolate_token_cache(tmp_path, monkeypatch):
    """Keep the on-disk token cache out of the real ~/.cache during tests."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    """Force bootstrap creds to come from the layer `.env`, never this
    machine's real keychain -- deterministic across dev boxes."""
    from copilot_cli.config.secrets_ladder import _SecretRungUnavailable

    def _unavailable(name, chain):
        raise _SecretRungUnavailable("keychain disabled in test")

    monkeypatch.setattr("copilot_cli.config.secrets_ladder._rung_keychain", _unavailable)


def _layer(tmp: Path, env_text: str, layer_id: str = "org", rank: int = 30) -> CliLayer:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / ".env").write_text(env_text)
    return CliLayer(id=layer_id, role="org", rank=rank, repo="r", ref="main", auth="anon", root=tmp)


_STORE_ENV = (
    "INFISICAL_BASE_URL=https://secrets.example.com\n"
    "INFISICAL_WORKSPACE_ID=ws-123\n"
    "INFISICAL_ENVIRONMENT=prod\n"
    "INFISICAL_CLIENT_ID=cid\n"
    "INFISICAL_CLIENT_SECRET=csecret\n"
)


class _FakeClient:
    """Async stand-in for InfisicalClient. `secrets` / `raises` are set per test
    via `install()`. Counts `list_secrets` calls to prove caching."""

    secrets: list[dict] = []
    raises: Exception | None = None
    calls: int = 0

    def __init__(self, base_url, client_id, client_secret, timeout=30.0):
        self.base_url = base_url
        self._token = None  # mirrors the real client; _fetch_all reads/sets it

    async def list_secrets(self, workspace, environment, secret_path="/"):
        type(self).calls += 1
        if type(self).raises is not None:
            raise type(self).raises
        return type(self).secrets

    async def close(self):
        pass


def _install_fake(monkeypatch, secrets=None, raises=None):
    _FakeClient.secrets = secrets or []
    _FakeClient.raises = raises
    _FakeClient.calls = 0
    monkeypatch.setattr(
        "copilot_cli.services.infisical.core.api_client.InfisicalClient", _FakeClient
    )
    return _FakeClient


class _ExplodingClient:
    def __init__(self, *a, **k):
        raise AssertionError("InfisicalClient must NOT be constructed when the store is dormant")


class TestDormant:
    def test_no_workspace_means_no_network(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient", _ExplodingClient
        )
        layer = _layer(tmp_path, "INFISICAL_BASE_URL=https://x\n")  # no WORKSPACE_ID
        with pytest.raises(StoreUnavailable, match="no layer declares"):
            resolve_from_store("DISCORD_BOT_TOKEN", [layer])

    def test_empty_chain_is_dormant(self):
        with pytest.raises(StoreUnavailable):
            resolve_from_store("ANY", [])


class TestRecursionGuard:
    @pytest.mark.parametrize(
        "name",
        [
            "INFISICAL_CLIENT_ID",
            "INFISICAL_CLIENT_SECRET",
            "INFISICAL_BASE_URL",
            "INFISICAL_WORKSPACE_ID",
            "INFISICAL_ENVIRONMENT",
            "INFISICAL_SECRET_PATH",
        ],
    )
    def test_bootstrap_names_never_hit_the_store(self, tmp_path, monkeypatch, name):
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient", _ExplodingClient
        )
        layer = _layer(tmp_path, _STORE_ENV)  # store IS configured
        with pytest.raises(StoreUnavailable, match="store config/bootstrap"):
            resolve_from_store(name, [layer])


class TestResolution:
    def test_broker_configuration_never_requires_or_falls_back_to_universal_auth(
        self, tmp_path, monkeypatch
    ):
        from copilot_cli.config.broker_auth import AccessGrant

        observed: dict[str, object] = {}

        async def _grant(config, force_refresh=False):
            observed["config"] = config
            observed["force_refresh"] = force_refresh
            return AccessGrant("short-lived-token", "identity-shared", 9_999_999_999)

        class _BrokerClient:
            def __init__(self, **kwargs):
                observed["client"] = kwargs
                self._token = kwargs.get("access_token")

            async def list_secrets(self, workspace, environment, secret_path="/"):
                observed["scope"] = (workspace, environment, secret_path)
                return [{"secretKey": "K", "secretValue": "value"}]

            async def close(self):
                pass

        monkeypatch.setattr("copilot_cli.config.broker_auth.acquire_access_grant", _grant)
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient",
            _BrokerClient,
        )
        layer = _layer(
            tmp_path,
            "INFISICAL_BASE_URL=https://secrets.example.test\n"
            "INFISICAL_WORKSPACE_ID=ws-123\n"
            "INFISICAL_ENVIRONMENT=prod\n"
            "INFISICAL_SECRET_PATH=/shared\n"
            "INFISICAL_BROKER_URL=https://access.example.test\n"
            "INFISICAL_BROKER_ISSUER=https://access.example.test\n"
            "INFISICAL_BROKER_AUDIENCE=https://secrets.example.test\n"
            "INFISICAL_BROKER_ORG=Example-Org\n"
            "INFISICAL_STORE_SCOPE=shared\n",
        )

        assert resolve_from_store("K", [layer]) == "value"
        assert observed["client"] == {
            "base_url": "https://secrets.example.test",
            "timeout": ms._STORE_TIMEOUT,
            "access_token": "short-lived-token",
            "read_only": True,
        }

    def test_broker_refresh_failure_falls_through_without_universal_auth(
        self, tmp_path, monkeypatch
    ):
        from copilot_cli.config.broker_auth import AccessGrant, BrokerUnavailable

        calls: list[bool] = []

        async def _grant(config, force_refresh=False):
            del config
            calls.append(force_refresh)
            if force_refresh:
                raise BrokerUnavailable("broker unavailable")
            return AccessGrant("stale-token", "identity-shared", 9_999_999_999)

        class _RejectedBrokerClient:
            def __init__(self, **kwargs):
                assert "client_id" not in kwargs
                assert "client_secret" not in kwargs
                self._token = kwargs.get("access_token")

            async def list_secrets(self, workspace, environment, secret_path="/"):
                del workspace, environment, secret_path
                raise AuthenticationError("stale")

            async def close(self):
                pass

        monkeypatch.setattr("copilot_cli.config.broker_auth.acquire_access_grant", _grant)
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient",
            _RejectedBrokerClient,
        )
        layer = _layer(
            tmp_path,
            "INFISICAL_BASE_URL=https://secrets.example.test\n"
            "INFISICAL_WORKSPACE_ID=ws-123\n"
            "INFISICAL_ENVIRONMENT=prod\n"
            "INFISICAL_SECRET_PATH=/shared\n"
            "INFISICAL_BROKER_URL=https://access.example.test\n"
            "INFISICAL_BROKER_ISSUER=https://access.example.test\n"
            "INFISICAL_BROKER_AUDIENCE=https://secrets.example.test\n"
            "INFISICAL_BROKER_ORG=Example-Org\n"
            "INFISICAL_STORE_SCOPE=shared\n",
        )

        with pytest.raises(StoreUnavailable, match="refresh was unavailable"):
            resolve_from_store("K", [layer])
        assert calls == [False, True]

    def test_resolves_named_secret(self, tmp_path, monkeypatch):
        _install_fake(
            monkeypatch,
            secrets=[
                {"secretKey": "DISCORD_BOT_TOKEN", "secretValue": "tok-abc"},
                {"secretKey": "NOCODB_API_KEY", "secretValue": "nc-xyz"},
            ],
        )
        layer = _layer(tmp_path, _STORE_ENV)
        assert resolve_from_store("DISCORD_BOT_TOKEN", [layer]) == "tok-abc"
        assert resolve_from_store("NOCODB_API_KEY", [layer]) == "nc-xyz"

    def test_bulk_fetch_cached_once(self, tmp_path, monkeypatch):
        fake = _install_fake(
            monkeypatch,
            secrets=[
                {"secretKey": "A", "secretValue": "1"},
                {"secretKey": "B", "secretValue": "2"},
            ],
        )
        layer = _layer(tmp_path, _STORE_ENV)
        assert resolve_from_store("A", [layer]) == "1"
        assert resolve_from_store("B", [layer]) == "2"
        assert fake.calls == 1  # one list_secrets amortised across both

    def test_missing_name_falls_through(self, tmp_path, monkeypatch):
        _install_fake(monkeypatch, secrets=[{"secretKey": "OTHER", "secretValue": "v"}])
        layer = _layer(tmp_path, _STORE_ENV)
        with pytest.raises(StoreUnavailable, match="not present"):
            resolve_from_store("DISCORD_BOT_TOKEN", [layer])

    def test_empty_value_falls_through(self, tmp_path, monkeypatch):
        _install_fake(monkeypatch, secrets=[{"secretKey": "DISCORD_BOT_TOKEN", "secretValue": ""}])
        layer = _layer(tmp_path, _STORE_ENV)
        with pytest.raises(StoreUnavailable):
            resolve_from_store("DISCORD_BOT_TOKEN", [layer])

    def test_unreachable_store_falls_through(self, tmp_path, monkeypatch):
        _install_fake(monkeypatch, raises=InfisicalConnectionError("down"))
        layer = _layer(tmp_path, _STORE_ENV)
        with pytest.raises(StoreUnavailable, match="store read failed"):
            resolve_from_store("DISCORD_BOT_TOKEN", [layer])

    def test_no_bootstrap_creds_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient", _ExplodingClient
        )
        env = "INFISICAL_WORKSPACE_ID=ws-123\nINFISICAL_BASE_URL=https://x\n"  # no creds
        layer = _layer(tmp_path, env)
        with pytest.raises(StoreUnavailable, match="bootstrap credentials"):
            resolve_from_store("DISCORD_BOT_TOKEN", [layer])


class TestNearestWins:
    def test_nearest_layer_store_is_used(self, tmp_path, monkeypatch):
        fake = _install_fake(monkeypatch, secrets=[{"secretKey": "K", "secretValue": "from-org"}])
        # chain is highest-precedence-first: org (rank 30) then foundation (40).
        org = _layer(tmp_path / "org", _STORE_ENV, layer_id="org", rank=30)
        foundation = _layer(
            tmp_path / "foundation",
            "INFISICAL_WORKSPACE_ID=ws-foundation\nINFISICAL_CLIENT_ID=f\nINFISICAL_CLIENT_SECRET=f\n",
            layer_id="foundation",
            rank=40,
        )
        assert resolve_from_store("K", [org, foundation]) == "from-org"
        # the workspace actually queried was org's (ws-123), proven by the cache key
        assert any(key[1] == "ws-123" for key in ms._SECRET_CACHE)
        assert not any(key[1] == "ws-foundation" for key in ms._SECRET_CACHE)
        assert fake.calls == 1


class TestTokenCache:
    @staticmethod
    def _jwt(exp):
        import base64
        import json

        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
        return f"hdr.{payload}.sig"

    def test_save_then_load_roundtrip(self):
        import time

        tok = self._jwt(time.time() + 3600)
        ms._save_cached_token("https://x", "cid", tok)
        assert ms._load_cached_token("https://x", "cid") == tok

    def test_expired_token_not_returned(self):
        import time

        ms._save_cached_token("https://x", "cid", self._jwt(time.time() - 10))
        assert ms._load_cached_token("https://x", "cid") is None

    def test_missing_token_is_none(self):
        assert ms._load_cached_token("https://never", "nope") is None

    def test_cache_file_is_private(self):
        import stat
        import time

        ms._save_cached_token("https://x", "cid", self._jwt(time.time() + 3600))
        f = ms._token_cache_file("https://x", "cid")
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
