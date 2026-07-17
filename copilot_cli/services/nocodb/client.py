"""NocoDB / CRM API client for record and schema management."""

from __future__ import annotations

from typing import Any

import httpx

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.http_client import api_request, create_client

SERVICE = "nocodb"


class NocoDBClient:
    """Thin wrapper around the NocoDB REST API.

    Exposes two internal httpx clients:

    * ``_data`` -- targets ``/api/v1`` for row-level CRUD and bulk ops.
    * ``_meta`` -- targets ``/api/v2/meta`` for base/table schema ops.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_id: str = settings.nocodb_base_id
        auth_headers = {"xc-token": settings.nocodb_api_key}

        self._data: httpx.Client = create_client(
            base_url=f"{settings.nocodb_url.rstrip('/')}/api/v1",
            headers=auth_headers,
        )
        self._meta: httpx.Client = create_client(
            base_url=f"{settings.nocodb_url.rstrip('/')}/api/v2/meta",
            headers=auth_headers,
        )

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    def create_client(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new client record.

        Args:
            data: Field values for the new client row.

        Returns:
            The created client record.
        """
        return api_request(self._data, "POST", "/db/data/noco/clients", service=SERVICE, json=data)

    def get_client(self, client_id: str) -> dict[str, Any]:
        """Fetch a single client by ID.

        Args:
            client_id: Primary key of the client row.

        Returns:
            The client record.
        """
        return api_request(self._data, "GET", f"/db/data/noco/clients/{client_id}", service=SERVICE)

    def update_client(self, client_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing client.

        Args:
            client_id: Primary key of the client row.
            data: Fields to patch.

        Returns:
            The updated client record.
        """
        return api_request(
            self._data, "PATCH", f"/db/data/noco/clients/{client_id}", service=SERVICE, json=data
        )

    def delete_client(self, client_id: str) -> dict[str, Any]:
        """Delete a client by ID.

        Args:
            client_id: Primary key of the client row.

        Returns:
            API confirmation payload.
        """
        return api_request(
            self._data, "DELETE", f"/db/data/noco/clients/{client_id}", service=SERVICE
        )

    def list_clients(
        self,
        limit: int = 25,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List client records with optional filtering.

        Args:
            limit: Maximum rows to return.
            offset: Number of rows to skip.
            status: Optional status value to filter on.
            search: Optional free-text search term.

        Returns:
            Paginated response with ``list`` of client rows.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where_clauses: list[str] = []
        if status:
            where_clauses.append(f"(Status,eq,{status})")
        if search:
            params["search"] = search
        if where_clauses:
            params["where"] = "~and".join(where_clauses)
        return api_request(
            self._data, "GET", "/db/data/noco/clients", service=SERVICE, params=params
        )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def create_project(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new project record.

        Args:
            data: Field values for the new project row.

        Returns:
            The created project record.
        """
        return api_request(self._data, "POST", "/db/data/noco/projects", service=SERVICE, json=data)

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Fetch a single project by ID.

        Args:
            project_id: Primary key of the project row.

        Returns:
            The project record.
        """
        return api_request(
            self._data, "GET", f"/db/data/noco/projects/{project_id}", service=SERVICE
        )

    def list_projects(
        self,
        limit: int = 25,
        offset: int = 0,
        client_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List project records with optional filtering.

        Args:
            limit: Maximum rows to return.
            offset: Number of rows to skip.
            client_id: Filter by associated client ID.
            status: Filter by project status.

        Returns:
            Paginated response with ``list`` of project rows.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where_clauses: list[str] = []
        if client_id:
            where_clauses.append(f"(ClientId,eq,{client_id})")
        if status:
            where_clauses.append(f"(Status,eq,{status})")
        if where_clauses:
            params["where"] = "~and".join(where_clauses)
        return api_request(
            self._data, "GET", "/db/data/noco/projects", service=SERVICE, params=params
        )

    # ------------------------------------------------------------------
    # Leads
    # ------------------------------------------------------------------

    def create_lead(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new lead record.

        Args:
            data: Field values for the new lead row.

        Returns:
            The created lead record.
        """
        return api_request(self._data, "POST", "/db/data/noco/leads", service=SERVICE, json=data)

    def convert_lead(
        self,
        lead_id: str,
        client_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert a lead into a client record.

        Reads the lead, creates a new client (merging optional overrides),
        and marks the lead status as ``Converted``.

        Args:
            lead_id: Primary key of the lead row.
            client_data: Optional field overrides for the new client.

        Returns:
            Dict with ``lead``, ``client``, and ``status`` keys.
        """
        lead = api_request(self._data, "GET", f"/db/data/noco/leads/{lead_id}", service=SERVICE)

        new_client: dict[str, Any] = {
            "Name": lead.get("Name", ""),
            "Email": lead.get("Email", ""),
            "Phone": lead.get("Phone", ""),
            "Company": lead.get("Company", ""),
            "Source": "lead_conversion",
            "Status": "Active",
        }
        if client_data:
            new_client.update(client_data)

        client = self.create_client(new_client)

        self.update_client_lead_status(lead_id)

        return {"lead": lead, "client": client, "status": "converted"}

    def update_client_lead_status(self, lead_id: str) -> dict[str, Any]:
        """Mark a lead as Converted.

        Args:
            lead_id: Primary key of the lead row.

        Returns:
            The updated lead record.
        """
        return api_request(
            self._data,
            "PATCH",
            f"/db/data/noco/leads/{lead_id}",
            service=SERVICE,
            json={"Status": "Converted"},
        )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def create_resource(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new resource record.

        Args:
            data: Field values for the new resource row.

        Returns:
            The created resource record.
        """
        return api_request(
            self._data, "POST", "/db/data/noco/resources", service=SERVICE, json=data
        )

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def bulk_create(self, table: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Bulk-insert rows into the given table.

        Args:
            table: NocoDB table name.
            records: List of row dicts to insert.

        Returns:
            API response with inserted row count or IDs.
        """
        return api_request(
            self._data, "POST", f"/db/data/bulk/noco/{table}", service=SERVICE, json=records
        )

    def bulk_update(self, table: str, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """Bulk-patch rows in the given table.

        Args:
            table: NocoDB table name.
            updates: List of row dicts (must include primary key) with updated fields.

        Returns:
            API response with updated row count.
        """
        return api_request(
            self._data, "PATCH", f"/db/data/bulk/noco/{table}", service=SERVICE, json=updates
        )

    # ------------------------------------------------------------------
    # Meta / schema operations  (uses /api/v2/meta)
    # ------------------------------------------------------------------

    def get_bases(self) -> dict[str, Any]:
        """List all NocoDB bases visible to the token.

        Returns:
            Response containing a ``list`` of base objects.
        """
        return api_request(self._meta, "GET", "/bases", service=SERVICE)

    def get_base(self, base_id: str) -> dict[str, Any]:
        """Fetch details for a single base.

        Args:
            base_id: NocoDB base identifier.

        Returns:
            The base object.
        """
        return api_request(self._meta, "GET", f"/bases/{base_id}", service=SERVICE)

    def list_tables(self, base_id: str) -> dict[str, Any]:
        """List tables within a base.

        Args:
            base_id: NocoDB base identifier.

        Returns:
            Response containing a ``list`` of table objects.
        """
        return api_request(self._meta, "GET", f"/bases/{base_id}/tables", service=SERVICE)

    def create_table(self, base_id: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Create a new table in the given base.

        Args:
            base_id: NocoDB base identifier.
            schema: Table schema definition (name, columns, etc.).

        Returns:
            The created table object.
        """
        return api_request(
            self._meta, "POST", f"/bases/{base_id}/tables", service=SERVICE, json=schema
        )

    def delete_table(self, table_id: str) -> dict[str, Any]:
        """Delete a table by its ID.

        Args:
            table_id: NocoDB table identifier.

        Returns:
            API confirmation payload.
        """
        return api_request(self._meta, "DELETE", f"/tables/{table_id}", service=SERVICE)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Test connectivity to the NocoDB instance.

        Returns:
            Dict with ``healthy`` boolean and optional detail keys.
        """
        try:
            bases = self.get_bases()
            return {"healthy": True, "status": "healthy", "bases": len(bases.get("list", []))}
        except CopilotError as exc:
            return {"healthy": False, "status": "unhealthy", "error": str(exc)}
        except Exception as exc:
            return {"healthy": False, "status": "unhealthy", "error": str(exc)}
