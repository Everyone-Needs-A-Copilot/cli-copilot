"""Server management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage Coolify servers.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_servers() -> None:
    """List all servers."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        servers = run_async(client.list_servers())

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(servers, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import server_table

            if not servers:
                console.print("[dim]No servers found.[/dim]")
                return
            console.print(server_table(servers))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_server(
    query: Annotated[str, typer.Argument(help="Server UUID, name, or IP address")],
) -> None:
    """Get detailed server information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_server

        uuid = run_async(resolve_server(client, query))
        server = run_async(client.get_server(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(server, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import server_detail_panel

            console.print(server_detail_panel(server))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("resources")
def server_resources(
    query: Annotated[str, typer.Argument(help="Server UUID, name, or IP address")],
) -> None:
    """List resources on a server."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_server

        uuid = run_async(resolve_server(client, query))
        resources = run_async(client.get_server_resources(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(resources, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import server_resource_table

            if not resources:
                console.print("[dim]No resources found on this server.[/dim]")
                return
            console.print(server_resource_table(resources))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("domains")
def server_domains(
    query: Annotated[str, typer.Argument(help="Server UUID, name, or IP address")],
) -> None:
    """List domains configured on a server."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_server

        uuid = run_async(resolve_server(client, query))
        domains = run_async(client.get_server_domains(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(domains, state.output_format)
        else:
            from rich.table import Table

            table = Table(title="Server Domains", show_lines=False)
            table.add_column("IP", style="bold")
            table.add_column("Domains")
            for d in domains:
                ip = d.get("ip", "")
                domain_list = d.get("domains", [])
                table.add_row(ip, "\n".join(domain_list) if domain_list else "\u2014")
            console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("validate")
def validate_server(
    query: Annotated[str, typer.Argument(help="Server UUID, name, or IP address")],
) -> None:
    """Validate server connection."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_server

        uuid = run_async(resolve_server(client, query))
        result = run_async(client.validate_server(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "")
            logs = result.get("validation_logs")
            console.print(f"[success]{msg}[/success]")
            if logs:
                console.print(f"\n[dim]{logs}[/dim]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
