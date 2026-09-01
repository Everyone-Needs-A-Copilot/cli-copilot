"""Regression tests for deferred `requires_secret` resolution.

The `Settings` models are flat -- one model carries every service's fields --
so an EAGER `SecretRefSource` resolved every declared secret in the whole tier
chain the moment ANY command built its settings. One unresolvable name then
signed the entire CLI out of commands that never touch that service
(`Signed-out: no credential-ladder rung resolved secret 'X'` on
`copilot <unrelated-service> ...`).

`DeferredSecretsMixin` moves the raise from model construction to first read of
the field. These tests pin both halves of that: an unrelated unresolvable secret
must not block a command, and the command's OWN unresolvable secret must still
fail closed with `SecretResolutionError` (`secrets_ladder.py`, red-team §6.3 --
never an `""` default handed to an HTTP header).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from copilot_cli.config.layers import CliLayer
from copilot_cli.config.secrets_ladder import SecretResolutionError
from copilot_cli.config.settings import (
    DeferredSecretsMixin,
    SecretRefSource,
    Settings,
)


class TwoServiceSettings(DeferredSecretsMixin):
    """Stand-in for the real flat models: two unrelated services' credentials
    on one model, which is the shape that made eager resolution fatal."""

    model_config = SettingsConfigDict(extra="ignore")

    used_api_key: str = ""
    unrelated_api_key: str = ""
    plain_setting: str = "default"


def _layer(tmp: Path, overlay: dict) -> CliLayer:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "cli.overlay.yml").write_text(yaml.safe_dump(overlay))
    return CliLayer(id="org", role="org", rank=30, repo="r", ref="main", auth="anon", root=tmp)


def _two_service_layer(tmp_path: Path) -> CliLayer:
    return _layer(
        tmp_path,
        {
            "version": 1,
            "provides": [
                {
                    "service": "used",
                    "module": "pkg.used",
                    "requires_secret": [{"name": "USED_API_KEY", "from": "store"}],
                },
                {
                    "service": "unrelated",
                    "module": "pkg.unrelated",
                    "requires_secret": [{"name": "UNRELATED_API_KEY", "from": "store"}],
                },
            ],
        },
    )


def _build(settings_cls, layer, monkeypatch, resolver):
    """Construct *settings_cls* with only `init` + `SecretRefSource`, so the
    machine's real `.env`/environment cannot supply either secret."""
    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", resolver)
    source = SecretRefSource(settings_cls, [layer])
    return settings_cls(**source())


def test_unrelated_unresolvable_secret_does_not_block_construction(tmp_path, monkeypatch):
    """The reported defect: `copilot n8n ...` died on RESEARCH_COPILOT_API_KEY."""
    attempted: list[str] = []

    def resolver(name, chain, prefer=None):
        attempted.append(name)
        if name == "UNRELATED_API_KEY":
            raise SecretResolutionError(name)
        return "used-value"

    settings = _build(TwoServiceSettings, _two_service_layer(tmp_path), monkeypatch, resolver)

    assert settings.plain_setting == "default"
    assert settings.used_api_key == "used-value"
    # The unrelated name is never even walked: nothing read that field.
    assert attempted == ["USED_API_KEY"]


def test_own_unresolvable_secret_still_fails_closed(tmp_path, monkeypatch):
    """Fail-closed survives -- it just lands at the point of use."""

    def resolver(name, chain, prefer=None):
        raise SecretResolutionError(name)

    settings = _build(TwoServiceSettings, _two_service_layer(tmp_path), monkeypatch, resolver)

    with pytest.raises(SecretResolutionError) as excinfo:
        _ = settings.used_api_key
    assert excinfo.value.name == "USED_API_KEY"


def test_repeated_read_of_a_miss_reraises_without_walking_the_ladder_again(tmp_path, monkeypatch):
    """A second read must not re-walk the ladder -- rung 4 would re-prompt."""
    calls: list[str] = []

    def resolver(name, chain, prefer=None):
        calls.append(name)
        raise SecretResolutionError(name)

    settings = _build(TwoServiceSettings, _two_service_layer(tmp_path), monkeypatch, resolver)

    with pytest.raises(SecretResolutionError) as first:
        _ = settings.used_api_key
    with pytest.raises(SecretResolutionError) as second:
        _ = settings.used_api_key
    assert first.value is second.value
    assert calls == ["USED_API_KEY"]


def test_resolved_secret_is_memoised_after_first_read(tmp_path, monkeypatch):
    calls: list[str] = []

    def resolver(name, chain, prefer=None):
        calls.append(name)
        return "value"

    settings = _build(TwoServiceSettings, _two_service_layer(tmp_path), monkeypatch, resolver)

    assert settings.used_api_key == "value"
    assert settings.used_api_key == "value"
    assert calls == ["USED_API_KEY"]


def test_higher_precedence_source_still_outranks_the_ladder(tmp_path, monkeypatch):
    """`SecretRefSource` is LAST (lowest precedence). A value from any source
    ahead of it wins and the ladder is never walked -- the same outcome eager
    resolution produced by having its value overwritten in the merge."""

    def resolver(name, chain, prefer=None):
        raise AssertionError("ladder must not run for a field another source supplied")

    monkeypatch.setattr("copilot_cli.config.settings.resolve_secret", resolver)
    source = SecretRefSource(TwoServiceSettings, [_two_service_layer(tmp_path)])
    settings = TwoServiceSettings(used_api_key="from-env", **source())

    assert settings.used_api_key == "from-env"


def test_manifest_absent_fast_path_defers_nothing(monkeypatch):
    """No manifest -> `SecretRefSource` is never constructed, the default four
    sources are returned untouched, and no field is deferred."""
    monkeypatch.setattr("copilot_cli.config.settings.resolve_cli_layer_chain", lambda: None)
    init, env, dotenv, filesec = object(), object(), object(), object()

    out = Settings.settings_customise_sources(Settings, init, env, dotenv, filesec)

    assert out == (init, env, dotenv, filesec)
    assert Settings(_env_file=None).deferred_secrets_ == {}


def test_model_without_the_mixin_is_refused(tmp_path):
    """Refusing the wiring error is itself fail-closed: `extra="ignore"` would
    otherwise drop the deferral plan and no declared secret would ever
    resolve."""

    class NoMixin(BaseSettings):
        used_api_key: str = ""

    with pytest.raises(TypeError, match="DeferredSecretsMixin"):
        SecretRefSource(NoMixin, [_two_service_layer(tmp_path)])
