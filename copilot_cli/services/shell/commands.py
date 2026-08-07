"""Typer subcommand group for shell operations."""

from __future__ import annotations

import typer
from rich.console import Console

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_success, print_table

app = typer.Typer(no_args_is_help=True)
console = Console()


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.shell.client import ShellClient

    return ShellClient()


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command("exec")
def exec_cmd(
    command: str = typer.Argument(..., help="Shell command to execute."),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds."),
    working_dir: str | None = typer.Option(None, "--working-dir", "-d", help="Working directory."),
) -> None:
    """Execute a shell command."""
    try:
        result = _client().execute(
            command=command,
            timeout=timeout,
            working_dir=working_dir,
        )
        if result["stdout"]:
            console.print(result["stdout"], end="")
        if result["stderr"]:
            console.print(f"[dim]{result['stderr']}[/dim]", end="")
        if result["exit_code"] != 0:
            print_error(f"Exit code: {result['exit_code']}")
            raise typer.Exit(result["exit_code"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command("run")
def run(
    script_name: str = typer.Argument(..., help="Script filename to execute."),
    timeout: int = typer.Option(3600, "--timeout", "-t", help="Timeout in seconds."),
) -> None:
    """Run a script from configured script paths."""
    try:
        result = _client().run_script(
            script_name=script_name,
            timeout=timeout,
        )
        if result["stdout"]:
            console.print(result["stdout"], end="")
        if result["stderr"]:
            console.print(f"[dim]{result['stderr']}[/dim]", end="")
        if result["exit_code"] != 0:
            print_error(f"Script exited with code {result['exit_code']}")
            raise typer.Exit(result["exit_code"])
        else:
            print_success(f"Script {script_name} completed ({result.get('script_path', '')})")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command("find")
def find(
    pattern: str = typer.Option("*.sh", "--pattern", "-p", help="Glob pattern."),
    path: str | None = typer.Option(None, "--path", help="Directory to search."),
) -> None:
    """Find scripts in configured paths."""
    try:
        rows = _client().find_scripts(pattern=pattern, path=path)
        print_table(
            rows,
            title="Scripts",
            columns=["name", "path", "size", "modified", "executable"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command("ps")
def ps(
    pattern: str | None = typer.Option(None, "--pattern", "-p", help="Filter pattern."),
    user: str | None = typer.Option(None, "--user", "-u", help="Filter by user."),
) -> None:
    """List running processes."""
    try:
        output = _client().list_processes(pattern=pattern, user=user)
        console.print(output)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
