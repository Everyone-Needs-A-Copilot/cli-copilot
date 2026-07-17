"""Environment variable management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage environment variables on apps/services.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_envvars(
    resource: Annotated[str, typer.Argument(help="App or service UUID/name")],
    resource_type: Annotated[
        str, typer.Option("--type", "-t", help="Resource type: app or service")
    ] = "app",
) -> None:
    """List environment variables."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        if resource_type == "service":
            from copilot_cli.services.coolify.core.resolver import resolve_service

            uuid = run_async(resolve_service(client, resource))
            envvars = run_async(client.list_service_envvars(uuid))
        else:
            from copilot_cli.services.coolify.core.resolver import resolve_application

            uuid = run_async(resolve_application(client, resource))
            envvars = run_async(client.list_app_envvars(uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(envvars, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import envvar_table

            if not envvars:
                console.print("[dim]No environment variables found.[/dim]")
                return
            console.print(envvar_table(envvars))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_envvar(
    resource: Annotated[str, typer.Argument(help="App or service UUID/name")],
    key: Annotated[str, typer.Argument(help="Variable key")],
    value: Annotated[str, typer.Argument(help="Variable value")],
    resource_type: Annotated[
        str, typer.Option("--type", "-t", help="Resource type: app or service")
    ] = "app",
    build_time: Annotated[bool, typer.Option("--build-time", help="Build-time variable")] = False,
    preview: Annotated[bool, typer.Option("--preview", help="Preview variable")] = False,
) -> None:
    """Create an environment variable."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        data: dict[str, object] = {"key": key, "value": value}
        if build_time:
            data["is_build_time"] = True
        if preview:
            data["is_preview"] = True
        if resource_type == "service":
            from copilot_cli.services.coolify.core.resolver import resolve_service

            uuid = run_async(resolve_service(client, resource))
            result = run_async(client.create_service_envvar(uuid, data))
        else:
            from copilot_cli.services.coolify.core.resolver import resolve_application

            uuid = run_async(resolve_application(client, resource))
            result = run_async(client.create_app_envvar(uuid, data))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print(f"[success]Environment variable '{key}' created.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("update")
def update_envvar(
    resource: Annotated[str, typer.Argument(help="App or service UUID/name")],
    key: Annotated[str, typer.Argument(help="Variable key")],
    value: Annotated[str, typer.Argument(help="New value")],
    resource_type: Annotated[
        str, typer.Option("--type", "-t", help="Resource type: app or service")
    ] = "app",
    build_time: Annotated[bool, typer.Option("--build-time", help="Build-time variable")] = False,
) -> None:
    """Update an environment variable."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        data: dict[str, object] = {"key": key, "value": value}
        if build_time:
            data["is_build_time"] = True
        if resource_type == "service":
            from copilot_cli.services.coolify.core.resolver import resolve_service

            uuid = run_async(resolve_service(client, resource))
            result = run_async(client.update_service_envvar(uuid, data))
        else:
            from copilot_cli.services.coolify.core.resolver import resolve_application

            uuid = run_async(resolve_application(client, resource))
            result = run_async(client.update_app_envvar(uuid, data))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print(f"[success]Environment variable '{key}' updated.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_envvar(
    resource: Annotated[str, typer.Argument(help="App or service UUID/name")],
    env_uuid: Annotated[str, typer.Argument(help="Env var UUID to delete")],
    resource_type: Annotated[
        str, typer.Option("--type", "-t", help="Resource type: app or service")
    ] = "app",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete an environment variable."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        if not force:
            if not typer.confirm(f"Delete environment variable {env_uuid}?"):
                raise typer.Abort()

        if resource_type == "service":
            from copilot_cli.services.coolify.core.resolver import resolve_service

            uuid = run_async(resolve_service(client, resource))
            result = run_async(client.delete_service_envvar(uuid, env_uuid))
        else:
            from copilot_cli.services.coolify.core.resolver import resolve_application

            uuid = run_async(resolve_application(client, resource))
            result = run_async(client.delete_app_envvar(uuid, env_uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Environment variable deleted.[/success]")
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)


@app.command("bulk")
def bulk_update(
    resource: Annotated[str, typer.Argument(help="App UUID/name")],
    env_file: Annotated[str, typer.Argument(help="Path to .env file")],
) -> None:
    """Bulk update env vars from a .env file."""
    state, run_async, handle_error = _get_deps()
    try:
        from pathlib import Path

        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, resource))

        # Parse .env file
        env_path = Path(env_file)
        if not env_path.exists():
            console.print(f"[error]File not found: {env_file}[/error]")
            raise typer.Exit(1)

        envvars = []
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                envvars.append({"key": key.strip(), "value": value.strip()})

        if not envvars:
            console.print("[warning]No variables found in file.[/warning]")
            return

        result = run_async(client.bulk_update_app_envvars(uuid, envvars))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print(f"[success]Bulk updated {len(envvars)} environment variables.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
