"""Least-privilege, resumable Infisical identity provisioning."""

from __future__ import annotations

import hashlib
import socket
import subprocess
import sys
from typing import Any, Awaitable, Callable

from copilot_cli.config.secrets_ladder import KEYCHAIN_SERVICE
from copilot_cli.services.infisical.core.exceptions import APIError

CredentialReader = Callable[[str], str | None]
CredentialWriter = Callable[[str, str], bool]


def _read_keychain(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _write_keychain(name: str, value: str) -> bool:
    if sys.platform != "darwin" or not value:
        return False
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            name,
            "-w",
            value,
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.returncode == 0


def _role_slug(environment: str, secret_path: str) -> str:
    digest = hashlib.sha256(f"{environment}|{secret_path}".encode()).hexdigest()[:12]
    return f"copilot-read-{digest}"


def _identity_record(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("identity")
    return nested if isinstance(nested, dict) else item


def _identity_id(item: dict[str, Any]) -> str:
    nested = _identity_record(item)
    return str(nested.get("id") or item.get("identityId") or "")


def _identity_name(item: dict[str, Any]) -> str:
    return str(_identity_record(item).get("name") or "")


def _membership_identity_id(item: dict[str, Any]) -> str:
    identity = item.get("identity")
    return str(item.get("identityId") or (identity.get("id") if isinstance(identity, dict) else "") or "")


def _membership_roles(item: dict[str, Any]) -> set[str]:
    roles = item.get("roles")
    if not isinstance(roles, list):
        return set()
    return {
        str(role.get("customRoleSlug") or role.get("role") or "")
        for role in roles
        if isinstance(role, dict)
    }


def _role_permissions(environment: str, secret_path: str) -> list[dict[str, Any]]:
    return [
        {
            "subject": "secrets",
            "action": "read",
            "conditions": {"environment": environment, "secretPath": secret_path},
        }
    ]


async def provision_machine_identity(
    client: Any,
    *,
    project_id: str,
    environment: str,
    secret_path: str,
    name: str | None = None,
    apply: bool = False,
    read_credential: CredentialReader = _read_keychain,
    write_credential: CredentialWriter = _write_keychain,
) -> dict[str, Any]:
    """Plan/apply a scoped identity without ever returning credentials."""
    identity_name = name or f"copilot-device-{socket.gethostname().lower()}"
    slug = _role_slug(environment, secret_path)
    org_id = await client.get_org_id("")
    if not org_id:
        return {"schema_version": "1.0", "result": "blocked", "detail": "Infisical organization identity could not be confirmed."}

    identities = await client.list_identities(org_id)
    matches = [item for item in identities if _identity_name(item) == identity_name]
    if len(matches) > 1:
        return {"schema_version": "1.0", "result": "blocked", "detail": "More than one machine identity uses this device name; setup did not guess."}
    identity = matches[0] if matches else None
    existing_client_id = read_credential("INFISICAL_CLIENT_ID")
    existing_client_secret = read_credential("INFISICAL_CLIENT_SECRET")
    if bool(existing_client_id) != bool(existing_client_secret):
        return {"schema_version": "1.0", "result": "blocked", "detail": "The keychain contains an incomplete store credential pair; setup did not replace it."}
    if not identity and existing_client_id:
        return {"schema_version": "1.0", "result": "blocked", "detail": "This device already has store credentials for another identity; setup did not replace them."}

    roles = await client.list_project_roles(project_id)
    role = next((item for item in roles if item.get("slug") == slug), None)
    if role is not None and role.get("permissions") not in (None, _role_permissions(environment, secret_path)):
        return {"schema_version": "1.0", "result": "blocked", "detail": "The existing scoped role differs from the required read-only path policy."}

    identity_id = _identity_id(identity) if identity else ""
    memberships = await client.list_identity_memberships(project_id)
    membership_ready = bool(
        identity_id
        and any(
            _membership_identity_id(item) == identity_id and slug in _membership_roles(item)
            for item in memberships
        )
    )
    credentials_ready = bool(existing_client_id and existing_client_secret)
    if not apply:
        ready = bool(identity and role and membership_ready and credentials_ready)
        return {
            "schema_version": "1.0",
            "result": "ready" if ready else "changes-required",
            "identity": "existing" if identity else "missing",
            "role": "ready" if role else "missing",
            "membership": "ready" if membership_ready else "missing",
            "credentials": "keychain" if credentials_ready else "missing",
            "scope": {"environment": environment, "secret_path": secret_path, "access": "read"},
        }

    if identity is None:
        identity = await client.create_identity(identity_name, org_id, "no-access")
        identity_id = _identity_id(identity)
        if not identity_id:
            return {"schema_version": "1.0", "result": "blocked", "detail": "Infisical did not confirm machine identity creation."}

    if role is None:
        role = await client.create_project_role(
            project_id,
            slug=slug,
            name="Copilot device read access",
            permissions=_role_permissions(environment, secret_path),
            description=f"Read-only access for Copilot devices at {environment}:{secret_path}",
        )

    if not membership_ready:
        await client.add_identity_membership(project_id, identity_id, slug)

    if credentials_ready:
        return {
            "schema_version": "1.0",
            "result": "applied",
            "identity": "reused",
            "role": "ready",
            "membership": "ready",
            "credentials": "keychain",
            "scope": {"environment": environment, "secret_path": secret_path, "access": "read"},
        }

    try:
        universal = await client.get_universal_auth(identity_id)
    except APIError as exc:
        if exc.status_code != 404:
            raise
        universal = await client.attach_universal_auth(identity_id)
    client_id = str(universal.get("clientId") or "")
    if not client_id:
        return {"schema_version": "1.0", "result": "blocked", "detail": "Infisical did not return the machine identity client ID."}

    secret_response = await client.create_universal_auth_client_secret(
        identity_id, f"Copilot Control Tower credential for {socket.gethostname()}"
    )
    client_secret = str(secret_response.get("clientSecret") or "")
    secret_data = secret_response.get("clientSecretData")
    secret_id = str(secret_data.get("id") or "") if isinstance(secret_data, dict) else ""
    if not client_secret:
        return {"schema_version": "1.0", "result": "blocked", "detail": "Infisical did not return the one-time client secret."}

    stored = write_credential("INFISICAL_CLIENT_ID", client_id) and write_credential(
        "INFISICAL_CLIENT_SECRET", client_secret
    )
    if not stored:
        if secret_id:
            try:
                await client.revoke_universal_auth_client_secret(identity_id, secret_id)
            except Exception:
                pass
        return {"schema_version": "1.0", "result": "blocked", "detail": "The one-time store credential could not be secured in the OS keychain and was not returned."}

    return {
        "schema_version": "1.0",
        "result": "applied",
        "identity": "ready",
        "role": "ready",
        "membership": "ready",
        "credentials": "keychain",
        "scope": {"environment": environment, "secret_path": secret_path, "access": "read"},
    }
