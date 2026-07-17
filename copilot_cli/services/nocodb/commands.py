"""Typer subcommand group for NocoDB / CRM operations."""

from __future__ import annotations

import json

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success, print_table

app = typer.Typer(no_args_is_help=True)

# -- Nested sub-apps for resource groups --
clients_app = typer.Typer(no_args_is_help=True, help="Client record management.")
projects_app = typer.Typer(no_args_is_help=True, help="Project record management.")
leads_app = typer.Typer(no_args_is_help=True, help="Lead record management.")
tables_app = typer.Typer(no_args_is_help=True, help="NocoDB table schema operations.")
bases_app = typer.Typer(no_args_is_help=True, help="NocoDB base operations.")

app.add_typer(clients_app, name="clients")
app.add_typer(projects_app, name="projects")
app.add_typer(leads_app, name="leads")
app.add_typer(tables_app, name="tables")
app.add_typer(bases_app, name="bases")


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.nocodb.client import NocoDBClient

    return NocoDBClient()


# ======================================================================
# Clients
# ======================================================================


@clients_app.command("list")
def clients_list(
    limit: int = typer.Option(25, "--limit", help="Max rows to return."),
    offset: int = typer.Option(0, "--offset", help="Number of rows to skip."),
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
    search: str | None = typer.Option(None, "--search", help="Free-text search term."),
) -> None:
    """List client records."""
    try:
        result = _client().list_clients(limit=limit, offset=offset, status=status, search=search)
        rows = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Clients")
        else:
            print_json(result, title="Clients")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@clients_app.command("get")
def clients_get(
    client_id: str = typer.Argument(..., help="Client row ID."),
) -> None:
    """Get a single client by ID."""
    try:
        result = _client().get_client(client_id)
        print_json(result, title=f"Client {client_id}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@clients_app.command("create")
def clients_create(
    name: str = typer.Option(..., "--name", help="Client name."),
    email: str | None = typer.Option(None, "--email", help="Email address."),
    phone: str | None = typer.Option(None, "--phone", help="Phone number."),
    company: str | None = typer.Option(None, "--company", help="Company name."),
    status: str | None = typer.Option(None, "--status", help="Initial status."),
) -> None:
    """Create a new client record."""
    try:
        data: dict = {"Name": name}
        if email:
            data["Email"] = email
        if phone:
            data["Phone"] = phone
        if company:
            data["Company"] = company
        if status:
            data["Status"] = status
        result = _client().create_client(data)
        print_success(f"Client created: {result.get('Id', result.get('id', ''))}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@clients_app.command("update")
def clients_update(
    client_id: str = typer.Argument(..., help="Client row ID."),
    name: str | None = typer.Option(None, "--name", help="Client name."),
    email: str | None = typer.Option(None, "--email", help="Email address."),
    phone: str | None = typer.Option(None, "--phone", help="Phone number."),
    company: str | None = typer.Option(None, "--company", help="Company name."),
    status: str | None = typer.Option(None, "--status", help="Status value."),
) -> None:
    """Update an existing client record."""
    try:
        data: dict = {}
        if name is not None:
            data["Name"] = name
        if email is not None:
            data["Email"] = email
        if phone is not None:
            data["Phone"] = phone
        if company is not None:
            data["Company"] = company
        if status is not None:
            data["Status"] = status
        if not data:
            print_error("No fields provided to update.")
            raise typer.Exit(1)
        result = _client().update_client(client_id, data)
        print_success(f"Client {client_id} updated.")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@clients_app.command("delete")
def clients_delete(
    client_id: str = typer.Argument(..., help="Client row ID."),
) -> None:
    """Delete a client record."""
    try:
        _client().delete_client(client_id)
        print_success(f"Client {client_id} deleted.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Projects
# ======================================================================


@projects_app.command("list")
def projects_list(
    limit: int = typer.Option(25, "--limit", help="Max rows to return."),
    offset: int = typer.Option(0, "--offset", help="Number of rows to skip."),
    client_id: str | None = typer.Option(None, "--client-id", help="Filter by client ID."),
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
) -> None:
    """List project records."""
    try:
        result = _client().list_projects(
            limit=limit, offset=offset, client_id=client_id, status=status
        )
        rows = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Projects")
        else:
            print_json(result, title="Projects")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@projects_app.command("get")
def projects_get(
    project_id: str = typer.Argument(..., help="Project row ID."),
) -> None:
    """Get a single project by ID."""
    try:
        result = _client().get_project(project_id)
        print_json(result, title=f"Project {project_id}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@projects_app.command("create")
def projects_create(
    name: str = typer.Option(..., "--name", help="Project name."),
    client_id: str | None = typer.Option(None, "--client-id", help="Associated client ID."),
    description: str | None = typer.Option(None, "--description", help="Project description."),
    status: str | None = typer.Option(None, "--status", help="Initial status."),
) -> None:
    """Create a new project record."""
    try:
        data: dict = {"Name": name}
        if client_id:
            data["ClientId"] = client_id
        if description:
            data["Description"] = description
        if status:
            data["Status"] = status
        result = _client().create_project(data)
        print_success(f"Project created: {result.get('Id', result.get('id', ''))}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Leads
# ======================================================================


@leads_app.command("create")
def leads_create(
    name: str = typer.Option(..., "--name", help="Lead name."),
    email: str | None = typer.Option(None, "--email", help="Email address."),
    phone: str | None = typer.Option(None, "--phone", help="Phone number."),
    company: str | None = typer.Option(None, "--company", help="Company name."),
    source: str | None = typer.Option(None, "--source", help="Lead source."),
    status: str | None = typer.Option(None, "--status", help="Initial status."),
) -> None:
    """Create a new lead record."""
    try:
        data: dict = {"Name": name}
        if email:
            data["Email"] = email
        if phone:
            data["Phone"] = phone
        if company:
            data["Company"] = company
        if source:
            data["Source"] = source
        if status:
            data["Status"] = status
        result = _client().create_lead(data)
        print_success(f"Lead created: {result.get('Id', result.get('id', ''))}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@leads_app.command("convert")
def leads_convert(
    lead_id: str = typer.Argument(..., help="Lead row ID to convert."),
) -> None:
    """Convert a lead into a client record."""
    try:
        result = _client().convert_lead(lead_id)
        print_success(f"Lead {lead_id} converted to client.")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Tables (meta)
# ======================================================================


@tables_app.command("list")
def tables_list(
    base_id: str | None = typer.Option(
        None, "--base-id", help="NocoDB base ID (defaults to configured base)."
    ),
) -> None:
    """List tables in a NocoDB base."""
    try:
        c = _client()
        bid = base_id or c._base_id
        if not bid:
            print_error(
                "No base ID provided and none configured.",
                hint="Set NOCODB_BASE_ID or pass --base-id.",
            )
            raise typer.Exit(1)
        result = c.list_tables(bid)
        rows = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Tables", columns=["id", "title", "type", "meta"])
        else:
            print_json(result, title="Tables")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@tables_app.command("create")
def tables_create(
    base_id: str | None = typer.Option(None, "--base-id", help="NocoDB base ID."),
    schema: str = typer.Option(..., "--schema", help="Table schema as JSON string."),
) -> None:
    """Create a new table from a JSON schema definition."""
    try:
        c = _client()
        bid = base_id or c._base_id
        if not bid:
            print_error(
                "No base ID provided and none configured.",
                hint="Set NOCODB_BASE_ID or pass --base-id.",
            )
            raise typer.Exit(1)
        schema_data = json.loads(schema)
        result = c.create_table(bid, schema_data)
        print_success(f"Table created: {result.get('id', '')}")
        print_json(result)
    except json.JSONDecodeError as exc:
        print_error(f"Invalid JSON schema: {exc}")
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@tables_app.command("delete")
def tables_delete(
    table_id: str = typer.Argument(..., help="Table ID to delete."),
) -> None:
    """Delete a NocoDB table."""
    try:
        _client().delete_table(table_id)
        print_success(f"Table {table_id} deleted.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Bases (meta)
# ======================================================================


@bases_app.command("list")
def bases_list() -> None:
    """List all NocoDB bases."""
    try:
        result = _client().get_bases()
        rows = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Bases", columns=["id", "title", "type"])
        else:
            print_json(result, title="Bases")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Health
# ======================================================================


@app.command()
def health() -> None:
    """Check NocoDB connectivity."""
    from copilot_cli.shared.output import print_health

    result = _client().health()
    healthy = result.get("healthy", False)
    print_health("nocodb", healthy, result if not healthy else None)
    if not healthy:
        raise typer.Exit(1)
