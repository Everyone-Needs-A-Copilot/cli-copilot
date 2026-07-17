"""Application management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage Coolify applications.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_apps() -> None:
    """List all applications."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        apps = run_async(client.list_applications())

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(apps, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import application_table

            if not apps:
                console.print("[dim]No applications found.[/dim]")
                return
            console.print(application_table(apps))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Get detailed application information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        application = run_async(client.get_application(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(application, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import application_detail_panel

            console.print(application_detail_panel(application))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("logs")
def app_logs(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of log lines")] = 100,
) -> None:
    """View application logs."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        logs = run_async(client.get_application_logs(uuid, lines))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(logs, state.output_format)
        else:
            if isinstance(logs, str):
                console.print(logs)
            elif isinstance(logs, dict):
                # Some APIs return logs in a dict
                log_text = logs.get("logs", str(logs))
                console.print(log_text)
            elif isinstance(logs, list):
                for entry in logs:
                    console.print(str(entry))
            else:
                console.print(str(logs))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("start")
def start_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Start an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        result = run_async(client.start_application(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Application start initiated")
            dep_uuid = result.get("deployment_uuid", "")
            console.print(f"[success]{msg}[/success]")
            if dep_uuid:
                console.print(f"[dim]Deployment UUID: {dep_uuid}[/dim]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("stop")
def stop_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Stop an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        result = run_async(client.stop_application(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Application stop initiated")
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("restart")
def restart_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Restart an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        result = run_async(client.restart_application(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Application restart initiated")
            dep_uuid = result.get("deployment_uuid", "")
            console.print(f"[success]{msg}[/success]")
            if dep_uuid:
                console.print(f"[dim]Deployment UUID: {dep_uuid}[/dim]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    delete_volumes: Annotated[
        bool, typer.Option("--delete-volumes", help="Also delete volumes")
    ] = False,
    docker_cleanup: Annotated[
        bool, typer.Option("--docker-cleanup", help="Run docker cleanup")
    ] = False,
) -> None:
    """Delete an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))

        if not force:
            # Show what we're about to delete
            application = run_async(client.get_application(uuid))
            name = application.get("name", uuid)
            if not typer.confirm(f"Delete application '{name}' ({uuid})?"):
                raise typer.Abort()

        result = run_async(
            client.delete_application(
                uuid,
                delete_volumes=delete_volumes,
                docker_cleanup=docker_cleanup,
            )
        )

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Application deleted")
            console.print(f"[success]{msg}[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
