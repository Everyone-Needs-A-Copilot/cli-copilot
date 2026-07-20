"""Pydantic Settings - loads all credentials from project root .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource

from copilot_cli.config.layers import CliLayer, load_tier_overlay, resolve_cli_layer_chain
from copilot_cli.config.secrets_ladder import resolve_secret


def _find_env_file() -> Path:
    """Walk up from CWD to find the nearest .env file.

    Resolution order:
    1. COPILOT_ENV_FILE environment variable (explicit override)
    2. Walk up from CWD, stopping at project root markers
    3. Standard machine-agnostic user config locations ($HOME-relative, so they
       are identical on every machine and carry no hardcoded absolute paths).
       This is what lets a hook or script running in any project subdirectory
       find the shared copilot config without a baked path.
    4. Fall back to .env in current directory
    """
    import os

    # 1. Explicit override
    explicit = os.environ.get("COPILOT_ENV_FILE")
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p

    # 2. Walk up from CWD
    current = Path.cwd()
    root_markers = {".git", "pyproject.toml", ".mcp.json", "package.json"}
    for parent in [current, *current.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
        # Stop at any project root marker
        if any((parent / marker).exists() for marker in root_markers):
            return parent / ".env"

    # 3. Standard user config locations (portable across machines)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    standard = [
        Path(xdg) / "copilot" / ".env" if xdg else Path.home() / ".config" / "copilot" / ".env",
        Path.home() / ".copilot-cli" / ".env",
    ]
    for candidate in standard:
        if candidate.is_file():
            return candidate

    # 4. Fallback
    return Path(".env")


class SecretRefSource(PydanticBaseSettingsSource):
    """Resolves declared `requires_secret: <NAME>` refs via the credential
    ladder (`secrets_ladder.resolve_secret`) -- the single place a secret
    *value* enters `Settings` in the layered path. Only engaged when
    `settings_customise_sources` builds the layered source tuple (i.e. a
    `copilot.layers.yml` with `component: cli` entries resolves); the
    manifest-absent fast path never constructs this class.

    A field only resolves through this source if some tier's
    `cli.overlay.yml` declares it in `requires_secret` (matched
    case-insensitively: `USPTO_CLI_API_KEY` -> `uspto_cli_api_key`). Every
    other field is left untouched here, falling through to the tier `.env`
    sources ahead of it in the tuple.

    Fail-closed by construction: a declared secret that misses every ladder
    rung raises `SecretResolutionError` (via `resolve_secret`) instead of
    silently leaving the field at its `""` default -- see
    `secrets_ladder.py` and red-team §6.3 ("no silent no-op").

    A declared secret may also carry a per-name routing hint (`cli.overlay.
    yml`'s mapping-form `requires_secret: [{name, from}]`, parsed by
    `layers.load_tier_overlay` into `TierOverlay.all_requires_secret_hints()`)
    -- threaded through to `resolve_secret`'s `prefer` param below. The hint
    is a pure ladder-rung filter (see `secrets_ladder._RUNG_SUBSET_FOR_HINT`):
    it never changes *whether* a name resolves through this source, only
    which rungs are consulted while resolving it.
    """

    def __init__(self, settings_cls: type[BaseSettings], chain: list[CliLayer]):
        super().__init__(settings_cls)
        self._chain = chain
        self._secret_names, self._secret_hints = self._collect_secret_names(chain)

    @staticmethod
    def _collect_secret_names(chain: list[CliLayer]) -> tuple[set[str], dict[str, str]]:
        names: set[str] = set()
        hints: dict[str, str] = {}
        for layer in chain:
            overlay = load_tier_overlay(layer.overlay_path)
            names.update(overlay.all_requires_secret())
            # Nearest tier wins on a hint conflict, same as every other
            # nearest-wins fold in this module -- `chain` is already
            # highest-precedence-first, so first-seen-per-name wins here.
            for name, hint in overlay.all_requires_secret_hints().items():
                hints.setdefault(name, hint)
        return names, hints

    def get_field_value(self, field, field_name: str) -> tuple[object, str, bool]:
        env_name = field_name.upper()
        if env_name not in self._secret_names:
            return None, field_name, False
        prefer = self._secret_hints.get(env_name)
        return resolve_secret(env_name, self._chain, prefer=prefer), field_name, False

    def __call__(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field, field_name)
            if value is None:
                continue
            result[key] = self.prepare_field_value(field_name, field, value, is_complex)
        return result


class TierConfigSource(PydanticBaseSettingsSource):
    """Surfaces ONE tier's committed `cli.overlay.yml` `adopt[].config` block
    as a settings source -- the config-inheritance counterpart to
    `SecretRefSource`. This is what lets non-secret store/service config
    (e.g. `infisical_workspace_id`) inherit down-tier from a committed
    overlay instead of only ever living in that tier's local `.env`.

    Unlike `SecretRefSource` (which spans the whole chain), one instance
    covers exactly one layer, so `settings_customise_sources` can interleave
    it immediately AHEAD of that SAME layer's `DotEnvSettingsSource` in the
    source tuple -- giving a tier's committed `config:` precedence over its
    OWN `.env`, while a NEARER tier's `.env` still outranks a FARTHER tier's
    `config:` because nearest-wins is preserved by source ORDER, not by
    anything in this class.

    Overlay config keys are already lowercase field-name-shaped (e.g.
    `infisical_base_url`, matching the field name exactly, matched
    case-sensitively here); a key that isn't an actual `Settings` field
    simply never matches any `field_name` iterated in `__call__` below --
    belt-and-suspenders alongside `extra="ignore"`.
    """

    def __init__(self, settings_cls: type[BaseSettings], layer: CliLayer):
        super().__init__(settings_cls)
        self._config = self._collect_config(layer)

    @staticmethod
    def _collect_config(layer: CliLayer) -> dict[str, str]:
        overlay = load_tier_overlay(layer.overlay_path)
        merged: dict[str, str] = {}
        for adopt in overlay.adopt:
            merged.update(adopt.config)
        return merged

    def get_field_value(self, field, field_name: str) -> tuple[object, str, bool]:
        if field_name not in self._config:
            return None, field_name, False
        return self._config[field_name], field_name, False

    def __call__(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field, field_name)
            if value is None:
                continue
            result[key] = self.prepare_field_value(field_name, field, value, is_complex)
        return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_find_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer the CLI tier chain into settings resolution -- gated
        entirely behind `resolve_cli_layer_chain()` (design doc §1.2, D5).

        No manifest resolves (or none of its entries are `component: cli`)
        -> returns the IDENTICAL source tuple as pre-Phase-1, so
        `_find_env_file()` (baked into `model_config.env_file` above) is
        reached completely unchanged and `COPILOT_ENV_FILE` keeps working
        exactly as it always has. This is the back-compat fast path the
        parity fitness test gates.
        """
        chain = resolve_cli_layer_chain()
        if chain is None:
            return (init_settings, env_settings, dotenv_settings, file_secret_settings)

        # ---- LAYERED PATH: highest precedence FIRST (personal ... foundation) ----
        # Per tier, a `TierConfigSource` is interleaved immediately AHEAD of
        # that SAME tier's `DotEnvSettingsSource` -- so a tier's committed
        # `cli.overlay.yml` config outranks its OWN `.env`, while a NEARER
        # tier's `.env` still outranks a FARTHER tier's `config:` (nearest-
        # wins preserved by list order, not by pairing). Do NOT hoist every
        # tier's config ahead of every tier's `.env` -- that would invert
        # nearest-wins across tiers.
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        for layer in chain:
            sources.append(TierConfigSource(cls, layer))
            sources.append(DotEnvSettingsSource(cls, env_file=layer.env_path))
        sources.append(SecretRefSource(cls, chain))
        return tuple(sources)

    # --- Git ---
    git_user_name: str = "copilot"
    git_user_email: str = "dev@example.com"

    # --- Docker ---
    docker_socket: str = "/var/run/docker.sock"

    # --- Shell ---
    shell_scripts_path: str = ""
    shell_timeout: int = 3600

    # --- PostgreSQL ---
    # nocodb_database_url / n8n_database_url are example *logical database
    # names* for the generic multi-DB feature (like formbricks_database_url,
    # which has never had a matching CLI service) -- unrelated to any
    # `copilot <service>` adapter of the same name.
    database_url: str = ""
    nocodb_database_url: str = ""
    n8n_database_url: str = ""
    formbricks_database_url: str = ""

    # --- Filesystem ---
    allowed_volumes: str = "/tmp"
    max_file_size_mb: int = 500

    # --- Monitoring ---
    cpu_alert_threshold: int = 80
    memory_alert_threshold: int = 85
    disk_alert_threshold: int = 90

    # --- USPTO ---
    uspto_cli_base_url: str = ""
    uspto_cli_api_key: str = ""
    uspto_tsdr_base_url: str = "https://tsdrapi.uspto.gov"

    # --- Skills ---
    skill_paths: str = ""  # Comma-separated additional skill search paths

    # --- Database backups / transfers ---
    backup_dir: str = "~/copilot-backups"

    # --- General ---
    log_level: str = "info"

    def get_allowed_volumes(self) -> list[str]:
        return [v.strip() for v in self.allowed_volumes.split(",") if v.strip()]

    def get_backup_dir(self) -> Path:
        """Return ``backup_dir`` as an expanded ``Path``. Does not create it."""
        return Path(self.backup_dir).expanduser()

    def get_database_configs(self) -> dict[str, str]:
        """Return map of database name -> connection URL."""
        configs: dict[str, str] = {}
        if self.nocodb_database_url:
            configs["nocodb"] = self.nocodb_database_url
        if self.n8n_database_url:
            configs["n8n"] = self.n8n_database_url
        if self.formbricks_database_url:
            configs["formbricks"] = self.formbricks_database_url
        if self.database_url:
            configs["main"] = self.database_url
        return configs


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
