"""ADR-002 acceptance tests for `InfisicalSettings.base_url`'s tier-source
fallback (`services/infisical/core/config.py`'s `_tier_config_value` /
`load_settings`).

Covers:
- No-`.env` acceptance: `base_url` resolves from the nearest tier's
  committed `cli.overlay.yml` `config:` block with zero `.env` anywhere in
  the scratch tree.
- Back-compat: an explicit env var / `.env` value always wins over a
  differing tier `config:` value -- byte-identical to pre-ADR-002 behavior.
- No circular dependency: the `base_url` tier-fallback path never
  constructs `Settings()` and never touches the managed store -- proven by
  spying on both (and having the spy raise, for a loud, unambiguous
  failure) and asserting zero calls while `base_url` still resolves
  correctly.

Isolation pattern mirrors `tests/test_config/test_config_inheritance.py`
(`_isolated_layers`, `_write_manifest`, `_mirror_dir`) -- a scratch
`COPILOT_LAYERS_FILE` + `COPILOT_MIRRORS_ROOT`, never the real machine
`~/.config/copilot/copilot.layers.yml` / `~/.copilot/mirrors`, and never a
real OS-keychain or network call (the keychain rung is monkeypatched to a
deterministic miss in every test below, matching
`test_config_inheritance.py`'s own posture).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from copilot_cli.config.secrets_ladder import _SecretRungUnavailable

_ORG_LAYER = {
    "id": "org",
    "role": "org",
    "product": "cli",
    "rank": 30,
    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git"},
    "auth": "ssh-work",
}


def _write_manifest(path: Path, layers: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"version": 1, "layers": layers}))


def _mirror_dir(mirrors_root: Path, layer_id: str) -> Path:
    d = mirrors_root / "mirrors" / "cli" / layer_id
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def _isolated_layers(tmp_path, monkeypatch):
    """Point BOTH layer-manifest and mirror-root discovery at a scratch tmp
    tree -- never the real `copilot.layers.yml` / `~/.copilot/mirrors`."""
    mirrors_root = tmp_path / "mirrors-root"
    manifest_path = tmp_path / "copilot.layers.yml"
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(mirrors_root))
    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest_path))
    return manifest_path, mirrors_root


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    """Every test below is a fully isolated scratch scenario -- never let a
    real bootstrap credential on this machine's OS keychain leak in (this
    machine legitimately has `INFISICAL_CLIENT_ID`/`_SECRET` entries for
    live use, which would make an "isolated" test non-deterministic)."""

    def _always_miss(name: str, chain: object) -> str:
        raise _SecretRungUnavailable(f"no fake keychain entry for {name}")

    monkeypatch.setattr("copilot_cli.config.secrets_ladder._rung_keychain", _always_miss)


def _write_org_overlay(org_root: Path, base_url: str) -> None:
    (org_root / "cli.overlay.yml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "adopt": [{"service": "infisical", "config": {"infisical_base_url": base_url}}],
            }
        )
    )


class TestNoEnvAcceptance:
    """The no-`.env` acceptance case: `base_url` resolves purely from the
    committed overlay, with NO `.env` anywhere in the scratch tree."""

    def test_base_url_resolves_from_committed_overlay_with_zero_env(
        self, monkeypatch, _isolated_layers
    ):
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(manifest_path, [_ORG_LAYER])
        org_root = _mirror_dir(mirrors_root, "org")
        _write_org_overlay(org_root, "https://secrets.example.com")
        assert not (org_root / ".env").exists()  # the point of this case

        from copilot_cli.services.infisical.core import config as infisical_config

        # Deterministic "no .env anywhere" -- avoids any CWD-walk-up flakiness.
        monkeypatch.setattr(infisical_config, "find_env_file", lambda search_root=None: None)

        settings = infisical_config.load_settings()
        assert settings.base_url == "https://secrets.example.com"

    def test_provides_config_also_folds_for_base_url(self, monkeypatch, _isolated_layers):
        """`infisical_base_url` folds identically whether declared under
        `adopt:` (the real committed shape) or `provides:` (ADR-001
        symmetry, same `_collect_config`-shaped fold `_tier_config_value`
        mirrors)."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(manifest_path, [_ORG_LAYER])
        org_root = _mirror_dir(mirrors_root, "org")
        (org_root / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "provides": [
                        {
                            "service": "some-service",
                            "module": "pkg.mod",
                            "config": {"infisical_base_url": "https://from-provides.example"},
                        }
                    ],
                }
            )
        )

        from copilot_cli.services.infisical.core import config as infisical_config

        monkeypatch.setattr(infisical_config, "find_env_file", lambda search_root=None: None)

        settings = infisical_config.load_settings()
        assert settings.base_url == "https://from-provides.example"


class TestBackCompat:
    """An explicit value from env/`.env` always wins over a differing tier
    `config:` value -- byte-identical to pre-ADR-002 behavior."""

    def test_env_var_beats_tier_overlay(self, monkeypatch, _isolated_layers):
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(manifest_path, [_ORG_LAYER])
        org_root = _mirror_dir(mirrors_root, "org")
        _write_org_overlay(org_root, "https://from-overlay.example")

        monkeypatch.setenv("INFISICAL_BASE_URL", "https://from-env.example")

        from copilot_cli.services.infisical.core import config as infisical_config

        monkeypatch.setattr(infisical_config, "find_env_file", lambda search_root=None: None)

        settings = infisical_config.load_settings()
        assert settings.base_url == "https://from-env.example"

    def test_dotenv_file_beats_tier_overlay(self, monkeypatch, _isolated_layers, tmp_path):
        """Mirrors the real-world shape: a project `.env` (like this tier's
        real committed `.env` today) sets `INFISICAL_BASE_URL` -- that value
        wins even though a tier overlay is also configured (with a
        DIFFERENT value), proving the fallback only ever activates when
        `.env` stops setting the value."""
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(manifest_path, [_ORG_LAYER])
        org_root = _mirror_dir(mirrors_root, "org")
        _write_org_overlay(org_root, "https://from-overlay.example")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".env").write_text("INFISICAL_BASE_URL=https://from-dotenv.example\n")
        monkeypatch.chdir(project_dir)

        from copilot_cli.services.infisical.core.config import load_settings

        settings = load_settings()
        assert settings.base_url == "https://from-dotenv.example"

    def test_no_manifest_is_byte_identical_to_pre_adr_002(self, monkeypatch, tmp_path):
        """No `copilot.layers.yml` resolves at all (today's default on most
        machines) -- `_tier_config_value` must return `None` and `base_url`
        must resolve exactly as it always has: `.env` if present, else the
        hard default. This is the fast path every pre-ADR-002 caller took."""
        monkeypatch.setenv("COPILOT_LAYERS_FILE", "/nonexistent/no-manifest.yml")
        monkeypatch.delenv("COPILOT_MIRRORS_ROOT", raising=False)

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".env").write_text("INFISICAL_BASE_URL=https://from-dotenv.example\n")
        monkeypatch.chdir(project_dir)

        from copilot_cli.services.infisical.core.config import load_settings

        settings = load_settings()
        assert settings.base_url == "https://from-dotenv.example"

    def test_no_manifest_and_no_env_falls_back_to_hard_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COPILOT_LAYERS_FILE", "/nonexistent/no-manifest.yml")
        monkeypatch.delenv("COPILOT_MIRRORS_ROOT", raising=False)

        from copilot_cli.services.infisical.core import config as infisical_config

        monkeypatch.setattr(infisical_config, "find_env_file", lambda search_root=None: None)

        settings = infisical_config.load_settings()
        assert settings.base_url == infisical_config._DEFAULT_BASE_URL


class TestNoCircularDependency:
    """`base_url` resolution must never construct `Settings()` and must
    never touch the managed store -- both are spied on (and raise, for an
    unambiguous failure) while `base_url` still resolves correctly."""

    def test_base_url_never_constructs_settings_or_touches_the_store(
        self, monkeypatch, _isolated_layers
    ):
        manifest_path, mirrors_root = _isolated_layers
        _write_manifest(manifest_path, [_ORG_LAYER])
        org_root = _mirror_dir(mirrors_root, "org")
        _write_org_overlay(org_root, "https://from-overlay.example")

        import copilot_cli.config.managed_store as managed_store_module
        import copilot_cli.config.settings as settings_module

        settings_init_calls = {"count": 0}

        def _boom_settings_init(*args, **kwargs):
            settings_init_calls["count"] += 1
            raise AssertionError("Settings() must never be constructed by the base_url path")

        store_calls = {"count": 0}

        def _boom_store(*args, **kwargs):
            store_calls["count"] += 1
            raise AssertionError("the managed store must never be touched by the base_url path")

        monkeypatch.setattr(settings_module.Settings, "__init__", _boom_settings_init)
        monkeypatch.setattr(managed_store_module, "resolve_from_store", _boom_store)
        # Belt-and-suspenders: also guard the lower-level client construction
        # in case a future refactor bypasses `resolve_from_store`.
        monkeypatch.setattr(
            "copilot_cli.services.infisical.core.api_client.InfisicalClient", _boom_store
        )

        from copilot_cli.services.infisical.core import config as infisical_config

        monkeypatch.setattr(infisical_config, "find_env_file", lambda search_root=None: None)

        settings = infisical_config.load_settings()

        assert settings.base_url == "https://from-overlay.example"
        assert settings_init_calls["count"] == 0
        assert store_calls["count"] == 0
