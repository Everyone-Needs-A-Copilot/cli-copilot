"""Project management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage Coolify projects.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_projects() -> None:
    """List all projects."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        projects = run_async(client.list_projects())
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(projects, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import project_table

            if not projects:
                console.print("[dim]No projects found.[/dim]")
                return
            console.print(project_table(projects))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_project(
    query: Annotated[str, typer.Argument(help="Project UUID or name")],
) -> None:
    """Get detailed project information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        uuid = run_async(resolve_project(client, query))
        project = run_async(client.get_project(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(project, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import project_detail_panel

            console.print(project_detail_panel(project))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_project(
    name: Annotated[str, typer.Argument(help="Project name")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Description")] = "",
) -> None:
    """Create a new project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        data = {"name": name}
        if description:
            data["description"] = description
        result = run_async(client.create_project(data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            uuid = result.get("uuid", "")
            console.print(f"[success]Project created:[/success] {uuid}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("update")
def update_project(
    query: Annotated[str, typer.Argument(help="Project UUID or name")],
    name: Annotated[str, typer.Option("--name", help="New name")] = "",
    description: Annotated[str, typer.Option("--desc", "-d", help="New description")] = "",
) -> None:
    """Update a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        uuid = run_async(resolve_project(client, query))
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if not data:
            console.print("[warning]No fields to update.[/warning]")
            return
        result = run_async(client.update_project(uuid, data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Project updated.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_project(
    query: Annotated[str, typer.Argument(help="Project UUID or name")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        uuid = run_async(resolve_project(client, query))
        if not force:
            project = run_async(client.get_project(uuid))
            name = project.get("name", uuid)
            if not typer.confirm(f"Delete project '{name}' ({uuid})?"):
                raise typer.Abort()
        result = run_async(client.delete_project(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Project deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
