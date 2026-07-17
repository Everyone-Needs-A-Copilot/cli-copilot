"""System services client - macOS launchctl and process management."""

from __future__ import annotations

import subprocess
from typing import Any

from copilot_cli.shared.errors import CopilotError, NotFoundError

SERVICE = "system_services"


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command and return the result.

    Args:
        cmd: Command and arguments to execute.
        check: If True, raise on non-zero exit code.

    Returns:
        CompletedProcess instance with captured stdout and stderr.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=check,
        )
    except subprocess.TimeoutExpired:
        raise CopilotError(
            f"Command timed out: {' '.join(cmd)}",
            service=SERVICE,
        )
    except subprocess.CalledProcessError as exc:
        raise CopilotError(
            f"Command failed (exit {exc.returncode}): {exc.stderr.strip() or exc.stdout.strip()}",
            service=SERVICE,
        )
    except FileNotFoundError:
        raise CopilotError(
            f"Command not found: {cmd[0]}",
            service=SERVICE,
            hint="Ensure the command is installed and on your PATH.",
        )


def _build_domain_target(service: str, domain: str) -> str:
    """Build the launchctl domain target string."""
    if domain == "system":
        return f"system/{service}"
    # user domain uses the current UID
    import os

    uid = os.getuid()
    return f"user/{uid}/{service}"


# ---------------------------------------------------------------------------
# Service management (launchctl)
# ---------------------------------------------------------------------------


def list_services(domain: str = "user") -> list[dict[str, Any]]:
    """List launchctl services by parsing ``launchctl list`` output.

    Args:
        domain: Service domain -- ``user`` or ``system``.

    Returns:
        List of dicts with keys: pid, status, label.
    """
    cmd = ["launchctl", "list"]
    result = _run(cmd)
    if result.returncode != 0:
        raise CopilotError(
            f"launchctl list failed: {result.stderr.strip()}",
            service=SERVICE,
        )

    lines = result.stdout.strip().splitlines()
    services: list[dict[str, Any]] = []
    # First line is the header: PID  Status  Label
    for line in lines[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid_str, status_str, label = parts
        services.append(
            {
                "pid": int(pid_str) if pid_str != "-" else None,
                "status": int(status_str) if status_str != "-" else None,
                "label": label,
            }
        )
    return services


def get_status(service: str, domain: str = "user") -> dict[str, Any]:
    """Get detailed status of a specific service.

    Args:
        service: The service label (e.g. ``com.apple.Spotlight``).
        domain: Service domain -- ``user`` or ``system``.

    Returns:
        Dict with status details including pid, status, and label.
    """
    all_services = list_services(domain=domain)
    for svc in all_services:
        if svc["label"] == service:
            running = svc["pid"] is not None
            return {
                "label": svc["label"],
                "pid": svc["pid"],
                "status": svc["status"],
                "running": running,
                "domain": domain,
            }
    raise NotFoundError(
        f"Service not found: {service}",
        service=SERVICE,
        hint="Use 'list' to see available services.",
    )


def start_service(service: str, domain: str = "user") -> dict[str, Any]:
    """Start a launchctl service.

    Args:
        service: The service label.
        domain: Service domain.

    Returns:
        Dict with keys: label, action, success, message.
    """
    target = _build_domain_target(service, domain)
    result = _run(["launchctl", "kickstart", "-k", target])
    success = result.returncode == 0
    return {
        "label": service,
        "action": "start",
        "success": success,
        "message": result.stderr.strip() or result.stdout.strip() or "Service started",
    }


def stop_service(service: str, domain: str = "user") -> dict[str, Any]:
    """Stop a launchctl service.

    Args:
        service: The service label.
        domain: Service domain.

    Returns:
        Dict with keys: label, action, success, message.
    """
    target = _build_domain_target(service, domain)
    result = _run(["launchctl", "kill", "SIGTERM", target])
    success = result.returncode == 0
    return {
        "label": service,
        "action": "stop",
        "success": success,
        "message": result.stderr.strip() or result.stdout.strip() or "Service stopped",
    }


def restart_service(service: str, domain: str = "user") -> dict[str, Any]:
    """Restart a launchctl service by stopping then starting it.

    Args:
        service: The service label.
        domain: Service domain.

    Returns:
        Dict with keys: label, action, success, message.
    """
    stop_result = stop_service(service, domain=domain)
    start_result = start_service(service, domain=domain)
    return {
        "label": service,
        "action": "restart",
        "success": start_result["success"],
        "message": f"stop: {stop_result['message']}; start: {start_result['message']}",
    }


def load_service(path: str, domain: str = "user") -> dict[str, Any]:
    """Load a service plist via ``launchctl load``.

    Args:
        path: Path to the plist file.
        domain: Service domain.

    Returns:
        Dict with keys: path, action, success, message.
    """
    cmd = ["launchctl", "load"]
    if domain == "user":
        cmd.append("-w")
    cmd.append(path)
    result = _run(cmd)
    success = result.returncode == 0
    return {
        "path": path,
        "action": "load",
        "success": success,
        "message": result.stderr.strip() or result.stdout.strip() or "Service loaded",
    }


def unload_service(path: str, domain: str = "user") -> dict[str, Any]:
    """Unload a service plist via ``launchctl unload``.

    Args:
        path: Path to the plist file.
        domain: Service domain.

    Returns:
        Dict with keys: path, action, success, message.
    """
    cmd = ["launchctl", "unload"]
    if domain == "user":
        cmd.append("-w")
    cmd.append(path)
    result = _run(cmd)
    success = result.returncode == 0
    return {
        "path": path,
        "action": "unload",
        "success": success,
        "message": result.stderr.strip() or result.stdout.strip() or "Service unloaded",
    }


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------


def list_processes(
    name_filter: str | None = None,
    user_only: bool = True,
) -> list[dict[str, Any]]:
    """List running processes by parsing ``ps aux`` output.

    Args:
        name_filter: Substring to filter process commands.
        user_only: If True, only show processes for the current user.

    Returns:
        List of dicts with keys: pid, user, cpu, mem, command.
    """
    cmd = ["ps", "aux"]
    result = _run(cmd)
    if result.returncode != 0:
        raise CopilotError(
            f"ps command failed: {result.stderr.strip()}",
            service=SERVICE,
        )

    import os
    import pwd

    current_user = pwd.getpwuid(os.getuid()).pw_name

    lines = result.stdout.strip().splitlines()
    processes: list[dict[str, Any]] = []
    # Header: USER PID %CPU %MEM VSZ RSS TT STAT STARTED TIME COMMAND
    for line in lines[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue

        user = parts[0]
        pid = parts[1]
        cpu = parts[2]
        mem = parts[3]
        command = parts[10]

        if user_only and user != current_user:
            continue

        if name_filter and name_filter.lower() not in command.lower():
            continue

        processes.append(
            {
                "pid": int(pid),
                "user": user,
                "cpu": float(cpu),
                "mem": float(mem),
                "command": command,
            }
        )

    return processes


def get_process_info(pid: int) -> dict[str, Any]:
    """Get detailed information for a specific process by PID.

    Args:
        pid: The process ID.

    Returns:
        Dict with keys: pid, user, cpu, mem, command, started, time, stat.
    """
    cmd = ["ps", "-p", str(pid), "-o", "user,pid,%cpu,%mem,vsz,rss,stat,started,time,command"]
    result = _run(cmd)
    if result.returncode != 0 or len(result.stdout.strip().splitlines()) < 2:
        raise NotFoundError(
            f"Process not found: PID {pid}",
            service=SERVICE,
        )

    lines = result.stdout.strip().splitlines()
    parts = lines[1].split(None, 9)
    if len(parts) < 10:
        raise CopilotError(
            f"Unexpected ps output for PID {pid}",
            service=SERVICE,
        )

    return {
        "pid": int(parts[1]),
        "user": parts[0],
        "cpu": float(parts[2]),
        "mem": float(parts[3]),
        "vsz": int(parts[4]),
        "rss": int(parts[5]),
        "stat": parts[6],
        "started": parts[7],
        "time": parts[8],
        "command": parts[9],
    }


def health() -> dict[str, Any]:
    """Return health status for the system services module.

    Returns:
        Dict with keys: status, healthy, launchctl_available, process_count.
    """
    launchctl_ok = False
    try:
        result = _run(["launchctl", "list"])
        launchctl_ok = result.returncode == 0
    except CopilotError:
        pass

    ps_ok = False
    process_count = 0
    try:
        result = _run(["ps", "aux"])
        ps_ok = result.returncode == 0
        if ps_ok:
            process_count = max(0, len(result.stdout.strip().splitlines()) - 1)
    except CopilotError:
        pass

    healthy = launchctl_ok and ps_ok
    return {
        "status": "healthy" if healthy else "unhealthy",
        "healthy": healthy,
        "launchctl_available": launchctl_ok,
        "ps_available": ps_ok,
        "process_count": process_count,
    }
