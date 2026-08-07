"""Typer subcommand group for document management operations."""

from __future__ import annotations

import typer
from rich.console import Console

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(no_args_is_help=True)
console = Console()


def _mod():
    """Lazy-import the document client module."""
    from copilot_cli.services.document import client

    return client


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def search(
    path: str = typer.Argument(..., help="Directory to search in."),
    query: str = typer.Argument(..., help="Text to search for."),
    ext: str | None = typer.Option(
        None, "--ext", "-e", help="File extension filter (e.g. md, txt)."
    ),
) -> None:
    """Search document contents for matching text."""
    try:
        results = _mod().search_documents(path=path, query=query, extension=ext)
        print_table(
            results,
            title=f"Search: '{query}'",
            columns=["filename", "line_number", "line", "path"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def get(
    path: str = typer.Argument(..., help="Path to the document file."),
) -> None:
    """Read and display a document."""
    try:
        result = _mod().get_document(path=path)
        console.print(result["content"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def create(
    path: str = typer.Argument(..., help="Path for the new document."),
    content: str = typer.Option(..., "--content", "-c", help="Text content for the document."),
) -> None:
    """Create a new document file."""
    try:
        result = _mod().create_document(path=path, content=content)
        print_success(f"Created {result['path']} ({result['size']} bytes)")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def update(
    path: str = typer.Argument(..., help="Path to the document."),
    content: str = typer.Option(..., "--content", "-c", help="New text content."),
) -> None:
    """Update an existing document file."""
    try:
        result = _mod().update_document(path=path, content=content)
        print_success(f"Updated {result['path']} ({result['size']} bytes)")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def delete(
    path: str = typer.Argument(..., help="Path to the document."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Delete a document file."""
    if not force:
        confirm = typer.confirm(f"Delete {path}?")
        if not confirm:
            raise typer.Abort()
    try:
        result = _mod().delete_document(path=path)
        print_success(f"Deleted {result['path']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def collections(
    path: str = typer.Argument(..., help="Base directory to scan."),
) -> None:
    """List subdirectories as document collections."""
    try:
        results = _mod().list_collections(base_path=path)
        print_table(
            results,
            title="Document Collections",
            columns=["name", "document_count", "total_size", "path"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def stats() -> None:
    """Show document statistics for the current directory."""
    try:
        result = _mod().get_stats()
        print_json(result, title="Document Statistics")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Check document service health."""
    try:
        result = _mod().health()
        is_healthy = result.get("healthy", False)
        print_health("document", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success(f"Document service OK - cwd: {result.get('cwd', '?')}")
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
