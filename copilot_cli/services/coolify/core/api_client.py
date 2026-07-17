"""Async HTTP client for the Coolify API v1."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from copilot_cli.services.coolify.core.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
)


def _to_base64(value: str) -> str:
    """Base64-encode a string, passing through already-encoded values."""
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        if base64.b64encode(decoded.encode("utf-8")).decode("utf-8") == value:
            return value
    except Exception:
        pass
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _clean_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None values, keep explicit False."""
    return {k: v for k, v in data.items() if v is not None}


class CoolifyClient:
    """HTTP client for the Coolify API."""

    def __init__(self, base_url: str, access_token: str, timeout: float = 30.0):
        if not base_url:
            raise ConnectionError("Coolify base URL is required")
        if not access_token:
            raise AuthenticationError("Coolify access token is required")
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> CoolifyClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _build_query(self, params: dict[str, Any]) -> dict[str, Any]:
        return {k: str(v) for k, v in params.items() if v is not None}

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                json=json_data,
                params=params,
            )
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Failed to connect to Coolify server at {self.base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Request timed out: {e}") from e

        if response.status_code == 401:
            raise AuthenticationError("Invalid API token")
        if response.status_code == 403:
            raise AuthenticationError("Access denied — check API token permissions")

        text = response.text
        data: Any = {}
        if text:
            try:
                data = response.json()
            except Exception:
                data = text

        if not response.is_success:
            error_msg = ""
            errors: dict = {}
            if isinstance(data, dict):
                error_msg = data.get("message", f"HTTP {response.status_code}")
                errors = data.get("errors", {})
            else:
                error_msg = f"HTTP {response.status_code}: {response.reason_phrase}"
            raise APIError(error_msg, response.status_code, errors)

        return data

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_data=data)

    async def patch(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json_data=data)

    async def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("DELETE", path, params=params)

    # ─── Health & Version ─────────────────────────────────────────────────

    async def get_version(self) -> str:
        """Get Coolify server version (returns plain text)."""
        try:
            response = await self._client.get(
                "/version",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect: {e}") from e
        if not response.is_success:
            raise APIError(f"HTTP {response.status_code}", response.status_code)
        return response.text.strip()

    async def validate_connection(self) -> str:
        """Validate the API connection by fetching version."""
        return await self.get_version()

    # ─── Servers ──────────────────────────────────────────────────────────

    async def list_servers(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/servers", params=params or None)
        return result if isinstance(result, list) else []

    async def get_server(self, uuid: str) -> dict:
        return await self.get(f"/servers/{uuid}")

    async def create_server(self, data: dict[str, Any]) -> dict:
        return await self.post("/servers", data)

    async def update_server(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/servers/{uuid}", data)

    async def delete_server(self, uuid: str) -> dict:
        return await self.delete(f"/servers/{uuid}")

    async def get_server_resources(self, uuid: str) -> list[dict]:
        result = await self.get(f"/servers/{uuid}/resources")
        return result if isinstance(result, list) else []

    async def get_server_domains(self, uuid: str) -> list[dict]:
        result = await self.get(f"/servers/{uuid}/domains")
        return result if isinstance(result, list) else []

    async def validate_server(self, uuid: str) -> dict:
        return await self.get(f"/servers/{uuid}/validate")

    # ─── Projects ─────────────────────────────────────────────────────────

    async def list_projects(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/projects", params=params or None)
        return result if isinstance(result, list) else []

    async def get_project(self, uuid: str) -> dict:
        return await self.get(f"/projects/{uuid}")

    async def create_project(self, data: dict[str, Any]) -> dict:
        return await self.post("/projects", data)

    async def update_project(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/projects/{uuid}", data)

    async def delete_project(self, uuid: str) -> dict:
        return await self.delete(f"/projects/{uuid}")

    # ─── Environments ─────────────────────────────────────────────────────

    async def list_environments(self, project_uuid: str) -> list[dict]:
        result = await self.get(f"/projects/{project_uuid}/environments")
        return result if isinstance(result, list) else []

    async def get_environment(self, project_uuid: str, env_name_or_uuid: str) -> dict:
        return await self.get(f"/projects/{project_uuid}/{env_name_or_uuid}")

    async def create_environment(self, project_uuid: str, data: dict[str, Any]) -> dict:
        return await self.post(f"/projects/{project_uuid}/environments", data)

    async def delete_environment(self, project_uuid: str, env_name_or_uuid: str) -> dict:
        return await self.delete(f"/projects/{project_uuid}/environments/{env_name_or_uuid}")

    # ─── Applications ─────────────────────────────────────────────────────

    async def list_applications(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/applications", params=params or None)
        return result if isinstance(result, list) else []

    async def get_application(self, uuid: str) -> dict:
        return await self.get(f"/applications/{uuid}")

    async def create_application_public(self, data: dict[str, Any]) -> dict:
        return await self.post("/applications/public", data)

    async def create_application_private_gh(self, data: dict[str, Any]) -> dict:
        return await self.post("/applications/private-github-app", data)

    async def create_application_private_key(self, data: dict[str, Any]) -> dict:
        return await self.post("/applications/private-deploy-key", data)

    async def create_application_dockerfile(self, data: dict[str, Any]) -> dict:
        return await self.post("/applications/dockerfile", data)

    async def create_application_docker_image(self, data: dict[str, Any]) -> dict:
        return await self.post("/applications/dockerimage", data)

    async def create_application_docker_compose(self, data: dict[str, Any]) -> dict:
        payload = {**data}
        if "docker_compose_raw" in payload:
            payload["docker_compose_raw"] = _to_base64(payload["docker_compose_raw"])
        return await self.post("/applications/dockercompose", payload)

    async def update_application(self, uuid: str, data: dict[str, Any]) -> dict:
        payload = {**data}
        if "docker_compose_raw" in payload:
            payload["docker_compose_raw"] = _to_base64(payload["docker_compose_raw"])
        return await self.patch(f"/applications/{uuid}", payload)

    async def delete_application(self, uuid: str, **opts: Any) -> dict:
        params = self._build_query(
            {
                "delete_configurations": opts.get("delete_configurations"),
                "delete_volumes": opts.get("delete_volumes"),
                "docker_cleanup": opts.get("docker_cleanup"),
                "delete_connected_networks": opts.get("delete_connected_networks"),
            }
        )
        return await self.delete(f"/applications/{uuid}", params=params or None)

    async def get_application_logs(self, uuid: str, lines: int = 100) -> Any:
        return await self.get(f"/applications/{uuid}/logs", params={"lines": str(lines)})

    async def start_application(self, uuid: str) -> dict:
        return await self.post(f"/applications/{uuid}/start")

    async def stop_application(self, uuid: str) -> dict:
        return await self.post(f"/applications/{uuid}/stop")

    async def restart_application(self, uuid: str) -> dict:
        return await self.post(f"/applications/{uuid}/restart")

    # ─── Application Env Vars ─────────────────────────────────────────────

    async def list_app_envvars(self, uuid: str) -> list[dict]:
        result = await self.get(f"/applications/{uuid}/envs")
        return result if isinstance(result, list) else []

    async def create_app_envvar(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.post(f"/applications/{uuid}/envs", _clean_data(data))

    async def update_app_envvar(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/applications/{uuid}/envs", _clean_data(data))

    async def bulk_update_app_envvars(self, uuid: str, data: list[dict[str, Any]]) -> dict:
        return await self.patch(f"/applications/{uuid}/envs/bulk", {"data": data})

    async def delete_app_envvar(self, app_uuid: str, env_uuid: str) -> dict:
        return await self.delete(f"/applications/{app_uuid}/envs/{env_uuid}")

    # ─── Application Deployments ──────────────────────────────────────────

    async def list_app_deployments(self, app_uuid: str) -> list[dict]:
        result = await self.get(f"/applications/{app_uuid}/deployments")
        return result if isinstance(result, list) else []

    # ─── Databases ────────────────────────────────────────────────────────

    async def list_databases(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/databases", params=params or None)
        return result if isinstance(result, list) else []

    async def get_database(self, uuid: str) -> dict:
        return await self.get(f"/databases/{uuid}")

    async def create_database(self, db_type: str, data: dict[str, Any]) -> dict:
        return await self.post(f"/databases/{db_type}", data)

    async def update_database(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/databases/{uuid}", data)

    async def delete_database(self, uuid: str, **opts: Any) -> dict:
        params = self._build_query(
            {
                "delete_configurations": opts.get("delete_configurations"),
                "delete_volumes": opts.get("delete_volumes"),
                "docker_cleanup": opts.get("docker_cleanup"),
                "delete_connected_networks": opts.get("delete_connected_networks"),
            }
        )
        return await self.delete(f"/databases/{uuid}", params=params or None)

    async def start_database(self, uuid: str) -> dict:
        return await self.post(f"/databases/{uuid}/start")

    async def stop_database(self, uuid: str) -> dict:
        return await self.post(f"/databases/{uuid}/stop")

    async def restart_database(self, uuid: str) -> dict:
        return await self.post(f"/databases/{uuid}/restart")

    # ─── Services ─────────────────────────────────────────────────────────

    async def list_services(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/services", params=params or None)
        return result if isinstance(result, list) else []

    async def get_service(self, uuid: str) -> dict:
        return await self.get(f"/services/{uuid}")

    async def create_service(self, data: dict[str, Any]) -> dict:
        payload = {**data}
        if "docker_compose_raw" in payload:
            payload["docker_compose_raw"] = _to_base64(payload["docker_compose_raw"])
        return await self.post("/services", payload)

    async def update_service(self, uuid: str, data: dict[str, Any]) -> dict:
        payload = {**data}
        if "docker_compose_raw" in payload:
            payload["docker_compose_raw"] = _to_base64(payload["docker_compose_raw"])
        return await self.patch(f"/services/{uuid}", payload)

    async def delete_service(self, uuid: str, **opts: Any) -> dict:
        params = self._build_query(
            {
                "delete_configurations": opts.get("delete_configurations"),
                "delete_volumes": opts.get("delete_volumes"),
                "docker_cleanup": opts.get("docker_cleanup"),
                "delete_connected_networks": opts.get("delete_connected_networks"),
            }
        )
        return await self.delete(f"/services/{uuid}", params=params or None)

    async def start_service(self, uuid: str) -> dict:
        return await self.get(f"/services/{uuid}/start")

    async def stop_service(self, uuid: str) -> dict:
        return await self.get(f"/services/{uuid}/stop")

    async def restart_service(self, uuid: str) -> dict:
        return await self.get(f"/services/{uuid}/restart")

    # ─── Service Env Vars ─────────────────────────────────────────────────

    async def list_service_envvars(self, uuid: str) -> list[dict]:
        result = await self.get(f"/services/{uuid}/envs")
        return result if isinstance(result, list) else []

    async def create_service_envvar(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.post(f"/services/{uuid}/envs", _clean_data(data))

    async def update_service_envvar(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/services/{uuid}/envs", _clean_data(data))

    async def delete_service_envvar(self, svc_uuid: str, env_uuid: str) -> dict:
        return await self.delete(f"/services/{svc_uuid}/envs/{env_uuid}")

    # ─── Deployments ──────────────────────────────────────────────────────

    async def list_deployments(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[dict]:
        params = self._build_query({"page": page, "per_page": per_page})
        result = await self.get("/deployments", params=params or None)
        return result if isinstance(result, list) else []

    async def get_deployment(self, uuid: str) -> dict:
        return await self.get(f"/deployments/{uuid}")

    async def deploy(self, uuid_or_tag: str, force: bool = False) -> dict:
        """Deploy by UUID or tag."""
        import re

        is_uuid = bool(re.match(r"^[a-z0-9]{20,}$", uuid_or_tag, re.I)) or bool(
            re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", uuid_or_tag, re.I
            )
        )
        param = "uuid" if is_uuid else "tag"
        return await self.get("/deploy", params={param: uuid_or_tag, "force": str(force).lower()})

    async def cancel_deployment(self, uuid: str) -> dict:
        return await self.post(f"/deployments/{uuid}/cancel")

    # ─── Teams ────────────────────────────────────────────────────────────

    async def list_teams(self) -> list[dict]:
        result = await self.get("/teams")
        return result if isinstance(result, list) else []

    async def get_team(self, team_id: int) -> dict:
        return await self.get(f"/teams/{team_id}")

    async def get_team_members(self, team_id: int) -> list[dict]:
        result = await self.get(f"/teams/{team_id}/members")
        return result if isinstance(result, list) else []

    async def get_current_team(self) -> dict:
        return await self.get("/teams/current")

    async def get_current_team_members(self) -> list[dict]:
        result = await self.get("/teams/current/members")
        return result if isinstance(result, list) else []

    # ─── Private Keys ────────────────────────────────────────────────────

    async def list_private_keys(self) -> list[dict]:
        result = await self.get("/security/keys")
        return result if isinstance(result, list) else []

    async def get_private_key(self, uuid: str) -> dict:
        return await self.get(f"/security/keys/{uuid}")

    async def create_private_key(self, data: dict[str, Any]) -> dict:
        return await self.post("/security/keys", data)

    async def update_private_key(self, uuid: str, data: dict[str, Any]) -> dict:
        return await self.patch(f"/security/keys/{uuid}", data)

    async def delete_private_key(self, uuid: str) -> dict:
        return await self.delete(f"/security/keys/{uuid}")

    # ─── GitHub Apps ──────────────────────────────────────────────────────

    async def list_github_apps(self) -> list[dict]:
        result = await self.get("/github-apps")
        return result if isinstance(result, list) else []

    async def create_github_app(self, data: dict[str, Any]) -> dict:
        return await self.post("/github-apps", data)

    async def update_github_app(self, app_id: int, data: dict[str, Any]) -> dict:
        return await self.patch(f"/github-apps/{app_id}", _clean_data(data))

    async def delete_github_app(self, app_id: int) -> dict:
        return await self.delete(f"/github-apps/{app_id}")

    # ─── Database Backups ─────────────────────────────────────────────────

    async def list_database_backups(self, db_uuid: str) -> list[dict]:
        result = await self.get(f"/databases/{db_uuid}/backups")
        if not isinstance(result, list):
            return []

        # Coolify can return configurations for a different database kind when
        # two polymorphic database tables happen to use the same numeric ID.
        # The resource UUID still identifies the intended kind, so filter the
        # collection by its Laravel model type before presenting or mutating it.
        database = await self.get_database(db_uuid)
        resource_type = database.get("database_type") or database.get("type")
        if not resource_type:
            return result
        expected_type = "standalone" + str(resource_type).removeprefix("standalone-")
        expected_type = "".join(
            character for character in expected_type.lower() if character.isalnum()
        )
        return [
            backup
            for backup in result
            if not backup.get("database_type")
            or "".join(
                character
                for character in str(backup["database_type"]).rsplit("\\", 1)[-1].lower()
                if character.isalnum()
            )
            == expected_type
        ]

    async def get_database_backup(self, db_uuid: str, backup_uuid: str) -> dict:
        # Coolify exposes backup configurations through the collection GET;
        # the item path is PATCH/DELETE-only.
        backups = await self.list_database_backups(db_uuid)
        for backup in backups:
            if backup.get("uuid") == backup_uuid:
                return backup
        raise APIError("Backup configuration not found.", 404)

    async def create_database_backup(self, db_uuid: str, data: dict[str, Any]) -> dict:
        return await self.post(f"/databases/{db_uuid}/backups", _clean_data(data))

    async def update_database_backup(
        self, db_uuid: str, backup_uuid: str, data: dict[str, Any]
    ) -> dict:
        return await self.patch(f"/databases/{db_uuid}/backups/{backup_uuid}", data)

    async def delete_database_backup(self, db_uuid: str, backup_uuid: str) -> dict:
        return await self.delete(f"/databases/{db_uuid}/backups/{backup_uuid}")

    async def list_backup_executions(self, db_uuid: str, backup_uuid: str) -> list[dict]:
        result = await self.get(f"/databases/{db_uuid}/backups/{backup_uuid}/executions")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            executions = result.get("executions", [])
            return executions if isinstance(executions, list) else []
        return []
