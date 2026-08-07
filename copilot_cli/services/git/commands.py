"""Typer subcommand group for Git operations."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success

app = typer.Typer(no_args_is_help=True)


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.git.client import GitClient

    return GitClient()


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def clone(
    url: str = typer.Option(..., "--url", help="Remote repository URL."),
    path: str = typer.Option(..., "--path", help="Local directory for the clone."),
    branch: str | None = typer.Option(None, "--branch", help="Branch to check out."),
) -> None:
    """Clone a remote Git repository."""
    try:
        result = _client().clone(url=url, path=path, branch=branch)
        print_success(f"Cloned {url} -> {result['path']} (branch: {result['branch']})")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def pull(
    path: str = typer.Option(".", "--path", help="Repository path."),
    remote: str = typer.Option("origin", "--remote", help="Remote name."),
    branch: str | None = typer.Option(None, "--branch", help="Branch to pull."),
) -> None:
    """Pull latest changes from a remote."""
    try:
        result = _client().pull(path=path, remote=remote, branch=branch)
        print_success(f"Pulled {result['remote']}/{result['branch']} - {result['status']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def status(
    path: str = typer.Option(".", "--path", help="Repository path."),
) -> None:
    """Show the working-tree status of a repository."""
    try:
        result = _client().status(path=path)
        print_json(result, title="Git Status")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def add(
    path: str = typer.Option(".", "--path", help="Repository path."),
    files: list[str] = typer.Argument(..., help="Files to stage."),
) -> None:
    """Stage files for the next commit."""
    try:
        result = _client().add(path=path, files=files)
        print_success(f"Staged {len(result['staged'])} file(s)")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def commit(
    path: str = typer.Option(".", "--path", help="Repository path."),
    message: str = typer.Option(..., "--message", "-m", help="Commit message."),
    author: str | None = typer.Option(None, "--author", help="Author in 'Name <email>' format."),
) -> None:
    """Commit staged changes."""
    try:
        result = _client().commit(path=path, message=message, author=author)
        print_success(f"Committed {result['sha'][:8]}: {result['message']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
