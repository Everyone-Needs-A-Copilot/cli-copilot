"""Unit tests for `config/store_readiness.py` -- the presence-only managed-
store readiness REPORT for `copilot update` (#2b, cred-boundary QA F9).

Every test asserts no secret VALUE ever appears in the result (`detail`,
`status`, or `layer_id`) -- only presence booleans feed the outcome. The
keychain lookup is always faked (`_rung_keychain`) so these tests never
touch the real macOS keychain and are deterministic across dev boxes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from copilot_cli.config.layers import CliLayer
from copilot_cli.config.store_readiness import StoreReadiness, check_store_readiness

_REAL_CLIENT_ID = "super-secret-client-id-do-not-leak"
_REAL_CLIENT_SECRET = "super-secret-client-secret-do-not-leak"


def _layer(tmp: Path, env_text: str, layer_id: str = "org", rank: int = 30) -> CliLayer:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / ".env").write_text(env_text)
    return CliLayer(id=layer_id, role="org", rank=rank, repo="r", ref="main", auth="anon", root=tmp)


def _fake_keychain(monkeypatch, values: dict[str, str]):
    """Fake `_rung_keychain` so tests never touch the real OS keychain."""
    from copilot_cli.config.secrets_ladder import _SecretRungUnavailable

    def _lookup(name, chain):
        if name in values:
            return values[name]
        raise _SecretRungUnavailable("not in fake keychain")

    monkeypatch.setattr("copilot_cli.config.secrets_ladder._rung_keychain", _lookup)


class TestNoneDeclared:
    def test_empty_chain_reports_none(self):
        result = check_store_readiness([])

        assert result == StoreReadiness(status="none", detail="store: none declared")

    def test_layer_without_workspace_id_reports_none(self, tmp_path, monkeypatch):
        _fake_keychain(monkeypatch, {})
        layer = _layer(tmp_path, "INFISICAL_BASE_URL=https://x\n")  # no WORKSPACE_ID

        result = check_store_readiness([layer])

        assert result.status == "none"
        assert result.layer_id is None


class TestCredsMissing:
    def test_workspace_declared_but_no_creds_anywhere(self, tmp_path, monkeypatch):
        _fake_keychain(monkeypatch, {})
        layer = _layer(tmp_path, "INFISICAL_WORKSPACE_ID=ws-123\n")

        result = check_store_readiness([layer])

        assert result.status == "creds_missing"
        assert result.layer_id == "org"
        assert "provision" in result.detail

    def test_only_client_id_present_is_still_missing(self, tmp_path, monkeypatch):
        _fake_keychain(monkeypatch, {"INFISICAL_CLIENT_ID": _REAL_CLIENT_ID})
        layer = _layer(tmp_path, "INFISICAL_WORKSPACE_ID=ws-123\n")

        result = check_store_readiness([layer])

        assert result.status == "creds_missing"


class TestReady:
    def test_workspace_and_keychain_creds_present(self, tmp_path, monkeypatch):
        _fake_keychain(
            monkeypatch,
            {
                "INFISICAL_CLIENT_ID": _REAL_CLIENT_ID,
                "INFISICAL_CLIENT_SECRET": _REAL_CLIENT_SECRET,
            },
        )
        layer = _layer(tmp_path, "INFISICAL_WORKSPACE_ID=ws-123\n")

        result = check_store_readiness([layer])

        assert result.status == "ready"
        assert result.layer_id == "org"
        assert result.detail == "store: ready"

    def test_workspace_and_env_creds_present(self, tmp_path, monkeypatch):
        """Bootstrap creds may also come from the tier's own `.env` (the
        `_read_bootstrap_cred` fallback) -- still `ready`, not just when
        sourced from the keychain."""
        _fake_keychain(monkeypatch, {})
        layer = _layer(
            tmp_path,
            "INFISICAL_WORKSPACE_ID=ws-123\n"
            f"INFISICAL_CLIENT_ID={_REAL_CLIENT_ID}\n"
            f"INFISICAL_CLIENT_SECRET={_REAL_CLIENT_SECRET}\n",
        )

        result = check_store_readiness([layer])

        assert result.status == "ready"


class TestNearestTierWins:
    def test_nearer_layer_without_store_falls_through_to_next(self, tmp_path, monkeypatch):
        _fake_keychain(monkeypatch, {})
        nearer = _layer(
            tmp_path / "personal", "INFISICAL_BASE_URL=https://x\n", layer_id="personal", rank=10
        )
        farther = _layer(
            tmp_path / "org", "INFISICAL_WORKSPACE_ID=ws-123\n", layer_id="org", rank=30
        )

        result = check_store_readiness([nearer, farther])

        assert result.status == "creds_missing"
        assert result.layer_id == "org"


class TestNeverLeaksASecretValue:
    @pytest.mark.parametrize(
        "keychain_values",
        [
            {},
            {"INFISICAL_CLIENT_ID": _REAL_CLIENT_ID},
            {
                "INFISICAL_CLIENT_ID": _REAL_CLIENT_ID,
                "INFISICAL_CLIENT_SECRET": _REAL_CLIENT_SECRET,
            },
        ],
    )
    def test_result_never_contains_the_credential_value(
        self, tmp_path, monkeypatch, keychain_values
    ):
        _fake_keychain(monkeypatch, keychain_values)
        layer = _layer(tmp_path, "INFISICAL_WORKSPACE_ID=ws-123\n")

        result = check_store_readiness([layer])

        rendered = f"{result.status} {result.detail} {result.layer_id}"
        assert _REAL_CLIENT_ID not in rendered
        assert _REAL_CLIENT_SECRET not in rendered

    def test_no_network_call_when_dormant(self, monkeypatch):
        """`status="none"` must be decided before any network-capable code
        path is even imported/constructed -- `check_store_readiness([])`
        must not attempt to reach Infisical."""

        class _ExplodingClient:
            def __init__(self, *a, **k):
                raise AssertionError("InfisicalClient must NOT be constructed for a dormant store")

        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient", _ExplodingClient
        )

        result = check_store_readiness([])

        assert result.status == "none"
