"""Comprehensive tests for the n8n workflow automation API service.

Covers:
- N8nClient method calls with correct endpoints and parameters
- Workflow CRUD (list, get, create, update, delete)
- Workflow activation and deactivation
- Execution listing with filters
- Health check success and failure paths
- CLI commands (workflows list, executions list, health)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.shared.errors import ConnectionError, CopilotError, TimeoutError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api_request():
    with patch("copilot_cli.services.n8n.client.api_request") as mock:
        yield mock


@pytest.fixture
def mock_create_client():
    with patch("copilot_cli.services.n8n.client.create_client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def n8n(mock_api_request, mock_create_client):
    """Instantiate an N8nClient with mocked HTTP plumbing."""
    from copilot_cli.services.n8n.client import N8nClient

    return N8nClient()


# ======================================================================
# Workflows - list
# ======================================================================


class TestListWorkflows:
    """N8nClient.list_workflows method."""

    def test_default_params(self, n8n, mock_api_request):
        """list_workflows uses default limit=250 and no cursor/active filter."""
        mock_api_request.return_value = {"data": []}
        result = n8n.list_workflows()

        mock_api_request.assert_called_once_with(
            n8n._client,
            "GET",
            "/workflows",
            service="n8n",
            params={"limit": 250},
        )
        assert result["data"] == []

    def test_with_active_true(self, n8n, mock_api_request):
        """list_workflows passes active=true as lowercase string."""
        mock_api_request.return_value = {"data": [{"id": "w1", "active": True}]}
        n8n.list_workflows(active=True)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["active"] == "true"

    def test_with_active_false(self, n8n, mock_api_request):
        """list_workflows passes active=false as lowercase string."""
        mock_api_request.return_value = {"data": []}
        n8n.list_workflows(active=False)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["active"] == "false"

    def test_active_none_omits_param(self, n8n, mock_api_request):
        """list_workflows omits active param when None."""
        mock_api_request.return_value = {"data": []}
        n8n.list_workflows(active=None)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "active" not in params

    def test_with_cursor(self, n8n, mock_api_request):
        """list_workflows passes cursor for pagination."""
        mock_api_request.return_value = {"data": [], "nextCursor": None}
        n8n.list_workflows(cursor="abc123")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["cursor"] == "abc123"

    def test_custom_limit(self, n8n, mock_api_request):
        """list_workflows respects custom limit."""
        mock_api_request.return_value = {"data": []}
        n8n.list_workflows(limit=10)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["limit"] == 10


# ======================================================================
# Workflows - get
# ======================================================================


class TestGetWorkflow:
    """N8nClient.get_workflow method."""

    def test_fetches_by_id(self, n8n, mock_api_request):
        """get_workflow GETs /workflows/{id}."""
        mock_api_request.return_value = {"id": "w1", "name": "Email Sequence", "active": True}
        result = n8n.get_workflow("w1")

        mock_api_request.assert_called_once_with(n8n._client, "GET", "/workflows/w1", service="n8n")
        assert result["name"] == "Email Sequence"

    def test_numeric_id(self, n8n, mock_api_request):
        """get_workflow handles numeric string IDs."""
        mock_api_request.return_value = {"id": "123"}
        n8n.get_workflow("123")

        path = mock_api_request.call_args[0][2]
        assert path == "/workflows/123"


# ======================================================================
# Workflows - create
# ======================================================================


class TestCreateWorkflow:
    """N8nClient.create_workflow method."""

    def test_posts_data(self, n8n, mock_api_request):
        """create_workflow POSTs to /workflows."""
        workflow_data = {
            "name": "New Workflow",
            "nodes": [],
            "connections": {},
            "settings": {},
        }
        mock_api_request.return_value = {"id": "w-new", **workflow_data}
        result = n8n.create_workflow(workflow_data)

        mock_api_request.assert_called_once_with(
            n8n._client, "POST", "/workflows", service="n8n", json=workflow_data
        )
        assert result["id"] == "w-new"

    def test_empty_workflow(self, n8n, mock_api_request):
        """create_workflow handles minimal payload."""
        mock_api_request.return_value = {"id": "w-2", "name": "Empty"}
        n8n.create_workflow({"name": "Empty"})

        json_data = mock_api_request.call_args.kwargs.get("json")
        assert json_data["name"] == "Empty"


# ======================================================================
# Workflows - update
# ======================================================================


class TestUpdateWorkflow:
    """N8nClient.update_workflow method."""

    def test_puts_data(self, n8n, mock_api_request):
        """update_workflow PUTs to /workflows/{id}."""
        updated = {"name": "Renamed Workflow", "nodes": [{"type": "n8n-nodes-base.start"}]}
        mock_api_request.return_value = {"id": "w1", **updated}
        n8n.update_workflow("w1", updated)

        mock_api_request.assert_called_once_with(
            n8n._client, "PUT", "/workflows/w1", service="n8n", json=updated
        )


# ======================================================================
# Workflows - delete
# ======================================================================


class TestDeleteWorkflow:
    """N8nClient.delete_workflow method."""

    def test_deletes_by_id(self, n8n, mock_api_request):
        """delete_workflow DELETEs /workflows/{id}."""
        mock_api_request.return_value = {"id": "w1"}
        n8n.delete_workflow("w1")

        mock_api_request.assert_called_once_with(
            n8n._client, "DELETE", "/workflows/w1", service="n8n"
        )


# ======================================================================
# Workflows - activate / deactivate
# ======================================================================


class TestActivateWorkflow:
    """N8nClient.activate_workflow method."""

    def test_patches_active_true(self, n8n, mock_api_request):
        """activate_workflow PATCHes with active=True."""
        mock_api_request.return_value = {"id": "w1", "active": True}
        result = n8n.activate_workflow("w1")

        mock_api_request.assert_called_once_with(
            n8n._client,
            "PATCH",
            "/workflows/w1",
            service="n8n",
            json={"active": True},
        )
        assert result["active"] is True


class TestDeactivateWorkflow:
    """N8nClient.deactivate_workflow method."""

    def test_patches_active_false(self, n8n, mock_api_request):
        """deactivate_workflow PATCHes with active=False."""
        mock_api_request.return_value = {"id": "w1", "active": False}
        result = n8n.deactivate_workflow("w1")

        mock_api_request.assert_called_once_with(
            n8n._client,
            "PATCH",
            "/workflows/w1",
            service="n8n",
            json={"active": False},
        )
        assert result["active"] is False


# ======================================================================
# Executions
# ======================================================================


class TestListExecutions:
    """N8nClient.list_executions method."""

    def test_default_params(self, n8n, mock_api_request):
        """list_executions uses default limit=20."""
        mock_api_request.return_value = {"data": []}
        n8n.list_executions()

        mock_api_request.assert_called_once_with(
            n8n._client,
            "GET",
            "/executions",
            service="n8n",
            params={"limit": 20},
        )

    def test_with_workflow_filter(self, n8n, mock_api_request):
        """list_executions passes workflowId param."""
        mock_api_request.return_value = {"data": []}
        n8n.list_executions(workflow_id="w1")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["workflowId"] == "w1"

    def test_with_status_filter(self, n8n, mock_api_request):
        """list_executions passes status param."""
        mock_api_request.return_value = {"data": []}
        n8n.list_executions(status="error")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["status"] == "error"

    def test_with_all_filters(self, n8n, mock_api_request):
        """list_executions passes all params when provided."""
        mock_api_request.return_value = {"data": []}
        n8n.list_executions(workflow_id="w1", status="success", limit=5)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"limit": 5, "workflowId": "w1", "status": "success"}

    def test_none_filters_omitted(self, n8n, mock_api_request):
        """list_executions omits None-valued filters."""
        mock_api_request.return_value = {"data": []}
        n8n.list_executions(workflow_id=None, status=None)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "workflowId" not in params
        assert "status" not in params


class TestGetExecution:
    """N8nClient.get_execution method."""

    def test_fetches_by_id(self, n8n, mock_api_request):
        """get_execution GETs /executions/{id}."""
        mock_api_request.return_value = {"id": "e1", "status": "success"}
        result = n8n.get_execution("e1")

        mock_api_request.assert_called_once_with(
            n8n._client, "GET", "/executions/e1", service="n8n"
        )
        assert result["status"] == "success"


# ======================================================================
# Health
# ======================================================================


class TestHealth:
    """N8nClient.health method."""

    def test_healthy_on_success(self, n8n, mock_api_request):
        """health returns healthy=True when /workflows call succeeds."""
        mock_api_request.return_value = {"data": [{"id": "w1"}]}
        result = n8n.health()

        assert result["healthy"] is True
        assert result["workflows_accessible"] is True
        assert result["sample_count"] == 1

    def test_healthy_with_empty_data(self, n8n, mock_api_request):
        """health returns healthy=True even with no workflows."""
        mock_api_request.return_value = {"data": []}
        result = n8n.health()

        assert result["healthy"] is True
        assert result["sample_count"] == 0

    def test_unhealthy_on_connection_error(self, n8n, mock_api_request):
        """health returns healthy=False on ConnectionError."""
        mock_api_request.side_effect = ConnectionError("refused", service="n8n")
        result = n8n.health()

        assert result["healthy"] is False
        assert "refused" in result["error"]

    def test_unhealthy_on_timeout(self, n8n, mock_api_request):
        """health returns healthy=False on TimeoutError."""
        mock_api_request.side_effect = TimeoutError("timed out", service="n8n")
        result = n8n.health()

        assert result["healthy"] is False
        assert "timed out" in result["error"]

    def test_unhealthy_on_generic_exception(self, n8n, mock_api_request):
        """health returns healthy=False on unexpected exceptions."""
        mock_api_request.side_effect = RuntimeError("something broke")
        result = n8n.health()

        assert result["healthy"] is False
        assert "something broke" in result["error"]

    def test_health_calls_with_limit_1(self, n8n, mock_api_request):
        """health fetches /workflows with limit=1 for minimal overhead."""
        mock_api_request.return_value = {"data": []}
        n8n.health()

        mock_api_request.assert_called_once_with(
            n8n._client,
            "GET",
            "/workflows",
            service="n8n",
            params={"limit": 1},
        )


# ======================================================================
# CLI commands
# ======================================================================


class TestCLIWorkflowsListCommand:
    """CLI: copilot n8n workflows list."""

    def test_workflows_list_success(self, cli):
        """n8n workflows list renders workflow table."""
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = {
            "data": [
                {
                    "id": "w1",
                    "name": "Email Sequence",
                    "active": True,
                    "createdAt": "2025-01-01T00:00:00Z",
                    "updatedAt": "2025-01-02T00:00:00Z",
                },
                {
                    "id": "w2",
                    "name": "Data Sync",
                    "active": False,
                    "createdAt": "2025-01-03T00:00:00Z",
                    "updatedAt": "2025-01-04T00:00:00Z",
                },
            ]
        }
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "list")

        assert result.exit_code == 0
        assert "Email Sequence" in result.output
        assert "Data Sync" in result.output

    def test_workflows_list_empty(self, cli):
        """n8n workflows list handles empty data gracefully."""
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = {"data": []}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "list")

        assert result.exit_code == 0

    def test_workflows_list_error(self, cli):
        """n8n workflows list exits 1 on API error."""
        mock_client = MagicMock()
        mock_client.list_workflows.side_effect = CopilotError("unavailable")
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "list")

        assert result.exit_code == 1


class TestCLIWorkflowsGetCommand:
    """CLI: copilot n8n workflows get."""

    def test_workflows_get_success(self, cli):
        """n8n workflows get ID renders the workflow."""
        mock_client = MagicMock()
        mock_client.get_workflow.return_value = {
            "id": "w1",
            "name": "Test Workflow",
            "active": True,
        }
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "get", "w1")

        assert result.exit_code == 0
        assert "Test Workflow" in result.output


class TestCLIWorkflowsActivateCommand:
    """CLI: copilot n8n workflows activate."""

    def test_activate_success(self, cli):
        """n8n workflows activate ID succeeds."""
        mock_client = MagicMock()
        mock_client.activate_workflow.return_value = {"id": "w1", "active": True}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "activate", "w1")

        assert result.exit_code == 0
        assert "activated" in result.output.lower()


class TestCLIWorkflowsDeactivateCommand:
    """CLI: copilot n8n workflows deactivate."""

    def test_deactivate_success(self, cli):
        """n8n workflows deactivate ID succeeds."""
        mock_client = MagicMock()
        mock_client.deactivate_workflow.return_value = {"id": "w1", "active": False}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "deactivate", "w1")

        assert result.exit_code == 0
        assert "deactivated" in result.output.lower()


class TestCLIExecutionsListCommand:
    """CLI: copilot n8n executions list."""

    def test_executions_list_success(self, cli):
        """n8n executions list renders execution table."""
        mock_client = MagicMock()
        mock_client.list_executions.return_value = {
            "data": [
                {
                    "id": "e1",
                    "workflowId": "w1",
                    "status": "success",
                    "startedAt": "2025-01-01T00:00:00Z",
                    "stoppedAt": "2025-01-01T00:00:05Z",
                },
            ]
        }
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "executions", "list")

        assert result.exit_code == 0
        assert "e1" in result.output

    def test_executions_list_empty(self, cli):
        """n8n executions list handles no executions."""
        mock_client = MagicMock()
        mock_client.list_executions.return_value = {"data": []}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "executions", "list")

        assert result.exit_code == 0

    def test_executions_list_with_filters(self, cli):
        """n8n executions list passes filter options through."""
        mock_client = MagicMock()
        mock_client.list_executions.return_value = {"data": []}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli(
                "n8n",
                "executions",
                "list",
                "--workflow-id",
                "w1",
                "--status",
                "error",
                "--limit",
                "5",
            )

        assert result.exit_code == 0
        mock_client.list_executions.assert_called_once_with(
            workflow_id="w1", status="error", limit=5
        )


class TestCLIHealthCommand:
    """CLI: copilot n8n health."""

    def test_health_success(self, cli):
        """n8n health exits 0 and prints reachable message when healthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": True,
            "workflows_accessible": True,
            "sample_count": 5,
        }
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "health")

        assert result.exit_code == 0
        assert "reachable" in result.output.lower()

    def test_health_failure(self, cli):
        """n8n health exits 1 when unhealthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": False,
            "error": "connection refused",
        }
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "health")

        assert result.exit_code == 1


class TestCLIWorkflowsDeleteCommand:
    """CLI: copilot n8n workflows delete."""

    def test_delete_success(self, cli):
        """n8n workflows delete ID succeeds."""
        mock_client = MagicMock()
        mock_client.delete_workflow.return_value = {"id": "w1"}
        with patch("copilot_cli.services.n8n.commands._client", return_value=mock_client):
            result = cli("n8n", "workflows", "delete", "w1")

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
