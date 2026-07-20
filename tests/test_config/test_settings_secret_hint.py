"""Unit tests proving `SecretRefSource` threads the overlay's per-secret
routing hint (`requires_secret: [{name, from}]`, item #3) through to
`secrets_ladder.resolve_secret`'s `prefer` param.

`layers.py`'s mapping-form parsing and `secrets_ladder.py`'s rung-filtering
are unit-tested independently (`test_layers.py::TestRequiresSecretRoutingHint`
and `test_secrets_ladder.py::TestPreferRoutingHint`); this file covers only
the plumbing between the two -- `SecretRefSource._collect_secret_names`
collecting `{name: hint}` across the chain (nearest-tier-wins) and
`get_field_value` passing it as `prefer`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from copilot_cli.config.layers import CliLayer
from copilot_cli.config.settings import SecretRefSource, Settings


def _layer(tmp: Path, overlay: dict, layer_id: str, rank: int) -> CliLayer:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "cli.overlay.yml").write_text(yaml.safe_dump(overlay))
    return CliLayer(id=layer_id, role="org", rank=rank, repo="r", ref="main", auth="anon", root=tmp)


def test_hinted_name_threads_prefer_into_resolve_secret(tmp_path, monkeypatch):
    layer = _layer(
        tmp_path,
        {
            "provides": [
                {
                    "service": "discord",
                    "module": "pkg.mod",
                    "requires_secret": [{"name": "DISCORD_BOT_TOKEN", "from": "keychain"}],
                }
            ]
        },
        layer_id="org",
        rank=30,
    )
    captured: dict[str, object] = {}

    def _fake_resolve(name, chain, prefer=None):
        captured["name"] = name
        captured["prefer"] = prefer
        return "resolved-value"

    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", _fake_resolve)

    source = SecretRefSource(Settings, [layer])
    value, key, _is_complex = source.get_field_value(None, "discord_bot_token")
    assert value == "resolved-value"
    assert key == "discord_bot_token"
    assert captured["name"] == "DISCORD_BOT_TOKEN"
    assert captured["prefer"] == "keychain"


def test_unhinted_name_threads_none_prefer_back_compat(tmp_path, monkeypatch):
    """A bare-string `requires_secret` entry (no hint declared anywhere)
    resolves with `prefer=None` -- `resolve_secret`'s unrestricted, unchanged
    default path."""
    layer = _layer(
        tmp_path,
        {"adopt": [{"service": "uspto", "requires_secret": ["USPTO_CLI_API_KEY"]}]},
        layer_id="org",
        rank=30,
    )
    captured: dict[str, object] = {}

    def _fake_resolve(name, chain, prefer=None):
        captured["prefer"] = prefer
        return "resolved-value"

    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", _fake_resolve)

    source = SecretRefSource(Settings, [layer])
    source.get_field_value(None, "uspto_cli_api_key")
    assert captured["prefer"] is None


def test_undeclared_field_never_reaches_resolve_secret(tmp_path, monkeypatch):
    """A field no tier declared under `requires_secret` at all is left
    untouched (falls through to `.env`/dotenv sources ahead of this one) --
    unaffected by the hint feature."""
    layer = _layer(tmp_path, {"adopt": [{"service": "git"}]}, layer_id="org", rank=30)

    def _fail(*a, **k):
        raise AssertionError("resolve_secret must not be called for an undeclared field")

    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", _fail)

    source = SecretRefSource(Settings, [layer])
    value, _key, _is_complex = source.get_field_value(None, "git_user_name")
    assert value is None


def test_nearest_layer_hint_wins_on_conflict(tmp_path, monkeypatch):
    """`chain` is highest-precedence-first; when two tiers declare the same
    name with different hints, the NEARER tier's hint wins -- matching
    nearest-wins semantics used everywhere else in the layered fold."""
    near = _layer(
        tmp_path / "near",
        {"adopt": [{"service": "uspto", "requires_secret": [{"name": "SHARED", "from": "keychain"}]}]},
        layer_id="org",
        rank=30,
    )
    far = _layer(
        tmp_path / "far",
        {"adopt": [{"service": "uspto", "requires_secret": [{"name": "SHARED", "from": "store"}]}]},
        layer_id="foundation",
        rank=40,
    )
    captured: dict[str, object] = {}

    def _fake_resolve(name, chain, prefer=None):
        captured["prefer"] = prefer
        return "v"

    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", _fake_resolve)

    # chain is already ordered highest-precedence-first (org, then foundation).
    source = SecretRefSource(Settings, [near, far])
    source.get_field_value(None, "shared")
    assert captured["prefer"] == "keychain"
