"""Rich output helpers for consistent CLI formatting.

Mostly pure formatters (`print_json`, `print_table`, `print_health`, ...). The
one exception is `report_health`, which also decides the command's exit status:
the health-command contract couples "what to report" to "what to exit with", and
splitting them across modules is what let four services drift into crashing
instead of reporting. It lives beside `print_health` so there is exactly one
place to read that contract.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .errors import CopilotError

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


def report_health(
    service: str,
    check: Callable[[], dict[str, Any]],
    *,
    success_message: Callable[[dict[str, Any]], str] | None = None,
) -> None:
    """Run one service's health probe and REPORT a verdict -- never a traceback.

    A `health` command has a stricter contract than every other command in a
    service module: it exists to answer "is this service usable?", so a failure
    it cannot recover from is its ANSWER, not a crash. Clients already honour
    half of that -- `Client.health()` downgrades a failed probe to
    `{"healthy": False, ...}` -- but BUILDING the client reads the credential,
    and a signed-out credential raises `SecretResolutionError` there. That raise
    is upstream of the client's own guard, so it escaped as a raw traceback in
    every command that lacked an `except CopilotError`.

    `check` is therefore the whole construct-then-probe expression
    (`lambda: _client().health()`), not a bound method -- guarding only the
    probe would leave the construction crash exactly where it was.

    Fail-closed is preserved, not weakened: a missing credential is still a
    visible failure with exit code 1 (see `credentials-and-boundary.md` §1.4).
    Only the SHAPE of the report changes, from traceback to verdict.

    Diagnosis is preserved too, and this is why the failure is not flattened to
    a generic message:

    * An unhealthy probe reports the client's own result dict verbatim, so
      service-specific findings survive (cloudflare's `token_active` /
      `zones_visible` / `dns_ready`, and whatever each other client reports).
    * A raised `CopilotError` reports its message as `error` and its remediation
      as `hint`, so the operator learns which credential is missing and how to
      provision it.

    Only `CopilotError` is caught. A genuine bug -- `TypeError`, `KeyError`,
    anything outside the service's own error hierarchy -- must still surface as
    a traceback rather than be laundered into a misleading "unhealthy".

    Args:
        service: Name shown on the health line (the CLI's service name).
        check: Zero-arg callable returning the client's health dict. Should
            construct the client too, so construction failures are covered.
        success_message: Optional formatter for an extra `print_success` line on
            a healthy verdict, receiving the health dict (used by services that
            report a detail worth surfacing, e.g. cloudflare's zone count).

    Raises:
        typer.Exit: With code 1 on any unhealthy or unreachable verdict. The
            healthy path returns normally, leaving Typer's implicit exit 0.
    """
    try:
        result = check()
    except CopilotError as exc:
        print_health(service, False, {"error": str(exc), "hint": exc.hint})
        raise typer.Exit(1) from None

    healthy = result.get("healthy", False)
    print_health(service, healthy, result if not healthy else None)
    if not healthy:
        raise typer.Exit(1)
    if success_message is not None:
        print_success(success_message(result))
