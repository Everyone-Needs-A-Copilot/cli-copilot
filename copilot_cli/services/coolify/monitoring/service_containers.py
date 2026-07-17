"""Service container discovery and log retrieval via SSH."""

from __future__ import annotations

from dataclasses import dataclass

from copilot_cli.services.coolify.core.ssh_client import SSHClient


@dataclass
class ContainerInfo:
    name: str = ""
    container_id: str = ""
    image: str = ""
    status: str = ""
    service_component: str = ""


def discover_service_containers(ssh: SSHClient | None, service_uuid: str) -> list[ContainerInfo]:
    """Find all Docker containers belonging to a Coolify service.

    Strategy:
    1. Filter by Docker label coolify.serviceId={uuid}
    2. Fallback: search container names for UUID substring
    3. Return empty list if SSH unavailable
    """
    if not ssh:
        return []

    containers: list[ContainerInfo] = []
    try:
        # Try label-based discovery first (Coolify labels its containers)
        output = ssh.execute(
            f'docker ps -a --filter "label=coolify.serviceId={service_uuid}" '
            f'--format "{{{{.Names}}}}|{{{{.ID}}}}|{{{{.Image}}}}|{{{{.Status}}}}"'
        )
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                name = parts[0].strip()
                # Extract component name from container name (e.g., "svc-uuid-formbricks" -> "formbricks")
                component = name.rsplit("-", 1)[-1] if "-" in name else name
                containers.append(
                    ContainerInfo(
                        name=name,
                        container_id=parts[1].strip()[:12],
                        image=parts[2].strip(),
                        status=parts[3].strip(),
                        service_component=component,
                    )
                )

        if containers:
            return containers

        # Fallback: search by UUID substring in container names
        output = ssh.execute('docker ps -a --format "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}"')
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                name = parts[0].strip()
                if service_uuid in name or service_uuid.replace("-", "") in name:
                    component = name.rsplit("-", 1)[-1] if "-" in name else name
                    containers.append(
                        ContainerInfo(
                            name=name,
                            container_id=parts[1].strip()[:12],
                            image=parts[2].strip(),
                            status=parts[3].strip(),
                            service_component=component,
                        )
                    )
    except Exception:
        pass

    return containers


def get_service_container_logs(ssh: SSHClient | None, container_name: str, lines: int = 200) -> str:
    """Retrieve logs from a specific container via docker logs."""
    if not ssh:
        return ""
    try:
        return ssh.execute(f"docker logs --tail {lines} {container_name}")
    except Exception:
        return ""


def get_all_service_logs(
    ssh: SSHClient | None, service_uuid: str, lines: int = 200
) -> dict[str, str]:
    """Retrieve logs from ALL containers in a service, keyed by container name."""
    if not ssh:
        return {}

    containers = discover_service_containers(ssh, service_uuid)
    logs: dict[str, str] = {}
    for c in containers:
        log_text = get_service_container_logs(ssh, c.name, lines)
        if log_text:
            logs[c.name] = log_text
    return logs
