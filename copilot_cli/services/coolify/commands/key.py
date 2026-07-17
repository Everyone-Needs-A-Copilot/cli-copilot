"""Private key management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage SSH private keys.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_keys() -> None:
    """List all private keys."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        keys = run_async(client.list_private_keys())
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(keys, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import private_key_table

            if not keys:
                console.print("[dim]No private keys found.[/dim]")
                return
            console.print(private_key_table(keys))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_key(
    uuid: Annotated[str, typer.Argument(help="Key UUID")],
) -> None:
    """Get private key details."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        key = run_async(client.get_private_key(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(key, state.output_format)
        else:
            from rich.panel import Panel
            from rich.table import Table

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="label", width=15)
            table.add_column("Value")
            table.add_row("Name", key.get("name", ""))
            table.add_row("UUID", key.get("uuid", ""))
            table.add_row("Description", key.get("description") or "—")
            table.add_row("Fingerprint", key.get("fingerprint") or "—")
            table.add_row("Git Related", str(key.get("is_git_related", False)))
            console.print(Panel(table, title="Private Key", border_style="cyan"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_key(
    name: Annotated[str, typer.Argument(help="Key name")],
    key_file: Annotated[str, typer.Argument(help="Path to private key file")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Description")] = "",
) -> None:
    """Create a private key from a file."""
    state, run_async, handle_error = _get_deps()
    try:
        from pathlib import Path

        client = state.get_client()
        key_path = Path(key_file)
        if not key_path.exists():
            console.print(f"[error]Key file not found: {key_file}[/error]")
            raise typer.Exit(1)
        private_key = key_path.read_text()
        data = {"name": name, "private_key": private_key}
        if description:
            data["description"] = description
        result = run_async(client.create_private_key(data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            uuid = result.get("uuid", "")
            console.print(f"[success]Private key created:[/success] {uuid}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_key(
    uuid: Annotated[str, typer.Argument(help="Key UUID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a private key."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        if not force:
            if not typer.confirm(f"Delete private key {uuid}?"):
                raise typer.Abort()
        result = run_async(client.delete_private_key(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Private key deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
