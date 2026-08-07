"""Organisation-level admin commands for Infisical."""

from __future__ import annotations

import typer

app = typer.Typer(help="Organisation admin commands.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.infisical.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("disable-signup")
def disable_signup(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Disable open registration (requires super-admin).

    Note: this endpoint requires super-admin privileges. The machine identity
    used for API auth must be listed in adminIdentityIds in the admin config.
    """
    state, run_async, handle_error = _get_deps()
    try:
        from copilot_cli.services.infisical.output.console import console

        # Show current state first
        client = state.get_client()
        config = run_async(client.get_admin_config())
        current = config.get("allowSignUp", None)
        console.print(f"[label]Current allowSignUp:[/label] {current}")

        if current is False:
            console.print("[success]Open signup is already disabled.[/success]")
            return

        if not force and not typer.confirm("Disable open signup?"):
            raise typer.Abort()

        result = run_async(client.update_admin_config(allowSignUp=False))

        if state.is_json():
            from copilot_cli.services.infisical.output.json_out import output_data

            output_data(result, state.output_format)
            return

        console.print("[success]Open signup disabled.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
