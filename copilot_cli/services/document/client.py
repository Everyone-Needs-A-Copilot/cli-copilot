"""Document management service - lightweight local filesystem document operations."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from copilot_cli.shared.errors import NotFoundError, ValidationError

SERVICE = "document"


def _format_timestamp(ts: float) -> str:
    """Convert a POSIX timestamp to an ISO-8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_documents(
    path: str,
    query: str,
    extension: str | None = None,
) -> list[dict[str, Any]]:
    """Search file contents under a directory for lines matching a query.

    Args:
        path: Root directory to search.
        query: Text string to search for (case-insensitive).
        extension: Optional file extension filter (e.g. ``.md``).

    Returns:
        List of dicts with keys: path, filename, line_number, line.
    """
    root = Path(path)
    if not root.is_dir():
        raise NotFoundError(f"Directory not found: {path}", service=SERVICE)

    results: list[dict[str, Any]] = []
    query_lower = query.lower()

    glob_pattern = f"*{extension}" if extension else "*"
    if extension and not extension.startswith("."):
        glob_pattern = f"*.{extension}"

    for entry in root.rglob(glob_pattern):
        if not entry.is_file():
            continue
        try:
            lines = entry.read_text(encoding="utf-8", errors="replace").splitlines()
            for idx, line in enumerate(lines, start=1):
                if query_lower in line.lower():
                    results.append(
                        {
                            "path": str(entry.resolve()),
                            "filename": entry.name,
                            "line_number": idx,
                            "line": line.strip(),
                        }
                    )
        except (OSError, UnicodeDecodeError):
            continue

    return results


def get_document(path: str) -> dict[str, Any]:
    """Read a document file and return its content with metadata.

    Args:
        path: Path to the document file.

    Returns:
        Dict with keys: path, content, size, modified.
    """
    p = Path(path)
    if not p.exists():
        raise NotFoundError(f"Document not found: {path}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}", service=SERVICE)

    st = p.stat()
    content = p.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(p.resolve()),
        "content": content,
        "size": st.st_size,
        "modified": _format_timestamp(st.st_mtime),
    }


def create_document(path: str, content: str) -> dict[str, Any]:
    """Create a new document file.

    Args:
        path: File path for the new document.
        content: Text content to write.

    Returns:
        Dict with keys: path, size, success.

    Raises:
        ValidationError: If the file already exists.
    """
    p = Path(path)
    if p.exists():
        raise ValidationError(
            f"Document already exists: {path}",
            service=SERVICE,
            hint="Use update_document to modify an existing file.",
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {
        "path": str(p.resolve()),
        "size": p.stat().st_size,
        "success": True,
    }


def update_document(path: str, content: str) -> dict[str, Any]:
    """Update an existing document file.

    Args:
        path: File path to the document.
        content: New text content.

    Returns:
        Dict with keys: path, size, success.
    """
    p = Path(path)
    if not p.exists():
        raise NotFoundError(f"Document not found: {path}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}", service=SERVICE)

    p.write_text(content, encoding="utf-8")
    return {
        "path": str(p.resolve()),
        "size": p.stat().st_size,
        "success": True,
    }


def delete_document(path: str) -> dict[str, Any]:
    """Delete a document file.

    Args:
        path: File path to the document.

    Returns:
        Dict with keys: path, success.
    """
    p = Path(path)
    if not p.exists():
        raise NotFoundError(f"Document not found: {path}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}", service=SERVICE)

    p.unlink()
    return {"path": str(p.resolve()), "success": True}


def list_collections(base_path: str) -> list[dict[str, Any]]:
    """List subdirectories as document collections.

    Args:
        base_path: Root directory to scan.

    Returns:
        List of dicts with keys: name, path, document_count, total_size.
    """
    root = Path(base_path)
    if not root.is_dir():
        raise NotFoundError(f"Directory not found: {base_path}", service=SERVICE)

    results: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        files = list(entry.rglob("*"))
        file_list = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in file_list if f.exists())

        results.append(
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "document_count": len(file_list),
                "total_size": total_size,
            }
        )

    return results


def get_stats() -> dict[str, Any]:
    """Return aggregate document statistics for the current working directory.

    Returns:
        Dict with keys: base_path, document_count, total_size_bytes,
        extensions (frequency map).
    """
    base = Path.cwd()
    extensions: dict[str, int] = {}
    total_size = 0
    doc_count = 0

    for entry in base.rglob("*"):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        doc_count += 1
        total_size += st.st_size
        ext = entry.suffix.lower() or "(none)"
        extensions[ext] = extensions.get(ext, 0) + 1

    return {
        "base_path": str(base.resolve()),
        "document_count": doc_count,
        "total_size_bytes": total_size,
        "extensions": dict(sorted(extensions.items(), key=lambda x: -x[1])),
    }


def health() -> dict[str, Any]:
    """Check that base paths are accessible.

    Returns:
        Dict with ``healthy`` boolean and path accessibility details.
    """
    cwd = Path.cwd()
    cwd_ok = cwd.is_dir() and os.access(str(cwd), os.R_OK)
    return {
        "healthy": cwd_ok,
        "cwd": str(cwd.resolve()),
        "readable": cwd_ok,
    }
