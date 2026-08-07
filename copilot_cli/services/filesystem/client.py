"""Filesystem service client - local file and directory operations."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import NotFoundError, ValidationError

SERVICE = "filesystem"


def _validate_path(path: Path) -> None:
    """Ensure the resolved path falls within an allowed volume."""
    settings = get_settings()
    allowed = settings.get_allowed_volumes()
    resolved = str(path.resolve())
    if not any(resolved.startswith(vol) for vol in allowed):
        raise ValidationError(
            f"Path '{resolved}' is outside allowed volumes: {', '.join(allowed)}",
            service=SERVICE,
            hint="Update ALLOWED_VOLUMES in your .env to include this path.",
        )


def _validate_file_size(path: Path) -> None:
    """Raise if a file exceeds the configured max size."""
    settings = get_settings()
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if path.exists() and path.stat().st_size > max_bytes:
        raise ValidationError(
            f"File size exceeds limit of {settings.max_file_size_mb} MB",
            service=SERVICE,
        )


def _format_timestamp(ts: float) -> str:
    """Convert a POSIX timestamp to an ISO-8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _permissions_string(mode: int) -> str:
    """Return a unix-style permission string like 'rwxr-xr--'."""
    parts: list[str] = []
    for who in (
        stat.S_IRUSR,
        stat.S_IWUSR,
        stat.S_IXUSR,
        stat.S_IRGRP,
        stat.S_IWGRP,
        stat.S_IXGRP,
        stat.S_IROTH,
        stat.S_IWOTH,
        stat.S_IXOTH,
    ):
        parts.append(
            "r"
            if who in (stat.S_IRUSR, stat.S_IRGRP, stat.S_IROTH) and mode & who
            else "w"
            if who in (stat.S_IWUSR, stat.S_IWGRP, stat.S_IWOTH) and mode & who
            else "x"
            if who in (stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH) and mode & who
            else "-"
        )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_file(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """Read a file and return its content with metadata.

    Returns:
        Dict with keys: content, size, modified, encoding.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"File not found: {p}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {p}", service=SERVICE)
    _validate_file_size(p)

    st = p.stat()
    content = p.read_text(encoding=encoding)
    return {
        "content": content,
        "size": st.st_size,
        "modified": _format_timestamp(st.st_mtime),
        "encoding": encoding,
    }


def write_file(
    path: str, content: str, encoding: str = "utf-8", overwrite: bool = True
) -> dict[str, Any]:
    """Write content to a file, creating parent directories as needed.

    Args:
        path: Destination file path.
        content: Content to write.
        encoding: File encoding.
        overwrite: If False, raise ValidationError when destination exists.

    Returns:
        Dict with keys: path, size, success.
    """
    p = Path(path)
    _validate_path(p)
    if not overwrite and p.exists():
        raise ValidationError(
            f"Destination already exists: {p}",
            service=SERVICE,
            hint="Use --force to overwrite.",
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return {
        "path": str(p.resolve()),
        "size": p.stat().st_size,
        "success": True,
    }


def delete_file(path: str) -> dict[str, Any]:
    """Delete a file.

    Returns:
        Dict with keys: path, success.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"File not found: {p}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {p}", service=SERVICE)
    p.unlink()
    return {"path": str(p.resolve()), "success": True}


def copy_file(
    source: str,
    destination: str,
    preserve_timestamps: bool = False,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Copy a file from source to destination.

    Args:
        source: Source file path.
        destination: Destination file path.
        preserve_timestamps: Preserve source file timestamps.
        overwrite: If False, raise ValidationError when destination exists.

    Returns:
        Dict with keys: source, destination, size, success.
    """
    src = Path(source)
    dst = Path(destination)
    _validate_path(src)
    _validate_path(dst)
    if not src.exists():
        raise NotFoundError(f"Source not found: {src}", service=SERVICE)
    if not src.is_file():
        raise ValidationError(f"Source is not a file: {src}", service=SERVICE)
    _validate_file_size(src)
    if not overwrite and dst.exists():
        raise ValidationError(
            f"Destination already exists: {dst}",
            service=SERVICE,
            hint="Use --force to overwrite.",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    if preserve_timestamps:
        shutil.copy2(str(src), str(dst))
    else:
        shutil.copy(str(src), str(dst))

    return {
        "source": str(src.resolve()),
        "destination": str(dst.resolve()),
        "size": dst.stat().st_size,
        "success": True,
    }


def move_file(source: str, destination: str, overwrite: bool = True) -> dict[str, Any]:
    """Move a file from source to destination.

    Args:
        source: Source file path.
        destination: Destination file path.
        overwrite: If False, raise ValidationError when destination exists.

    Returns:
        Dict with keys: source, destination, success.
    """
    src = Path(source)
    dst = Path(destination)
    _validate_path(src)
    _validate_path(dst)
    if not src.exists():
        raise NotFoundError(f"Source not found: {src}", service=SERVICE)
    if not overwrite and dst.exists():
        raise ValidationError(
            f"Destination already exists: {dst}",
            service=SERVICE,
            hint="Use --force to overwrite.",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {
        "source": str(src.resolve()),
        "destination": str(dst.resolve()),
        "success": True,
    }


def list_directory(
    path: str,
    files_only: bool = False,
    dirs_only: bool = False,
    pattern: str | None = None,
    sort_by: str = "name",
) -> list[dict[str, Any]]:
    """List contents of a directory.

    Args:
        path: Directory path to list.
        files_only: Show only files.
        dirs_only: Show only directories.
        pattern: Glob pattern to filter entries (e.g. ``*.json``).
        sort_by: Sort key -- ``name``, ``size``, or ``modified``.

    Returns:
        List of dicts with keys: name, path, type, size, modified.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"Directory not found: {p}", service=SERVICE)
    if not p.is_dir():
        raise ValidationError(f"Not a directory: {p}", service=SERVICE)

    entries: list[Path] = list(p.glob(pattern)) if pattern else list(p.iterdir())

    results: list[dict[str, Any]] = []
    for entry in entries:
        if files_only and not entry.is_file():
            continue
        if dirs_only and not entry.is_dir():
            continue

        try:
            st = entry.stat()
        except OSError:
            continue

        results.append(
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "type": "file" if entry.is_file() else "dir" if entry.is_dir() else "other",
                "size": st.st_size,
                "modified": _format_timestamp(st.st_mtime),
            }
        )

    sort_keys = {
        "name": lambda r: r["name"].lower(),
        "size": lambda r: r["size"],
        "modified": lambda r: r["modified"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["name"])
    results.sort(key=key_fn)
    return results


def create_directory(path: str, recursive: bool = True) -> dict[str, Any]:
    """Create a directory.

    Returns:
        Dict with keys: path, success.
    """
    p = Path(path)
    _validate_path(p)
    if recursive:
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.mkdir(exist_ok=True)
    return {"path": str(p.resolve()), "success": True}


def search_files(
    path: str,
    extension: str | None = None,
    name: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
) -> list[dict[str, Any]]:
    """Recursively search for files matching given criteria.

    Args:
        path: Root directory to search.
        extension: File extension filter (e.g. ``.json``).
        name: Substring match on file name.
        min_size: Minimum file size in bytes.
        max_size: Maximum file size in bytes.

    Returns:
        List of dicts with keys: name, path, size, modified.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"Directory not found: {p}", service=SERVICE)
    if not p.is_dir():
        raise ValidationError(f"Not a directory: {p}", service=SERVICE)

    results: list[dict[str, Any]] = []
    for entry in p.rglob("*"):
        if not entry.is_file():
            continue

        if extension:
            ext = extension if extension.startswith(".") else f".{extension}"
            if entry.suffix.lower() != ext.lower():
                continue

        if name and name.lower() not in entry.name.lower():
            continue

        try:
            st = entry.stat()
        except OSError:
            continue

        if min_size is not None and st.st_size < min_size:
            continue
        if max_size is not None and st.st_size > max_size:
            continue

        results.append(
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "size": st.st_size,
                "modified": _format_timestamp(st.st_mtime),
            }
        )

    results.sort(key=lambda r: r["name"].lower())
    return results


def calculate_checksum(path: str, algorithm: str = "sha256") -> dict[str, str]:
    """Calculate the checksum of a file.

    Args:
        path: File path.
        algorithm: Hash algorithm name (sha256, md5, sha1, etc.).

    Returns:
        Dict with keys: path, algorithm, checksum.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"File not found: {p}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {p}", service=SERVICE)
    _validate_file_size(p)

    try:
        h = hashlib.new(algorithm)
    except ValueError:
        raise ValidationError(
            f"Unsupported hash algorithm: {algorithm}",
            service=SERVICE,
            hint="Try sha256, sha1, md5, or sha512.",
        )

    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)

    return {
        "path": str(p.resolve()),
        "algorithm": algorithm,
        "checksum": h.hexdigest(),
    }


def get_metadata(path: str) -> dict[str, Any]:
    """Return detailed metadata for a file or directory.

    Returns:
        Dict with keys: path, type, size, created, modified, permissions.
    """
    p = Path(path)
    _validate_path(p)
    if not p.exists():
        raise NotFoundError(f"Path not found: {p}", service=SERVICE)

    st = p.stat()
    return {
        "path": str(p.resolve()),
        "type": "file" if p.is_file() else "dir" if p.is_dir() else "other",
        "size": st.st_size,
        "created": _format_timestamp(st.st_birthtime)
        if hasattr(st, "st_birthtime")
        else _format_timestamp(st.st_ctime),
        "modified": _format_timestamp(st.st_mtime),
        "permissions": _permissions_string(st.st_mode),
    }


def get_volumes() -> list[dict[str, Any]]:
    """Check which configured volumes are accessible.

    Returns:
        List of dicts with keys: volume, accessible, exists, is_dir.
    """
    settings = get_settings()
    results: list[dict[str, Any]] = []
    for vol in settings.get_allowed_volumes():
        vp = Path(vol)
        results.append(
            {
                "volume": vol,
                "accessible": vp.is_dir() and os.access(vol, os.R_OK),
                "exists": vp.exists(),
                "is_dir": vp.is_dir(),
            }
        )
    return results


def health() -> dict[str, Any]:
    """Return health status for the filesystem service.

    Returns:
        Dict with keys: status, healthy, volumes.
    """
    volumes = get_volumes()
    accessible = [v for v in volumes if v["accessible"]]
    all_ok = len(accessible) == len(volumes) and len(volumes) > 0
    return {
        "status": "healthy" if all_ok else "degraded",
        "healthy": all_ok,
        "accessible_volumes": len(accessible),
        "total_volumes": len(volumes),
        "volumes": volumes,
    }
