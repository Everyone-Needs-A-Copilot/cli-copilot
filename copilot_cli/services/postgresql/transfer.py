"""Database dump / restore primitives.

Two operations:

- :func:`remote_pg_dump` runs ``pg_dump`` inside the database's container on a
  remote host via SSH, streaming the dump to a local file. Uses the version of
  ``pg_dump`` shipped inside the container, so there is no client-server
  version skew to worry about.
- :func:`local_pg_restore` runs ``pg_restore`` (custom-format dumps) or ``psql``
  (plain SQL dumps) on the local machine against a target connection URL. The
  caller is responsible for verifying that the target is local before invoking
  this function — see :mod:`copilot_cli.services.postgresql.safety`.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from copilot_cli.shared.errors import CopilotError


@dataclass(frozen=True)
class SSHTarget:
    """Connection details for the remote host that runs ``docker exec``."""

    user: str
    host: str
    port: int = 22
    key_file: str | None = None

    def args(self) -> list[str]:
        out = ["ssh"]
        if self.key_file:
            out += ["-i", self.key_file]
        out += [
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{self.user}@{self.host}",
        ]
        return out


def remote_pg_dump(
    *,
    ssh: SSHTarget,
    container: str,
    db_user: str,
    db_name: str,
    output_path: Path,
    fmt: str = "custom",
    schema_only: bool = False,
    data_only: bool = False,
    table: str | None = None,
) -> dict:
    """Stream a ``pg_dump`` from a remote container into *output_path*.

    Args:
        ssh: SSH connection details for the host running the container.
        container: Container name (Coolify uses the database UUID as the
            container name for managed Postgres databases).
        db_user: Postgres role to authenticate as (uses peer auth inside the
            container, so no password is needed).
        db_name: Postgres database to dump.
        output_path: Local file to write the dump to. Parent directories are
            created if missing.
        fmt: ``"custom"`` (default; ``-Fc``, restorable with ``pg_restore``) or
            ``"plain"`` (``-Fp``, restorable with ``psql``).
        schema_only: Pass ``--schema-only`` to dump DDL only.
        data_only: Pass ``--data-only`` to dump rows only.
        table: If set, dump only this table.

    Returns:
        Dict with ``path``, ``size_bytes``, ``format``.

    Raises:
        CopilotError: If ``pg_dump`` exits non-zero. The partial output file is
            removed before raising.
    """
    if fmt not in ("custom", "plain"):
        raise CopilotError(f"Invalid dump format: {fmt!r}", service="postgresql")
    if schema_only and data_only:
        raise CopilotError(
            "--schema-only and --data-only are mutually exclusive",
            service="postgresql",
        )

    pg_args: list[str] = ["pg_dump", "-U", db_user, "-d", db_name, "--no-owner", "--no-acl"]
    pg_args += ["-Fc"] if fmt == "custom" else ["-Fp"]
    if schema_only:
        pg_args.append("--schema-only")
    if data_only:
        pg_args.append("--data-only")
    if table:
        pg_args += ["-t", table]

    remote_cmd = (
        "docker exec " + shlex.quote(container) + " " + " ".join(shlex.quote(a) for a in pg_args)
    )
    cmd = [*ssh.args(), remote_cmd]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)

    if proc.returncode != 0:
        # Clean up an empty partial file so a failed dump doesn't leave a misleading
        # zero-byte artifact behind. A non-empty partial is preserved for debugging.
        if output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CopilotError(
            f"pg_dump failed (exit {proc.returncode}): {stderr}",
            service="postgresql",
            hint="Check that the container is running and the role has access.",
        )

    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "format": fmt,
    }


def local_pg_dump(
    *,
    source_url: str,
    output_path: Path,
    fmt: str = "custom",
    schema_only: bool = False,
    data_only: bool = False,
    table: str | None = None,
) -> dict:
    """Run ``pg_dump`` on the local machine against *source_url*.

    Mirrors :func:`remote_pg_dump` but without the SSH+docker indirection —
    used for local-to-local transitions.

    Args:
        source_url: Connection URL of the source database.
        output_path: Local file to write the dump to.
        fmt: ``"custom"`` or ``"plain"``.
        schema_only: Pass ``--schema-only``.
        data_only: Pass ``--data-only``.
        table: If set, dump only this table.

    Returns:
        Dict with ``path``, ``size_bytes``, ``format``.
    """
    if fmt not in ("custom", "plain"):
        raise CopilotError(f"Invalid dump format: {fmt!r}", service="postgresql")
    if schema_only and data_only:
        raise CopilotError(
            "--schema-only and --data-only are mutually exclusive",
            service="postgresql",
        )

    cmd: list[str] = ["pg_dump", "--no-owner", "--no-acl"]
    cmd += ["-Fc"] if fmt == "custom" else ["-Fp"]
    if schema_only:
        cmd.append("--schema-only")
    if data_only:
        cmd.append("--data-only")
    if table:
        cmd += ["-t", table]
    cmd += ["-d", source_url]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)

    if proc.returncode != 0:
        if output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CopilotError(
            f"pg_dump failed (exit {proc.returncode}): {stderr}",
            service="postgresql",
        )

    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "format": fmt,
    }


def detect_dump_format(path: Path) -> str:
    """Return ``"custom"`` for a ``pg_dump -Fc`` archive, ``"plain"`` otherwise.

    Custom-format archives start with the ASCII bytes ``PGDMP``.
    """
    with path.open("rb") as fh:
        head = fh.read(5)
    return "custom" if head == b"PGDMP" else "plain"


def local_pg_restore(
    *,
    dump_path: Path,
    target_url: str,
    clean: bool = False,
) -> dict:
    """Restore *dump_path* into the database at *target_url* on the local host.

    Picks ``pg_restore`` for custom-format dumps and ``psql`` for plain SQL.

    The caller MUST have already validated that ``target_url`` points at a
    local, non-tunneled database. This function does not enforce locality —
    use :func:`copilot_cli.services.postgresql.safety.assert_local_writeable`
    before calling.

    Args:
        dump_path: Path to the dump file.
        target_url: PostgreSQL connection URL of the target database.
        clean: For custom-format dumps, pass ``--clean --if-exists`` so the
            restore drops existing objects first.

    Returns:
        Dict with ``tool`` (``"pg_restore"`` or ``"psql"``) and the last few
        lines of the tool's stderr for diagnostics.
    """
    if not dump_path.exists():
        raise CopilotError(f"Dump file not found: {dump_path}", service="postgresql")

    fmt = detect_dump_format(dump_path)
    if fmt == "custom":
        cmd = ["pg_restore", "--no-owner", "--no-acl", "-d", target_url]
        if clean:
            cmd += ["--clean", "--if-exists"]
        cmd.append(str(dump_path))
    else:
        cmd = ["psql", "-d", target_url, "-v", "ON_ERROR_STOP=1", "-f", str(dump_path)]

    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CopilotError(
            f"restore failed (exit {proc.returncode}): {stderr}",
            service="postgresql",
            hint="Check that the local database exists and the role has privileges.",
        )

    stderr_lines = proc.stderr.decode("utf-8", errors="replace").splitlines()
    return {
        "tool": "pg_restore" if fmt == "custom" else "psql",
        "format": fmt,
        "stderr_tail": stderr_lines[-5:],
    }
