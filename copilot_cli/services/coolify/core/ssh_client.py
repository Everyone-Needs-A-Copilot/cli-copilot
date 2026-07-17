"""SSH client for server-side commands via Paramiko."""

from __future__ import annotations

from typing import Any

import paramiko

from copilot_cli.services.coolify.core.exceptions import SSHError


class SSHClient:
    """Wrapper around paramiko for executing remote commands."""

    def __init__(self, host: str, user: str = "root", port: int = 22, key_file: str | None = None):
        if not host:
            raise SSHError("SSH host is required")
        self.host = host
        self.user = user
        self.port = port
        self.key_file = key_file
        self._client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        """Establish SSH connection."""
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs: dict[str, Any] = {
                "hostname": self.host,
                "username": self.user,
                "port": self.port,
                "timeout": 10,
            }
            if self.key_file:
                kwargs["key_filename"] = self.key_file
            self._client.connect(**kwargs)
        except paramiko.AuthenticationException as e:
            raise SSHError(f"SSH authentication failed: {e}") from e
        except paramiko.SSHException as e:
            raise SSHError(f"SSH connection error: {e}") from e
        except Exception as e:
            raise SSHError(f"Cannot connect to {self.host}:{self.port}: {e}") from e

    def close(self) -> None:
        """Close SSH connection."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> SSHClient:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def execute(self, command: str, timeout: int = 30) -> str:
        """Execute a command and return stdout."""
        if not self._client:
            self.connect()
        try:
            _, stdout, stderr = self._client.exec_command(command, timeout=timeout)  # type: ignore[union-attr]
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0 and not output:
                raise SSHError(f"Command failed (exit {exit_code}): {error.strip()}")
            return output
        except paramiko.SSHException as e:
            raise SSHError(f"Command execution failed: {e}") from e

    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self._client:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()
