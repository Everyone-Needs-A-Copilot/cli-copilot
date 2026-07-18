"""Phase-1 hard gate for the CLI tier-inheritance model.

With no `copilot.layers.yml` resolving anywhere the CLI looks, `copilot`
must behave byte-for-byte as it did before this change (v1.4.5):

  (a) `resolve_cli_services()` yields exactly the base 12 services, same
      names, same order, same help text `main.py` used to hardcode.
  (b) `Settings` resolves identically to the pre-change behavior for a
      fixed env, with `COPILOT_ENV_FILE` honored exactly as before.

This is the fitness test the tier-inheritance design doc's D5 (the
"live-tool risk" decision) requires to gate any merge of the layered
`settings.py` / manifest-driven `services/_loader.py` change. See
`docs/03-tier-inheritance.md`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from copilot_cli.config.layers import resolve_cli_layer_chain
from copilot_cli.config.settings import Settings
from copilot_cli.services._loader import resolve_cli_services

# The exact 12 (name, help) pairs `main.py` hardcoded pre-Phase-1, in
# registration order. Frozen here so a drift in `_loader.py`'s
# `_BASE_SERVICES` is caught against an independent expectation, not just
# "the loader agrees with itself."
EXPECTED_BASE_SERVICES: tuple[tuple[str, str], ...] = (
    ("git", "Git repository operations"),
    ("docker", "Docker container management"),
    ("shell", "Shell command execution"),
    ("fs", "File system operations"),
    ("services", "System service management (launchctl)"),
    ("db", "PostgreSQL database operations"),
    ("docs", "Document management"),
    ("bi", "Business intelligence"),
    ("monitoring", "System monitoring"),
    ("infisical", "Infisical secrets management"),
    ("skill", "Skill runtime — discover, execute, verify skills"),
    ("uspto", "USPTO patent and trademark data access"),
)


@pytest.fixture(autouse=True)
def _no_manifest_anywhere(tmp_path, monkeypatch):
    """Guarantee the fast path is actually reached: no `copilot.layers.yml`
    resolves from any source (explicit override, CWD walk-up, or standard
    user config locations) -- so these in-process assertions can't be
    accidentally satisfied by a manifest that happens to exist elsewhere on
    this machine."""
    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    monkeypatch.chdir(project_dir)


class TestNoManifestFastPath:
    def test_resolve_cli_layer_chain_is_none(self):
        assert resolve_cli_layer_chain() is None

    def test_resolve_cli_services_yields_exactly_the_base_12(self):
        services = resolve_cli_services()
        actual = tuple((svc.name, svc.help) for svc in services)
        assert actual == EXPECTED_BASE_SERVICES

    def test_every_base_service_reports_foundation_base_provenance(self):
        for svc in resolve_cli_services():
            assert svc.tier == "foundation"
            assert svc.mode == "base"

    def test_settings_customise_sources_matches_pydantic_settings_default(self):
        """Proves the mechanism, not just the outcome: when no manifest
        resolves, `Settings.settings_customise_sources` returns EXACTLY
        what `pydantic_settings.BaseSettings`'s own unmodified default
        implementation returns for the same inputs -- i.e. overriding the
        hook changes nothing when the chain is `None`."""
        from pydantic_settings import BaseSettings

        sentinels = ("init-sentinel", "env-sentinel", "dotenv-sentinel", "secrets-sentinel")
        gated = Settings.settings_customise_sources(Settings, *sentinels)
        default = BaseSettings.settings_customise_sources(Settings, *sentinels)
        assert gated == default == sentinels


class TestSettingsFixedEnvParity:
    def test_settings_honors_copilot_env_file_identically_to_v1_4_5(self, tmp_path):
        """Env-file resolution bakes into `Settings.model_config.env_file`
        at *module import time* (see `_find_env_file()` in
        `config/settings.py`, and `TestPortability`'s own note in
        `test_soul_conformance.py`), so in-process monkeypatching of
        `COPILOT_ENV_FILE` after this test module's imports have already
        run cannot exercise it -- a genuinely fresh interpreter is
        required, exactly as the existing portability tests already do.
        """
        foreign_cwd = tmp_path / "not-this-repo"
        foreign_cwd.mkdir()
        env_file = tmp_path / "fixed.env"
        env_file.write_text(
            "GIT_USER_NAME=parity-user\n"
            "GIT_USER_EMAIL=parity@example.com\n"
            "DATABASE_URL=postgresql://parity:parity@localhost:5432/paritydb\n"
            "LOG_LEVEL=debug\n"
        )
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)

        env = {**os.environ, "COPILOT_ENV_FILE": str(env_file), "HOME": str(home)}
        env.pop("COPILOT_LAYERS_FILE", None)
        env.pop("XDG_CONFIG_HOME", None)

        script = (
            "import json\n"
            "from copilot_cli.config.layers import resolve_cli_layer_chain\n"
            "from copilot_cli.config.settings import get_settings\n"
            "s = get_settings()\n"
            "print(json.dumps({\n"
            "    'chain_is_none': resolve_cli_layer_chain() is None,\n"
            "    'git_user_name': s.git_user_name,\n"
            "    'git_user_email': s.git_user_email,\n"
            "    'database_url': s.database_url,\n"
            "    'log_level': s.log_level,\n"
            "    'docker_socket': s.docker_socket,\n"
            "    'shell_timeout': s.shell_timeout,\n"
            "}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(foreign_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip())

        # No manifest resolves anywhere in this subprocess either -- the
        # fast path was truly reached, not just "happened to look right."
        assert payload["chain_is_none"] is True
        # COPILOT_ENV_FILE is honored exactly as pre-Phase-1.
        assert payload["git_user_name"] == "parity-user"
        assert payload["git_user_email"] == "parity@example.com"
        assert payload["database_url"] == "postgresql://parity:parity@localhost:5432/paritydb"
        assert payload["log_level"] == "debug"
        # Untouched fields still fall through to class defaults -- proves
        # this is a genuine [env-file, defaults] merge, not something
        # layering-specific clobbering every field.
        assert payload["docker_socket"] == "/var/run/docker.sock"
        assert payload["shell_timeout"] == 3600
