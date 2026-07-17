"""Docker container monitoring via SSH."""

from __future__ import annotations

from dataclasses import dataclass

from copilot_cli.services.coolify.core.ssh_client import SSHClient


@dataclass
class ContainerStats:
    name: str = ""
    container_id: str = ""
    cpu_percent: float = 0.0
    memory_usage: str = ""
    memory_limit: str = ""
    memory_percent: float = 0.0
    net_io: str = ""
    block_io: str = ""
    status: str = ""
    image: str = ""


def get_docker_stats(ssh: SSHClient) -> list[ContainerStats]:
    """Get docker stats for all running containers."""
    containers: list[ContainerStats] = []
    try:
        output = ssh.execute(
            'docker stats --no-stream --format "{{.Name}}|{{.ID}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}"'
        )
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) >= 7:
                mem_parts = parts[3].split("/")
                c = ContainerStats(
                    name=parts[0].strip(),
                    container_id=parts[1].strip()[:12],
                    cpu_percent=float(parts[2].strip().rstrip("%")),
                    memory_usage=mem_parts[0].strip() if len(mem_parts) > 0 else "",
                    memory_limit=mem_parts[1].strip() if len(mem_parts) > 1 else "",
                    memory_percent=float(parts[4].strip().rstrip("%")),
                    net_io=parts[5].strip(),
                    block_io=parts[6].strip(),
                )
                containers.append(c)
    except Exception:
        pass

    # Get status for each container
    try:
        ps_output = ssh.execute('docker ps -a --format "{{.Names}}|{{.Status}}|{{.Image}}"')
        status_map: dict[str, str] = {}
        image_map: dict[str, str] = {}
        for line in ps_output.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                status_map[parts[0].strip()] = parts[1].strip()
                image_map[parts[0].strip()] = parts[2].strip()

        for c in containers:
            c.status = status_map.get(c.name, "")
            c.image = image_map.get(c.name, "")
    except Exception:
        pass

    return containers


def get_docker_ps(ssh: SSHClient) -> list[dict]:
    """Get docker ps output for all containers."""
    containers: list[dict] = []
    try:
        output = ssh.execute(
            'docker ps -a --format "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}|{{.Ports}}|{{.CreatedAt}}"'
        )
        for line in output.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 6:
                containers.append(
                    {
                        "name": parts[0].strip(),
                        "id": parts[1].strip()[:12],
                        "image": parts[2].strip(),
                        "status": parts[3].strip(),
                        "ports": parts[4].strip(),
                        "created": parts[5].strip(),
                    }
                )
    except Exception:
        pass
    return containers


def get_service_docker_stats(ssh: SSHClient | None, service_uuid: str) -> list[ContainerStats]:
    """Get docker stats filtered to containers belonging to a specific service."""
    if not ssh:
        return []
    from copilot_cli.services.coolify.monitoring.service_containers import (
        discover_service_containers,
    )

    service_containers = discover_service_containers(ssh, service_uuid)
    if not service_containers:
        return []

    all_stats = get_docker_stats(ssh)
    service_names = {c.name for c in service_containers}
    return [s for s in all_stats if s.name in service_names]
