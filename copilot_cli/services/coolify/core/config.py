"""Configuration management for Coolify CLI.

Three config layers with ascending priority:
1. ``~/.coolify-cli/config.toml`` — persistent file
2. Environment variables (``COOLIFY_ACCESS_TOKEN``, ``COOLIFY_BASE_URL``, etc.)
   including a local ``.env`` file (searched upward from ``cwd``)
3. CLI flags (``--token``, ``--base-url``, ``--config``)

The ``init`` wizard can optionally seed credentials from a project-level
``.mcp.json`` file (used by the Coolify MCP server).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from copilot_cli.services.coolify.core.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR: Path = Path.home() / ".coolify-cli"
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

# ---------------------------------------------------------------------------
# Settings models — env-var layer handled by pydantic-settings
# ---------------------------------------------------------------------------


class APIConfig(BaseSettings):
    """Coolify API connection settings."""

    base_url: str = ""
    access_token: str = ""
    api_key: str = ""

    model_config = {"env_prefix": "COOLIFY_", "extra": "ignore"}

    @model_validator(mode="after")
    def _coerce_api_key(self) -> APIConfig:
        """Allow COOLIFY_API_KEY as an alias for COOLIFY_ACCESS_TOKEN."""
        if not self.access_token and self.api_key:
            self.access_token = self.api_key
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            self.base_url = f"https://{self.base_url}"
        return self


class SSHConfig(BaseSettings):
    """SSH tunnel settings for log streaming / exec."""

    host: str = ""
    user: str = "root"
    port: int = 22
    key_file: str = str(Path.home() / ".ssh" / "id_ed25519")

    model_config = {"env_prefix": "COOLIFY_SSH_", "extra": "ignore"}


class DefaultsConfig(BaseSettings):
    """CLI output defaults."""

    output_format: str = "table"
    page_size: int = 50
    log_lines: int = 100

    model_config = {"env_prefix": "COOLIFY_DEFAULTS_", "extra": "ignore"}


class MonitoringConfig(BaseSettings):
    """Thresholds and intervals for the monitoring dashboard."""

    dashboard_refresh: int = 2
    health_check_interval: int = 30
    ssl_warn_days: int = 30
    cpu_threshold: int = 80
    memory_threshold: int = 85
    disk_threshold: int = 90
    response_time_ms: int = 2000

    model_config = {"env_prefix": "COOLIFY_MONITORING_", "extra": "ignore"}


class Settings(BaseSettings):
    """Root settings container that composes all sub-sections."""

    api: APIConfig = Field(default_factory=APIConfig)
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# TOML persistence
# ---------------------------------------------------------------------------


def load_toml_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from a TOML file.

    Args:
        config_path: Explicit path. Falls back to ``~/.coolify-cli/config.toml``.

    Returns:
        Parsed TOML data as a nested dict, or an empty dict when the file
        does not exist.
    """
    path = config_path or CONFIG_FILE
    if not path.exists():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def save_toml_config(data: dict[str, Any], config_path: Path | None = None) -> Path:
    """Write configuration to a TOML file.

    The parent directory is created if it does not exist and the file
    permissions are restricted to owner-only (``0o600``) because the file
    contains API tokens.

    Args:
        data: Nested dict matching the TOML structure.
        config_path: Target path. Defaults to ``~/.coolify-cli/config.toml``.

    Returns:
        The resolved ``Path`` that was written.
    """
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        tomli_w.dump(data, fh)
    path.chmod(0o600)
    return path


# ---------------------------------------------------------------------------
# MCP credential discovery
# ---------------------------------------------------------------------------

_MCP_SERVER_KEY = "coolify"


def find_mcp_credentials(search_root: Path | None = None) -> dict[str, str] | None:
    """Locate Coolify credentials inside a ``.mcp.json`` file.

    Searches the *search_root* (defaults to ``cwd()``) and each of its
    parent directories up to the filesystem root.  The first ``.mcp.json``
    that contains a ``mcpServers.coolify.env`` section with both
    ``COOLIFY_ACCESS_TOKEN`` and ``COOLIFY_BASE_URL`` wins.

    Args:
        search_root: Starting directory for the upward walk. Defaults to
            the current working directory.

    Returns:
        A dict with ``access_token`` and ``base_url`` keys, or ``None``
        if no matching file is found.
    """
    start = search_root or Path.cwd()

    for directory in [start, *start.parents]:
        mcp_file = directory / ".mcp.json"
        if not mcp_file.is_file():
            continue
        try:
            raw = json.loads(mcp_file.read_text(encoding="utf-8"))
            env = raw.get("mcpServers", {}).get(_MCP_SERVER_KEY, {}).get("env", {})
            token: str = env.get("COOLIFY_ACCESS_TOKEN", "")
            base_url: str = env.get("COOLIFY_BASE_URL", "")
            if token and base_url:
                return {"access_token": token, "base_url": base_url}
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    return None


# ---------------------------------------------------------------------------
# .env discovery
# ---------------------------------------------------------------------------


def find_env_file(search_root: Path | None = None) -> Path | None:
    """Locate a ``.env`` file starting from *search_root* and walking upward."""
    start = search_root or Path.cwd()
    for directory in [start, *start.parents]:
        env_file = directory / ".env"
        if env_file.is_file():
            return env_file
    return None


# ---------------------------------------------------------------------------
# Unified settings loader
# ---------------------------------------------------------------------------


def load_settings(
    config_path: Path | None = None,
    base_url_override: str | None = None,
    token_override: str | None = None,
) -> Settings:
    """Load settings by merging all three configuration layers.

    Priority (highest wins):
        1. *CLI flag overrides* — ``base_url_override`` / ``token_override``
        2. *Environment variables* — handled automatically by pydantic-settings
           (e.g. ``COOLIFY_ACCESS_TOKEN``, ``COOLIFY_BASE_URL``)
        3. *TOML config file* — ``~/.coolify-cli/config.toml``

    Args:
        config_path: Optional non-default path to a TOML config file.
        base_url_override: Value from ``--base-url`` CLI flag.
        token_override: Value from ``--token`` CLI flag.

    Returns:
        A fully-resolved ``Settings`` instance.
    """
    toml_data = load_toml_config(config_path)

    api_data = toml_data.get("api", {})
    ssh_data = toml_data.get("ssh", {})
    defaults_data = toml_data.get("defaults", {})
    monitoring_data = toml_data.get("monitoring", {})

    env_file = find_env_file()

    # pydantic-settings merges env vars (and .env if present) on top of kwargs
    api = APIConfig(**api_data, _env_file=env_file)
    ssh = SSHConfig(**ssh_data, _env_file=env_file)
    defaults = DefaultsConfig(**defaults_data, _env_file=env_file)
    monitoring = MonitoringConfig(**monitoring_data, _env_file=env_file)

    # CLI flags override everything
    if base_url_override:
        api.base_url = base_url_override
    if token_override:
        api.access_token = token_override

    return Settings(api=api, ssh=ssh, defaults=defaults, monitoring=monitoring)


def require_settings(
    config_path: Path | None = None,
    base_url_override: str | None = None,
    token_override: str | None = None,
) -> Settings:
    """Load settings and raise ``ConfigError`` when credentials are missing.

    This is the primary entry point used by commands that need a valid API
    connection. It calls ``load_settings`` and then validates that both
    ``api.base_url`` and ``api.access_token`` are non-empty.

    Raises:
        ConfigError: When either the base URL or access token is blank.
    """
    settings = load_settings(
        config_path=config_path,
        base_url_override=base_url_override,
        token_override=token_override,
    )
    missing: list[str] = []
    if not settings.api.base_url:
        missing.append("base_url (set COOLIFY_BASE_URL or run `coolify init`)")
    if not settings.api.access_token:
        missing.append("access_token (set COOLIFY_ACCESS_TOKEN or run `coolify init`)")
    if missing:
        raise ConfigError("Missing required configuration: " + "; ".join(missing))
    return settings


def get_config_path() -> Path:
    """Return the default config file path."""
    return CONFIG_FILE


def settings_to_toml(settings: Settings) -> dict[str, Any]:
    """Convert a ``Settings`` instance to a TOML-serialisable dict.

    This is the inverse of the TOML loading step and is used when writing
    the config file during ``coolify init``.
    """
    return {
        "api": {
            "base_url": settings.api.base_url,
            "access_token": settings.api.access_token,
        },
        "ssh": {
            "host": settings.ssh.host,
            "user": settings.ssh.user,
            "port": settings.ssh.port,
            "key_file": settings.ssh.key_file,
        },
        "defaults": {
            "output_format": settings.defaults.output_format,
            "page_size": settings.defaults.page_size,
            "log_lines": settings.defaults.log_lines,
        },
        "monitoring": {
            "dashboard_refresh": settings.monitoring.dashboard_refresh,
            "health_check_interval": settings.monitoring.health_check_interval,
            "ssl_warn_days": settings.monitoring.ssl_warn_days,
            "cpu_threshold": settings.monitoring.cpu_threshold,
            "memory_threshold": settings.monitoring.memory_threshold,
            "disk_threshold": settings.monitoring.disk_threshold,
            "response_time_ms": settings.monitoring.response_time_ms,
        },
    }
