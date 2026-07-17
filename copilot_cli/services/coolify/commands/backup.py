"""Database backup management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from copilot_cli.services.coolify.output.console import console

app = typer.Typer(help="Manage database backups.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


@app.command("list")
def list_backups(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
) -> None:
    """List backup schedules for a database."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        db_uuid = run_async(resolve_database(client, database))
        backups = run_async(client.list_database_backups(db_uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(backups, state.output_format)
        else:
            from copilot_cli.services.coolify.output.tables import backup_table

            if not backups:
                console.print("[dim]No backups found.[/dim]")
                return
            console.print(backup_table(backups))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("get")
def get_backup(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
    backup_uuid: Annotated[str, typer.Argument(help="Backup UUID")],
) -> None:
    """Get backup details."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        db_uuid = run_async(resolve_database(client, database))
        backup = run_async(client.get_database_backup(db_uuid, backup_uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(backup, state.output_format)
        else:
            from rich.panel import Panel
            from rich.table import Table

            from copilot_cli.services.coolify.output.formatters import bool_icon, status_badge

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="label", width=20)
            table.add_column("Value")
            table.add_row("UUID", backup.get("uuid", ""))
            table.add_row("Status", status_badge(backup.get("status")))
            table.add_row("Frequency", backup.get("frequency", ""))
            table.add_row("Enabled", bool_icon(backup.get("enabled")))
            table.add_row("S3", bool_icon(backup.get("save_s3")))
            table.add_row("Dump All", bool_icon(backup.get("dump_all")))
            console.print(Panel(table, title="Backup Schedule", border_style="cyan"))
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("create")
def create_backup(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
    frequency: Annotated[str, typer.Argument(help="Cron expression for frequency")],
    enabled: Annotated[bool, typer.Option("--enabled/--disabled", help="Enable schedule")] = True,
    keep_local: Annotated[
        int, typer.Option("--keep-local", min=0, help="Number of local backups to retain")
    ] = 7,
    retention_days_local: Annotated[
        int,
        typer.Option("--retention-days-local", min=0, help="Days to retain local backups"),
    ] = 7,
    max_local_gb: Annotated[
        float,
        typer.Option("--max-local-gb", min=0, help="Maximum local backup storage in GB"),
    ] = 0,
    backup_now: Annotated[
        bool, typer.Option("--backup-now", help="Trigger a backup immediately after creation")
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", min=60, max=36000, help="Backup timeout in seconds")
    ] = 3600,
) -> None:
    """Create a local backup schedule with bounded retention by default."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        db_uuid = run_async(resolve_database(client, database))
        data = {
            "frequency": frequency,
            "enabled": enabled,
            "save_s3": False,
            "database_backup_retention_amount_locally": keep_local,
            "database_backup_retention_days_locally": retention_days_local,
            "database_backup_retention_max_storage_locally": max_local_gb,
            "backup_now": backup_now,
            "timeout": timeout,
        }
        result = run_async(client.create_database_backup(db_uuid, data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Backup schedule created.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("update")
def update_backup(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
    backup_uuid: Annotated[str, typer.Argument(help="Backup UUID")],
    frequency: Annotated[str, typer.Option("--frequency", help="New cron expression")] = "",
    enable: Annotated[bool, typer.Option("--enable", help="Enable the schedule")] = False,
    disable: Annotated[bool, typer.Option("--disable", help="Disable the schedule")] = False,
    keep_local: Annotated[
        int | None,
        typer.Option("--keep-local", min=0, help="Number of local backups to retain"),
    ] = None,
    retention_days_local: Annotated[
        int | None,
        typer.Option("--retention-days-local", min=0, help="Days to retain local backups"),
    ] = None,
    max_local_gb: Annotated[
        float | None,
        typer.Option("--max-local-gb", min=0, help="Maximum local backup storage in GB"),
    ] = None,
    timeout: Annotated[
        int | None,
        typer.Option("--timeout", min=60, max=36000, help="Backup timeout in seconds"),
    ] = None,
) -> None:
    """Update a backup schedule without enabling off-server storage."""
    state, run_async, handle_error = _get_deps()
    try:
        if enable and disable:
            raise ValueError("Choose either --enable or --disable, not both.")

        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        db_uuid = run_async(resolve_database(client, database))
        data: dict[str, object] = {}
        if frequency:
            data["frequency"] = frequency
        if enable or disable:
            data["enabled"] = enable
        if keep_local is not None:
            data["database_backup_retention_amount_locally"] = keep_local
        if retention_days_local is not None:
            data["database_backup_retention_days_locally"] = retention_days_local
        if max_local_gb is not None:
            data["database_backup_retention_max_storage_locally"] = max_local_gb
        if timeout is not None:
            data["timeout"] = timeout
        if not data:
            console.print("[warning]No fields to update.[/warning]")
            return

        result = run_async(client.update_database_backup(db_uuid, backup_uuid, data))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
        else:
            console.print("[success]Backup schedule updated.[/success]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("delete")
def delete_backup(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
    backup_uuid: Annotated[str, typer.Argument(help="Backup UUID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a backup schedule."""
    console.print(
        "[error]Refused: the cli-copilot tool is not permitted to delete backup "
        "schedules on remote Coolify databases. Manage schedules via the Coolify UI.[/error]"
    )
    raise typer.Exit(1)


@app.command("executions")
def list_executions(
    database: Annotated[str, typer.Argument(help="Database UUID or name")],
    backup_uuid: Annotated[str, typer.Argument(help="Backup UUID")],
) -> None:
    """List backup executions."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.core.resolver import resolve_database

        db_uuid = run_async(resolve_database(client, database))
        executions = run_async(client.list_backup_executions(db_uuid, backup_uuid))
        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(executions, state.output_format)
        else:
            from rich.table import Table

            from copilot_cli.services.coolify.output.formatters import (
                format_bytes,
                relative_time,
                status_badge,
            )

            table = Table(title="Backup Executions", show_lines=False)
            table.add_column("UUID", style="uuid")
            table.add_column("Status")
            table.add_column("Size")
            table.add_column("Filename")
            table.add_column("When")
            for ex in executions:
                table.add_row(
                    ex.get("uuid", ""),
                    status_badge(ex.get("status")),
                    format_bytes(ex.get("size")),
                    ex.get("filename") or "—",
                    relative_time(ex.get("created_at")),
                )
            console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
