"""Secret management commands for Infisical.

Values are intentionally NOT printed in list output. Use `secret get` to
retrieve a specific value explicitly.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(help="Manage Infisical secrets.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.infisical.main import handle_error, run_async, state

    return state, run_async, handle_error


def _require_project(state, project: str) -> str:
    project_id = project or state.default_project
    if not project_id:
        from copilot_cli.services.coolify.output.console import err_console

        err_console.print("[error]--project is required.[/error]")
        raise typer.Exit(1)
    return project_id


@app.command("list")
def list_secrets(
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Secret path")] = "/",
) -> None:
    """List secrets (keys only — use `secret get` to see a value)."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = _require_project(state, project)
        secrets = run_async(client.list_secrets(project_id, env, path))

        if state.is_json():
            # Strip values from JSON output too unless --show-values
            safe = [{k: v for k, v in s.items() if k != "secretValue"} for s in secrets]
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(safe, state.output_format)
            return

        from copilot_cli.services.coolify.output.console import console

        if not secrets:
            console.print("[dim]No secrets found.[/dim]")
            return

        table = Table(title=f"Secrets — {env}:{path}")
        table.add_column("Key", style="bold")
        table.add_column("Type")
        table.add_column("Updated")

        for s in secrets:
            table.add_row(
                s.get("secretKey", ""),
                s.get("type", ""),
                s.get("updatedAt", "")[:10],
            )

        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_secret(
    key: Annotated[str, typer.Argument(help="Secret key name")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Secret path")] = "/",
) -> None:
    """Get a secret value (explicitly requested — value is shown)."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = _require_project(state, project)
        secret = run_async(client.get_secret(project_id, env, key, path))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(secret, state.output_format)
            return

        from rich.panel import Panel

        from copilot_cli.services.coolify.output.console import console

        lines = [
            f"[label]Key:[/label]     {secret.get('secretKey', key)}",
            f"[label]Value:[/label]   {secret.get('secretValue', '')}",
            f"[label]Type:[/label]    {secret.get('type', '')}",
            f"[label]Path:[/label]    {secret.get('secretPath', path)}",
            f"[label]Updated:[/label] {secret.get('updatedAt', '')[:19]}",
        ]
        console.print(Panel("\n".join(lines), title=f"Secret: {key}"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("set")
def set_secret(
    key: Annotated[str, typer.Argument(help="Secret key name")],
    value: Annotated[str, typer.Argument(help="Secret value")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Secret path")] = "/",
) -> None:
    """Create or update a secret value."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = _require_project(state, project)

        # Try update first; fall back to create if not found
        try:
            run_async(client.update_secret(project_id, env, key, value, path))
            action = "updated"
        except Exception as update_err:
            # If the secret doesn't exist, create it
            err_str = str(update_err).lower()
            if "not found" in err_str or "404" in err_str or "secret not found" in err_str:
                run_async(client.create_secret(project_id, env, key, value, path))
                action = "created"
            else:
                raise

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data({"key": key, "action": action}, state.output_format)
            return

        from copilot_cli.services.coolify.output.console import console

        console.print(f"[success]Secret {action}:[/success] {key}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_secret(
    key: Annotated[str, typer.Argument(help="Secret key name")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "dev",
    path: Annotated[str, typer.Option("--path", help="Secret path")] = "/",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a secret."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        project_id = _require_project(state, project)

        if not force:
            if not typer.confirm(f"Delete secret '{key}' in {env}:{path}?"):
                raise typer.Abort()

        run_async(client.delete_secret(project_id, env, key, path))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data({"key": key, "deleted": True}, state.output_format)
            return

        from copilot_cli.services.coolify.output.console import console

        console.print(f"[success]Secret deleted:[/success] {key}")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
