"""Configuration management for the Infisical CLI.

Env-var layer (loaded from the project .env via pydantic-settings):
  INFISICAL_CLIENT_ID       — Universal Auth client ID
  INFISICAL_CLIENT_SECRET   — Universal Auth client secret
  INFISICAL_BASE_URL        — API base URL (default: https://app.infisical.com)
  INFISICAL_ORG_ID          — Organisation ID (auto-discovered from identity if unset)

No persistent config file is used for Infisical; all credentials come from
the environment, keeping secrets out of the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from copilot_cli.services.infisical.core.exceptions import ConfigError

_DEFAULT_BASE_URL = "https://app.infisical.com"


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class InfisicalSettings(BaseSettings):
    """Infisical connection settings loaded from environment variables."""

    client_id: str = ""
    client_secret: str = ""
    base_url: str = _DEFAULT_BASE_URL
    org_id: str = ""

    model_config = {"env_prefix": "INFISICAL_", "extra": "ignore"}


# ---------------------------------------------------------------------------
# .env discovery (mirrors coolify pattern)
# ---------------------------------------------------------------------------


def find_env_file(search_root: Path | None = None) -> Path | None:
    """Locate a .env file starting from *search_root* and walking upward."""
    start = search_root or Path.cwd()
    for directory in [start, *start.parents]:
        env_file = directory / ".env"
        if env_file.is_file():
            return env_file
    return None


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------


def load_settings() -> InfisicalSettings:
    """Load settings, merging env file and environment variables."""
    env_file = find_env_file()
    return InfisicalSettings(_env_file=env_file)


def require_settings() -> InfisicalSettings:
    """Load settings and raise ConfigError when required credentials are missing."""
    settings = load_settings()
    missing: list[str] = []
    if not settings.client_id:
        missing.append("client_id (set INFISICAL_CLIENT_ID)")
    if not settings.client_secret:
        missing.append("client_secret (set INFISICAL_CLIENT_SECRET)")
    if missing:
        raise ConfigError("Missing required Infisical configuration: " + "; ".join(missing))
    return settings
