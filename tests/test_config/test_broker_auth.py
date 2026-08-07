from __future__ import annotations

import base64
import json
import stat
import time
from pathlib import Path

import pytest

import copilot_cli.config.broker_auth as broker
from copilot_cli.config.broker_auth import BrokerConfig, BrokerUnavailable
from copilot_cli.services.infisical.core.api_client import InfisicalClient
from copilot_cli.services.infisical.core.exceptions import AuthenticationError


def _jwt(expires_at: float) -> str:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": expires_at, "identityId": "identity-shared"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHTTP:
    calls: list[tuple[str, str, dict | None]] = []
    proof_lifetime_seconds = 50

    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        del args

    async def get(self, url: str):
        type(self).calls.append(("GET", url, None))
        return _Response(200, {"issuer": "https://access.example.test"})

    async def post(self, url: str, json: dict):
        type(self).calls.append(("POST", url, json))
        now = time.time()
        if url.endswith("/v1/challenges"):
            return _Response(
                200,
                {
                    "nonce_id": "nonce-id-long-enough-1234",
                    "nonce": "nonce-value-long-enough-1234567890",
                    "expires_at": broker.datetime.fromtimestamp(
                        now + type(self).proof_lifetime_seconds, tz=broker.UTC
                    ).isoformat(),
                },
            )
        if url.endswith("/v1/assertions"):
            return _Response(
                200,
                {
                    "organization": "Example-Org",
                    "machine_id": json["machine_id"],
                    "assertions": [
                        {
                            "scope": "shared",
                            "identity_id": "identity-shared",
                            "assertion": "broker.assertion.value",
                            "expires_at": broker.datetime.fromtimestamp(
                                now + type(self).proof_lifetime_seconds, tz=broker.UTC
                            ).isoformat(),
                        }
                    ],
                },
            )
        if url.endswith("/api/v1/auth/oidc-auth/login"):
            return _Response(200, {"accessToken": _jwt(now + 850)})
        raise AssertionError(f"unexpected URL: {url}")


@pytest.fixture
def broker_config(tmp_path: Path, monkeypatch) -> BrokerConfig:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    auth_root = tmp_path / "auth"
    auth_root.mkdir()
    (auth_root / "active.json").write_text(json.dumps({"login": "Pablo"}))
    public_key = tmp_path / "device.pub"
    public_key.write_text("ssh-ed25519 " + base64.b64encode(b"public-key").decode() + " test")
    return BrokerConfig(
        broker_url="https://access.example.test",
        issuer="https://access.example.test",
        audience="https://secrets.example.test",
        organization="Example-Org",
        scope="shared",
        infisical_url="https://secrets.example.test",
        public_key_path=public_key,
        auth_root=auth_root,
    )


@pytest.mark.asyncio
async def test_broker_flow_exchanges_scope_assertion_and_caches_only_short_lived_token(
    broker_config, monkeypatch
):
    _FakeHTTP.calls = []
    monkeypatch.setattr(broker.httpx, "AsyncClient", _FakeHTTP)
    monkeypatch.setattr(broker, "_sign", lambda path, message: "signed-proof")

    grant = await broker.acquire_access_grant(broker_config)
    assert grant.identity_id == "identity-shared"
    assert 0 < grant.expires_at - time.time() <= 900
    assert grant.cache_path is not None
    assert stat.S_IMODE(grant.cache_path.stat().st_mode) == 0o600

    oidc_request = next(payload for _, url, payload in _FakeHTTP.calls if "oidc-auth" in url)
    assert oidc_request == {
        "identityId": "identity-shared",
        "jwt": "broker.assertion.value",
    }
    rendered = json.dumps(_FakeHTTP.calls)
    assert "clientSecret" not in rendered
    assert "clientId" not in rendered

    call_count = len(_FakeHTTP.calls)
    cached = await broker.acquire_access_grant(broker_config)
    assert cached.token == grant.token
    assert len(_FakeHTTP.calls) == call_count


@pytest.mark.asyncio
async def test_broker_accepts_bounded_clock_skew_at_proof_lifetime_boundary(
    broker_config, monkeypatch
):
    _FakeHTTP.calls = []
    monkeypatch.setattr(_FakeHTTP, "proof_lifetime_seconds", 60.5)
    monkeypatch.setattr(broker.httpx, "AsyncClient", _FakeHTTP)
    monkeypatch.setattr(broker, "_sign", lambda path, message: "signed-proof")

    grant = await broker.acquire_access_grant(broker_config, force_refresh=True)

    assert grant.identity_id == "identity-shared"


@pytest.mark.asyncio
async def test_broker_rejects_proof_lifetime_beyond_clock_skew_tolerance(
    broker_config, monkeypatch
):
    _FakeHTTP.calls = []
    monkeypatch.setattr(_FakeHTTP, "proof_lifetime_seconds", 66)
    monkeypatch.setattr(broker.httpx, "AsyncClient", _FakeHTTP)

    with pytest.raises(BrokerUnavailable, match="invalid challenge"):
        await broker.acquire_access_grant(broker_config, force_refresh=True)


@pytest.mark.asyncio
async def test_broker_configuration_fails_closed_before_network(broker_config, monkeypatch):
    monkeypatch.setattr(
        broker.httpx,
        "AsyncClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network")),
    )
    mismatched = BrokerConfig(
        **{
            **broker_config.__dict__,
            "issuer": "https://different.example.test",
        }
    )
    with pytest.raises(BrokerUnavailable, match="must match"):
        await broker.acquire_access_grant(mismatched)


@pytest.mark.asyncio
async def test_direct_broker_token_cannot_mutate_infisical():
    client = InfisicalClient(
        "https://secrets.example.test",
        access_token="short-lived",
        read_only=True,
    )
    try:
        with pytest.raises(AuthenticationError, match="read-only"):
            await client.post("/api/v1/anything", {"unsafe": True})
    finally:
        await client.close()
