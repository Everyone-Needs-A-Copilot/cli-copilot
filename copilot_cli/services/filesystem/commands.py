"""Typer commands for the filesystem service."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success, print_table

app = typer.Typer(no_args_is_help=True)


@app.command()
def read(
    path: str = typer.Argument(..., help="Path to the file to read."),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="File encoding."),
) -> None:
    """Read and display a file's contents."""
    from .client import read_file

    try:
        result = read_file(path, encoding=encoding)
        typer.echo(result["content"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def write(
    path: str = typer.Argument(..., help="Destination file path."),
    content: str = typer.Option(..., "--content", "-c", help="Content to write."),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="File encoding."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if destination exists."),
) -> None:
    """Write content to a file."""
    from pathlib import Path as _Path

    from .client import write_file

    if not force and _Path(path).exists():
        confirmed = typer.confirm(f"{path} already exists. Overwrite?")
        if not confirmed:
            raise typer.Abort()

    try:
        result = write_file(path, content, encoding=encoding, overwrite=True)
        print_success(f"Wrote {result['size']} bytes to {result['path']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def delete(
    path: str = typer.Argument(..., help="File to delete."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Delete a file."""
    from .client import delete_file

    if not force:
        confirmed = typer.confirm(f"Delete {path}?")
        if not confirmed:
            raise typer.Abort()

    try:
        result = delete_file(path)
        print_success(f"Deleted {result['path']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def cp(
    source: str = typer.Argument(..., help="Source file path."),
    dest: str = typer.Argument(..., help="Destination file path."),
    preserve: bool = typer.Option(False, "--preserve", "-p", help="Preserve timestamps."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if destination exists."),
) -> None:
    """Copy a file."""
    from pathlib import Path as _Path

    from .client import copy_file

    if not force and _Path(dest).exists():
        confirmed = typer.confirm(f"{dest} already exists. Overwrite?")
        if not confirmed:
            raise typer.Abort()

    try:
        result = copy_file(source, dest, preserve_timestamps=preserve, overwrite=True)
        print_success(f"Copied to {result['destination']} ({result['size']} bytes)")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def mv(
    source: str = typer.Argument(..., help="Source path."),
    dest: str = typer.Argument(..., help="Destination path."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if destination exists."),
) -> None:
    """Move a file."""
    from pathlib import Path as _Path

    from .client import move_file

    if not force and _Path(dest).exists():
        confirmed = typer.confirm(f"{dest} already exists. Overwrite?")
        if not confirmed:
            raise typer.Abort()

    try:
        result = move_file(source, dest, overwrite=True)
        print_success(f"Moved to {result['destination']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def ls(
    path: str = typer.Argument(".", help="Directory to list."),
    files_only: bool = typer.Option(False, "--files-only", help="Show only files."),
    dirs_only: bool = typer.Option(False, "--dirs-only", help="Show only directories."),
    pattern: str | None = typer.Option(None, "--pattern", "-p", help="Glob pattern filter."),
    sort_by: str = typer.Option("name", "--sort-by", "-s", help="Sort by: name, size, modified."),
) -> None:
    """List directory contents."""
    from .client import list_directory

    try:
        rows = list_directory(
            path,
            files_only=files_only,
            dirs_only=dirs_only,
            pattern=pattern,
            sort_by=sort_by,
        )
        print_table(rows, title=f"Contents of {path}", columns=["name", "type", "size", "modified"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def mkdir(
    path: str = typer.Argument(..., help="Directory path to create."),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Create parent directories."
    ),
) -> None:
    """Create a directory."""
    from .client import create_directory

    try:
        result = create_directory(path, recursive=recursive)
        print_success(f"Created {result['path']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def search(
    path: str = typer.Argument(".", help="Root directory to search."),
    ext: str | None = typer.Option(None, "--ext", help="File extension filter (e.g. .json)."),
    name: str | None = typer.Option(None, "--name", "-n", help="File name substring match."),
    min_size: int | None = typer.Option(None, "--min-size", help="Minimum file size in bytes."),
    max_size: int | None = typer.Option(None, "--max-size", help="Maximum file size in bytes."),
) -> None:
    """Search for files recursively."""
    from .client import search_files

    try:
        rows = search_files(
            path,
            extension=ext,
            name=name,
            min_size=min_size,
            max_size=max_size,
        )
        print_table(
            rows, title=f"Search results in {path}", columns=["name", "path", "size", "modified"]
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def checksum(
    path: str = typer.Argument(..., help="File to calculate checksum for."),
    algorithm: str = typer.Option("sha256", "--algorithm", "-a", help="Hash algorithm."),
) -> None:
    """Calculate a file's checksum."""
    from .client import calculate_checksum

    try:
        result = calculate_checksum(path, algorithm=algorithm)
        print_success(f"{result['algorithm']}: {result['checksum']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def meta(
    path: str = typer.Argument(..., help="File or directory path."),
) -> None:
    """Show detailed metadata for a file or directory."""
    from .client import get_metadata

    try:
        result = get_metadata(path)
        print_json(result, title="Metadata")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def volumes() -> None:
    """List configured volumes and their accessibility."""
    from .client import get_volumes

    try:
        rows = get_volumes()
        print_table(rows, title="Configured Volumes")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Run a health check on the filesystem service."""
    from copilot_cli.shared.output import print_health

    from .client import health as _health

    try:
        result = _health()
        print_health("filesystem", result["healthy"], result)
        for vol in result.get("volumes", []):
            print_health(f"  {vol['volume']}", vol["accessible"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
