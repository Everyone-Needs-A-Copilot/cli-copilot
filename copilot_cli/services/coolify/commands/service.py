"""Service management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage Coolify services.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_services() -> None:
    """List all services."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        services = run_async(client.list_services())

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(services, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import service_table

            if not services:
                console.print("[dim]No services found.[/dim]")
                return
            console.print(service_table(services))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_service(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
) -> None:
    """Get detailed service information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))
        service = run_async(client.get_service(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(service, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import service_detail_panel

            console.print(service_detail_panel(service))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("start")
def start_service(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
) -> None:
    """Start a service."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))
        result = run_async(client.start_service(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Service start initiated")
                if isinstance(result, dict)
                else "Service start initiated"
            )
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("stop")
def stop_service(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
) -> None:
    """Stop a service."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))
        result = run_async(client.stop_service(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Service stop initiated")
                if isinstance(result, dict)
                else "Service stop initiated"
            )
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("restart")
def restart_service(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
) -> None:
    """Restart a service."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))
        result = run_async(client.restart_service(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Service restart initiated")
                if isinstance(result, dict)
                else "Service restart initiated"
            )
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("logs")
def service_logs(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of log lines")] = 100,
    container: Annotated[str, typer.Option("--container", "-c", help="Specific container")] = "",
) -> None:
    """View service container logs (requires SSH)."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))

        # Get SSH client
        from copilot_cli.services.coolify.commands.monitor import _get_ssh_client

        ssh = _get_ssh_client()
        if not ssh:
            console.print(
                "[error]SSH not configured. Service logs require SSH access.[/error]\n"
                "[dim]Run 'coolify config init' to set up SSH.[/dim]"
            )
            raise typer.Exit(1)

        from copilot_cli.services.coolify.monitoring.service_containers import (
            discover_service_containers,
            get_all_service_logs,
            get_service_container_logs,
        )

        with ssh:
            if container:
                # Specific container
                log_text = get_service_container_logs(ssh, container, lines)
                if not log_text:
                    console.print(f"[dim]No logs found for container '{container}'.[/dim]")
                    return

                if state.is_json():
                    from copilot_cli.services.coolify.output.json_out import output_data

                    output_data({"container": container, "logs": log_text}, state.output_format)
                else:
                    from rich.panel import Panel

                    console.print(Panel(log_text, title=f"Logs: {container}", border_style="cyan"))
            else:
                # All containers in the service
                containers = discover_service_containers(ssh, uuid)
                if not containers:
                    console.print("[dim]No containers found for this service.[/dim]")
                    return

                all_logs = get_all_service_logs(ssh, uuid, lines)

                if state.is_json():
                    from copilot_cli.services.coolify.output.json_out import output_data

                    output_data(
                        {
                            "service_uuid": uuid,
                            "containers": [
                                {
                                    "name": c.name,
                                    "component": c.service_component,
                                    "status": c.status,
                                }
                                for c in containers
                            ],
                            "logs": all_logs,
                        },
                        state.output_format,
                    )
                else:
                    from rich.panel import Panel

                    console.print(f"[bold]Service containers ({len(containers)}):[/bold]")
                    for c in containers:
                        console.print(f"  {c.service_component} ({c.name}): {c.status}")

                    for name, log_text in all_logs.items():
                        console.print(
                            Panel(
                                log_text[-2000:] if len(log_text) > 2000 else log_text,
                                title=f"Logs: {name}",
                                border_style="cyan",
                            )
                        )
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_service(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    delete_volumes: Annotated[
        bool, typer.Option("--delete-volumes", help="Also delete volumes")
    ] = False,
) -> None:
    """Delete a service."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_service

        uuid = run_async(resolve_service(client, query))

        if not force:
            service = run_async(client.get_service(uuid))
            name = service.get("name", uuid)
            if not typer.confirm(f"Delete service '{name}' ({uuid})?"):
                raise typer.Abort()

        result = run_async(client.delete_service(uuid, delete_volumes=delete_volumes))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Service deleted")
                if isinstance(result, dict)
                else "Service deleted"
            )
            console.print(f"[success]{msg}[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_service(
    type_: Annotated[
        str, typer.Option("--type", help="Service type (e.g. minio-community-edition)")
    ],
    name: Annotated[str, typer.Option("--name", help="Human-friendly service name")],
    project: Annotated[str, typer.Option("--project", help="Project UUID")],
    environment: Annotated[str, typer.Option("--environment", help="Environment UUID")],
    server: Annotated[
        str | None, typer.Option("--server", help="Server UUID (defaults to localhost)")
    ] = None,
    compose: Annotated[
        str | None, typer.Option("--compose", help="Path to docker-compose override file")
    ] = None,
) -> None:
    """Create a new service."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()

        # Resolve server UUID — default to localhost if not specified
        server_uuid = server
        if not server_uuid:
            servers = run_async(client.list_servers())
            if servers:
                server_uuid = servers[0].get("uuid", "")
            if not server_uuid:
                console.print("[error]No server found. Specify --server UUID.[/error]")
                raise typer.Exit(1)

        data: dict = {
            "type": type_,
            "name": name,
            "project_uuid": project,
            "environment_name": environment,
            "server_uuid": server_uuid,
        }

        if compose is not None:
            import pathlib

            compose_path = pathlib.Path(compose)
            if not compose_path.is_file():
                console.print(f"[error]Compose file not found: {compose}[/error]")
                raise typer.Exit(1)
            data["docker_compose_raw"] = compose_path.read_text()

        result = run_async(client.create_service(data))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Service created")
                if isinstance(result, dict)
                else "Service created"
            )
            uuid = result.get("uuid", "") if isinstance(result, dict) else ""
            console.print(f"[success]{msg}[/success]")
            if uuid:
                console.print(f"[dim]UUID: {uuid}[/dim]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
