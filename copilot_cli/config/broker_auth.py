"""Short-lived GitHub-authorized Infisical access for interactive Macs.

The broker never receives a GitHub bearer token or an Infisical credential.
This client proves possession of the existing Copilot SSH device key, receives
a scope-bound OIDC assertion, and immediately exchanges it with Infisical.
Only the resulting short-lived access token is cached, in a private file and
never beyond the token's own expiry.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from copilot_cli.services.infisical.core.api_client import _decode_jwt_payload

_NAMESPACE = "copilot-control-tower"
_TIMEOUT = 8.0
_SKEW_SECONDS = 60


class BrokerUnavailable(RuntimeError):
    """The configured interactive store authority could not prove access."""


@dataclass(frozen=True)
class BrokerConfig:
    broker_url: str
    issuer: str
    audience: str
    organization: str
    scope: str
    infisical_url: str
    public_key_path: Path
    auth_root: Path


@dataclass(frozen=True)
class AccessGrant:
    token: str
    identity_id: str
    expires_at: float
    cache_path: Path | None = None


def _origin(value: str, name: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise BrokerUnavailable(f"{name} is not a safe HTTPS origin")
    return value.rstrip("/")


def validate_config(config: BrokerConfig) -> BrokerConfig:
    broker_url = _origin(config.broker_url, "broker URL")
    issuer = _origin(config.issuer, "broker issuer")
    audience = _origin(config.audience, "broker audience")
    infisical_url = _origin(config.infisical_url, "Infisical URL")
    if broker_url != issuer:
        raise BrokerUnavailable("broker URL and issuer must match")
    if audience != infisical_url:
        raise BrokerUnavailable("broker audience and Infisical URL must match")
    if not config.organization.strip() or not config.scope.strip():
        raise BrokerUnavailable("broker organization and scope are required")
    return BrokerConfig(
        broker_url=broker_url,
        issuer=issuer,
        audience=audience,
        organization=config.organization.strip(),
        scope=config.scope.strip().casefold(),
        infisical_url=infisical_url,
        public_key_path=config.public_key_path.expanduser(),
        auth_root=config.auth_root.expanduser(),
    )


def _read_identity(auth_root: Path) -> str:
    try:
        payload = json.loads((auth_root / "active.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrokerUnavailable("GitHub sign-in is required before shared access") from exc
    login = payload.get("login") if isinstance(payload, dict) else None
    if not isinstance(login, str) or not login.strip():
        raise BrokerUnavailable("GitHub sign-in is required before shared access")
    return login.strip()


def _public_key(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BrokerUnavailable("this Mac's Copilot SSH identity is unavailable") from exc
    fields = value.split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise BrokerUnavailable("this Mac's Copilot SSH identity is not supported")
    try:
        base64.b64decode(fields[1], validate=True)
    except ValueError as exc:
        raise BrokerUnavailable("this Mac's Copilot SSH public key is malformed") from exc
    return f"{fields[0]} {fields[1]}"


def machine_id(public_key: str) -> str:
    """Stable non-secret device ID derived from the public key itself."""
    return hashlib.sha256(public_key.encode("utf-8")).hexdigest()[:32]


def canonical_challenge(
    *, issuer: str, login: str, device_id: str, nonce_id: str, nonce: str
) -> bytes:
    values = ("1", issuer, login.casefold(), device_id, nonce_id, nonce)
    if any("\n" in value or "\r" in value for value in values):
        raise BrokerUnavailable("broker challenge was malformed")
    return ("\n".join(values) + "\n").encode("utf-8")


def _sign(public_key_path: Path, message: bytes) -> str:
    executable = shutil.which("ssh-keygen")
    if executable is None:
        raise BrokerUnavailable("ssh-keygen is required for this Mac's identity proof")
    try:
        result = subprocess.run(
            [
                executable,
                "-Y",
                "sign",
                "-f",
                str(public_key_path),
                "-n",
                _NAMESPACE,
                "-",
            ],
            input=message,
            capture_output=True,
            check=False,
            timeout=15,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "SSH_AUTH_SOCK": os.environ.get("SSH_AUTH_SOCK", ""),
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrokerUnavailable("this Mac could not sign the access challenge") from exc
    if result.returncode != 0:
        raise BrokerUnavailable("this Mac could not sign the access challenge")
    try:
        signature = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BrokerUnavailable("this Mac returned an unreadable identity proof") from exc
    if not signature.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise BrokerUnavailable("this Mac returned an invalid identity proof")
    return signature


def _cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    path = base / "copilot" / "infisical" / "broker"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _cache_file(config: BrokerConfig, device_id: str, identity_id: str) -> Path:
    key = "|".join(
        (
            config.broker_url,
            config.infisical_url,
            config.organization.casefold(),
            config.scope,
            device_id,
            identity_id,
        )
    )
    return _cache_dir() / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def _matching_cache(config: BrokerConfig, device_id: str) -> AccessGrant | None:
    expected = {
        "broker_url": config.broker_url,
        "infisical_url": config.infisical_url,
        "organization": config.organization.casefold(),
        "scope": config.scope,
        "machine_id": device_id,
    }
    try:
        candidates = list(_cache_dir().glob("*.json"))
    except OSError:
        return None
    for path in candidates:
        try:
            if path.stat().st_mode & 0o077:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
            continue
        token = payload.get("token")
        identity_id = payload.get("identity_id")
        expires = payload.get("expires_at")
        if (
            isinstance(token, str)
            and token
            and isinstance(identity_id, str)
            and identity_id
            and isinstance(expires, (int, float))
            and float(expires) - time.time() > _SKEW_SECONDS
        ):
            return AccessGrant(token, identity_id, float(expires), path)
    return None


def _save_cache(
    config: BrokerConfig, device_id: str, identity_id: str, token: str, expires_at: float
) -> Path | None:
    path = _cache_file(config, device_id, identity_id)
    payload = {
        "broker_url": config.broker_url,
        "infisical_url": config.infisical_url,
        "organization": config.organization.casefold(),
        "scope": config.scope,
        "machine_id": device_id,
        "identity_id": identity_id,
        "expires_at": expires_at,
        "token": token,
    }
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8"
        ) as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            temp_path = Path(handle.name)
        temp_path.chmod(0o600)
        os.replace(temp_path, path)
        return path
    except OSError:
        return None


def clear_cached_grant(grant: AccessGrant) -> None:
    if grant.cache_path is None:
        return
    try:
        grant.cache_path.unlink()
    except OSError:
        pass


def _json(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise BrokerUnavailable(f"{context} returned an unreadable response") from exc
    if not isinstance(payload, dict):
        raise BrokerUnavailable(f"{context} returned an unfamiliar response")
    return payload


def _parse_time(value: Any, context: str) -> float:
    if not isinstance(value, str):
        raise BrokerUnavailable(f"{context} returned an invalid expiry")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC).timestamp()
    except ValueError as exc:
        raise BrokerUnavailable(f"{context} returned an invalid expiry") from exc


async def acquire_access_grant(
    raw_config: BrokerConfig, *, force_refresh: bool = False
) -> AccessGrant:
    config = validate_config(raw_config)
    login = _read_identity(config.auth_root)
    public_key = _public_key(config.public_key_path)
    device_id = machine_id(public_key)
    if not force_refresh:
        cached = _matching_cache(config, device_id)
        if cached is not None:
            return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            discovery_response = await client.get(
                f"{config.broker_url}/.well-known/openid-configuration"
            )
            if discovery_response.status_code != 200:
                raise BrokerUnavailable("the organization's access service is unavailable")
            discovery = _json(discovery_response, "access service")
            if discovery.get("issuer") != config.issuer:
                raise BrokerUnavailable("the access service reported an unexpected issuer")

            challenge_response = await client.post(
                f"{config.broker_url}/v1/challenges",
                json={"schema_version": "1.0", "login": login, "machine_id": device_id},
            )
            if challenge_response.status_code != 200:
                raise BrokerUnavailable("the organization's access service denied the challenge")
            challenge = _json(challenge_response, "access challenge")
            nonce_id = challenge.get("nonce_id")
            nonce = challenge.get("nonce")
            expires_at = _parse_time(challenge.get("expires_at"), "access challenge")
            if (
                not isinstance(nonce_id, str)
                or not isinstance(nonce, str)
                or expires_at <= time.time()
                or expires_at - time.time() > 60
            ):
                raise BrokerUnavailable("the access service returned an invalid challenge")
            signature = _sign(
                config.public_key_path,
                canonical_challenge(
                    issuer=config.issuer,
                    login=login,
                    device_id=device_id,
                    nonce_id=nonce_id,
                    nonce=nonce,
                ),
            )
            assertion_response = await client.post(
                f"{config.broker_url}/v1/assertions",
                json={
                    "schema_version": "1.0",
                    "login": login,
                    "machine_id": device_id,
                    "nonce_id": nonce_id,
                    "nonce": nonce,
                    "signature": signature,
                },
            )
            if assertion_response.status_code != 200:
                raise BrokerUnavailable("current GitHub access did not authorize this store scope")
            assertion_payload = _json(assertion_response, "access assertion")
            if (
                assertion_payload.get("organization", "").casefold()
                != config.organization.casefold()
                or assertion_payload.get("machine_id") != device_id
            ):
                raise BrokerUnavailable("the access assertion was issued for a different context")
            rows = assertion_payload.get("assertions")
            if not isinstance(rows, list):
                raise BrokerUnavailable("the access service returned no scope assertions")
            matches = [
                row for row in rows if isinstance(row, dict) and row.get("scope") == config.scope
            ]
            if len(matches) != 1:
                raise BrokerUnavailable("current GitHub access does not include this store scope")
            identity_id = matches[0].get("identity_id")
            assertion = matches[0].get("assertion")
            assertion_exp = _parse_time(matches[0].get("expires_at"), "access assertion")
            if (
                not isinstance(identity_id, str)
                or not identity_id
                or not isinstance(assertion, str)
                or not assertion
                or assertion_exp <= time.time()
                or assertion_exp - time.time() > 60
            ):
                raise BrokerUnavailable("the access service returned an invalid scope assertion")

            login_response = await client.post(
                f"{config.infisical_url}/api/v1/auth/oidc-auth/login",
                json={
                    "identityId": identity_id,
                    "jwt": assertion,
                },
            )
            if login_response.status_code not in {200, 201}:
                raise BrokerUnavailable("the shared store rejected the access assertion")
            login_payload = _json(login_response, "shared store")
    except BrokerUnavailable:
        raise
    except httpx.HTTPError as exc:
        raise BrokerUnavailable("the organization's shared access path is unavailable") from exc

    token = login_payload.get("accessToken")
    if not isinstance(token, str) or not token:
        raise BrokerUnavailable("the shared store returned no access token")
    token_payload = _decode_jwt_payload(token)
    try:
        token_exp = float(token_payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BrokerUnavailable("the shared store returned a token without an expiry") from exc
    if token_exp <= time.time() or token_exp - time.time() > 900:
        raise BrokerUnavailable("the shared store returned a token outside the 15-minute policy")
    return AccessGrant(
        token=token,
        identity_id=identity_id,
        expires_at=token_exp,
        cache_path=_save_cache(config, device_id, identity_id, token, token_exp),
    )
