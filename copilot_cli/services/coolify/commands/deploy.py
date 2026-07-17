"""Deployment management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage deployments.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("trigger")
def trigger_deploy(
    uuid_or_tag: Annotated[str, typer.Argument(help="Application UUID or tag to deploy")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Force rebuild")] = False,
) -> None:
    """Trigger a deployment by UUID or tag."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(client.deploy(uuid_or_tag, force=force))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            if isinstance(result, dict):
                msg = result.get("message", "Deployment triggered")
                console.print(f"[success]{msg}[/success]")
            elif isinstance(result, list):
                console.print(f"[success]Triggered {len(result)} deployment(s).[/success]")
                for item in result:
                    if isinstance(item, dict):
                        console.print(
                            f"  {item.get('application_name', '?')}: {item.get('deployment_uuid', '?')}"
                        )
            else:
                console.print(f"[success]{result}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("list")
def list_deployments(
    page: Annotated[int, typer.Option("--page", "-p", help="Page number")] = 1,
    per_page: Annotated[int, typer.Option("--per-page", help="Items per page")] = 20,
) -> None:
    """List recent deployments."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        deployments = run_async(client.list_deployments(page=page, per_page=per_page))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(deployments, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import deployment_table

            if not deployments:
                console.print("[dim]No deployments found.[/dim]")
                return
            console.print(deployment_table(deployments))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_deployment(
    uuid: Annotated[str, typer.Argument(help="Deployment UUID")],
    logs: Annotated[bool, typer.Option("--logs", "-l", help="Include deployment logs")] = False,
) -> None:
    """Get deployment details."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        deployment = run_async(client.get_deployment(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(deployment, state.output_format)
        else:
            from copilot_cli.services.coolify.output.panels import deployment_detail_panel

            console.print(deployment_detail_panel(deployment))
            if logs and isinstance(deployment, dict) and deployment.get("logs"):
                console.print("\n[bold]Deployment Logs:[/bold]")
                console.print(deployment["logs"])
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("cancel")
def cancel_deployment(
    uuid: Annotated[str, typer.Argument(help="Deployment UUID")],
) -> None:
    """Cancel a running deployment."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(client.cancel_deployment(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            msg = (
                result.get("message", "Deployment cancelled")
                if isinstance(result, dict)
                else "Deployment cancelled"
            )
            console.print(f"[success]{msg}[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("history")
def deployment_history(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Show deployment history for an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        uuid = run_async(resolve_application(client, query))
        deployments = run_async(client.list_app_deployments(uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(deployments, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import deployment_table

            if not deployments:
                console.print("[dim]No deployments found for this application.[/dim]")
                return
            console.print(deployment_table(deployments))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
