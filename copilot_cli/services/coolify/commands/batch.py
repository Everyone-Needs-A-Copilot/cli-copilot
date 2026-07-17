"""Batch operation commands."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.panel import Panel

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Batch operations across resources.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


def _print_batch_result(result: dict) -> None:
    """Pretty-print a batch operation result."""
    summary = result.get("summary", {})
    console.print(
        Panel(
            f"Total: {summary.get('total', 0)}  "
            f"[green]Succeeded: {summary.get('succeeded', 0)}[/green]  "
            f"[red]Failed: {summary.get('failed', 0)}[/red]",
            title="Batch Result",
            border_style="cyan",
        )
    )
    for s in result.get("succeeded", []):
        console.print(f"  [green]✓[/green] {s.get('name', s.get('uuid', ''))}")
    for f in result.get("failed", []):
        console.print(f"  [red]✗[/red] {f.get('name', f.get('uuid', ''))}: {f.get('error', '')}")


async def _restart_project_apps(client, project_uuid: str) -> dict:
    """Restart all apps in a project."""
    all_apps = await client.list_applications()
    project_apps = [a for a in all_apps if a.get("project_uuid") == project_uuid]
    if not project_apps:
        return {"summary": {"total": 0, "succeeded": 0, "failed": 0}, "succeeded": [], "failed": []}

    results = await asyncio.gather(
        *[client.restart_application(a["uuid"]) for a in project_apps],
        return_exceptions=True,
    )

    succeeded = []
    failed = []
    for app_data, result in zip(project_apps, results):
        name = app_data.get("name", app_data.get("uuid", ""))
        if isinstance(result, Exception):
            failed.append({"uuid": app_data["uuid"], "name": name, "error": str(result)})
        else:
            succeeded.append({"uuid": app_data["uuid"], "name": name})

    return {
        "summary": {"total": len(project_apps), "succeeded": len(succeeded), "failed": len(failed)},
        "succeeded": succeeded,
        "failed": failed,
    }


async def _stop_all_apps(client) -> dict:
    """Stop all running applications."""
    all_apps = await client.list_applications()
    running = [
        a
        for a in all_apps
        if "running" in (a.get("status") or "") or "healthy" in (a.get("status") or "")
    ]
    if not running:
        return {"summary": {"total": 0, "succeeded": 0, "failed": 0}, "succeeded": [], "failed": []}

    results = await asyncio.gather(
        *[client.stop_application(a["uuid"]) for a in running],
        return_exceptions=True,
    )

    succeeded = []
    failed = []
    for app_data, result in zip(running, results):
        name = app_data.get("name", app_data.get("uuid", ""))
        if isinstance(result, Exception):
            failed.append({"uuid": app_data["uuid"], "name": name, "error": str(result)})
        else:
            succeeded.append({"uuid": app_data["uuid"], "name": name})

    return {
        "summary": {"total": len(running), "succeeded": len(succeeded), "failed": len(failed)},
        "succeeded": succeeded,
        "failed": failed,
    }


async def _redeploy_project(client, project_uuid: str, force: bool = True) -> dict:
    """Redeploy all apps in a project."""
    all_apps = await client.list_applications()
    project_apps = [a for a in all_apps if a.get("project_uuid") == project_uuid]
    if not project_apps:
        return {"summary": {"total": 0, "succeeded": 0, "failed": 0}, "succeeded": [], "failed": []}

    results = await asyncio.gather(
        *[client.deploy(a["uuid"], force=force) for a in project_apps],
        return_exceptions=True,
    )

    succeeded = []
    failed = []
    for app_data, result in zip(project_apps, results):
        name = app_data.get("name", app_data.get("uuid", ""))
        if isinstance(result, Exception):
            failed.append({"uuid": app_data["uuid"], "name": name, "error": str(result)})
        else:
            succeeded.append({"uuid": app_data["uuid"], "name": name})

    return {
        "summary": {"total": len(project_apps), "succeeded": len(succeeded), "failed": len(failed)},
        "succeeded": succeeded,
        "failed": failed,
    }


@app.command("restart-project")
def restart_project(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Restart all applications in a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))

        if not force:
            if not typer.confirm(f"Restart all applications in project {project}?"):
                raise typer.Abort()

        result = run_async(_restart_project_apps(client, project_uuid))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            _print_batch_result(result)
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)


@app.command("redeploy")
def redeploy(
    project: Annotated[str, typer.Argument(help="Project UUID or name")],
    force_rebuild: Annotated[bool, typer.Option("--force", "-f", help="Force rebuild")] = True,
    confirm: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Redeploy all applications in a project."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_project

        project_uuid = run_async(resolve_project(client, project))

        if not confirm:
            if not typer.confirm(f"Redeploy all applications in project {project}?"):
                raise typer.Abort()

        result = run_async(_redeploy_project(client, project_uuid, force=force_rebuild))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            _print_batch_result(result)
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)


@app.command("stop-all")
def stop_all(
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Emergency stop all running applications."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()

        if not force:
            console.print("[error]WARNING: This will stop ALL running applications![/error]")
            if not typer.confirm("Are you sure?"):
                raise typer.Abort()

        result = run_async(_stop_all_apps(client))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            _print_batch_result(result)
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)


@app.command("bulk-env")
def bulk_env(
    key: Annotated[str, typer.Argument(help="Env var key")],
    value: Annotated[str, typer.Argument(help="Env var value")],
    apps: Annotated[str, typer.Option("--apps", help="Comma-separated app UUIDs or names")] = "",
    build_time: Annotated[bool, typer.Option("--build-time", help="Build-time variable")] = False,
) -> None:
    """Set an env var across multiple applications."""
    state, run_async, handle_error = _get_deps()
    try:
        if not apps:
            console.print("[error]Provide --apps with comma-separated UUIDs or names.[/error]")
            raise typer.Exit(1)

        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_application

        app_queries = [a.strip() for a in apps.split(",") if a.strip()]
        app_uuids = []
        for q in app_queries:
            uuid = run_async(resolve_application(client, q))
            app_uuids.append(uuid)

        async def _bulk():
            all_apps = await client.list_applications()
            app_map = {a.get("uuid"): a.get("name", a.get("uuid")) for a in all_apps}
            results_list = await asyncio.gather(
                *[
                    client.update_app_envvar(
                        uuid, {"key": key, "value": value, "is_build_time": build_time}
                    )
                    for uuid in app_uuids
                ],
                return_exceptions=True,
            )
            succeeded = []
            failed = []
            for uuid, result in zip(app_uuids, results_list):
                name = app_map.get(uuid, uuid)
                if isinstance(result, Exception):
                    failed.append({"uuid": uuid, "name": name, "error": str(result)})
                else:
                    succeeded.append({"uuid": uuid, "name": name})
            return {
                "summary": {
                    "total": len(app_uuids),
                    "succeeded": len(succeeded),
                    "failed": len(failed),
                },
                "succeeded": succeeded,
                "failed": failed,
            }

        result = run_async(_bulk())

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            _print_batch_result(result)
    except (SystemExit, typer.Abort):
        raise
    except Exception as e:
        handle_error(e)
