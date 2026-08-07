"""Configuration management for the Infisical CLI.

Env-var layer (loaded from the project .env via pydantic-settings):
  INFISICAL_CLIENT_ID       — Universal Auth client ID
  INFISICAL_CLIENT_SECRET   — Universal Auth client secret
  INFISICAL_BASE_URL        — API base URL (default: https://app.infisical.com)
  INFISICAL_ORG_ID          — Organisation ID (auto-discovered from identity if unset)

No persistent config file is used for Infisical; all credentials come from
the environment, keeping secrets out of the filesystem.

ADR-002 (tier-source fallback for `base_url`): this module is self-contained
by design (`env_prefix="INFISICAL_"`, its own `.env` walk-up) and bypasses
the layered `copilot_cli.config.settings.Settings` chain entirely, so a
tier's committed `cli.overlay.yml` `config:` (e.g. the org's
`infisical_base_url`) never used to reach it -- only a local `.env` copy
did. `load_settings()` now falls back to that composed overlay value when
`base_url` has no explicit env/`.env` source, via `_tier_config_value()`.
That helper reads `load_tier_overlay()` directly (pure YAML, the same
non-recursive path `copilot_cli.config.managed_store._find_store_layer`
uses to fold overlay config for the store gate) -- it never constructs the
full `Settings()` and never touches the managed store, so resolving
`base_url` (needed to REACH the store) carries no circular-dependency risk.
An explicit env/`.env` value always wins; the overlay only fills a gap, and
a lookup failure here never raises -- it just falls through to the
existing hard default.
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
    broker_url: str = ""
    broker_issuer: str = ""
    broker_audience: str = ""
    broker_org: str = ""
    store_scope: str = "shared"
    ssh_public_key: str = ""
    auth_root: str = ""

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


def _keychain_lookup(name: str) -> str:
    """Best-effort read of *name* from the per-user OS keychain, via the shared
    credential ladder's keychain rung. Returns ``""`` on any miss so callers can
    treat it as 'not configured' without a try/except."""
    try:
        from copilot_cli.config.secrets_ladder import _rung_keychain, _SecretRungUnavailable

        try:
            return _rung_keychain(name, [])
        except _SecretRungUnavailable:
            return ""
    except Exception:
        return ""


def _tier_config_value(field_name: str) -> str | None:
    """Read *field_name* (lowercase, `Settings`-field-shaped, e.g.
    ``"infisical_base_url"``) from the nearest CLI tier's committed
    `cli.overlay.yml` `config:` block -- ADR-002's non-recursive tier-source
    fallback.

    Mirrors `copilot_cli.config.managed_store._find_store_layer`'s own fold
    exactly: per layer (nearest-precedence first), `adopt[].config` then
    `provides[].config`, last-write-wins within a tier (provides wins on a
    same-tier collision, matching `TierConfigSource._collect_config`); the
    first tier with a non-empty value wins across tiers (nearest-wins).

    Deliberately reimplements that small fold locally rather than importing
    `copilot_cli.config.settings.TierConfigSource` -- this keeps the import
    surface to exactly `copilot_cli.config.layers` (pure YAML parsing: no
    pydantic-settings, no `Settings()` construction, no store/network call),
    so a caller resolving `base_url` -- needed to REACH the store -- can
    never recurse into it.

    Returns ``None`` when no `copilot.layers.yml` resolves, no tier declares
    the field, or anything in between raises -- never propagates an
    exception, so callers can treat a lookup failure exactly like "not
    configured" and fall through to their prior behavior.
    """
    try:
        from copilot_cli.config.layers import load_tier_overlay, resolve_cli_layer_chain

        chain = resolve_cli_layer_chain()
        if not chain:
            return None
        for layer in chain:
            overlay = load_tier_overlay(layer.overlay_path)
            merged: dict[str, str] = {}
            for adopt in overlay.adopt:
                merged.update(adopt.config)
            for provide in overlay.provides:
                merged.update(provide.config)
            if merged.get(field_name):
                return merged[field_name]
        return None
    except Exception:
        return None


def load_settings() -> InfisicalSettings:
    """Load settings, merging env file, environment variables, and (ADR-002)
    the composed tier-overlay `config:` fallback for `base_url`.

    Keychain fallback for the machine-identity bootstrap credentials
    (invariant #6): `INFISICAL_CLIENT_ID` / `_SECRET` are the one secret pair
    that cannot live in the managed store they unlock (bootstrap paradox), so
    when they are absent from the environment / `.env` they are resolved from
    the per-user OS keychain -- the same rung the credential ladder uses. An
    explicit env/`.env` value always wins; the keychain only fills a gap.

    `base_url` resolution order (ADR-002, safe-fallback): an explicit
    env/`.env` value (`model_fields_set` -- distinguishes "provided by some
    source" from "left at the class default") wins first; else the nearest
    tier's committed `cli.overlay.yml` `infisical_base_url` (via
    `_tier_config_value`, pure YAML, no store/network call); else the
    existing hard default (`_DEFAULT_BASE_URL`). With today's `.env` still
    populated, this is byte-identical to the pre-ADR-002 behavior -- the
    fallback only ever activates once `.env` stops setting `INFISICAL_BASE_URL`.
    """
    env_file = find_env_file()
    settings = InfisicalSettings(_env_file=env_file)
    tier_fields = {
        "base_url": "infisical_base_url",
        "broker_url": "infisical_broker_url",
        "broker_issuer": "infisical_broker_issuer",
        "broker_audience": "infisical_broker_audience",
        "broker_org": "infisical_broker_org",
        "store_scope": "infisical_store_scope",
        "ssh_public_key": "infisical_ssh_public_key",
        "auth_root": "infisical_auth_root",
    }
    updates: dict[str, str] = {}
    for field, tier_key in tier_fields.items():
        if field not in settings.model_fields_set:
            tier_value = _tier_config_value(tier_key)
            if tier_value:
                updates[field] = tier_value
    if updates:
        settings = settings.model_copy(update=updates)
    if settings.broker_url:
        # A configured interactive broker is an explicit fail-closed path.
        # Never read or silently fall back to a long-lived Universal Auth pair.
        return settings
    if not settings.client_id or not settings.client_secret:
        client_id = settings.client_id or _keychain_lookup("INFISICAL_CLIENT_ID")
        client_secret = settings.client_secret or _keychain_lookup("INFISICAL_CLIENT_SECRET")
        if client_id != settings.client_id or client_secret != settings.client_secret:
            settings = settings.model_copy(
                update={"client_id": client_id, "client_secret": client_secret}
            )
    return settings


def require_settings() -> InfisicalSettings:
    """Load settings and raise ConfigError when required credentials are missing."""
    settings = load_settings()
    if settings.broker_url:
        missing_broker: list[str] = []
        for field in ("broker_issuer", "broker_audience", "broker_org", "store_scope"):
            if not getattr(settings, field):
                missing_broker.append(field)
        if missing_broker:
            raise ConfigError("Missing required broker configuration: " + "; ".join(missing_broker))
        return settings

    missing: list[str] = []
    if not settings.client_id:
        missing.append("client_id (set INFISICAL_CLIENT_ID)")
    if not settings.client_secret:
        missing.append("client_secret (set INFISICAL_CLIENT_SECRET)")
    if missing:
        raise ConfigError("Missing required Infisical configuration: " + "; ".join(missing))
    return settings


def broker_config(settings: InfisicalSettings):
    """Build the validated-path input for the interactive broker client.

    Kept here so the service CLI, top-level health command, and tests resolve
    the same non-secret defaults. Validation itself remains in broker_auth.
    """
    from copilot_cli.config.broker_auth import BrokerConfig

    return BrokerConfig(
        broker_url=settings.broker_url,
        issuer=settings.broker_issuer,
        audience=settings.broker_audience,
        organization=settings.broker_org,
        scope=settings.store_scope,
        infisical_url=settings.base_url,
        public_key_path=(
            Path(settings.ssh_public_key)
            if settings.ssh_public_key
            else Path.home() / ".ssh" / "id_ed25519_copilot.pub"
        ),
        auth_root=(
            Path(settings.auth_root) if settings.auth_root else Path.home() / ".copilot" / "auth"
        ),
    )
