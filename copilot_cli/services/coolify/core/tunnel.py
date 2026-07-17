"""SSH tunnel to a Coolify-managed database container.

Coolify databases default to ``is_public = false`` — they listen on
``5432`` only on the internal Docker bridge network and are unreachable
from outside the VPS. To run a one-off query from the laptop without
flipping the DB to public, this module opens a short-lived
``ssh -L 127.0.0.1:<local>:<container_ip>:5432`` tunnel via a subprocess,
yields a connection URL pointing at ``127.0.0.1:<local>``, and tears the
tunnel down on exit.

The resulting URL is registered with the PostgreSQL safety guard as
``tunneled-remote`` so destructive SQL through that URL is still refused
even though the host portion is ``127.0.0.1``.
"""

from __future__ import annotations

import shlex
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote

from copilot_cli.services.coolify.core.exceptions import ConfigError, SSHError
from copilot_cli.services.postgresql.safety import register_tunneled, unregister_tunneled
from copilot_cli.services.postgresql.transfer import SSHTarget


@dataclass(frozen=True)
class TunnelHandle:
    """Lightweight record returned for tests / introspection."""

    local_port: int
    url: str


def _allocate_free_local_port() -> int:
    """Bind to an ephemeral port and immediately release it.

    Race-free enough for our purposes: the kernel won't hand the same port
    to another bind in the microseconds between this and the SSH ``-L`` bind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _resolve_container_ip(ssh: SSHTarget, container: str, network: str = "coolify") -> str:
    """Look up *container*'s IP on the *network* docker bridge over SSH.

    Raises:
        SSHError: If the docker inspect call fails or returns empty.
    """
    fmt = "{{ .NetworkSettings.Networks." + network + ".IPAddress }}"
    remote_cmd = "docker inspect -f " + shlex.quote(fmt) + " " + shlex.quote(container)
    proc = subprocess.run([*ssh.args(), remote_cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SSHError(f"docker inspect failed (exit {proc.returncode}): {proc.stderr.strip()}")
    ip = proc.stdout.strip()
    if not ip:
        raise SSHError(
            f"Container '{container}' has no IP on network '{network}'. "
            "Is the container running and attached to that network?"
        )
    return ip


def _wait_for_local_port(port: int, proc: subprocess.Popen, timeout: float = 10.0) -> None:
    """Block until *port* on 127.0.0.1 accepts a TCP connection.

    If *proc* exits before the port opens, raise immediately with its stderr —
    that means the ``ssh -L`` failed (bad key, bad host, etc.).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            raise SSHError(f"SSH tunnel exited with code {proc.returncode}: {stderr.strip()[:500]}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.15)
    proc.terminate()
    raise SSHError(f"SSH tunnel did not become ready on 127.0.0.1:{port} within {timeout}s")


@contextmanager
def open_tunnel(
    *,
    ssh: SSHTarget,
    container: str,
    db_user: str,
    db_password: str,
    db_name: str,
    db_port: int = 5432,
    network: str = "coolify",
    ready_timeout: float = 10.0,
) -> Iterator[str]:
    """Yield a localhost connection URL that points at a remote DB via SSH.

    The URL is registered as ``tunneled-remote`` in the safety guard for the
    duration of the context, so destructive SQL routed through it is refused.

    Args:
        ssh: SSH connection details for the host running the container.
        container: Container name (Coolify uses the DB UUID).
        db_user: Postgres role for the connection URL.
        db_password: Postgres password.
        db_name: Postgres database name.
        db_port: Remote DB port (default 5432).
        network: Docker network the container is attached to (default
            ``coolify`` — matches the Coolify default).
        ready_timeout: How long to wait for the local port to start
            accepting connections before giving up.

    Yields:
        A ``postgresql://`` URL with host ``127.0.0.1`` and an ephemeral port.

    Raises:
        SSHError: If the tunnel cannot be established.
        ConfigError: If required parameters are missing.
    """
    if not container:
        raise ConfigError("container is required to open a tunnel")
    if not ssh.host:
        raise ConfigError("ssh.host is required to open a tunnel")

    container_ip = _resolve_container_ip(ssh, container, network=network)
    local_port = _allocate_free_local_port()

    ssh_cmd = [
        *ssh.args(),
        "-N",  # no remote command
        "-L",
        f"127.0.0.1:{local_port}:{container_ip}:{db_port}",
    ]
    proc = subprocess.Popen(
        ssh_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_local_port(local_port, proc, timeout=ready_timeout)
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise

    url = (
        f"postgresql://{quote(db_user, safe='')}:"
        f"{quote(db_password, safe='')}@127.0.0.1:{local_port}/"
        f"{quote(db_name, safe='')}"
    )
    register_tunneled(url)

    try:
        yield url
    finally:
        unregister_tunneled(url)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
