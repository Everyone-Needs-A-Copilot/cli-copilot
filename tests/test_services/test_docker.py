"""Tests for the Docker service -- client layer and CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from docker.errors import APIError, DockerException, NotFound
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.docker.client import DockerClient
from copilot_cli.shared.errors import ConnectionError, CopilotError, NotFoundError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_docker_api():
    """Return a MagicMock that impersonates docker.DockerClient."""
    api = MagicMock()
    api.ping.return_value = True
    return api


@pytest.fixture
def docker_client(mock_docker_api):
    """Return a DockerClient with a pre-wired mock API so it never
    touches the real Docker socket."""
    client = DockerClient()
    client._api = mock_docker_api
    return client


def _make_container(
    short_id: str = "abc123",
    name: str = "my-container",
    status: str = "running",
    image_tags: list[str] | None = None,
    ports: dict | None = None,
    attrs: dict | None = None,
):
    """Helper to build a fake container object."""
    c = MagicMock()
    c.short_id = short_id
    c.name = name
    c.status = status
    image = MagicMock()
    image.tags = image_tags if image_tags is not None else ["nginx:latest"]
    image.id = "sha256:aabbccdd1234"
    c.image = image
    c.ports = ports or {}
    c.attrs = attrs or {"State": {"Status": status}, "Created": "2025-01-01T00:00:00"}
    return c


# ------------------------------------------------------------------ #
# Client -- container_list
# ------------------------------------------------------------------ #


class TestContainerList:
    """Tests for DockerClient.container_list()."""

    def test_list_running_containers(self, docker_client, mock_docker_api):
        """container_list returns formatted dicts for each container."""
        containers = [
            _make_container("aaa111", "web", "running", ["nginx:latest"]),
            _make_container("bbb222", "db", "running", ["postgres:16"]),
        ]
        mock_docker_api.containers.list.return_value = containers

        result = docker_client.container_list(all=False)

        mock_docker_api.containers.list.assert_called_once_with(all=False)
        assert len(result) == 2
        assert result[0]["id"] == "aaa111"
        assert result[0]["names"] == "web"
        assert result[1]["image"] == "postgres:16"

    def test_list_all_containers(self, docker_client, mock_docker_api):
        """container_list(all=True) passes the flag through."""
        mock_docker_api.containers.list.return_value = [
            _make_container(status="exited"),
        ]

        result = docker_client.container_list(all=True)

        mock_docker_api.containers.list.assert_called_once_with(all=True)
        assert len(result) == 1
        assert result[0]["status"] == "exited"

    def test_list_empty(self, docker_client, mock_docker_api):
        """container_list returns empty list when no containers exist."""
        mock_docker_api.containers.list.return_value = []

        result = docker_client.container_list()

        assert result == []

    def test_list_image_without_tags(self, docker_client, mock_docker_api):
        """container_list falls back to image id[:12] when tags are empty."""
        container = _make_container(image_tags=[])
        mock_docker_api.containers.list.return_value = [container]

        result = docker_client.container_list()

        assert result[0]["image"] == "sha256:aabbc"

    def test_list_docker_exception_raises_copilot_error(self, docker_client, mock_docker_api):
        """container_list wraps DockerException in CopilotError."""
        mock_docker_api.containers.list.side_effect = DockerException("boom")

        with pytest.raises(CopilotError, match="Failed to list containers"):
            docker_client.container_list()


# ------------------------------------------------------------------ #
# Client -- container_start
# ------------------------------------------------------------------ #


class TestContainerStart:
    """Tests for DockerClient.container_start()."""

    def test_start_success(self, docker_client, mock_docker_api):
        """container_start starts the container and returns new status."""
        container = _make_container("abc123", status="exited")
        mock_docker_api.containers.get.return_value = container
        # After start + reload, status changes
        container.status = "running"

        result = docker_client.container_start(id="abc123")

        container.start.assert_called_once()
        container.reload.assert_called_once()
        assert result["id"] == "abc123"
        assert result["status"] == "running"

    def test_start_api_error_raises_copilot_error(self, docker_client, mock_docker_api):
        """container_start wraps APIError in CopilotError."""
        container = _make_container()
        mock_docker_api.containers.get.return_value = container
        container.start.side_effect = APIError("start failed")

        with pytest.raises(CopilotError, match="Failed to start container"):
            docker_client.container_start(id="abc123")


# ------------------------------------------------------------------ #
# Client -- container_stop
# ------------------------------------------------------------------ #


class TestContainerStop:
    """Tests for DockerClient.container_stop()."""

    def test_stop_success(self, docker_client, mock_docker_api):
        """container_stop stops a running container."""
        container = _make_container("abc123", status="running")
        mock_docker_api.containers.get.return_value = container
        container.status = "exited"

        result = docker_client.container_stop(id="abc123", timeout=5)

        container.stop.assert_called_once_with(timeout=5)
        container.reload.assert_called_once()
        assert result["status"] == "exited"

    def test_stop_api_error_raises_copilot_error(self, docker_client, mock_docker_api):
        """container_stop wraps APIError in CopilotError."""
        container = _make_container()
        mock_docker_api.containers.get.return_value = container
        container.stop.side_effect = APIError("stop failed")

        with pytest.raises(CopilotError, match="Failed to stop container"):
            docker_client.container_stop(id="abc123")


# ------------------------------------------------------------------ #
# Client -- container_restart
# ------------------------------------------------------------------ #


class TestContainerRestart:
    """Tests for DockerClient.container_restart()."""

    def test_restart_success(self, docker_client, mock_docker_api):
        """container_restart restarts and returns updated status."""
        container = _make_container("abc123", status="running")
        mock_docker_api.containers.get.return_value = container

        result = docker_client.container_restart(id="abc123", timeout=15)

        container.restart.assert_called_once_with(timeout=15)
        container.reload.assert_called_once()
        assert result["id"] == "abc123"


# ------------------------------------------------------------------ #
# Client -- system_info
# ------------------------------------------------------------------ #


class TestSystemInfo:
    """Tests for DockerClient.system_info()."""

    def test_system_info_returns_formatted_dict(self, docker_client, mock_docker_api):
        """system_info returns a normalized info dict."""
        mock_docker_api.info.return_value = {
            "Containers": 5,
            "ContainersRunning": 3,
            "ContainersPaused": 0,
            "ContainersStopped": 2,
            "Images": 12,
            "NCPU": 8,
            "MemTotal": 16 * (1024**3),
            "OperatingSystem": "Docker Desktop",
        }
        mock_docker_api.version.return_value = {"Version": "24.0.7"}

        result = docker_client.system_info()

        assert result["containers"] == 5
        assert result["running"] == 3
        assert result["paused"] == 0
        assert result["stopped"] == 2
        assert result["images"] == 12
        assert result["version"] == "24.0.7"
        assert result["cpus"] == 8
        assert result["memory_gb"] == 16.0
        assert result["os"] == "Docker Desktop"

    def test_system_info_docker_exception(self, docker_client, mock_docker_api):
        """system_info wraps DockerException in CopilotError."""
        mock_docker_api.info.side_effect = DockerException("daemon down")

        with pytest.raises(CopilotError, match="Failed to retrieve Docker info"):
            docker_client.system_info()


# ------------------------------------------------------------------ #
# Client -- health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for DockerClient.health()."""

    def test_health_healthy(self, docker_client, mock_docker_api):
        """health() returns healthy=True when ping and info succeed."""
        mock_docker_api.ping.return_value = True
        mock_docker_api.info.return_value = {
            "Containers": 3,
            "ContainersRunning": 2,
            "ContainersPaused": 0,
            "ContainersStopped": 1,
            "Images": 5,
            "NCPU": 4,
            "MemTotal": 8 * (1024**3),
            "OperatingSystem": "Linux",
        }
        mock_docker_api.version.return_value = {"Version": "24.0.7"}

        result = docker_client.health()

        assert result["healthy"] is True
        assert result["version"] == "24.0.7"
        assert result["containers"] == 3

    def test_health_unhealthy_on_exception(self, docker_client, mock_docker_api):
        """health() returns healthy=False and error string on failure."""
        mock_docker_api.ping.side_effect = DockerException("cannot connect")

        result = docker_client.health()

        assert result["healthy"] is False
        assert "cannot connect" in result["error"]


# ------------------------------------------------------------------ #
# Client -- _get_container (NotFoundError)
# ------------------------------------------------------------------ #


class TestGetContainer:
    """Tests for DockerClient._get_container error paths."""

    def test_missing_container_raises_not_found(self, docker_client, mock_docker_api):
        """_get_container raises NotFoundError when container does not exist."""
        mock_docker_api.containers.get.side_effect = NotFound("no such container")

        with pytest.raises(NotFoundError, match="Container not found"):
            docker_client._get_container("ghost")

    def test_docker_error_raises_copilot_error(self, docker_client, mock_docker_api):
        """_get_container wraps generic DockerException in CopilotError."""
        mock_docker_api.containers.get.side_effect = DockerException("unexpected")

        with pytest.raises(CopilotError, match="Docker error looking up container"):
            docker_client._get_container("broken")


# ------------------------------------------------------------------ #
# Client -- _format_ports
# ------------------------------------------------------------------ #


class TestFormatPorts:
    """Tests for DockerClient._format_ports helper."""

    def test_empty_ports(self):
        assert DockerClient._format_ports({}) == ""

    def test_port_with_bindings(self):
        ports = {
            "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
        }
        assert DockerClient._format_ports(ports) == "0.0.0.0:8080->80/tcp"

    def test_port_without_bindings(self):
        ports = {"443/tcp": None}
        assert DockerClient._format_ports(ports) == "443/tcp"


# ------------------------------------------------------------------ #
# CLI -- docker ps
# ------------------------------------------------------------------ #


class TestDockerCLIPs:
    """CLI tests for `copilot docker ps`."""

    def test_ps_success(self, runner):
        """docker ps prints a table of containers."""
        mock_client = MagicMock()
        mock_client.container_list.return_value = [
            {
                "id": "abc123",
                "names": "web",
                "image": "nginx:latest",
                "status": "running",
                "state": "running",
                "ports": "0.0.0.0:80->80/tcp",
                "created": "2025-01-01T00:00:00",
            }
        ]

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "ps"])

        assert result.exit_code == 0
        assert "web" in result.output

    def test_ps_error_returns_exit_code_1(self, runner):
        """docker ps exits 1 on CopilotError."""
        mock_client = MagicMock()
        mock_client.container_list.side_effect = CopilotError(
            "Failed to list containers: connection refused",
            service="docker",
        )

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "ps"])

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# CLI -- docker start
# ------------------------------------------------------------------ #


class TestDockerCLIStart:
    """CLI tests for `copilot docker start`."""

    def test_start_success(self, runner):
        """docker start prints success message."""
        mock_client = MagicMock()
        mock_client.container_start.return_value = {
            "id": "abc123",
            "status": "running",
        }

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "start", "abc123"])

        assert result.exit_code == 0
        assert "running" in result.output

    def test_start_not_found_returns_exit_code_1(self, runner):
        """docker start exits 1 when container is not found."""
        mock_client = MagicMock()
        mock_client.container_start.side_effect = NotFoundError(
            "Container not found: ghost",
            service="docker",
            hint="Use 'docker ps --all' to see available containers.",
        )

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "start", "ghost"])

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# CLI -- docker stop
# ------------------------------------------------------------------ #


class TestDockerCLIStop:
    """CLI tests for `copilot docker stop`."""

    def test_stop_success(self, runner):
        """docker stop prints success message."""
        mock_client = MagicMock()
        mock_client.container_stop.return_value = {
            "id": "abc123",
            "status": "exited",
        }

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "stop", "abc123"])

        assert result.exit_code == 0
        assert "exited" in result.output


# ------------------------------------------------------------------ #
# CLI -- docker info
# ------------------------------------------------------------------ #


class TestDockerCLIInfo:
    """CLI tests for `copilot docker info`."""

    def test_info_success(self, runner):
        """docker info prints system info JSON."""
        mock_client = MagicMock()
        mock_client.system_info.return_value = {
            "containers": 5,
            "running": 3,
            "paused": 0,
            "stopped": 2,
            "images": 12,
            "version": "24.0.7",
            "cpus": 8,
            "memory_gb": 16.0,
            "os": "Docker Desktop",
        }

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "info"])

        assert result.exit_code == 0
        assert "24.0.7" in result.output

    def test_info_error_returns_exit_code_1(self, runner):
        """docker info exits 1 on CopilotError."""
        mock_client = MagicMock()
        mock_client.system_info.side_effect = CopilotError(
            "Failed to retrieve Docker info: daemon not running",
            service="docker",
        )

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "info"])

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# CLI -- docker health
# ------------------------------------------------------------------ #


class TestDockerCLIHealth:
    """CLI tests for `copilot docker health`."""

    def test_health_healthy(self, runner):
        """docker health exits 0 when daemon is reachable."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": True,
            "version": "24.0.7",
            "containers": 3,
        }

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "health"])

        assert result.exit_code == 0

    def test_health_unhealthy_exits_1(self, runner):
        """docker health exits 1 when daemon is unreachable."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": False,
            "error": "cannot connect",
        }

        with patch(
            "copilot_cli.services.docker.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["docker", "health"])

        assert result.exit_code == 1
