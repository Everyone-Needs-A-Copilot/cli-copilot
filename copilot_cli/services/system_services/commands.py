"""Typer commands for the system services module."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success, print_table

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_cmd(
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """List launchctl services."""
    from .client import list_services

    try:
        rows = list_services(domain=domain)
        print_table(rows, title=f"Services ({domain} domain)", columns=["pid", "status", "label"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def status(
    service: str = typer.Argument(..., help="Service label (e.g. com.apple.Spotlight)."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Get status of a specific service."""
    from .client import get_status

    try:
        result = get_status(service, domain=domain)
        print_json(result, title=f"Service: {service}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def start(
    service: str = typer.Argument(..., help="Service label to start."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Start a launchctl service."""
    from .client import start_service

    try:
        result = start_service(service, domain=domain)
        if result["success"]:
            print_success(f"Started {service}: {result['message']}")
        else:
            print_error(f"Failed to start {service}: {result['message']}")
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def stop(
    service: str = typer.Argument(..., help="Service label to stop."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Stop a launchctl service."""
    from .client import stop_service

    try:
        result = stop_service(service, domain=domain)
        if result["success"]:
            print_success(f"Stopped {service}: {result['message']}")
        else:
            print_error(f"Failed to stop {service}: {result['message']}")
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def restart(
    service: str = typer.Argument(..., help="Service label to restart."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Restart a launchctl service (stop then start)."""
    from .client import restart_service

    try:
        result = restart_service(service, domain=domain)
        if result["success"]:
            print_success(f"Restarted {service}: {result['message']}")
        else:
            print_error(f"Failed to restart {service}: {result['message']}")
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def load(
    path: str = typer.Argument(..., help="Path to the service plist file."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Load a service plist."""
    from .client import load_service

    try:
        result = load_service(path, domain=domain)
        if result["success"]:
            print_success(f"Loaded {path}: {result['message']}")
        else:
            print_error(f"Failed to load {path}: {result['message']}")
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def unload(
    path: str = typer.Argument(..., help="Path to the service plist file."),
    domain: str = typer.Option("user", "--domain", "-d", help="Service domain: user or system."),
) -> None:
    """Unload a service plist."""
    from .client import unload_service

    try:
        result = unload_service(path, domain=domain)
        if result["success"]:
            print_success(f"Unloaded {path}: {result['message']}")
        else:
            print_error(f"Failed to unload {path}: {result['message']}")
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def ps(
    filter: str | None = typer.Option(
        None, "--filter", "-f", help="Filter by command name substring."
    ),
    user_only: bool = typer.Option(
        True, "--user-only/--all-users", help="Show only current user processes."
    ),
) -> None:
    """List running processes."""
    from .client import list_processes

    try:
        rows = list_processes(name_filter=filter, user_only=user_only)
        print_table(rows, title="Processes", columns=["pid", "user", "cpu", "mem", "command"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def proc(
    pid: int = typer.Argument(..., help="Process ID."),
) -> None:
    """Get detailed information for a specific process."""
    from .client import get_process_info

    try:
        result = get_process_info(pid)
        print_json(result, title=f"Process {pid}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Run a health check on system services."""
    from copilot_cli.shared.output import print_health

    from .client import health as _health

    try:
        result = _health()
        print_health("system_services", result["healthy"], result)
        print_health("  launchctl", result["launchctl_available"])
        print_health("  ps", result["ps_available"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
