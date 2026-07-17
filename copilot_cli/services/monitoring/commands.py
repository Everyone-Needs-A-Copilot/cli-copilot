"""Typer subcommand group for system monitoring operations."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_success,
    print_table,
)

app = typer.Typer(no_args_is_help=True)


def _mod():
    """Lazy-import the monitoring client module."""
    from copilot_cli.services.monitoring import client

    return client


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show current system metrics (CPU, memory, disk)."""
    try:
        metrics = _mod().get_system_metrics()

        cpu_pct = metrics["cpu"]["usage_percent"]
        mem = metrics["memory"]

        rows = [
            {
                "metric": "CPU",
                "value": f"{cpu_pct}%",
                "status": "OK" if cpu_pct < 80 else "WARNING" if cpu_pct < 95 else "CRITICAL",
            },
            {
                "metric": "Memory",
                "value": f"{mem['used_percent']}% ({mem['used_gb']} / {mem['total_gb']} GB)",
                "status": "OK"
                if mem["used_percent"] < 85
                else "WARNING"
                if mem["used_percent"] < 95
                else "CRITICAL",
            },
        ]

        for disk in metrics["disk"]:
            disk_pct = disk["use_percent"]
            rows.append(
                {
                    "metric": f"Disk ({disk['mount']})",
                    "value": f"{disk_pct}% ({disk['used']} / {disk['size']})",
                    "status": "OK" if disk_pct < 90 else "WARNING" if disk_pct < 95 else "CRITICAL",
                }
            )

        print_table(rows, title="System Metrics", columns=["metric", "value", "status"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def alerts() -> None:
    """Show active alerts based on configured thresholds."""
    try:
        alert_list = _mod().get_alerts()

        if not alert_list:
            print_success("No active alerts - all metrics within thresholds")
            return

        rows = [
            {
                "level": a["level"].upper(),
                "metric": a["metric"],
                "current": f"{a['current']}%",
                "threshold": f"{a['threshold']}%",
                "message": a["message"],
            }
            for a in alert_list
        ]
        print_table(
            rows,
            title="Active Alerts",
            columns=["level", "metric", "current", "threshold", "message"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Check monitoring service health."""
    try:
        result = _mod().health()
        is_healthy = result.get("healthy", False)
        print_health("monitoring", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success(
                f"Monitoring OK - CPU: {result.get('cpu_percent', '?')}%, "
                f"Memory: {result.get('memory_percent', '?')}%"
            )
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
