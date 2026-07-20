"""Managed secret store resolution — the concrete backend for the credential
ladder's rung 1 (`secrets_ladder._rung_managed_store`).

Implements `credentials-and-boundary.md` §1.6.2's "tier-scoped managed secret
store" against the ecosystem's Infisical (reusing the base `infisical` service's
own `InfisicalClient`, so there is exactly one Infisical HTTP surface in the
foundation). Given the resolved layer chain and a secret *name*, this:

  1. Finds the **nearest** layer that declares store config (an
     ``INFISICAL_WORKSPACE_ID`` in its non-secret `.env`). Nearest-wins matches
     the ladder's own tier precedence: a personal-tier reference checks
     personal's store, never upward; org checks org's store. If no layer
     declares a workspace, the store is **absent** (not misconfigured) and this
     raises `StoreUnavailable` *before any network call* — the dormant default.
  2. Authenticates with that tier's machine identity. The bootstrap credentials
     (``INFISICAL_CLIENT_ID`` / ``_SECRET``) are sourced OUTSIDE the store —
     keychain first, then the layer `.env` — because a store cannot hold the
     credentials used to reach it (bootstrap paradox). Any store-config name is
     refused up front (`_NEVER_FROM_STORE`) so a `requires_secret` declaration
     of a bootstrap cred can never recurse into the store.
  3. Bulk-fetches the tier's secrets once per process (amortising a single
     `list_secrets` across every `requires_secret` field resolved in one
     `Settings()` construction) and returns the named value.

Fail-through, never fail-closed *here*: every miss — absent config, unreachable
endpoint, auth failure, name-not-in-store — raises `StoreUnavailable`, which the
ladder catches to try the next rung (keychain, …). The ladder's terminal
`SecretResolutionError` is the only fail-closed exit, and it lives one level up.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from copilot_cli.config.layers import CliLayer


class StoreUnavailable(Exception):
    """The managed store cannot resolve *this* name right now (config absent,
    endpoint unreachable, auth failed, or name not present). Internal to the
    rung-1 backend; the ladder translates it into a fall-through to rung 2."""


# Names that are store *configuration* / bootstrap credentials — resolving any
# of these THROUGH the store would be circular. They are refused up front so the
# rung falls through to keychain (where a bootstrap cred is meant to live).
_NEVER_FROM_STORE = frozenset(
    {
        "INFISICAL_CLIENT_ID",
        "INFISICAL_CLIENT_SECRET",
        "INFISICAL_BASE_URL",
        "INFISICAL_ORG_ID",
        "INFISICAL_WORKSPACE_ID",
        "INFISICAL_ENVIRONMENT",
        "INFISICAL_SECRET_PATH",
    }
)

# HTTP timeout for the store — deliberately short. Rung 1 is tried first, so a
# slow/unreachable store must fall through to keychain quickly rather than
# stalling every CLI invocation.
_STORE_TIMEOUT = 6.0

# Per-process cache: (base_url, workspace, env, path) -> {SECRET_NAME: value}.
# One `list_secrets` amortises across all `requires_secret` fields resolved in a
# single command; cleared naturally when the process exits.
_SECRET_CACHE: dict[tuple[str, str, str, str], dict[str, str]] = {}

# Cross-process cache of the short-lived Infisical access token (NOT secret
# values -- those are never written to disk). Avoids re-authenticating on every
# CLI invocation, which is both a latency cost and a real reliability risk:
# bursty callers (e.g. the Discord bridge firing per turn) can otherwise trip
# Infisical's auth rate limit and fail-closed. The token file is mode 0600 under
# the per-user cache dir; a stale token is detected and re-minted transparently.
_TOKEN_SKEW_SECONDS = 60


def _token_cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    d = base / "copilot" / "infisical"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _token_cache_file(base_url: str, client_id: str) -> Path:
    # Filename is a hash of endpoint+identity so it neither collides across
    # tiers/identities nor leaks the identity in the path.
    digest = hashlib.sha256(f"{base_url}|{client_id}".encode()).hexdigest()[:32]
    return _token_cache_dir() / f"{digest}.json"


def _token_exp(token: str) -> float:
    from copilot_cli.services.infisical.core.api_client import _decode_jwt_payload

    exp = _decode_jwt_payload(token).get("exp")
    try:
        return float(exp)
    except (TypeError, ValueError):
        return 0.0


def _load_cached_token(base_url: str, client_id: str) -> str | None:
    try:
        data = json.loads(_token_cache_file(base_url, client_id).read_text())
    except (OSError, ValueError):
        return None
    token = data.get("token")
    exp = data.get("exp", 0)
    if token and isinstance(exp, (int, float)) and exp - time.time() > _TOKEN_SKEW_SECONDS:
        return str(token)
    return None


def _save_cached_token(base_url: str, client_id: str, token: str) -> None:
    path = _token_cache_file(base_url, client_id)
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"token": token, "exp": _token_exp(token)}))
        tmp.chmod(0o600)
        tmp.replace(path)
    except OSError:
        pass  # cache is best-effort; a write failure just means re-auth next time


def _clear_cached_token(base_url: str, client_id: str) -> None:
    try:
        _token_cache_file(base_url, client_id).unlink()
    except OSError:
        pass


def _parse_env_keys(env_path, keys: set[str]) -> dict[str, str]:
    """Read *keys* from a `.env`-style file without pydantic. Values only for
    the requested keys; surrounding quotes stripped; missing file -> ``{}``."""
    try:
        text = env_path.read_text()
    except (OSError, FileNotFoundError):
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name not in keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name] = value
    return out


def _read_bootstrap_cred(name: str, env_values: dict[str, str]) -> str:
    """Source a bootstrap credential OUTSIDE the store: OS keychain first
    (invariant #6's per-user store), then the layer `.env` fallback. Empty
    string if neither has it."""
    # Local import: keychain lookup lives in the ladder; avoids an import cycle
    # at module load (secrets_ladder imports nothing from here at import time).
    from copilot_cli.config.secrets_ladder import _SecretRungUnavailable, _rung_keychain

    try:
        value = _rung_keychain(name, [])
        if value:
            return value
    except _SecretRungUnavailable:
        pass
    return env_values.get(name, "")


def _find_store_layer(chain: list[CliLayer]):
    """Return ``(layer, config)`` for the nearest layer declaring a store
    (an ``INFISICAL_WORKSPACE_ID``), or ``None`` if no layer does — the dormant
    default. *chain* is already highest-precedence-first, so the first match is
    the nearest tier."""
    wanted = {
        "INFISICAL_BASE_URL",
        "INFISICAL_WORKSPACE_ID",
        "INFISICAL_ENVIRONMENT",
        "INFISICAL_SECRET_PATH",
        "INFISICAL_CLIENT_ID",
        "INFISICAL_CLIENT_SECRET",
    }
    for layer in chain:
        cfg = _parse_env_keys(layer.env_path, wanted)
        if cfg.get("INFISICAL_WORKSPACE_ID"):
            return layer, cfg
    return None


async def _fetch_all(base_url: str, client_id: str, client_secret: str,
                     workspace: str, environment: str, secret_path: str) -> dict[str, str]:
    """Authenticate and bulk-read every secret at the tier's path into a
    ``{name: value}`` dict. Raises `StoreUnavailable` on any failure."""
    from copilot_cli.services.infisical.core.api_client import InfisicalClient
    from copilot_cli.services.infisical.core.exceptions import (
        APIError,
        AuthenticationError,
        ConnectionError as InfisicalConnectionError,
    )

    try:
        client = InfisicalClient(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            timeout=_STORE_TIMEOUT,
        )
    except (AuthenticationError, InfisicalConnectionError) as exc:
        raise StoreUnavailable(f"store client init failed: {exc}") from exc

    cached = _load_cached_token(base_url, client_id)
    if cached:
        client._token = cached  # skip the auth round-trip; verified below by use

    try:
        try:
            items = await client.list_secrets(workspace, environment, secret_path)
        except AuthenticationError:
            # No/stale cached token -> authenticate fresh exactly once and
            # persist the new token for the next process, then retry the read.
            client._token = None
            _clear_cached_token(base_url, client_id)
            await client.authenticate()
            _save_cached_token(base_url, client_id, client._token or "")
            items = await client.list_secrets(workspace, environment, secret_path)
        else:
            # list_secrets auto-authenticates when no token was cached; persist
            # whatever token the client now holds so the next process reuses it.
            if not cached and client._token:
                _save_cached_token(base_url, client_id, client._token)
    except (APIError, AuthenticationError, InfisicalConnectionError) as exc:
        raise StoreUnavailable(f"store read failed: {exc}") from exc
    finally:
        await client.close()

    resolved: dict[str, str] = {}
    for item in items or []:
        key = item.get("secretKey")
        val = item.get("secretValue")
        if key is not None and val is not None:
            resolved[str(key)] = str(val)
    return resolved


def resolve_from_store(name: str, chain: list[CliLayer]) -> str:
    """Resolve *name* from the nearest tier's managed store, or raise
    `StoreUnavailable` (never an empty string, never a guess).

    Contract for `secrets_ladder._rung_managed_store`: dormant (no network) when
    no layer declares a store; recursion-safe (store-config names refused); and
    a clean fall-through on every miss."""
    if name in _NEVER_FROM_STORE:
        raise StoreUnavailable(f"{name} is store config/bootstrap — never resolved via the store")

    found = _find_store_layer(chain)
    if found is None:
        raise StoreUnavailable("no layer declares a managed store (INFISICAL_WORKSPACE_ID)")
    _layer, cfg = found

    base_url = cfg.get("INFISICAL_BASE_URL") or "https://app.infisical.com"
    workspace = cfg["INFISICAL_WORKSPACE_ID"]
    environment = cfg.get("INFISICAL_ENVIRONMENT") or "prod"
    secret_path = cfg.get("INFISICAL_SECRET_PATH") or "/"

    client_id = _read_bootstrap_cred("INFISICAL_CLIENT_ID", cfg)
    client_secret = _read_bootstrap_cred("INFISICAL_CLIENT_SECRET", cfg)
    if not client_id or not client_secret:
        raise StoreUnavailable("no machine-identity bootstrap credentials for the store")

    cache_key = (base_url, workspace, environment, secret_path)
    secrets = _SECRET_CACHE.get(cache_key)
    if secrets is None:
        try:
            secrets = asyncio.run(
                _fetch_all(base_url, client_id, client_secret, workspace, environment, secret_path)
            )
        except RuntimeError as exc:
            # e.g. called with an event loop already running — fall through
            # rather than risk a hard failure at Settings construction.
            raise StoreUnavailable(f"store fetch could not run: {exc}") from exc
        _SECRET_CACHE[cache_key] = secrets

    if name in secrets and secrets[name]:
        return secrets[name]
    raise StoreUnavailable(f"{name} not present in the tier's managed store")
