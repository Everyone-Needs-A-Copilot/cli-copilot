"""Docker container and system operations using the Docker SDK."""

from __future__ import annotations

from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import ConnectionError, CopilotError, NotFoundError


class DockerClient:
    """Wrapper around the Docker SDK for Python."""

    def __init__(self) -> None:
        settings = get_settings()
        self._socket: str = settings.docker_socket
        self._api: docker.DockerClient | None = None

    @property
    def api(self) -> docker.DockerClient:
        """Lazily create the Docker client connection."""
        if self._api is None:
            try:
                self._api = docker.DockerClient(base_url=f"unix://{self._socket}")
            except DockerException as exc:
                raise ConnectionError(
                    f"Cannot connect to Docker at {self._socket}: {exc}",
                    service="docker",
                    hint="Is Docker running? Check the socket path in .env.",
                ) from exc
        return self._api

    # ------------------------------------------------------------------
    # Container operations
    # ------------------------------------------------------------------

    def container_list(self, all: bool = False) -> list[dict[str, Any]]:
        """List Docker containers.

        Args:
            all: If ``True``, include stopped containers.

        Returns:
            List of dicts with container details.
        """
        try:
            containers = self.api.containers.list(all=all)
            return [
                {
                    "id": c.short_id,
                    "names": c.name,
                    "image": ",".join(c.image.tags) if c.image.tags else str(c.image.id[:12]),
                    "status": c.status,
                    "state": c.attrs.get("State", {}).get("Status", ""),
                    "ports": self._format_ports(c.ports),
                    "created": c.attrs.get("Created", ""),
                }
                for c in containers
            ]
        except DockerException as exc:
            raise CopilotError(
                f"Failed to list containers: {exc}",
                service="docker",
            ) from exc

    def container_start(self, id: str) -> dict[str, str]:
        """Start a stopped container.

        Args:
            id: Container ID or name.

        Returns:
            Dict with ``id`` and ``status``.
        """
        container = self._get_container(id)
        try:
            container.start()
            container.reload()
            return {"id": container.short_id, "status": container.status}
        except APIError as exc:
            raise CopilotError(
                f"Failed to start container {id}: {exc}",
                service="docker",
            ) from exc

    def container_stop(self, id: str, timeout: int = 10) -> dict[str, str]:
        """Stop a running container.

        Args:
            id: Container ID or name.
            timeout: Seconds to wait before killing the container.

        Returns:
            Dict with ``id`` and ``status``.
        """
        container = self._get_container(id)
        try:
            container.stop(timeout=timeout)
            container.reload()
            return {"id": container.short_id, "status": container.status}
        except APIError as exc:
            raise CopilotError(
                f"Failed to stop container {id}: {exc}",
                service="docker",
            ) from exc

    def container_restart(self, id: str, timeout: int = 10) -> dict[str, str]:
        """Restart a container.

        Args:
            id: Container ID or name.
            timeout: Seconds to wait before killing the container during restart.

        Returns:
            Dict with ``id`` and ``status``.
        """
        container = self._get_container(id)
        try:
            container.restart(timeout=timeout)
            container.reload()
            return {"id": container.short_id, "status": container.status}
        except APIError as exc:
            raise CopilotError(
                f"Failed to restart container {id}: {exc}",
                service="docker",
            ) from exc

    # ------------------------------------------------------------------
    # System operations
    # ------------------------------------------------------------------

    def system_info(self) -> dict[str, Any]:
        """Return high-level Docker daemon information.

        Returns:
            Dict with ``containers``, ``running``, ``paused``, ``stopped``,
            ``images``, ``version``, ``cpus``, ``memory_gb``, and ``os``.
        """
        try:
            info = self.api.info()
            return {
                "containers": info.get("Containers", 0),
                "running": info.get("ContainersRunning", 0),
                "paused": info.get("ContainersPaused", 0),
                "stopped": info.get("ContainersStopped", 0),
                "images": info.get("Images", 0),
                "version": self.api.version().get("Version", "unknown"),
                "cpus": info.get("NCPU", 0),
                "memory_gb": round(info.get("MemTotal", 0) / (1024**3), 2),
                "os": info.get("OperatingSystem", "unknown"),
            }
        except DockerException as exc:
            raise CopilotError(
                f"Failed to retrieve Docker info: {exc}",
                service="docker",
            ) from exc

    def health(self) -> dict[str, Any]:
        """Check Docker daemon connectivity.

        Returns:
            Dict with ``healthy`` boolean and additional details.
        """
        try:
            self.api.ping()
            info = self.system_info()
            return {
                "healthy": True,
                "version": info["version"],
                "containers": info["containers"],
            }
        except Exception as exc:
            return {
                "healthy": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_container(self, id: str):
        """Fetch a container by ID or name."""
        try:
            return self.api.containers.get(id)
        except NotFound as exc:
            raise NotFoundError(
                f"Container not found: {id}",
                service="docker",
                hint="Use 'docker ps --all' to see available containers.",
            ) from exc
        except DockerException as exc:
            raise CopilotError(
                f"Docker error looking up container {id}: {exc}",
                service="docker",
            ) from exc

    @staticmethod
    def _format_ports(ports: dict) -> str:
        """Format the container ports mapping into a readable string."""
        if not ports:
            return ""
        parts: list[str] = []
        for container_port, bindings in ports.items():
            if bindings:
                for b in bindings:
                    host = b.get("HostIp", "0.0.0.0")
                    host_port = b.get("HostPort", "")
                    parts.append(f"{host}:{host_port}->{container_port}")
            else:
                parts.append(str(container_port))
        return ", ".join(parts)
