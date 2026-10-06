"""Project management commands for Infisical."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(help="Manage Infisical projects.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.infisical.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_projects() -> None:
    """List all projects."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        projects = run_async(client.list_projects())

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(projects, state.output_format)
            return

        from copilot_cli.services.infisical.output.console import console

        if not projects:
            console.print("[dim]No projects found.[/dim]")
            return

        table = Table(title="Infisical Projects")
        table.add_column("ID", style="uuid")
        table.add_column("Name", style="bold")
        table.add_column("Slug")
        table.add_column("Environments")
        table.add_column("Created")

        for p in projects:
            envs = ", ".join(e.get("slug", "") for e in p.get("environments", []))
            table.add_row(
                p.get("id", ""),
                p.get("name", ""),
                p.get("slug", ""),
                envs,
                p.get("createdAt", "")[:10],
            )

        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_project(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
) -> None:
    """Get detailed project information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project = run_async(client.get_project(project_id))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(project, state.output_format)
            return

        from rich.panel import Panel

        from copilot_cli.services.infisical.output.console import console

        lines = [
            f"[label]ID:[/label]          {project.get('id', '')}",
            f"[label]Name:[/label]        {project.get('name', '')}",
            f"[label]Slug:[/label]        {project.get('slug', '')}",
            f"[label]Org ID:[/label]      {project.get('orgId', '')}",
            f"[label]Created:[/label]     {project.get('createdAt', '')[:19]}",
        ]
        envs = project.get("environments", [])
        if envs:
            lines.append(
                f"[label]Environments:[/label] {', '.join(e.get('slug', '') for e in envs)}"
            )

        console.print(Panel("\n".join(lines), title=f"Project: {project.get('name', project_id)}"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_project(
    name: Annotated[str, typer.Argument(help="Project name")],
) -> None:
    """Create a new project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_write_client()
        org_id = run_async(client.get_org_id(state.org_id))
        if not org_id:
            from copilot_cli.services.infisical.output.console import err_console

            err_console.print("[error]Could not determine organisation ID.[/error]")
            raise typer.Exit(1)

        project = run_async(client.create_project(name, org_id))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(project, state.output_format)
            return

        from copilot_cli.services.infisical.output.console import console

        console.print(
            f"[success]Project created:[/success] {project.get('name', name)} "
            f"[uuid]({project.get('id', '')})[/uuid]"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_project(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_write_client()
        if not force:
            project = run_async(client.get_project(project_id))
            name = project.get("name", project_id)
            if not typer.confirm(f"Delete project '{name}' ({project_id})?"):
                raise typer.Abort()

        result = run_async(client.delete_project(project_id))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(result, state.output_format)
            return

        from copilot_cli.services.infisical.output.console import console

        console.print("[success]Project deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
