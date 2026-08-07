"""Shell command execution with security guardrails."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError, ValidationError
from copilot_cli.shared.errors import TimeoutError as CopilotTimeoutError

# Commands that are never allowed, regardless of context.
_DANGEROUS_PATTERNS: list[str] = [
    "rm -rf /",
    "format",
    "fdisk",
    "mkfs",
]


class ShellClient:
    """Execute shell commands and manage scripts with safety checks."""

    def __init__(self) -> None:
        settings = get_settings()
        self._scripts_path: str = settings.shell_scripts_path
        self._default_timeout: int = settings.shell_timeout

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_command(command: str) -> None:
        """Reject commands that match dangerous patterns.

        Raises:
            ValidationError: If the command is blocked.
        """
        lower = command.lower()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in lower:
                raise ValidationError(
                    f"Blocked dangerous command pattern: '{pattern}'",
                    service="shell",
                    hint="This command has been rejected for safety reasons.",
                )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def execute(
        self,
        command: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a shell command.

        Args:
            command: The command to run.
            args: Optional additional arguments appended to the command.
            working_dir: Working directory for the process.
            timeout: Maximum execution time in seconds.
            env: Extra environment variables merged with the current env.

        Returns:
            Dict with ``exit_code``, ``stdout``, and ``stderr``.

        Raises:
            ValidationError: If the command is blocked.
            CopilotTimeoutError: If the command exceeds *timeout*.
            CopilotError: On any other execution failure.
        """
        full_command = command
        if args:
            full_command = f"{command} {' '.join(args)}"

        self._validate_command(full_command)

        run_env: dict[str, str] | None = None
        if env:
            run_env = {**os.environ, **env}

        try:
            proc = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                env=run_env,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            raise CopilotTimeoutError(
                f"Command timed out after {timeout}s: {command}",
                service="shell",
                hint="Increase --timeout or simplify the command.",
            ) from exc
        except Exception as exc:
            raise CopilotError(
                f"Command execution failed: {exc}",
                service="shell",
            ) from exc

    def run_script(
        self,
        script_name: str,
        args: list[str] | None = None,
        timeout: int = 3600,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Locate and execute a script from the configured script paths.

        Args:
            script_name: Filename of the script (e.g. ``deploy.sh``).
            args: Arguments to pass to the script.
            timeout: Maximum execution time in seconds.
            env: Extra environment variables.

        Returns:
            Dict with ``exit_code``, ``stdout``, ``stderr``, and ``script_path``.

        Raises:
            CopilotError: If the script cannot be found or fails.
        """
        script_path = self._find_script(script_name)
        if script_path is None:
            raise CopilotError(
                f"Script not found: {script_name}",
                service="shell",
                hint=f"Searched in: {', '.join(self._search_paths())}",
            )

        result = self.execute(
            command=str(script_path),
            args=args,
            working_dir=str(script_path.parent),
            timeout=timeout,
            env=env,
        )
        result["script_path"] = str(script_path)
        return result

    def find_scripts(
        self,
        pattern: str = "*.sh",
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find scripts matching a glob pattern.

        Args:
            pattern: Glob pattern (default ``*.sh``).
            path: Specific directory to search. If ``None``, searches all
                  configured script paths.

        Returns:
            List of dicts with ``name``, ``path``, ``size``, ``modified``,
            and ``executable`` for each matching file.
        """
        dirs = [Path(path)] if path else [Path(p) for p in self._search_paths()]
        results: list[dict[str, Any]] = []

        for search_dir in dirs:
            if not search_dir.is_dir():
                continue
            for match in search_dir.rglob(pattern):
                if not match.is_file():
                    continue
                stat = match.stat()
                results.append(
                    {
                        "name": match.name,
                        "path": str(match),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "executable": os.access(match, os.X_OK),
                    }
                )

        return results

    def list_processes(
        self,
        pattern: str | None = None,
        user: str | None = None,
    ) -> str:
        """List running processes, optionally filtered.

        Args:
            pattern: Grep pattern to filter process names.
            user: Limit to processes owned by this user.

        Returns:
            Raw stdout text from the ``ps`` command.
        """
        cmd = "ps aux"
        if user:
            cmd = f"ps -u {user} -o pid,user,%cpu,%mem,command"

        result = self.execute(command=cmd, timeout=30)
        stdout: str = result["stdout"]

        if pattern and stdout:
            lines = stdout.splitlines()
            header = lines[0] if lines else ""
            filtered = [ln for ln in lines[1:] if pattern.lower() in ln.lower()]
            stdout = "\n".join([header, *filtered]) if filtered else header

        return stdout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_paths(self) -> list[str]:
        """Return the ordered list of directories to search for scripts."""
        paths: list[str] = []
        if self._scripts_path:
            paths.append(self._scripts_path)
        paths.append("./scripts/")
        return paths

    def _find_script(self, name: str) -> Path | None:
        """Search configured paths for a script by name."""
        for base in self._search_paths():
            candidate = Path(base) / name
            if candidate.is_file():
                return candidate
        return None


def health() -> dict[str, Any]:
    """Return health status for the shell service.

    A local capability check: confirms subprocess execution works,
    independent of any specific command.

    Returns:
        Dict with keys: healthy, shell.
    """
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", "true"],
            capture_output=True,
            timeout=5,
        )
        return {"healthy": proc.returncode == 0, "shell": "/bin/sh"}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}
