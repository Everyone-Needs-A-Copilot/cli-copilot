"""Rich output helpers for consistent CLI formatting."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

# Global JSON output mode
_json_mode: bool = False


def set_json_mode(enabled: bool) -> None:
    """Enable or disable global JSON output mode."""
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    """Check if global JSON output mode is active."""
    return _json_mode


def print_json(data: Any, title: str | None = None) -> None:
    """Pretty-print JSON data."""
    text = json.dumps(data, indent=2, default=str)
    if _json_mode:
        print(text)
        return
    if title:
        console.print(Panel(text, title=title, border_style="blue"))
    else:
        console.print_json(text)


def print_table(
    rows: list[dict], title: str | None = None, columns: list[str] | None = None
) -> None:
    """Print a list of dicts as a Rich table."""
    if _json_mode:
        print(json.dumps({"title": title, "data": rows}, indent=2, default=str))
        return

    if not rows:
        console.print("[dim]No results.[/dim]")
        return

    cols = columns or list(rows[0].keys())
    table = Table(title=title, show_lines=False)

    for col in cols:
        table.add_column(col, style="cyan", no_wrap=False)

    for row in rows:
        table.add_row(*[str(row.get(c, "")) for c in cols])

    console.print(table)


def print_success(message: str) -> None:
    if _json_mode:
        print(json.dumps({"status": "ok", "message": message}))
        return
    console.print(f"[green bold]OK[/green bold] {message}")


def print_error(message: str, hint: str = "") -> None:
    if _json_mode:
        data: dict[str, Any] = {"status": "error", "message": message}
        if hint:
            data["hint"] = hint
        print(json.dumps(data), file=sys.stderr)
        return
    err_console.print(f"[red bold]Error:[/red bold] {message}")
    if hint:
        err_console.print(f"[dim]Hint: {hint}[/dim]")


def print_warning(message: str) -> None:
    if _json_mode:
        print(json.dumps({"status": "warning", "message": message}), file=sys.stderr)
        return
    err_console.print(f"[yellow bold]Warning:[/yellow bold] {message}")


def print_health(
    service: str,
    healthy: bool,
    details: dict | None = None,
    skipped: bool = False,
) -> None:
    """Print a health-check result line."""
    if _json_mode:
        status_str = "skipped" if skipped else ("healthy" if healthy else "unhealthy")
        data: dict[str, Any] = {"service": service, "status": status_str}
        if details and not healthy and not skipped:
            data["details"] = details
        print(json.dumps(data, default=str))
        return
    if skipped:
        status = "[yellow]skipped[/yellow]"
    elif healthy:
        status = "[green]healthy[/green]"
    else:
        status = "[red]unhealthy[/red]"
    console.print(f"  {service:.<30s} {status}")
    if details and not healthy and not skipped:
        for k, v in details.items():
            console.print(f"    {k}: {v}")
