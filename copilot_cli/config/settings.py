"""Pydantic Settings - loads all credentials from project root .env file."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path:
    """Walk up from CWD to find the nearest .env file.

    Resolution order:
    1. COPILOT_ENV_FILE environment variable (explicit override)
    2. Walk up from CWD, stopping at project root markers
    3. Standard machine-agnostic user config locations ($HOME-relative, so they
       are identical on every machine and carry no hardcoded absolute paths).
       This is what lets a Discord away-mode hook running in any project find
       the shared copilot config without a baked path.
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_find_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- N8N ---
    n8n_base_url: str = ""
    n8n_api_key: str = ""

    # --- Git ---
    git_user_name: str = "copilot"
    git_user_email: str = "dev@example.com"

    # --- Docker ---
    docker_socket: str = "/var/run/docker.sock"

    # --- Shell ---
    shell_scripts_path: str = ""
    shell_timeout: int = 3600

    # --- NocoDB ---
    nocodb_url: str = ""
    nocodb_api_key: str = ""
    nocodb_base_id: str = ""

    # --- PostgreSQL ---
    database_url: str = ""
    nocodb_database_url: str = ""
    n8n_database_url: str = ""
    formbricks_database_url: str = ""

    # --- Brevo ---
    brevo_api_key: str = ""

    # --- Discord ---
    discord_bot_token: str = ""
    discord_webhook_url: str = ""
    discord_guild_id: str = ""
    discord_channel_id: str = ""
    discord_thread_id: str = ""
    discord_allowed_user_ids: str = ""
    discord_webhook_username: str = ""
    discord_webhook_avatar_url: str = ""
    # COPILOT_DISCORD_WAIT_TIMEOUT — seconds to park the session in away-mode;
    # 0 = wait forever. Default 0 so "I'm stepping away" remains valid overnight
    # or across a weekend while the terminal session stays alive.
    discord_wait_timeout: int = 0
    # COPILOT_DISCORD_AWAIT_DEFAULT — whether `discord handoff` arms await-mode
    # automatically.  Default False for backward compatibility.
    discord_await_default: bool = False

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

    def get_brevo_api_key(self) -> str:
        """Decode base64-wrapped Brevo API key if needed."""
        if not self.brevo_api_key:
            return ""
        try:
            decoded = base64.b64decode(self.brevo_api_key).decode()
            parsed = json.loads(decoded)
            return parsed.get("api_key", self.brevo_api_key)
        except Exception:
            return self.brevo_api_key

    def get_allowed_volumes(self) -> list[str]:
        return [v.strip() for v in self.allowed_volumes.split(",") if v.strip()]

    def get_discord_allowed_user_ids(self) -> list[str]:
        return [v.strip() for v in self.discord_allowed_user_ids.split(",") if v.strip()]

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
