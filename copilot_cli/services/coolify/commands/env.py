"""Project environment management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage project environments.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_envs(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
) -> None:
    """List environments in a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))
        envs = run_async(client.list_environments(project_uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(envs, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import environment_table

            if not envs:
                console.print("[dim]No environments found.[/dim]")
                return
            console.print(environment_table(envs))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_env(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
    environment: Annotated[str, typer.Argument(help="Environment name or UUID")],
) -> None:
    """Get environment details."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))
        env = run_async(client.get_environment(project_uuid, environment))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(env, state.output_format)
        else:
            from rich.panel import Panel
            from rich.table import Table

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="label", width=15)
            table.add_column("Value")
            for key in ("name", "uuid", "description", "created_at", "updated_at"):
                table.add_row(key, str(env.get(key, "—")))
            console.print(Panel(table, title="Environment", border_style="cyan"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_env(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
    name: Annotated[str, typer.Argument(help="Environment name")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Description")] = "",
) -> None:
    """Create a new environment in a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))
        data = {"name": name}
        if description:
            data["description"] = description
        result = run_async(client.create_environment(project_uuid, data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print(f"[success]Environment '{name}' created.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_env(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
    environment: Annotated[str, typer.Argument(help="Environment name or UUID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete an environment from a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))
        if not force:
            if not typer.confirm(f"Delete environment '{environment}'?"):
                raise typer.Abort()
        result = run_async(client.delete_environment(project_uuid, environment))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Environment deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
