"""System monitoring service - CPU, memory, disk metrics via subprocess."""

from __future__ import annotations

import platform
import subprocess
from typing import Any

import httpx

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError

SERVICE = "monitoring"


def _run_command(cmd: list[str], timeout: int = 10) -> str:
    """Run a shell command and return its stdout.

    Args:
        cmd: Command and arguments list.
        timeout: Seconds to wait for completion.

    Returns:
        Stripped stdout text.

    Raises:
        CopilotError: If the command fails.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise CopilotError(
            f"Command timed out after {timeout}s: {' '.join(cmd)}",
            service=SERVICE,
        )
    except FileNotFoundError:
        raise CopilotError(
            f"Command not found: {cmd[0]}",
            service=SERVICE,
            hint="This command may not be available on your OS.",
        )
    except Exception as exc:
        raise CopilotError(f"Command failed: {exc}", service=SERVICE) from exc


def _parse_cpu_usage() -> float:
    """Parse CPU usage percentage from system commands.

    Returns:
        CPU usage as a float percentage (0-100).
    """
    system = platform.system()
    if system == "Darwin":
        output = _run_command(["top", "-l", "1", "-n", "0", "-s", "0"])
        for line in output.splitlines():
            if "CPU usage" in line:
                # Format: "CPU usage: X.X% user, Y.Y% sys, Z.Z% idle"
                parts = line.split(",")
                for part in parts:
                    if "idle" in part:
                        idle = float(part.strip().split("%")[0].strip())
                        return round(100.0 - idle, 1)
        return 0.0
    else:
        # Linux fallback
        output = _run_command(["top", "-bn1"])
        for line in output.splitlines():
            if "Cpu(s)" in line or "%Cpu" in line:
                parts = line.split(",")
                for part in parts:
                    if "id" in part:
                        idle = float(part.strip().split()[0])
                        return round(100.0 - idle, 1)
        return 0.0


def _parse_memory_usage() -> dict[str, Any]:
    """Parse memory usage from system commands.

    Returns:
        Dict with used_percent, used_gb, total_gb.
    """
    system = platform.system()
    if system == "Darwin":
        output = _run_command(["vm_stat"])
        page_size = 16384  # default macOS page size
        stats: dict[str, int] = {}
        for line in output.splitlines():
            if "page size of" in line:
                try:
                    page_size = int(line.split("page size of")[1].strip().rstrip("."))
                except (ValueError, IndexError):
                    pass
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip().lower()
                try:
                    val = int(parts[1].strip().rstrip("."))
                    stats[key] = val
                except ValueError:
                    pass

        free_pages = stats.get("pages free", 0)
        active_pages = stats.get("pages active", 0)
        inactive_pages = stats.get("pages inactive", 0)
        wired_pages = stats.get("pages wired down", 0)
        speculative_pages = stats.get("pages speculative", 0)

        total_pages = free_pages + active_pages + inactive_pages + wired_pages + speculative_pages
        used_pages = active_pages + wired_pages

        total_gb = round((total_pages * page_size) / (1024**3), 2)
        used_gb = round((used_pages * page_size) / (1024**3), 2)
        used_pct = round((used_pages / total_pages) * 100, 1) if total_pages > 0 else 0.0

        return {
            "used_percent": used_pct,
            "used_gb": used_gb,
            "total_gb": total_gb,
        }
    else:
        # Linux fallback using /proc/meminfo
        output = _run_command(["cat", "/proc/meminfo"])
        mem: dict[str, int] = {}
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val_str = parts[1].strip().split()[0]
                try:
                    mem[key] = int(val_str)
                except ValueError:
                    pass

        total_kb = mem.get("MemTotal", 0)
        available_kb = mem.get("MemAvailable", 0)
        used_kb = total_kb - available_kb
        total_gb = round(total_kb / (1024**2), 2)
        used_gb = round(used_kb / (1024**2), 2)
        used_pct = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0.0

        return {
            "used_percent": used_pct,
            "used_gb": used_gb,
            "total_gb": total_gb,
        }


def _parse_disk_usage() -> list[dict[str, Any]]:
    """Parse disk usage from the ``df`` command.

    Returns:
        List of dicts with filesystem, size, used, available, use_percent, mount.
    """
    output = _run_command(["df", "-h"])
    results: list[dict[str, Any]] = []
    lines = output.splitlines()

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        # Skip virtual and small filesystems
        mount = parts[-1]
        if mount in ("/dev", "/dev/shm", "/run", "/sys", "/proc"):
            continue
        # Only include real mounts
        filesystem = parts[0]
        if not filesystem.startswith("/") and not filesystem.startswith("map"):
            continue

        try:
            use_pct = float(parts[-2].rstrip("%"))
        except (ValueError, IndexError):
            use_pct = 0.0

        results.append(
            {
                "filesystem": filesystem,
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": use_pct,
                "mount": mount,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_system_metrics() -> dict[str, Any]:
    """Collect CPU, memory, and disk usage metrics.

    Returns:
        Dict with cpu, memory, and disk sections.
    """
    cpu = _parse_cpu_usage()
    memory = _parse_memory_usage()
    disks = _parse_disk_usage()

    return {
        "cpu": {"usage_percent": cpu},
        "memory": memory,
        "disk": disks,
    }


def check_service_health(
    services: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Check if services are responding via HTTP health probes.

    Args:
        services: List of dicts with ``name`` and ``url`` keys.

    Returns:
        List of dicts with name, url, healthy, status_code, and response_ms.
    """
    results: list[dict[str, Any]] = []

    for svc in services:
        name = svc.get("name", "unknown")
        url = svc.get("url", "")
        try:
            resp = httpx.get(url, timeout=5.0, follow_redirects=True)
            results.append(
                {
                    "name": name,
                    "url": url,
                    "healthy": resp.is_success,
                    "status_code": resp.status_code,
                    "response_ms": round(resp.elapsed.total_seconds() * 1000, 1),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "name": name,
                    "url": url,
                    "healthy": False,
                    "status_code": None,
                    "error": str(exc),
                }
            )

    return results


def get_alerts(
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Compare current metrics against thresholds and return any alerts.

    Args:
        thresholds: Dict with optional keys ``cpu``, ``memory``, ``disk``
            as percentage thresholds.  Falls back to settings defaults.

    Returns:
        List of alert dicts with level, metric, current, threshold, message.
    """
    settings = get_settings()

    if thresholds is None:
        thresholds = {}

    cpu_thresh = thresholds.get("cpu", float(settings.cpu_alert_threshold))
    mem_thresh = thresholds.get("memory", float(settings.memory_alert_threshold))
    disk_thresh = thresholds.get("disk", float(settings.disk_alert_threshold))

    metrics = get_system_metrics()
    alerts: list[dict[str, Any]] = []

    cpu_pct = metrics["cpu"]["usage_percent"]
    if cpu_pct >= cpu_thresh:
        alerts.append(
            {
                "level": "warning" if cpu_pct < 95 else "critical",
                "metric": "cpu",
                "current": cpu_pct,
                "threshold": cpu_thresh,
                "message": f"CPU usage at {cpu_pct}% (threshold: {cpu_thresh}%)",
            }
        )

    mem_pct = metrics["memory"]["used_percent"]
    if mem_pct >= mem_thresh:
        alerts.append(
            {
                "level": "warning" if mem_pct < 95 else "critical",
                "metric": "memory",
                "current": mem_pct,
                "threshold": mem_thresh,
                "message": f"Memory usage at {mem_pct}% (threshold: {mem_thresh}%)",
            }
        )

    for disk in metrics["disk"]:
        disk_pct = disk["use_percent"]
        if disk_pct >= disk_thresh:
            alerts.append(
                {
                    "level": "warning" if disk_pct < 95 else "critical",
                    "metric": "disk",
                    "current": disk_pct,
                    "threshold": disk_thresh,
                    "message": (f"Disk {disk['mount']} at {disk_pct}% (threshold: {disk_thresh}%)"),
                }
            )

    return alerts


def health() -> dict[str, Any]:
    """Return overall monitoring service health.

    Returns:
        Dict with ``healthy`` boolean and basic metrics.
    """
    try:
        metrics = get_system_metrics()
        return {
            "healthy": True,
            "cpu_percent": metrics["cpu"]["usage_percent"],
            "memory_percent": metrics["memory"]["used_percent"],
        }
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}
