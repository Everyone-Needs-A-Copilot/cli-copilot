"""n8n workflow automation API client using the shared httpx wrapper."""

from __future__ import annotations

from typing import Any

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.http_client import api_request, create_client

SERVICE = "n8n"


class N8nClient:
    """Wrapper around the n8n REST API (v1)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = create_client(
            base_url=f"{settings.n8n_base_url.rstrip('/')}/api/v1",
            headers={
                "X-N8N-API-KEY": settings.n8n_api_key,
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def list_workflows(
        self,
        limit: int = 250,
        cursor: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """List workflows with optional filtering.

        Args:
            limit: Maximum number of workflows to return.
            cursor: Pagination cursor for the next page.
            active: Filter by active state.

        Returns:
            Response dict with ``data`` list of workflow objects.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if active is not None:
            params["active"] = str(active).lower()
        return api_request(self._client, "GET", "/workflows", service=SERVICE, params=params)

    def get_workflow(self, id: str) -> dict[str, Any]:
        """Retrieve a single workflow by ID.

        Args:
            id: Workflow ID.

        Returns:
            Workflow object dict.
        """
        return api_request(self._client, "GET", f"/workflows/{id}", service=SERVICE)

    def create_workflow(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new workflow.

        Args:
            data: Workflow definition object.

        Returns:
            Created workflow object dict.
        """
        return api_request(self._client, "POST", "/workflows", service=SERVICE, json=data)

    def update_workflow(self, id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing workflow.

        Args:
            id: Workflow ID.
            data: Updated workflow definition.

        Returns:
            Updated workflow object dict.
        """
        return api_request(self._client, "PUT", f"/workflows/{id}", service=SERVICE, json=data)

    def delete_workflow(self, id: str) -> dict[str, Any]:
        """Delete a workflow.

        Args:
            id: Workflow ID.

        Returns:
            Deletion confirmation dict.
        """
        return api_request(self._client, "DELETE", f"/workflows/{id}", service=SERVICE)

    def activate_workflow(self, id: str) -> dict[str, Any]:
        """Activate a workflow.

        Args:
            id: Workflow ID.

        Returns:
            Updated workflow object dict.
        """
        return api_request(
            self._client,
            "PATCH",
            f"/workflows/{id}",
            service=SERVICE,
            json={"active": True},
        )

    def deactivate_workflow(self, id: str) -> dict[str, Any]:
        """Deactivate a workflow.

        Args:
            id: Workflow ID.

        Returns:
            Updated workflow object dict.
        """
        return api_request(
            self._client,
            "PATCH",
            f"/workflows/{id}",
            service=SERVICE,
            json={"active": False},
        )

    # ------------------------------------------------------------------
    # Executions
    # ------------------------------------------------------------------

    def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List workflow executions with optional filtering.

        Args:
            workflow_id: Filter by workflow ID.
            status: Filter by execution status (e.g. ``success``, ``error``).
            limit: Maximum number of results.

        Returns:
            Response dict with ``data`` list of execution objects.
        """
        params: dict[str, Any] = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        return api_request(self._client, "GET", "/executions", service=SERVICE, params=params)

    def get_execution(self, id: str) -> dict[str, Any]:
        """Retrieve a single execution by ID.

        Args:
            id: Execution ID.

        Returns:
            Execution object dict.
        """
        return api_request(self._client, "GET", f"/executions/{id}", service=SERVICE)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check n8n API connectivity by fetching a minimal workflow list.

        Returns:
            Dict with ``healthy`` boolean and workflow count.
        """
        try:
            result = api_request(
                self._client,
                "GET",
                "/workflows",
                service=SERVICE,
                params={"limit": 1},
            )
            data = result.get("data", []) if isinstance(result, dict) else []
            return {
                "healthy": True,
                "workflows_accessible": True,
                "sample_count": len(data),
            }
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}
