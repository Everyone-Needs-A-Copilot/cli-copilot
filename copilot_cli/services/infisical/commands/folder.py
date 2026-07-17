"""Folder management commands for Infisical."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(help="Manage Infisical secret folders.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.infisical.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_folders(
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug (e.g. dev)")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Folder path")] = "/",
) -> None:
    """List folders in a project environment."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = project or state.default_project
        if not project_id:
            from copilot_cli.services.coolify.output.console import err_console

            err_console.print("[error]--project is required.[/error]")
            raise typer.Exit(1)

        folders = run_async(client.list_folders(project_id, env, path))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(folders, state.output_format)
            return

        from copilot_cli.services.coolify.output.console import console

        if not folders:
            console.print("[dim]No folders found.[/dim]")
            return

        table = Table(title=f"Folders — {env}:{path}")
        table.add_column("ID", style="uuid")
        table.add_column("Name", style="bold")
        table.add_column("Path")
        table.add_column("Created")

        for f in folders:
            table.add_row(
                f.get("id", ""),
                f.get("name", ""),
                f.get("path", ""),
                f.get("createdAt", "")[:10],
            )

        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_folder(
    name: Annotated[str, typer.Argument(help="Folder name")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Parent path")] = "/",
) -> None:
    """Create a folder in a project environment."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = project or state.default_project
        if not project_id:
            from copilot_cli.services.coolify.output.console import err_console

            err_console.print("[error]--project is required.[/error]")
            raise typer.Exit(1)

        folder = run_async(client.create_folder(project_id, env, name, path))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(folder, state.output_format)
            return

        from copilot_cli.services.coolify.output.console import console

        console.print(
            f"[success]Folder created:[/success] {folder.get('path', path + '/' + name)} "
            f"[uuid]({folder.get('id', '')})[/uuid]"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
