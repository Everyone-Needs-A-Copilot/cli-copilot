"""Async HTTP client for the Infisical API.

Confirmed endpoints (probed against a self-hosted Infisical instance;
compatible with https://app.infisical.com, Infisical Cloud):

  Auth
    POST /api/v1/auth/universal-auth/login  {clientId, clientSecret} → {accessToken}

  Projects (workspaces)
    GET    /api/v1/workspace                              → {workspaces: [...]}
    GET    /api/v1/workspace/{projectId}                  → {workspace: {...}}
    POST   /api/v2/workspace  {projectName, organizationId} → {project: {...}}
    DELETE /api/v1/workspace/{projectId}                  → {workspace: {...}}

  Folders
    GET  /api/v1/folders?workspaceId=&environment=&path= → {folders: [...]}
    POST /api/v1/folders {workspaceId, environment, path, name} → {folder: {...}}

  Secrets
    GET    /api/v3/secrets/raw?workspaceId=&environment=&secretPath= → {secrets:[...]}
    GET    /api/v3/secrets/raw/{name}?workspaceId=&environment=&secretPath= → {secret:{}}
    POST   /api/v3/secrets/raw/{name} {workspaceId, environment, secretPath, secretValue, type}
    PATCH  /api/v3/secrets/raw/{name} {workspaceId, environment, secretPath, secretValue}
    DELETE /api/v3/secrets/raw/{name} {workspaceId, environment, secretPath}  (body as JSON)

  Identities
    GET    /api/v1/identities?orgId=                     → {identities: [...]}
    GET    /api/v1/identities/{identityId}               → {identity: {...}}  (org membership)
    POST   /api/v1/identities  {name, organizationId, role} → {identity: {...}}
    DELETE /api/v1/identities/{identityId}               → {identity: {...}}

  Admin
    GET   /api/v1/admin/config  → {config: {...}}
    PATCH /api/v1/admin/config  {allowSignUp: bool}  (requires super-admin)
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from copilot_cli.services.infisical.core.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
)


def _decode_jwt_payload(token: str) -> dict:
    """Decode a JWT payload without verifying the signature."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part).decode("utf-8"))
    except Exception:
        return {}


class InfisicalClient:
    """Async HTTP client for the Infisical API."""

    def __init__(
        self,
        base_url: str,
        client_id: str = "",
        client_secret: str = "",
        timeout: float = 30.0,
        *,
        access_token: str | None = None,
        read_only: bool = False,
    ):
        if not base_url:
            raise ConnectionError("Infisical base URL is required")
        if not access_token and (not client_id or not client_secret):
            raise AuthenticationError(
                "an Infisical access token or Universal Auth credentials are required"
            )

        self.base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = access_token
        self._direct_access_token = bool(access_token)
        self._read_only = read_only
        self._identity_id: str | None = None
        self._org_id: str | None = None

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> InfisicalClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ─── Auth ──────────────────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Login via Universal Auth and cache the access token."""
        if self._direct_access_token:
            if self._token:
                return self._token
            raise AuthenticationError("The short-lived Infisical access token expired")
        try:
            response = await self._http.post(
                "/api/v1/auth/universal-auth/login",
                json={"clientId": self._client_id, "clientSecret": self._client_secret},
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Request timed out: {e}") from e

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "Authentication failed — check INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET"
            )

        if not response.is_success:
            raise APIError(f"Auth failed: HTTP {response.status_code}", response.status_code)

        data = response.json()
        self._token = data["accessToken"]

        # Decode JWT to get identityId (no network call needed)
        payload = _decode_jwt_payload(self._token)
        self._identity_id = payload.get("identityId")

        return self._token

    async def _ensure_authenticated(self) -> None:
        if not self._token:
            await self.authenticate()

    async def get_org_id(self, hint: str = "") -> str:
        """Return the org ID, discovering it from the identity endpoint if needed."""
        if hint:
            return hint
        if self._org_id:
            return self._org_id
        await self._ensure_authenticated()
        if self._identity_id:
            data = await self._get_raw(f"/api/v1/identities/{self._identity_id}")
            self._org_id = data.get("identity", {}).get("orgId", "")
        return self._org_id or ""

    # ─── Low-level request helpers ─────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if self._read_only and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            raise AuthenticationError("This GitHub-authorized shared-store session is read-only")
        await self._ensure_authenticated()
        clean_params = {k: str(v) for k, v in (params or {}).items() if v is not None}
        try:
            response = await self._http.request(
                method,
                path,
                json=json_data,
                params=clean_params or None,
                headers=self._auth_headers(),
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Request timed out: {e}") from e

        if response.status_code == 401:
            raise AuthenticationError("Invalid access token — re-authenticate")
        if response.status_code == 403:
            raise AuthenticationError(
                "Access denied — check identity permissions"
                + (": requires super-admin" if "super admin" in response.text.lower() else "")
            )

        text = response.text
        data: Any = {}
        if text:
            try:
                data = response.json()
            except Exception:
                data = text

        if not response.is_success:
            error_msg = ""
            if isinstance(data, dict):
                msg = data.get("message", "")
                if isinstance(msg, list):
                    # Zod validation errors come as a list of objects
                    error_msg = "; ".join(
                        f"{e.get('path', ['?'])[-1] if e.get('path') else '?'}: {e.get('message', '')}"
                        for e in msg
                    )
                else:
                    error_msg = msg or f"HTTP {response.status_code}"
            else:
                error_msg = f"HTTP {response.status_code}: {response.reason_phrase}"
            raise APIError(error_msg, response.status_code)

        return data

    async def _get_raw(self, path: str, params: dict | None = None) -> Any:
        """GET without authentication (used during auth flow)."""
        await self._ensure_authenticated()
        return await self._request("GET", path, params=params)

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_data=data)

    async def patch(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json_data=data)

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request("DELETE", path, json_data=json_data, params=params)

    # ─── Projects (workspaces) ─────────────────────────────────────────────

    async def list_projects(self) -> list[dict]:
        """GET /api/v1/workspace → workspaces list."""
        data = await self.get("/api/v1/workspace")
        return data.get("workspaces", []) if isinstance(data, dict) else []

    async def get_project(self, project_id: str) -> dict:
        """GET /api/v1/workspace/{projectId} → workspace dict."""
        data = await self.get(f"/api/v1/workspace/{project_id}")
        return data.get("workspace", data) if isinstance(data, dict) else data

    async def create_project(self, name: str, org_id: str) -> dict:
        """POST /api/v2/workspace {projectName, organizationId} → project dict."""
        data = await self.post("/api/v2/workspace", {"projectName": name, "organizationId": org_id})
        return data.get("project", data) if isinstance(data, dict) else data

    async def delete_project(self, project_id: str) -> dict:
        """DELETE /api/v1/workspace/{projectId} → workspace dict."""
        data = await self.delete(f"/api/v1/workspace/{project_id}")
        return data.get("workspace", data) if isinstance(data, dict) else data

    # ─── Folders ──────────────────────────────────────────────────────────

    async def list_folders(self, project_id: str, environment: str, path: str = "/") -> list[dict]:
        """GET /api/v1/folders?workspaceId=&environment=&path="""
        data = await self.get(
            "/api/v1/folders",
            params={"workspaceId": project_id, "environment": environment, "path": path},
        )
        return data.get("folders", []) if isinstance(data, dict) else []

    async def create_folder(
        self, project_id: str, environment: str, name: str, path: str = "/"
    ) -> dict:
        """POST /api/v1/folders {workspaceId, environment, path, name}"""
        data = await self.post(
            "/api/v1/folders",
            {"workspaceId": project_id, "environment": environment, "path": path, "name": name},
        )
        return data.get("folder", data) if isinstance(data, dict) else data

    # ─── Secrets ──────────────────────────────────────────────────────────

    async def list_secrets(
        self, project_id: str, environment: str, secret_path: str = "/"
    ) -> list[dict]:
        """GET /api/v3/secrets/raw?workspaceId=&environment=&secretPath="""
        data = await self.get(
            "/api/v3/secrets/raw",
            params={
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
            },
        )
        return data.get("secrets", []) if isinstance(data, dict) else []

    async def get_secret(
        self, project_id: str, environment: str, key: str, secret_path: str = "/"
    ) -> dict:
        """GET /api/v3/secrets/raw/{name}?workspaceId=&environment=&secretPath="""
        data = await self.get(
            f"/api/v3/secrets/raw/{key}",
            params={
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
            },
        )
        return data.get("secret", data) if isinstance(data, dict) else data

    async def create_secret(
        self,
        project_id: str,
        environment: str,
        key: str,
        value: str,
        secret_path: str = "/",
        secret_type: str = "shared",
    ) -> dict:
        """POST /api/v3/secrets/raw/{name}"""
        data = await self.post(
            f"/api/v3/secrets/raw/{key}",
            {
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
                "secretValue": value,
                "type": secret_type,
            },
        )
        return data.get("secret", data) if isinstance(data, dict) else data

    async def update_secret(
        self,
        project_id: str,
        environment: str,
        key: str,
        value: str,
        secret_path: str = "/",
    ) -> dict:
        """PATCH /api/v3/secrets/raw/{name}"""
        data = await self.patch(
            f"/api/v3/secrets/raw/{key}",
            {
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
                "secretValue": value,
            },
        )
        return data.get("secret", data) if isinstance(data, dict) else data

    async def delete_secret(
        self, project_id: str, environment: str, key: str, secret_path: str = "/"
    ) -> dict:
        """DELETE /api/v3/secrets/raw/{name}  (body as JSON — Infisical quirk)"""
        data = await self.delete(
            f"/api/v3/secrets/raw/{key}",
            json_data={
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
            },
        )
        return data.get("secret", data) if isinstance(data, dict) else data

    # ─── Identities ───────────────────────────────────────────────────────

    async def list_identities(self, org_id: str) -> list[dict]:
        """GET /api/v1/identities?orgId="""
        data = await self.get("/api/v1/identities", params={"orgId": org_id})
        return data.get("identities", []) if isinstance(data, dict) else []

    async def create_identity(self, name: str, org_id: str, role: str = "member") -> dict:
        """POST /api/v1/identities {name, organizationId, role}"""
        data = await self.post(
            "/api/v1/identities",
            {"name": name, "organizationId": org_id, "role": role},
        )
        return data.get("identity", data) if isinstance(data, dict) else data

    async def delete_identity(self, identity_id: str) -> dict:
        """DELETE /api/v1/identities/{identityId}"""
        data = await self.delete(f"/api/v1/identities/{identity_id}")
        return data.get("identity", data) if isinstance(data, dict) else data

    # ─── Admin ────────────────────────────────────────────────────────────

    async def get_admin_config(self) -> dict:
        """GET /api/v1/admin/config → config dict."""
        data = await self.get("/api/v1/admin/config")
        return data.get("config", data) if isinstance(data, dict) else data

    async def update_admin_config(self, **kwargs: Any) -> dict:
        """PATCH /api/v1/admin/config — requires super-admin privileges."""
        data = await self.patch("/api/v1/admin/config", dict(kwargs))
        return data.get("config", data) if isinstance(data, dict) else data

    # ─── Validate connection ───────────────────────────────────────────────

    async def validate_connection(self) -> str:
        """Authenticate and return identity name to confirm connectivity."""
        await self.authenticate()
        if self._identity_id:
            info = await self.get(f"/api/v1/identities/{self._identity_id}")
            return info.get("identity", {}).get("identity", {}).get("name", self._identity_id)
        return "authenticated"
