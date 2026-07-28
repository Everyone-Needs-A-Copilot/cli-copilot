"""Isolated acceptance test for config-inheritance item #1: a tier's
committed `cli.overlay.yml` `adopt[].config` block now feeds BOTH the
layered `Settings` source chain (`settings.py`'s `TierConfigSource`) and the
managed-store lookup (`managed_store._find_store_layer`), so non-secret
store config (workspace id / environment / secret path) can inherit
down-tier from a committed overlay instead of only ever living in a local
`.env`. See `cli-copilot/copilot_cli/config/settings.py` and
`cli-copilot/copilot_cli/config/managed_store.py`.

Deliberately lives in the FOUNDATION suite, not the `-internal` overlay
suite -- the `-internal` suite has a known cross-repo `sys.path` collision
via `_ensure_on_syspath`; this suite runs clean and exercises the exact same
`copilot_cli.config.managed_store` / `copilot_cli.config.layers` code the
overlay depends on (its own `settings_customise_sources` reuses
`TierConfigSource` unmodified, imported from this package).

Store faking is modeled on `tests/test_config/test_managed_store.py`
(`_FakeClient`, `_SECRET_CACHE` isolation, keychain isolation) -- this file
adds a THIRD isolation fixture (`_keychain_supplies_bootstrap`) so a mirror
root can have literally NO `.env` file while still authenticating: bootstrap
credentials (`INFISICAL_CLIENT_ID`/`_SECRET`) are sourced from the OS
keychain in a real deployment, never from `.env` or a committed overlay
(bootstrap paradox -- a store can't hold the credentials used to reach it),
so faking a keychain hit isolates what this test actually targets: the
non-secret store CONFIG fold.

`TestSettingsSourcePrecedence` below is the counterpart permanent test for
the OTHER consumer of `TierConfigSource`: it instantiates a real
`Settings()` (the two classes above never do -- they only exercise
`managed_store._find_store_layer`) and asserts precedence directly against
an actual `Settings` model field.

ADR-001 extends all of the above to `provides[].config` -- a `provides:`
entry's own `config:` block now folds into `TierConfigSource` and
`managed_store._find_store_layer` exactly like `adopt[].config` always has.
`TestProvidesConfigInheritsFromCommittedOverlay` mirrors
`TestConfigInheritsFromCommittedOverlay` for the store-config path, and
`TestSettingsSourcePrecedence` gains the `provides`-config counterparts of
its `adopt`-config precedence tests, plus the same-tier
adopt-vs-provides collision rule (provides wins -- see
`TierConfigSource._collect_config`'s docstring in `settings.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import copilot_cli.config.managed_store as ms
from copilot_cli.config.layers import resolve_cli_layer_chain
from copilot_cli.config.managed_store import resolve_from_store
from copilot_cli.config.secrets_ladder import _SecretRungUnavailable


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
def _keychain_supplies_bootstrap(monkeypatch):
    """Fake (never real-machine) keychain hit for the two bootstrap-cred
    names only -- everything else stays unavailable, matching the "no
    silent no-op" posture of the other store tests' keychain fixture."""

    def _fake_keychain(name: str, chain: object) -> str:
        if name == "INFISICAL_CLIENT_ID":
            return "keychain-client-id"
        if name == "INFISICAL_CLIENT_SECRET":
            return "keychain-client-secret"
        raise _SecretRungUnavailable(f"no fake keychain entry for {name}")

    monkeypatch.setattr("copilot_cli.config.secrets_ladder._rung_keychain", _fake_keychain)


class _FakeClient:
    """Async stand-in for `InfisicalClient` -- same shape as
    `test_managed_store.py`'s fake. Counts `list_secrets` calls."""

    secrets: list[dict] = []
    calls: int = 0

    def __init__(self, base_url, client_id, client_secret, timeout=30.0):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None  # mirrors the real client; _fetch_all reads/sets it

    async def list_secrets(self, workspace, environment, secret_path="/"):
        type(self).calls += 1
        return type(self).secrets

    async def close(self):
        pass


def _install_fake(monkeypatch, secrets: list[dict]) -> type[_FakeClient]:
    _FakeClient.secrets = secrets
    _FakeClient.calls = 0
    monkeypatch.setattr(
        "copilot_cli.services.infisical.core.api_client.InfisicalClient", _FakeClient
    )
    return _FakeClient


def _write_manifest(path: Path, layers: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"version": 1, "layers": layers}))


def _mirror_dir(mirrors_root: Path, layer_id: str) -> Path:
    d = mirrors_root / "mirrors" / "cli" / layer_id
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def _isolated_layers(tmp_path, monkeypatch):
    """Point BOTH layer-manifest and mirror-root discovery at a scratch tmp
    tree -- never the real `copilot.layers.yml` / `~/.copilot/mirrors` on
    this machine."""
    mirrors_root = tmp_path / "mirrors-root"
    manifest_path = tmp_path / "copilot.layers.yml"
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(mirrors_root))
    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest_path))
    return manifest_path, mirrors_root


# Non-secret store config only -- workspace id / environment / secret path,
# exactly the three keys item #1 moves out of `.env` (plus base_url, which
# stays dual per the design note in the real repo's `cli.overlay.yml`).
_ORG_OVERLAY_CONFIG = {
    "version": 1,
    "adopt": [
        {
            "service": "infisical",
            "config": {
                "infisical_base_url": "https://secrets.example.com",
                "infisical_workspace_id": "ws-from-overlay",
                "infisical_environment": "prod",
                "infisical_secret_path": "/shared",
            },
        }
    ],
}


class TestConfigInheritsFromCommittedOverlay:
    def test_store_resolves_with_zero_env(self, monkeypatch, _isolated_layers):
        """A single org layer whose mirror root has ONLY a `cli.overlay.yml`
        (config: block) and NO `.env` file at all still passes the
        workspace-id store gate and resolves a secret -- store CONFIG
        inherited entirely from the committed overlay, zero `.env`."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(yaml.safe_dump(_ORG_OVERLAY_CONFIG))
        assert not (org_root / ".env").exists()  # the point of this case

        fake = _install_fake(
            monkeypatch, secrets=[{"secretKey": "DISCORD_BOT_TOKEN", "secretValue": "tok-abc"}]
        )

        chain = resolve_cli_layer_chain()
        assert chain is not None
        assert [layer.id for layer in chain] == ["org"]

        found = ms._find_store_layer(chain)
        assert found is not None
        layer, cfg = found
        assert layer.id == "org"
        assert cfg["INFISICAL_WORKSPACE_ID"] == "ws-from-overlay"
        assert cfg["INFISICAL_ENVIRONMENT"] == "prod"
        assert cfg["INFISICAL_SECRET_PATH"] == "/shared"

        assert resolve_from_store("DISCORD_BOT_TOKEN", chain) == "tok-abc"
        assert fake.calls == 1
        assert any(key[1] == "ws-from-overlay" for key in ms._SECRET_CACHE)


class TestNearestWinsAcrossConfigFold:
    def test_nearer_empty_env_does_not_clobber_farther_tier_config(
        self, monkeypatch, _isolated_layers
    ):
        """A dept layer ABOVE org (nearer, higher precedence) with an EMPTY
        `.env` and no overlay at all must not block resolution -- the store
        gate keeps walking outward and still finds org's committed
        `config:`, proving a nearer tier's empty `.env` does not clobber a
        farther tier's inherited config."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "dept",
                    "role": "department",
                    "component": "cli",
                    "rank": 20,
                    "source": {"repo": "git@github-work:acme/cli-copilot-dept.git"},
                    "auth": "ssh-work",
                },
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                },
            ],
        )
        dept_root = _mirror_dir(mirrors_root, "dept")
        (dept_root / ".env").write_text("")  # present, empty, no store config, no overlay

        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(yaml.safe_dump(_ORG_OVERLAY_CONFIG))

        fake = _install_fake(
            monkeypatch, secrets=[{"secretKey": "DISCORD_BOT_TOKEN", "secretValue": "tok-abc"}]
        )

        chain = resolve_cli_layer_chain()
        assert chain is not None
        assert [layer.id for layer in chain] == ["dept", "org"]  # nearest first

        found = ms._find_store_layer(chain)
        assert found is not None
        layer, cfg = found
        assert layer.id == "org"
        assert cfg["INFISICAL_WORKSPACE_ID"] == "ws-from-overlay"

        assert resolve_from_store("DISCORD_BOT_TOKEN", chain) == "tok-abc"
        assert fake.calls == 1
        assert any(key[1] == "ws-from-overlay" for key in ms._SECRET_CACHE)
        assert not any(key[1] == "ws-dept" for key in ms._SECRET_CACHE)


class TestProvidesConfigInheritsFromCommittedOverlay:
    """ADR-001: `provides[].config` feeds `managed_store._find_store_layer`
    exactly like `adopt[].config` does -- same test as
    `TestConfigInheritsFromCommittedOverlay.test_store_resolves_with_zero_env`
    above, but the store config lives under a `provides:` entry (a tier
    shipping its OWN service, e.g. an org's `coolify` adapter, that also
    happens to declare the tier's managed-store config) instead of `adopt:`.
    """

    def test_store_resolves_with_zero_env_via_provides_config(self, monkeypatch, _isolated_layers):
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "copilot_overlay_internal.services.coolify.commands",
                            "config": {
                                "infisical_base_url": "https://secrets.example.com",
                                "infisical_workspace_id": "ws-from-provides-overlay",
                                "infisical_environment": "prod",
                                "infisical_secret_path": "/shared",
                            },
                        }
                    ],
                }
            )
        )
        assert not (org_root / ".env").exists()  # the point of this case

        fake = _install_fake(
            monkeypatch, secrets=[{"secretKey": "DISCORD_BOT_TOKEN", "secretValue": "tok-abc"}]
        )

        chain = resolve_cli_layer_chain()
        assert chain is not None
        assert [layer.id for layer in chain] == ["org"]

        found = ms._find_store_layer(chain)
        assert found is not None
        layer, cfg = found
        assert layer.id == "org"
        assert cfg["INFISICAL_WORKSPACE_ID"] == "ws-from-provides-overlay"

        assert resolve_from_store("DISCORD_BOT_TOKEN", chain) == "tok-abc"
        assert fake.calls == 1
        assert any(key[1] == "ws-from-provides-overlay" for key in ms._SECRET_CACHE)


class TestSettingsSourcePrecedence:
    """Permanent `Settings()`-level regression test for `TierConfigSource`
    precedence (`settings.py`'s `settings_customise_sources` layered path).
    The two test classes above only ever exercise
    `managed_store._find_store_layer`'s independent config fold -- neither
    instantiates a real `Settings()`, so `TierConfigSource`'s interleave
    into the pydantic-settings source tuple has no permanent coverage of its
    own. This class closes that gap.

    Uses `uspto_cli_base_url` -- a REAL `Settings` model field (see
    `copilot_cli/config/settings.py`), unlike the `infisical_*` overlay keys
    used above, which only feed `managed_store._find_store_layer` and are
    never read by `Settings` itself.
    """

    def test_uspto_cli_base_url_is_a_real_settings_field(self):
        """Canary for the field choice itself: if `uspto_cli_base_url` were
        ever renamed/removed, both tests below would still call `Settings()`
        successfully (extra="ignore") but silently stop proving anything --
        this assertion fails loudly instead."""
        from copilot_cli.config.settings import Settings

        assert "uspto_cli_base_url" in Settings.model_fields

    def test_same_tier_config_beats_own_env(self, monkeypatch, _isolated_layers):
        """A single tier whose committed overlay `config:` sets a field AND
        whose OWN `.env` sets the SAME field to a different value -- the
        overlay `config:` wins. This is exactly the `TierConfigSource` vs.
        that same layer's `DotEnvSettingsSource` ordering added in
        `settings_customise_sources`; if that interleave were removed (both
        sources reverted to plain per-tier `.env` merging, or `.env` were
        ever placed ahead of `TierConfigSource`), this assertion would flip
        to the `.env` value and fail."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "adopt": [
                        {
                            "service": "uspto",
                            "config": {"uspto_cli_base_url": "https://from-overlay.example"},
                        }
                    ],
                }
            )
        )
        (org_root / ".env").write_text("USPTO_CLI_BASE_URL=https://from-dotenv.example\n")

        from copilot_cli.config.settings import Settings

        settings = Settings()
        assert settings.uspto_cli_base_url == "https://from-overlay.example"

    def test_nearer_env_beats_farther_config(self, monkeypatch, _isolated_layers):
        """A FARTHER tier's overlay `config:` vs. a NEARER tier's `.env` for
        the same field -- the nearer tier's `.env` still wins. This proves
        nearest-wins is preserved ACROSS tiers: `TierConfigSource` is
        interleaved immediately ahead of its OWN layer's `.env` only, never
        hoisted ahead of every layer's `.env` regardless of tier -- if it
        were (config globally ahead of `.env`), the farther (org) tier's
        `config:` would win here instead and this assertion would fail."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "dept",
                    "role": "department",
                    "component": "cli",
                    "rank": 20,
                    "source": {"repo": "git@github-work:acme/cli-copilot-dept.git"},
                    "auth": "ssh-work",
                },
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                },
            ],
        )
        dept_root = _mirror_dir(mirrors_root, "dept")
        (dept_root / ".env").write_text("USPTO_CLI_BASE_URL=https://from-dept-dotenv.example\n")

        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "adopt": [
                        {
                            "service": "uspto",
                            "config": {"uspto_cli_base_url": "https://from-org-overlay.example"},
                        }
                    ],
                }
            )
        )

        from copilot_cli.config.settings import Settings

        chain = resolve_cli_layer_chain()
        assert chain is not None
        assert [layer.id for layer in chain] == ["dept", "org"]  # nearest first

        settings = Settings()
        assert settings.uspto_cli_base_url == "https://from-dept-dotenv.example"

    def test_provides_config_resolves_with_zero_env(self, monkeypatch, _isolated_layers):
        """ADR-001 acceptance test: a `provides:` entry's `config:` block
        resolves through `TierConfigSource` into a real `Settings` field,
        with NO `.env` at all -- `provides[].config` works exactly like
        `adopt[].config` (`test_same_tier_config_beats_own_env` above proves
        the adopt-config version of this same claim)."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "copilot_overlay_internal.services.coolify.commands",
                            "config": {
                                "uspto_cli_base_url": "https://from-provides-overlay.example"
                            },
                        }
                    ],
                }
            )
        )
        assert not (org_root / ".env").exists()

        from copilot_cli.config.settings import Settings

        settings = Settings()
        assert settings.uspto_cli_base_url == "https://from-provides-overlay.example"

    def test_nearer_env_beats_farther_provides_config(self, monkeypatch, _isolated_layers):
        """Cross-tier nearest-wins holds for `provides[].config` exactly as it
        does for `adopt[].config` (`test_nearer_env_beats_farther_config`
        above): a NEARER tier's plain `.env` still beats a FARTHER tier's
        committed `provides:` `config:` for the same field."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "dept",
                    "role": "department",
                    "component": "cli",
                    "rank": 20,
                    "source": {"repo": "git@github-work:acme/cli-copilot-dept.git"},
                    "auth": "ssh-work",
                },
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                },
            ],
        )
        dept_root = _mirror_dir(mirrors_root, "dept")
        (dept_root / ".env").write_text("USPTO_CLI_BASE_URL=https://from-dept-dotenv.example\n")

        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "copilot_overlay_internal.services.coolify.commands",
                            "config": {
                                "uspto_cli_base_url": "https://from-org-provides-overlay.example"
                            },
                        }
                    ],
                }
            )
        )

        from copilot_cli.config.settings import Settings

        chain = resolve_cli_layer_chain()
        assert chain is not None
        assert [layer.id for layer in chain] == ["dept", "org"]  # nearest first

        settings = Settings()
        assert settings.uspto_cli_base_url == "https://from-dept-dotenv.example"

    def test_same_tier_provides_config_wins_over_adopt_config(self, monkeypatch, _isolated_layers):
        """Same-tier adopt-vs-provides collision rule (ADR-001): within ONE
        tier's overlay, if BOTH an `adopt[].config` block and a
        `provides[].config` block set the same field, `provides` wins.
        `TierConfigSource._collect_config` folds `provides` after `adopt`
        (matching the canonical adopt -> provides -> override declaration
        order documented in `layers.py`), so this is a deterministic
        last-write-wins tie-break, not an arbitrary one -- see that method's
        docstring for the full rationale. This is an authoring edge case
        (the two blocks normally configure different services / fields);
        the rule only has to be deterministic and documented, not "smart".
        """
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(
            manifest_path,
            [
                {
                    "id": "org",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "adopt": [
                        {
                            "service": "uspto",
                            "config": {"uspto_cli_base_url": "https://from-adopt.example"},
                        }
                    ],
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "copilot_overlay_internal.services.coolify.commands",
                            "config": {"uspto_cli_base_url": "https://from-provides.example"},
                        }
                    ],
                }
            )
        )

        from copilot_cli.config.settings import Settings

        settings = Settings()
        assert settings.uspto_cli_base_url == "https://from-provides.example"

    def test_collect_config_folds_adopt_and_provides_unit(self, tmp_path, monkeypatch):
        """Unit-level companion to the two Settings()-level tests above:
        exercises `TierConfigSource._collect_config` directly against a
        `CliLayer`, without going through pydantic-settings at all."""
        from copilot_cli.config.layers import CliLayer
        from copilot_cli.config.settings import TierConfigSource

        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "adopt": [
                        {
                            "service": "uspto",
                            "config": {"shared_field": "from-adopt", "adopt_only": "a"},
                        }
                    ],
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "pkg.mod",
                            "config": {"shared_field": "from-provides", "provides_only": "p"},
                        }
                    ],
                }
            )
        )
        layer = CliLayer(
            id="org", role="org", rank=30, repo="r", ref="main", auth="anon", root=tmp_path
        )
        merged = TierConfigSource._collect_config(layer)
        assert merged == {
            "shared_field": "from-provides",  # provides wins on collision
            "adopt_only": "a",
            "provides_only": "p",
        }
