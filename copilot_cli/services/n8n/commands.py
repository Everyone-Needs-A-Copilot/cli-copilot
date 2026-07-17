"""Typer subcommand group for n8n workflow automation operations."""

from __future__ import annotations

import json

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(no_args_is_help=True)
workflows_app = typer.Typer(no_args_is_help=True, help="n8n workflow operations.")
executions_app = typer.Typer(no_args_is_help=True, help="n8n execution operations.")

app.add_typer(workflows_app, name="workflows")
app.add_typer(executions_app, name="executions")


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.n8n.client import N8nClient

    return N8nClient()


# ------------------------------------------------------------------
# Workflows
# ------------------------------------------------------------------


@workflows_app.command("list")
def workflows_list(
    limit: int = typer.Option(250, "--limit", "-n", help="Max workflows to return."),
    active: bool | None = typer.Option(None, "--active/--inactive", help="Filter by active state."),
) -> None:
    """List n8n workflows."""
    try:
        result = _client().list_workflows(limit=limit, active=active)
        data = result.get("data", []) if isinstance(result, dict) else []
        rows = [
            {
                "id": str(w.get("id", "")),
                "name": w.get("name", ""),
                "active": str(w.get("active", "")),
                "createdAt": w.get("createdAt", ""),
                "updatedAt": w.get("updatedAt", ""),
            }
            for w in data
        ]
        print_table(
            rows,
            title="n8n Workflows",
            columns=["id", "name", "active", "createdAt", "updatedAt"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@workflows_app.command("get")
def workflows_get(
    id: str = typer.Argument(..., help="Workflow ID."),
) -> None:
    """Retrieve a single n8n workflow."""
    try:
        result = _client().get_workflow(id=id)
        print_json(result, title=f"Workflow {id}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@workflows_app.command("create")
def workflows_create(
    data: str = typer.Option(..., "--data", "-d", help="Workflow definition as a JSON string."),
) -> None:
    """Create a new n8n workflow."""
    try:
        payload = json.loads(data)
        result = _client().create_workflow(data=payload)
        print_json(result, title="Created Workflow")
    except json.JSONDecodeError as exc:
        print_error(f"Invalid JSON in --data: {exc}")
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@workflows_app.command("activate")
def workflows_activate(
    id: str = typer.Argument(..., help="Workflow ID."),
) -> None:
    """Activate an n8n workflow."""
    try:
        result = _client().activate_workflow(id=id)
        print_success(f"Workflow {id} activated (active={result.get('active', True)})")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@workflows_app.command("deactivate")
def workflows_deactivate(
    id: str = typer.Argument(..., help="Workflow ID."),
) -> None:
    """Deactivate an n8n workflow."""
    try:
        result = _client().deactivate_workflow(id=id)
        print_success(f"Workflow {id} deactivated (active={result.get('active', False)})")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@workflows_app.command("delete")
def workflows_delete(
    id: str = typer.Argument(..., help="Workflow ID."),
) -> None:
    """Delete an n8n workflow."""
    try:
        _client().delete_workflow(id=id)
        print_success(f"Workflow {id} deleted")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ------------------------------------------------------------------
# Executions
# ------------------------------------------------------------------


@executions_app.command("list")
def executions_list(
    workflow_id: str | None = typer.Option(
        None, "--workflow-id", "-w", help="Filter by workflow ID."
    ),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by status (success, error, waiting)."
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max executions to return."),
) -> None:
    """List n8n workflow executions."""
    try:
        result = _client().list_executions(workflow_id=workflow_id, status=status, limit=limit)
        data = result.get("data", []) if isinstance(result, dict) else []
        rows = [
            {
                "id": str(e.get("id", "")),
                "workflowId": str(e.get("workflowId", e.get("workflowData", {}).get("id", ""))),
                "status": e.get("status", e.get("finished", "")),
                "startedAt": e.get("startedAt", ""),
                "stoppedAt": e.get("stoppedAt", ""),
            }
            for e in data
        ]
        print_table(
            rows,
            title="n8n Executions",
            columns=["id", "workflowId", "status", "startedAt", "stoppedAt"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@executions_app.command("get")
def executions_get(
    id: str = typer.Argument(..., help="Execution ID."),
) -> None:
    """Retrieve a single n8n execution."""
    try:
        result = _client().get_execution(id=id)
        print_json(result, title=f"Execution {id}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@app.command()
def health() -> None:
    """Check n8n API health."""
    try:
        result = _client().health()
        is_healthy = result.get("healthy", False)
        print_health("n8n", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success("n8n API is reachable")
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
