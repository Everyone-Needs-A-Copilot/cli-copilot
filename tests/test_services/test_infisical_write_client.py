"""Tests for State.get_write_client(): automatic ecosystem-admin writes.

No network: the read client and InfisicalClient construction are mocked.
"""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from copilot_cli.services.infisical import main as inf_main
from copilot_cli.services.infisical.core.config import (
    ADMIN_CLIENT_ID_KEY,
    ADMIN_CLIENT_SECRET_KEY,
    InfisicalSettings,
)
from copilot_cli.services.infisical.core.exceptions import ConfigError

PROJECT = "458e8f7a-3d53-4e72-9d1c-718956463e2f"


def _settings(**over):
    base = {
        "client_id": "",
        "client_secret": "",
        "base_url": "https://infisical.example.test",
        "broker_url": "https://broker.example.test",
        "admin_project": PROJECT,
        "admin_env": "prod",
        "admin_path": "/shared",
    }
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def wired(monkeypatch):
    """Patch settings, keychain, and the client class; return the recorders."""
    rec = SimpleNamespace(settings=_settings(), keychain={}, built=[], reader=MagicMock())
    monkeypatch.setattr(inf_main, "load_settings", lambda: rec.settings)
    monkeypatch.setattr(inf_main, "_keychain_lookup", lambda name: rec.keychain.get(name, ""))

    def fake_client(**kwargs):
        rec.built.append(kwargs)
        return SimpleNamespace(kwargs=kwargs)

    monkeypatch.setattr(inf_main, "InfisicalClient", fake_client)
    # run_async is the identity, so the reader's get_secret is a plain callable.
    monkeypatch.setattr(inf_main, "run_async", lambda value: value)
    monkeypatch.setattr(inf_main.State, "get_client", lambda self: rec.reader)
    return rec


def test_broker_session_reads_admin_pair_and_uses_universal_auth(wired):
    wired.reader.get_secret.side_effect = lambda *a: {
        ADMIN_CLIENT_ID_KEY: {"secretValue": "id-value"},
        ADMIN_CLIENT_SECRET_KEY: {"secretValue": "secret-value"},
    }[a[2]]
    client = inf_main.State().get_write_client()
    assert client.kwargs == {
        "base_url": "https://infisical.example.test",
        "client_id": "id-value",
        "client_secret": "secret-value",
    }
    calls = [c.args for c in wired.reader.get_secret.call_args_list]
    assert calls == [
        (PROJECT, "prod", ADMIN_CLIENT_ID_KEY, "/shared"),
        (PROJECT, "prod", ADMIN_CLIENT_SECRET_KEY, "/shared"),
    ]


def test_location_is_configurable(wired):
    wired.settings = _settings(admin_project="p2", admin_env="staging", admin_path="/x")
    wired.reader.get_secret.return_value = {"secretValue": "v"}
    inf_main.State().get_write_client()
    assert wired.reader.get_secret.call_args_list[0].args == (
        "p2",
        "staging",
        ADMIN_CLIENT_ID_KEY,
        "/x",
    )


def test_write_client_is_cached(wired):
    wired.reader.get_secret.return_value = {"secretValue": "v"}
    st = inf_main.State()
    assert st.get_write_client() is st.get_write_client()
    assert wired.reader.get_secret.call_count == 2


def test_explicit_settings_credentials_win_without_reading_infisical(wired):
    wired.settings = _settings(client_id="env-id", client_secret="env-key")
    client = inf_main.State().get_write_client()
    assert client.kwargs["client_id"] == "env-id"
    wired.reader.get_secret.assert_not_called()


def test_keychain_credentials_win(wired):
    wired.keychain = {"INFISICAL_CLIENT_ID": "kc-id", "INFISICAL_CLIENT_SECRET": "kc-key"}
    client = inf_main.State().get_write_client()
    assert client.kwargs["client_secret"] == "kc-key"
    wired.reader.get_secret.assert_not_called()


def test_non_broker_session_reuses_writable_default_client(wired):
    wired.settings = _settings(broker_url="")
    assert inf_main.State().get_write_client() is wired.reader


def test_missing_admin_secret_gives_clear_error_without_values(wired):
    wired.reader.get_secret.side_effect = lambda *a: (
        {"secretValue": "id-value"} if a[2] == ADMIN_CLIENT_ID_KEY else {"secretValue": ""}
    )
    with pytest.raises(ConfigError) as exc:
        inf_main.State().get_write_client()
    msg = str(exc.value)
    assert ADMIN_CLIENT_SECRET_KEY in msg
    assert PROJECT in msg
    assert "id-value" not in msg


def test_unreadable_admin_secret_wraps_error(wired):
    wired.reader.get_secret.side_effect = RuntimeError("404 not found")
    with pytest.raises(ConfigError, match="ecosystem-admin"):
        inf_main.State().get_write_client()


def test_settings_defaults_point_at_ecosystem_shared():
    s = InfisicalSettings()
    assert (s.admin_project, s.admin_env, s.admin_path) == (PROJECT, "prod", "/shared")


@pytest.mark.parametrize(
    ("module", "func"),
    [
        ("secret", "set_secret"),
        ("secret", "delete_secret"),
        ("folder", "create_folder"),
        ("project", "create_project"),
        ("project", "delete_project"),
        ("identity", "create_identity"),
        ("org", "disable_signup"),
    ],
)
def test_write_commands_use_write_client(module, func):
    mod = importlib.import_module(f"copilot_cli.services.infisical.commands.{module}")
    src = inspect.getsource(getattr(mod, func))
    assert "get_write_client()" in src
    assert "get_client()" not in src
