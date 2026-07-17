"""GitHub App management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage GitHub Apps.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_github_apps() -> None:
    """List all GitHub Apps."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        apps = run_async(client.list_github_apps())
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(apps, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import github_app_table

            if not apps:
                console.print("[dim]No GitHub Apps found.[/dim]")
                return
            console.print(github_app_table(apps))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_github_app(
    app_id: Annotated[int, typer.Argument(help="GitHub App ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a GitHub App."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        if not force:
            if not typer.confirm(f"Delete GitHub App {app_id}?"):
                raise typer.Abort()
        result = run_async(client.delete_github_app(app_id))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]GitHub App deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
