"""Machine identity management commands for Infisical."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(help="Manage Infisical machine identities.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.infisical.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_identities() -> None:
    """List all machine identities in the organisation."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        org_id = run_async(client.get_org_id(state.org_id))
        if not org_id:
            from copilot_cli.services.infisical.output.console import err_console

            err_console.print("[error]Could not determine organisation ID.[/error]")
            raise typer.Exit(1)

        identities = run_async(client.list_identities(org_id))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(identities, state.output_format)
            return

        from copilot_cli.services.infisical.output.console import console

        if not identities:
            console.print("[dim]No identities found.[/dim]")
            return

        table = Table(title="Machine Identities")
        table.add_column("Identity ID", style="uuid")
        table.add_column("Name", style="bold")
        table.add_column("Role")
        table.add_column("Auth Methods")
        table.add_column("Last Login")

        for m in identities:
            ident = m.get("identity", {})
            table.add_row(
                ident.get("id", m.get("identityId", "")),
                ident.get("name", ""),
                m.get("role", ""),
                ", ".join(ident.get("authMethods", [])),
                (m.get("lastLoginTime") or "")[:10],
            )

        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_identity(
    name: Annotated[str, typer.Argument(help="Identity name")],
    role: Annotated[
        str, typer.Option("--role", "-r", help="Org role (admin, member, viewer)")
    ] = "member",
) -> None:
    """Create a new machine identity in the organisation."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        org_id = run_async(client.get_org_id(state.org_id))
        if not org_id:
            from copilot_cli.services.infisical.output.console import err_console

            err_console.print("[error]Could not determine organisation ID.[/error]")
            raise typer.Exit(1)

        identity = run_async(client.create_identity(name, org_id, role))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(identity, state.output_format)
            return

        from copilot_cli.services.infisical.output.console import console

        console.print(
            f"[success]Identity created:[/success] {identity.get('name', name)} "
            f"[uuid]({identity.get('id', '')})[/uuid]"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
