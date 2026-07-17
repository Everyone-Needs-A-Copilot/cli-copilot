"""Rich Live dashboard for real-time infrastructure monitoring."""

from __future__ import annotations

from typing import Any

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from copilot_cli.services.coolify.output.formatters import status_badge


def _progress_bar(percent: float, width: int = 20, threshold: int = 80) -> str:
    """Create a text-based progress bar with color coding."""
    filled = int(width * percent / 100)
    empty = width - filled
    color = "green" if percent < threshold * 0.75 else "yellow" if percent < threshold else "red"
    bar = f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"
    return f"{bar} {percent:5.1f}%"


def build_system_panel(stats: Any) -> Panel:
    """Build the system resources panel."""
    if stats is None:
        return Panel("[dim]SSH not configured — no system metrics[/dim]", title="System Resources")

    lines = [
        f"  CPU   {_progress_bar(stats.cpu_percent)}",
        f"  MEM   {_progress_bar(stats.memory_percent, threshold=85)}  ({stats.memory_used_mb}MB / {stats.memory_total_mb}MB)",
        f"  DISK  {_progress_bar(stats.disk_percent, threshold=90)}  ({stats.disk_used_gb:.1f}GB / {stats.disk_total_gb:.1f}GB)",
        f"  SWAP  {_progress_bar(stats.swap_percent)}  ({stats.swap_used_mb}MB / {stats.swap_total_mb}MB)",
        f"  LOAD  {stats.load_1:.2f} / {stats.load_5:.2f} / {stats.load_15:.2f}",
    ]
    return Panel("\n".join(lines), title="[bold]System Resources[/bold]", border_style="cyan")


def build_docker_panel(containers: list[Any]) -> Panel:
    """Build the docker containers panel."""
    if not containers:
        return Panel("[dim]No container data[/dim]", title="Docker Containers")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Name", style="bold", max_width=25)
    table.add_column("CPU", justify="right", width=8)
    table.add_column("MEM", justify="right", width=12)
    table.add_column("MEM%", justify="right", width=6)

    for c in containers[:12]:  # Limit rows
        cpu_color = "green" if c.cpu_percent < 50 else "yellow" if c.cpu_percent < 80 else "red"
        mem_color = (
            "green" if c.memory_percent < 50 else "yellow" if c.memory_percent < 80 else "red"
        )
        table.add_row(
            c.name[:25],
            f"[{cpu_color}]{c.cpu_percent:.1f}%[/{cpu_color}]",
            c.memory_usage,
            f"[{mem_color}]{c.memory_percent:.1f}%[/{mem_color}]",
        )

    return Panel(table, title="[bold]Docker Containers[/bold]", border_style="cyan")


def build_apps_panel(apps: list[dict]) -> Panel:
    """Build the application status panel."""
    if not apps:
        return Panel("[dim]No applications[/dim]", title="Application Status")

    lines = []
    for app in apps[:15]:  # Limit rows
        name = app.get("name", "unknown")[:25]
        lines.append(f"  {status_badge(app.get('status'))}  {name}")

    return Panel("\n".join(lines), title="[bold]Application Status[/bold]", border_style="cyan")


def build_deployments_panel(deployments: list[dict]) -> Panel:
    """Build the recent deployments panel."""
    if not deployments:
        return Panel("[dim]No recent deployments[/dim]", title="Recent Deployments")

    from copilot_cli.services.coolify.output.formatters import deployment_status_icon, relative_time

    lines = []
    for dep in deployments[:8]:
        icon = deployment_status_icon(dep.get("status"))
        color = "green" if icon == "\u2713" else "red" if icon == "\u2717" else "yellow"
        app_name = (dep.get("application_name") or "")[:20]
        when = relative_time(dep.get("created_at"))
        lines.append(f"  [{color}]{icon}[/{color}]  {when:<12} {app_name}")

    return Panel("\n".join(lines), title="[bold]Recent Deployments[/bold]", border_style="cyan")


def build_dashboard_layout(
    system_stats: Any = None,
    docker_containers: list[Any] | None = None,
    apps: list[dict] | None = None,
    deployments: list[dict] | None = None,
) -> Layout:
    """Build the complete dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=3),
        Layout(name="bottom", ratio=2),
    )
    layout["top"].split_row(
        Layout(build_system_panel(system_stats), name="system"),
        Layout(build_docker_panel(docker_containers or []), name="docker"),
    )
    layout["bottom"].split_row(
        Layout(build_apps_panel(apps or []), name="apps"),
        Layout(build_deployments_panel(deployments or []), name="deployments"),
    )
    return layout
