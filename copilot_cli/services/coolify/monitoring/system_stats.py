"""System resource monitoring via SSH — CPU, memory, disk, load."""

from __future__ import annotations

from dataclasses import dataclass, field

from copilot_cli.services.coolify.core.ssh_client import SSHClient


@dataclass
class SystemStats:
    cpu_percent: float = 0.0
    memory_total_mb: int = 0
    memory_used_mb: int = 0
    memory_percent: float = 0.0
    swap_total_mb: int = 0
    swap_used_mb: int = 0
    swap_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_percent: float = 0.0
    load_1: float = 0.0
    load_5: float = 0.0
    load_15: float = 0.0
    disks: list[dict] = field(default_factory=list)


def get_system_stats(ssh: SSHClient) -> SystemStats:
    """Gather system resource stats via SSH."""
    stats = SystemStats()

    # CPU usage from /proc/stat (percentage of non-idle)
    try:
        cpu_output = ssh.execute(
            "grep 'cpu ' /proc/stat | awk '{usage=100-($5*100/($2+$3+$4+$5+$6+$7+$8))} END {print usage}'"
        )
        stats.cpu_percent = round(float(cpu_output.strip()), 1)
    except Exception:
        pass

    # Memory from free
    try:
        mem_output = ssh.execute("free -m | grep -E '^(Mem|Swap):'")
        for line in mem_output.strip().splitlines():
            parts = line.split()
            if parts[0] == "Mem:":
                stats.memory_total_mb = int(parts[1])
                stats.memory_used_mb = int(parts[2])
                if stats.memory_total_mb > 0:
                    stats.memory_percent = round(
                        stats.memory_used_mb / stats.memory_total_mb * 100, 1
                    )
            elif parts[0] == "Swap:":
                stats.swap_total_mb = int(parts[1])
                stats.swap_used_mb = int(parts[2])
                if stats.swap_total_mb > 0:
                    stats.swap_percent = round(stats.swap_used_mb / stats.swap_total_mb * 100, 1)
    except Exception:
        pass

    # Disk usage from df
    try:
        disk_output = ssh.execute("df -BG --output=source,size,used,pcent,target | grep '^/dev'")
        for line in disk_output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                total = float(parts[1].rstrip("G"))
                used = float(parts[2].rstrip("G"))
                pct = float(parts[3].rstrip("%"))
                mount = parts[4]
                stats.disks.append(
                    {
                        "device": parts[0],
                        "mount": mount,
                        "total_gb": total,
                        "used_gb": used,
                        "percent": pct,
                    }
                )
                if mount == "/":
                    stats.disk_total_gb = total
                    stats.disk_used_gb = used
                    stats.disk_percent = pct
    except Exception:
        pass

    # Load averages
    try:
        load_output = ssh.execute("cat /proc/loadavg")
        parts = load_output.strip().split()
        stats.load_1 = float(parts[0])
        stats.load_5 = float(parts[1])
        stats.load_15 = float(parts[2])
    except Exception:
        pass

    return stats
