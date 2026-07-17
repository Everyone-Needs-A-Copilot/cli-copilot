"""Rich panel builders for detail views."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from copilot_cli.services.coolify.output.formatters import (
    bool_icon,
    relative_time,
    status_badge,
    truncate,
)


def server_detail_panel(server: dict) -> Panel:
    """Build a detail panel for a server."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    table.add_row("Name", server.get("name", ""))
    table.add_row("UUID", f"[uuid]{server.get('uuid', '')}[/uuid]")
    table.add_row("IP", server.get("ip", ""))
    table.add_row("Port", str(server.get("port", 22)))
    table.add_row("User", server.get("user", "root"))
    table.add_row("Status", status_badge(server.get("status")))
    table.add_row("Reachable", bool_icon(server.get("is_reachable")))
    table.add_row("Usable", bool_icon(server.get("is_usable")))
    table.add_row("Build Server", bool_icon(server.get("is_build_server")))
    table.add_row("Proxy", server.get("proxy_type") or "\u2014")
    table.add_row("Proxy Status", server.get("proxy_status") or "\u2014")
    table.add_row("Created", relative_time(server.get("created_at")))
    table.add_row("Updated", relative_time(server.get("updated_at")))

    return Panel(
        table,
        title=f"[bold]Server: {server.get('name', '')}[/bold]",
        border_style="cyan",
    )


def application_detail_panel(app: dict) -> Panel:
    """Build a detail panel for an application."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    table.add_row("Name", app.get("name", ""))
    table.add_row("UUID", f"[uuid]{app.get('uuid', '')}[/uuid]")
    table.add_row("Status", status_badge(app.get("status")))
    table.add_row("Domain", app.get("fqdn") or "\u2014")
    table.add_row("Repository", app.get("git_repository") or "\u2014")
    table.add_row("Branch", app.get("git_branch") or "\u2014")
    table.add_row("Build Pack", app.get("build_pack") or "\u2014")
    table.add_row("Ports", app.get("ports_exposes") or "\u2014")
    table.add_row("Health Check", bool_icon(app.get("health_check_enabled")))
    if app.get("health_check_path"):
        table.add_row("Health Path", app["health_check_path"])
    table.add_row("Memory Limit", app.get("limits_memory") or "\u2014")
    table.add_row("CPU Limit", app.get("limits_cpus") or "\u2014")
    table.add_row("Created", relative_time(app.get("created_at")))
    table.add_row("Updated", relative_time(app.get("updated_at")))

    return Panel(
        table,
        title=f"[bold]Application: {app.get('name', '')}[/bold]",
        border_style="cyan",
    )


def database_detail_panel(db: dict) -> Panel:
    """Build a detail panel for a database."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    db_type = db.get("type") or db.get("database_type") or "unknown"
    table.add_row("Name", db.get("name", ""))
    table.add_row("UUID", f"[uuid]{db.get('uuid', '')}[/uuid]")
    table.add_row("Type", db_type)
    table.add_row("Status", status_badge(db.get("status")))
    table.add_row("Image", db.get("image") or "\u2014")
    table.add_row("Public", bool_icon(db.get("is_public")))
    if db.get("public_port"):
        table.add_row("Public Port", str(db["public_port"]))
    if db.get("internal_db_url"):
        table.add_row("Internal URL", truncate(db["internal_db_url"], 60))
    table.add_row("Created", relative_time(db.get("created_at")))
    table.add_row("Updated", relative_time(db.get("updated_at")))

    return Panel(
        table,
        title=f"[bold]Database: {db.get('name', '')}[/bold]",
        border_style="cyan",
    )


def service_detail_panel(svc: dict) -> Panel:
    """Build a detail panel for a service."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    table.add_row("Name", svc.get("name", ""))
    table.add_row("UUID", f"[uuid]{svc.get('uuid', '')}[/uuid]")
    table.add_row("Type", svc.get("type") or "\u2014")
    table.add_row("Status", status_badge(svc.get("status")))
    domains = svc.get("domains") or []
    table.add_row("Domains", ", ".join(domains) if domains else "\u2014")
    table.add_row("Created", relative_time(svc.get("created_at")))
    table.add_row("Updated", relative_time(svc.get("updated_at")))

    return Panel(
        table,
        title=f"[bold]Service: {svc.get('name', '')}[/bold]",
        border_style="cyan",
    )


def deployment_detail_panel(dep: dict) -> Panel:
    """Build a detail panel for a deployment."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    table.add_row("Deployment UUID", f"[uuid]{dep.get('deployment_uuid', '')}[/uuid]")
    table.add_row("Application", dep.get("application_name") or "\u2014")
    table.add_row("Status", status_badge(dep.get("status")))
    table.add_row("Commit", dep.get("commit") or "\u2014")
    table.add_row("Server", dep.get("server_name") or "\u2014")
    table.add_row("Force Rebuild", bool_icon(dep.get("force_rebuild")))
    table.add_row("Webhook", bool_icon(dep.get("is_webhook")))
    table.add_row("API", bool_icon(dep.get("is_api")))
    table.add_row("Created", relative_time(dep.get("created_at")))
    table.add_row("Updated", relative_time(dep.get("updated_at")))

    return Panel(table, title="[bold]Deployment[/bold]", border_style="cyan")


def project_detail_panel(project: dict) -> Panel:
    """Build a detail panel for a project."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    table.add_row("Name", project.get("name", ""))
    table.add_row("UUID", f"[uuid]{project.get('uuid', '')}[/uuid]")
    table.add_row("Description", project.get("description") or "\u2014")
    envs = project.get("environments") or []
    table.add_row("Environments", str(len(envs)))
    for env in envs:
        table.add_row(
            f"  \u2514 {env.get('name', '')}",
            f"[uuid]{env.get('uuid', '')}[/uuid]",
        )
    table.add_row("Created", relative_time(project.get("created_at")))

    return Panel(
        table,
        title=f"[bold]Project: {project.get('name', '')}[/bold]",
        border_style="cyan",
    )


def diagnostic_panel(title: str, data: dict) -> Panel:
    """Build a generic diagnostic panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="label", width=20)
    table.add_column("Value")

    for key, value in data.items():
        if isinstance(value, dict):
            table.add_row(key, str(value))
        elif isinstance(value, list):
            table.add_row(key, f"{len(value)} items")
        else:
            table.add_row(key, str(value) if value is not None else "\u2014")

    return Panel(table, title=f"[bold]{title}[/bold]", border_style="cyan")
