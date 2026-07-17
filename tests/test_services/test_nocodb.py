"""Comprehensive tests for the NocoDB / CRM API service.

Covers:
- NocoDBClient method calls with correct endpoints and parameters
- Lead conversion logic (multi-step workflow)
- Bulk operations
- Meta/schema operations (bases, tables)
- Health check success and failure paths
- CLI commands (clients list, health)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from copilot_cli.shared.errors import ConnectionError, CopilotError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api_request():
    with patch("copilot_cli.services.nocodb.client.api_request") as mock:
        yield mock


@pytest.fixture
def mock_create_client():
    with patch("copilot_cli.services.nocodb.client.create_client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def nocodb(mock_api_request, mock_create_client):
    """Instantiate a NocoDBClient with mocked HTTP plumbing."""
    from copilot_cli.services.nocodb.client import NocoDBClient

    return NocoDBClient()


# ======================================================================
# Client CRUD
# ======================================================================


class TestListClients:
    """NocoDBClient.list_clients method."""

    def test_default_params(self, nocodb, mock_api_request):
        """list_clients uses correct defaults for limit and offset."""
        mock_api_request.return_value = {"list": []}
        result = nocodb.list_clients()

        mock_api_request.assert_called_once_with(
            nocodb._data,
            "GET",
            "/db/data/noco/clients",
            service="nocodb",
            params={"limit": 25, "offset": 0},
        )
        assert result == {"list": []}

    def test_with_status_filter(self, nocodb, mock_api_request):
        """list_clients builds a where clause when status is provided."""
        mock_api_request.return_value = {"list": [{"Id": "1"}]}
        nocodb.list_clients(status="Active")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["where"] == "(Status,eq,Active)"

    def test_with_search(self, nocodb, mock_api_request):
        """list_clients passes search parameter through."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_clients(search="Acme")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["search"] == "Acme"

    def test_with_custom_pagination(self, nocodb, mock_api_request):
        """list_clients respects custom limit and offset."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_clients(limit=10, offset=50)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["limit"] == 10
        assert params["offset"] == 50

    def test_status_and_search_combined(self, nocodb, mock_api_request):
        """list_clients combines where clause with search param."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_clients(status="Active", search="Acme")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["where"] == "(Status,eq,Active)"
        assert params["search"] == "Acme"


class TestCreateClient:
    """NocoDBClient.create_client method."""

    def test_posts_correct_data(self, nocodb, mock_api_request):
        """create_client POSTs to the correct endpoint with the given payload."""
        payload = {"Name": "Test Corp", "Email": "hello@test.com"}
        mock_api_request.return_value = {"Id": "42", **payload}
        result = nocodb.create_client(payload)

        mock_api_request.assert_called_once_with(
            nocodb._data,
            "POST",
            "/db/data/noco/clients",
            service="nocodb",
            json=payload,
        )
        assert result["Id"] == "42"

    def test_empty_payload(self, nocodb, mock_api_request):
        """create_client passes an empty dict through without modification."""
        mock_api_request.return_value = {"Id": "1"}
        nocodb.create_client({})
        call_kwargs = mock_api_request.call_args
        assert call_kwargs.kwargs.get("json") == {}


class TestGetClient:
    """NocoDBClient.get_client method."""

    def test_fetches_by_id(self, nocodb, mock_api_request):
        """get_client GETs the correct path for a given ID."""
        mock_api_request.return_value = {"Id": "7", "Name": "Alice"}
        result = nocodb.get_client("7")

        mock_api_request.assert_called_once_with(
            nocodb._data, "GET", "/db/data/noco/clients/7", service="nocodb"
        )
        assert result["Name"] == "Alice"

    def test_numeric_string_id(self, nocodb, mock_api_request):
        """get_client handles numeric string IDs."""
        mock_api_request.return_value = {"Id": "999"}
        nocodb.get_client("999")

        path = mock_api_request.call_args[0][2]
        assert path == "/db/data/noco/clients/999"


class TestUpdateClient:
    """NocoDBClient.update_client method."""

    def test_patches_fields(self, nocodb, mock_api_request):
        """update_client PATCHes only the fields provided."""
        mock_api_request.return_value = {"Id": "5", "Status": "Inactive"}
        result = nocodb.update_client("5", {"Status": "Inactive"})

        mock_api_request.assert_called_once_with(
            nocodb._data,
            "PATCH",
            "/db/data/noco/clients/5",
            service="nocodb",
            json={"Status": "Inactive"},
        )
        assert result["Status"] == "Inactive"


class TestDeleteClient:
    """NocoDBClient.delete_client method."""

    def test_deletes_by_id(self, nocodb, mock_api_request):
        """delete_client DELETEs the correct path."""
        mock_api_request.return_value = {"msg": "deleted"}
        nocodb.delete_client("5")

        mock_api_request.assert_called_once_with(
            nocodb._data, "DELETE", "/db/data/noco/clients/5", service="nocodb"
        )


# ======================================================================
# Projects
# ======================================================================


class TestListProjects:
    """NocoDBClient.list_projects method."""

    def test_default_params(self, nocodb, mock_api_request):
        """list_projects uses correct defaults."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_projects()

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"limit": 25, "offset": 0}

    def test_with_client_and_status_filters(self, nocodb, mock_api_request):
        """list_projects builds where clause with both client_id and status."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_projects(client_id="c1", status="Active")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "(ClientId,eq,c1)" in params["where"]
        assert "(Status,eq,Active)" in params["where"]
        assert "~and" in params["where"]

    def test_with_only_status(self, nocodb, mock_api_request):
        """list_projects builds where clause with only status."""
        mock_api_request.return_value = {"list": []}
        nocodb.list_projects(status="Completed")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["where"] == "(Status,eq,Completed)"


# ======================================================================
# Leads
# ======================================================================


class TestConvertLead:
    """NocoDBClient.convert_lead multi-step workflow."""

    def test_converts_lead_to_client(self, nocodb, mock_api_request):
        """convert_lead reads lead, creates client, and marks lead converted."""
        lead_data = {
            "Id": "L1",
            "Name": "Jane Doe",
            "Email": "jane@example.com",
            "Phone": "555-1234",
            "Company": "Acme Inc",
        }
        created_client = {"Id": "C99", "Name": "Jane Doe", "Status": "Active"}

        mock_api_request.side_effect = [
            lead_data,  # GET lead
            created_client,  # POST create_client
            {},  # PATCH update lead status
        ]

        result = nocodb.convert_lead("L1")

        assert result["status"] == "converted"
        assert result["lead"]["Name"] == "Jane Doe"
        assert result["client"]["Id"] == "C99"

        # Verify the sequence of calls
        calls = mock_api_request.call_args_list
        # First call: GET the lead
        assert calls[0][0][1] == "GET"
        assert "leads/L1" in calls[0][0][2]
        # Second call: POST create client
        assert calls[1][0][1] == "POST"
        assert "clients" in calls[1][0][2]
        # Third call: PATCH lead status to Converted
        assert calls[2][0][1] == "PATCH"
        assert "leads/L1" in calls[2][0][2]
        assert calls[2].kwargs.get("json") == {"Status": "Converted"}

    def test_convert_with_overrides(self, nocodb, mock_api_request):
        """convert_lead merges client_data overrides into the new client."""
        lead_data = {
            "Id": "L2",
            "Name": "Bob",
            "Email": "",
            "Phone": "",
            "Company": "",
        }
        created_client = {"Id": "C100", "Name": "Bob", "Status": "VIP"}

        mock_api_request.side_effect = [
            lead_data,
            created_client,
            {},
        ]

        result = nocodb.convert_lead("L2", client_data={"Status": "VIP"})
        assert result["status"] == "converted"

        # The POST call should have the override merged in
        post_call = mock_api_request.call_args_list[1]
        json_payload = post_call.kwargs.get("json")
        assert json_payload["Status"] == "VIP"
        assert json_payload["Source"] == "lead_conversion"


# ======================================================================
# Bulk operations
# ======================================================================


class TestBulkOperations:
    """NocoDBClient bulk_create and bulk_update."""

    def test_bulk_create_calls_correct_endpoint(self, nocodb, mock_api_request):
        """bulk_create POSTs to /db/data/bulk/noco/{table}."""
        records = [{"Name": "A"}, {"Name": "B"}]
        mock_api_request.return_value = {"inserted": 2}
        nocodb.bulk_create("clients", records)

        mock_api_request.assert_called_once_with(
            nocodb._data,
            "POST",
            "/db/data/bulk/noco/clients",
            service="nocodb",
            json=records,
        )

    def test_bulk_update_calls_correct_endpoint(self, nocodb, mock_api_request):
        """bulk_update PATCHes to /db/data/bulk/noco/{table}."""
        updates = [{"Id": "1", "Status": "Done"}, {"Id": "2", "Status": "Done"}]
        mock_api_request.return_value = {"updated": 2}
        nocodb.bulk_update("clients", updates)

        mock_api_request.assert_called_once_with(
            nocodb._data,
            "PATCH",
            "/db/data/bulk/noco/clients",
            service="nocodb",
            json=updates,
        )

    def test_bulk_create_empty_list(self, nocodb, mock_api_request):
        """bulk_create handles empty records list."""
        mock_api_request.return_value = {"inserted": 0}
        result = nocodb.bulk_create("clients", [])
        assert result["inserted"] == 0


# ======================================================================
# Meta / Schema
# ======================================================================


class TestMetaOperations:
    """NocoDBClient meta operations (bases, tables)."""

    def test_get_bases(self, nocodb, mock_api_request):
        """get_bases GETs /bases on the meta client."""
        mock_api_request.return_value = {"list": [{"id": "b1", "title": "Main"}]}
        result = nocodb.get_bases()

        mock_api_request.assert_called_once_with(nocodb._meta, "GET", "/bases", service="nocodb")
        assert len(result["list"]) == 1

    def test_get_base(self, nocodb, mock_api_request):
        """get_base GETs /bases/{base_id} on the meta client."""
        mock_api_request.return_value = {"id": "b1", "title": "Main"}
        nocodb.get_base("b1")

        mock_api_request.assert_called_once_with(nocodb._meta, "GET", "/bases/b1", service="nocodb")

    def test_list_tables(self, nocodb, mock_api_request):
        """list_tables GETs /bases/{base_id}/tables."""
        mock_api_request.return_value = {"list": [{"id": "t1", "title": "Clients"}]}
        nocodb.list_tables("b1")

        mock_api_request.assert_called_once_with(
            nocodb._meta, "GET", "/bases/b1/tables", service="nocodb"
        )

    def test_create_table(self, nocodb, mock_api_request):
        """create_table POSTs schema to /bases/{base_id}/tables."""
        schema = {"title": "NewTable", "columns": []}
        mock_api_request.return_value = {"id": "t99"}
        nocodb.create_table("b1", schema)

        mock_api_request.assert_called_once_with(
            nocodb._meta,
            "POST",
            "/bases/b1/tables",
            service="nocodb",
            json=schema,
        )

    def test_delete_table(self, nocodb, mock_api_request):
        """delete_table DELETEs /tables/{table_id}."""
        mock_api_request.return_value = {"msg": "deleted"}
        nocodb.delete_table("t1")

        mock_api_request.assert_called_once_with(
            nocodb._meta, "DELETE", "/tables/t1", service="nocodb"
        )


# ======================================================================
# Health
# ======================================================================


class TestHealth:
    """NocoDBClient.health method."""

    def test_healthy_on_success(self, nocodb, mock_api_request):
        """health returns healthy=True when get_bases succeeds."""
        mock_api_request.return_value = {"list": [{"id": "b1"}, {"id": "b2"}]}
        result = nocodb.health()

        assert result["healthy"] is True
        assert result["status"] == "healthy"
        assert result["bases"] == 2

    def test_unhealthy_on_copilot_error(self, nocodb, mock_api_request):
        """health returns healthy=False when a CopilotError is raised."""
        mock_api_request.side_effect = ConnectionError("Cannot connect", service="nocodb")
        result = nocodb.health()

        assert result["healthy"] is False
        assert result["status"] == "unhealthy"
        assert "Cannot connect" in result["error"]

    def test_unhealthy_on_generic_exception(self, nocodb, mock_api_request):
        """health returns healthy=False on unexpected exceptions."""
        mock_api_request.side_effect = RuntimeError("unexpected")
        result = nocodb.health()

        assert result["healthy"] is False
        assert "unexpected" in result["error"]


# ======================================================================
# CLI commands
# ======================================================================


class TestCLIClientsListCommand:
    """CLI: copilot crm clients list."""

    def test_clients_list_success(self, cli):
        """crm clients list renders output when API returns rows."""
        mock_client = MagicMock()
        mock_client.list_clients.return_value = {
            "list": [
                {"Id": "1", "Name": "Alice", "Status": "Active"},
                {"Id": "2", "Name": "Bob", "Status": "Inactive"},
            ]
        }
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "clients", "list")

        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_clients_list_empty(self, cli):
        """crm clients list handles empty result set gracefully."""
        mock_client = MagicMock()
        mock_client.list_clients.return_value = {"list": []}
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "clients", "list")

        assert result.exit_code == 0

    def test_clients_list_error(self, cli):
        """crm clients list exits with code 1 on CopilotError."""
        mock_client = MagicMock()
        mock_client.list_clients.side_effect = CopilotError("API down")
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "clients", "list")

        assert result.exit_code == 1


class TestCLIClientsGetCommand:
    """CLI: copilot crm clients get."""

    def test_clients_get_success(self, cli):
        """crm clients get ID renders the client record."""
        mock_client = MagicMock()
        mock_client.get_client.return_value = {"Id": "7", "Name": "Charlie"}
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "clients", "get", "7")

        assert result.exit_code == 0
        assert "Charlie" in result.output


class TestCLIClientsCreateCommand:
    """CLI: copilot crm clients create."""

    def test_clients_create_success(self, cli):
        """crm clients create --name X creates a client and prints success."""
        mock_client = MagicMock()
        mock_client.create_client.return_value = {"Id": "10", "Name": "NewCo"}
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "clients", "create", "--name", "NewCo")

        assert result.exit_code == 0
        mock_client.create_client.assert_called_once()
        call_data = mock_client.create_client.call_args[0][0]
        assert call_data["Name"] == "NewCo"


class TestCLIHealthCommand:
    """CLI: copilot crm health."""

    def test_health_success(self, cli):
        """crm health exits 0 when healthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": True,
            "status": "healthy",
            "bases": 2,
        }
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "health")

        assert result.exit_code == 0

    def test_health_failure(self, cli):
        """crm health exits 1 when unhealthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": False,
            "status": "unhealthy",
            "error": "timeout",
        }
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "health")

        assert result.exit_code == 1


class TestCLIBasesListCommand:
    """CLI: copilot crm bases list."""

    def test_bases_list_success(self, cli):
        """crm bases list renders output."""
        mock_client = MagicMock()
        mock_client.get_bases.return_value = {
            "list": [{"id": "b1", "title": "Main", "type": "database"}]
        }
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "bases", "list")

        assert result.exit_code == 0
        assert "Main" in result.output


class TestCLITablesListCommand:
    """CLI: copilot crm tables list."""

    def test_tables_list_success(self, cli):
        """crm tables list renders table listing."""
        mock_client = MagicMock()
        mock_client._base_id = "test-base-id"
        mock_client.list_tables.return_value = {
            "list": [{"id": "t1", "title": "Clients", "type": "table", "meta": ""}]
        }
        with patch("copilot_cli.services.nocodb.commands._client", return_value=mock_client):
            result = cli("crm", "tables", "list")

        assert result.exit_code == 0
        assert "Clients" in result.output
