"""Database management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage Coolify databases.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_databases() -> None:
    """List all databases."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        dbs = run_async(client.list_databases())

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(dbs, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import database_table

            if not dbs:
                console.print("[dim]No databases found.[/dim]")
                return
            console.print(database_table(dbs))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_database(
    query: Annotated[str, typer.Argument(help="Database UUID or name")],
) -> None:
    """Get detailed database information."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        uuid = run_async(resolve_database(client, query))
        db = run_async(client.get_database(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(db, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import database_detail_panel

            console.print(database_detail_panel(db))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("start")
def start_database(
    query: Annotated[str, typer.Argument(help="Database UUID or name")],
) -> None:
    """Start a database."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        uuid = run_async(resolve_database(client, query))
        result = run_async(client.start_database(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Database start initiated")
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("stop")
def stop_database(
    query: Annotated[str, typer.Argument(help="Database UUID or name")],
) -> None:
    """Stop a database."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        uuid = run_async(resolve_database(client, query))
        result = run_async(client.stop_database(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Database stop initiated")
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("restart")
def restart_database(
    query: Annotated[str, typer.Argument(help="Database UUID or name")],
) -> None:
    """Restart a database."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        uuid = run_async(resolve_database(client, query))
        result = run_async(client.restart_database(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = result.get("message", "Database restart initiated")
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_database(
    query: Annotated[str, typer.Argument(help="Database UUID or name")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    delete_volumes: Annotated[
        bool, typer.Option("--delete-volumes", help="Also delete volumes")
    ] = False,
) -> None:
    """Delete a database."""
    console.print(
        "[error]Refused: the cli-copilot tool is not permitted to delete remote "
        "Coolify-managed databases. This is a hardcoded policy; remove databases "
        "via the Coolify UI if truly needed.[/error]"
    )
    raise typer.Exit(1)
