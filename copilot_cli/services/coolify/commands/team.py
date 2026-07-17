"""Team management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage teams.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_teams() -> None:
    """List all teams."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        teams = run_async(client.list_teams())
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(teams, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import team_table

            if not teams:
                console.print("[dim]No teams found.[/dim]")
                return
            console.print(team_table(teams))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_team(
    team_id: Annotated[int, typer.Argument(help="Team ID")],
) -> None:
    """Get team details."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        team = run_async(client.get_team(team_id))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(team, state.output_format)
        else:
            from rich.panel import Panel
            from rich.table import Table

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="label", width=15)
            table.add_column("Value")
            table.add_row("ID", str(team.get("id", "")))
            table.add_row("Name", team.get("name", ""))
            table.add_row("Description", team.get("description") or "—")
            table.add_row("Personal", str(team.get("personal_team", False)))
            console.print(Panel(table, title="Team", border_style="cyan"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("members")
def team_members(
    team_id: Annotated[int, typer.Argument(help="Team ID")],
) -> None:
    """List team members."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        members = run_async(client.get_team_members(team_id))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(members, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import team_member_table

            if not members:
                console.print("[dim]No members found.[/dim]")
                return
            console.print(team_member_table(members))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("current")
def current_team() -> None:
    """Show current team."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        team = run_async(client.get_current_team())
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(team, state.output_format)
        else:
            from rich.panel import Panel
            from rich.table import Table

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="label", width=15)
            table.add_column("Value")
            table.add_row("ID", str(team.get("id", "")))
            table.add_row("Name", team.get("name", ""))
            table.add_row("Description", team.get("description") or "—")
            console.print(Panel(table, title="Current Team", border_style="cyan"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
