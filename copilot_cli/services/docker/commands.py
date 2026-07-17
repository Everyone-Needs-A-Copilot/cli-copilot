"""Typer subcommand group for Docker operations."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(no_args_is_help=True)


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.docker.client import DockerClient

    return DockerClient()


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command("ps")
def ps(
    all: bool = typer.Option(False, "--all", "-a", help="Include stopped containers."),
) -> None:
    """List Docker containers."""
    try:
        rows = _client().container_list(all=all)
        print_table(
            rows,
            title="Docker Containers",
            columns=["id", "names", "image", "status", "ports"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def start(
    id: str = typer.Argument(..., help="Container ID or name."),
) -> None:
    """Start a stopped container."""
    try:
        result = _client().container_start(id=id)
        print_success(f"Container {result['id']} is now {result['status']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def stop(
    id: str = typer.Argument(..., help="Container ID or name."),
    timeout: int = typer.Option(10, "--timeout", "-t", help="Seconds before kill."),
) -> None:
    """Stop a running container."""
    try:
        result = _client().container_stop(id=id, timeout=timeout)
        print_success(f"Container {result['id']} is now {result['status']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def restart(
    id: str = typer.Argument(..., help="Container ID or name."),
    timeout: int = typer.Option(10, "--timeout", "-t", help="Seconds before kill."),
) -> None:
    """Restart a container."""
    try:
        result = _client().container_restart(id=id, timeout=timeout)
        print_success(f"Container {result['id']} is now {result['status']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """Show Docker daemon system information."""
    try:
        result = _client().system_info()
        print_json(result, title="Docker System Info")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Check Docker daemon health."""
    try:
        result = _client().health()
        is_healthy = result.get("healthy", False)
        print_health("docker", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success(
                f"Docker v{result.get('version', '?')} - {result.get('containers', 0)} container(s)"
            )
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
