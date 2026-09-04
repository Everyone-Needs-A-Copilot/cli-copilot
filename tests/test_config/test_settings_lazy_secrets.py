"""Regression tests for per-service, deferred `requires_secret` resolution.

The defect these pin: `requires_secret` is declared per SERVICE, but one
`Settings` model carries every service's fields, and the secret source used to
resolve all of them while the model was being BUILT. Because no command can run
without a `Settings` instance existing first, a single secret that was absent
from every ladder rung -- belonging to a service the invoked command never
touches -- aborted every command in the CLI.

Resolution now happens on FIRST READ of each declared field, so a command only
resolves the credentials it actually reads. What must NOT change is the
fail-closed guarantee (`secrets_ladder.py`, red-team §6.3): a declared secret
that misses every rung still raises `SecretResolutionError`, just at the read
that needed it rather than at construction. Both halves are asserted here --
laziness that quietly handed back `""` would be the exact silent no-op the
ladder exists to prevent.

`USPTO_CLI_API_KEY` stands in for the invoked service's secret and
`DATABASE_URL` for the unrelated service's absent one; both are real base
`Settings` fields, so no synthetic model is needed to exercise the real path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import copilot_cli.config.secrets_ladder as ladder_mod
import copilot_cli.config.settings as settings_mod
from copilot_cli.config.layers import CliLayer
from copilot_cli.config.secrets_ladder import SecretResolutionError
from copilot_cli.config.settings import LazySecretSettings, SecretRefSource, Settings

PRESENT = "USPTO_CLI_API_KEY"
ABSENT = "DATABASE_URL"


@pytest.fixture(autouse=True)
def _no_ambient_secret_values(monkeypatch):
    """`env_settings` sits ahead of the secret source, so a developer's real
    exported value would supply the field and suppress the deferral under
    test."""
    for name in (PRESENT, ABSENT):
        monkeypatch.delenv(name, raising=False)


def _layer(tmp: Path, overlay: dict, layer_id: str = "org", rank: int = 30) -> CliLayer:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "cli.overlay.yml").write_text(yaml.safe_dump(overlay))
    return CliLayer(id=layer_id, role="org", rank=rank, repo="r", ref="main", auth="anon", root=tmp)


def _two_service_layer(tmp: Path, *, hint: str | None = None) -> CliLayer:
    """One tier declaring two services' secrets -- the shape that broke."""

    def _entry(name: str) -> object:
        return {"name": name, "from": hint} if hint else name

    return _layer(
        tmp,
        {
            "adopt": [{"service": "uspto", "requires_secret": [_entry(PRESENT)]}],
            "provides": [
                {
                    "service": "unrelated",
                    "module": "pkg.mod",
                    "requires_secret": [_entry(ABSENT)],
                }
            ],
        },
    )


@pytest.fixture
def install_ladder(monkeypatch):
    """Replace the ladder's rungs with one that resolves `PRESENT` and misses
    on everything else, and record every name the ladder is asked for.

    Patching `_LADDER` itself (rather than `resolve_secret`) keeps the REAL
    `resolve_secret` in the path, so the fail-closed raise under test is the
    module's own, not a test double's. `_RUNG_SUBSET_FOR_HINT` is patched in
    step so a `from: store`-hinted name resolves through the same fake rung.
    """

    def _install() -> list[str]:
        asked: list[str] = []

        def _rung(name: str, chain: list[CliLayer]) -> str:
            del chain
            asked.append(name)
            if name != PRESENT:
                raise ladder_mod._SecretRungUnavailable("absent from this rung")
            return f"resolved-{name}"

        monkeypatch.setattr(ladder_mod, "_LADDER", (_rung,))
        monkeypatch.setattr(
            ladder_mod, "_RUNG_SUBSET_FOR_HINT", {"keychain": (_rung,), "store": (_rung,)}
        )
        return asked

    return _install


@pytest.fixture
def layered(monkeypatch):
    """Point both `Settings` and its sources at an explicit tier chain."""

    def _use(chain: list[CliLayer] | None) -> None:
        monkeypatch.setattr(settings_mod, "resolve_cli_layer_chain", lambda: chain)

    return _use


def test_absent_secret_for_one_service_does_not_block_another(tmp_path, layered, install_ladder):
    """THE regression: a secret declared by service B and absent from every
    rung must not stop service A's field -- or the model itself -- from
    working."""
    layered([_two_service_layer(tmp_path)])
    asked = install_ladder()

    settings = Settings(_env_file=None)

    assert settings.uspto_cli_api_key == f"resolved-{PRESENT}"
    assert settings.git_user_name == "copilot"  # an ordinary non-secret field
    # The unrelated service's absent secret was never even looked for.
    assert asked == [PRESENT]


def test_reading_the_absent_secret_still_fails_closed(tmp_path, layered, install_ladder):
    """Deferral moves WHEN the ladder runs, never WHETHER a miss fails. The
    field must never be observable as its `""` default."""
    layered([_two_service_layer(tmp_path)])
    install_ladder()

    settings = Settings(_env_file=None)

    with pytest.raises(SecretResolutionError) as excinfo:
        _ = settings.database_url
    assert excinfo.value.name == ABSENT


def test_construction_never_consults_the_ladder(tmp_path, layered, install_ladder):
    """Building the model resolves nothing at all -- the property that makes
    an unrelated command's cost independent of every other service."""
    layered([_two_service_layer(tmp_path)])
    asked = install_ladder()

    Settings(_env_file=None)

    assert asked == []


def test_higher_precedence_value_wins_and_skips_the_ladder(tmp_path, layered, install_ladder):
    """The secret source still sits LAST, so a tier `.env` supplying a declared
    name keeps that value and the field is never deferred -- the same
    precedence the eager source got from its position in the tuple."""
    layer = _two_service_layer(tmp_path)
    (tmp_path / ".env").write_text(f"{PRESENT}=from-tier-env\n")
    layered([layer])
    asked = install_ladder()

    settings = Settings(_env_file=None)

    assert settings.uspto_cli_api_key == "from-tier-env"
    assert asked == []


def test_routing_hint_is_still_threaded_at_read_time(tmp_path, layered, monkeypatch):
    """`from: store` / `from: keychain` must keep reaching `resolve_secret`'s
    `prefer` param now that the call happens on read."""
    layered([_two_service_layer(tmp_path, hint="store")])
    captured: dict[str, object] = {}

    def _fake_resolve(name, chain, prefer=None):
        captured[name] = prefer
        return "v"

    monkeypatch.setattr(settings_mod, "resolve_secret", _fake_resolve)

    settings = Settings(_env_file=None)
    assert settings.uspto_cli_api_key == "v"
    assert captured == {PRESENT: "store"}


def test_resolution_is_memoized_per_name(tmp_path, layered, install_ladder):
    """At most one ladder run per name per process -- matching the old eager
    behaviour, and keeping rung 4's one-time paste from re-prompting."""
    layered([_two_service_layer(tmp_path)])
    asked = install_ladder()

    settings = Settings(_env_file=None)
    assert settings.uspto_cli_api_key == f"resolved-{PRESENT}"
    assert settings.uspto_cli_api_key == f"resolved-{PRESENT}"

    assert asked == [PRESENT]
    # A resolved secret reads as source-provided, exactly as eager resolution
    # left it -- this module treats `model_fields_set` as "provided vs. default"
    # (see `services/infisical/core/config.load_settings`).
    assert "uspto_cli_api_key" in settings.model_fields_set


def test_fast_path_drops_a_previous_constructions_plan(tmp_path, layered, install_ladder):
    """A layered construction must not leave a plan behind that a later
    manifest-absent construction of the same class would resolve against."""
    layered([_two_service_layer(tmp_path)])
    asked = install_ladder()
    Settings(_env_file=None)

    layered(None)
    settings = Settings(_env_file=None)

    assert settings.uspto_cli_api_key == ""  # class default, nothing declared
    assert settings.database_url == ""
    assert asked == []


def test_secret_source_refuses_a_model_that_cannot_defer(tmp_path):
    """Fail-closed backstop: a model reaching the secret source without
    `LazySecretSettings` has nothing to perform the deferred read, so its
    declared secrets would silently sit at their defaults."""
    from pydantic_settings import BaseSettings

    class NotLazy(BaseSettings):
        uspto_cli_api_key: str = ""

    assert not issubclass(NotLazy, LazySecretSettings)
    source = SecretRefSource(NotLazy, [_two_service_layer(tmp_path)])

    with pytest.raises(TypeError, match="LazySecretSettings"):
        source()
