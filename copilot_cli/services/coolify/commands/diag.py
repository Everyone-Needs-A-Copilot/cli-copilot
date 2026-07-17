"""Diagnostic commands — composite infrastructure analysis."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from copilot_cli.services.coolify.output.console import console
from copilot_cli.services.coolify.output.formatters import bool_icon, relative_time, status_badge

app = typer.Typer(help="Infrastructure diagnostics.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


async def _diagnose_application(client, query: str) -> dict:
    """Aggregate app diagnostics: details, logs, env vars, recent deployments."""
    from copilot_cli.services.coolify.core.resolver import resolve_application

    try:
        uuid = await resolve_application(client, query)
    except Exception as e:
        return {
            "application": None,
            "health": {"status": "unknown", "issues": []},
            "logs": None,
            "environment_variables": {"count": 0},
            "recent_deployments": [],
            "errors": [str(e)],
        }

    results = await asyncio.gather(
        client.get_application(uuid),
        client.get_application_logs(uuid, 50),
        client.list_app_envvars(uuid),
        client.list_app_deployments(uuid),
        return_exceptions=True,
    )

    errors = []

    def extract(result, name):
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
            return None
        return result

    app_data = extract(results[0], "application")
    logs = extract(results[1], "logs")
    envvars = extract(results[2], "envvars")
    deployments = extract(results[3], "deployments")

    issues = []
    health_status = "unknown"
    if app_data:
        status = app_data.get("status") or ""
        if "running" in status:
            health_status = "healthy"
        elif "exited" in status or "unhealthy" in status or "error" in status:
            health_status = "unhealthy"
            issues.append(f"Status: {status}")

    if deployments and isinstance(deployments, list):
        failed = [d for d in deployments[:5] if d.get("status") == "failed"]
        if failed:
            issues.append(f"{len(failed)} failed deployment(s) in last 5")
            if health_status == "healthy":
                health_status = "unhealthy"

    from copilot_cli.services.coolify.monitoring.log_analyzer import extract_log_text

    log_text = extract_log_text(logs)

    return {
        "application": {
            "uuid": app_data.get("uuid", ""),
            "name": app_data.get("name", ""),
            "status": app_data.get("status", "unknown"),
            "fqdn": app_data.get("fqdn"),
            "git_repository": app_data.get("git_repository"),
            "git_branch": app_data.get("git_branch"),
        }
        if app_data
        else None,
        "health": {"status": health_status, "issues": issues},
        "logs": log_text or None,
        "environment_variables": {
            "count": len(envvars) if isinstance(envvars, list) else 0,
            "variables": [
                {"key": v.get("key"), "is_build_time": v.get("is_build_time", False)}
                for v in (envvars or [])
                if isinstance(v, dict)
            ],
        },
        "recent_deployments": [
            {"uuid": d.get("uuid"), "status": d.get("status"), "created_at": d.get("created_at")}
            for d in (deployments or [])[:5]
            if isinstance(d, dict)
        ],
        "errors": errors if errors else [],
    }


async def _diagnose_service(client, query: str, ssh=None) -> dict:
    """Aggregate service diagnostics: details, env vars, containers, logs."""
    from copilot_cli.services.coolify.core.resolver import resolve_service

    try:
        uuid = await resolve_service(client, query)
    except Exception as e:
        return {
            "service": None,
            "health": {"status": "unknown", "issues": []},
            "environment_variables": {"count": 0},
            "containers": [],
            "logs": {},
            "recommendations": [],
            "ssh_available": ssh is not None,
            "errors": [str(e)],
        }

    results = await asyncio.gather(
        client.get_service(uuid),
        client.list_service_envvars(uuid),
        return_exceptions=True,
    )

    errors = []

    def extract(result, name):
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
            return None
        return result

    svc_data = extract(results[0], "service")
    envvars = extract(results[1], "envvars")

    # SSH-based container diagnostics
    containers_info = []
    container_stats = []
    log_analyses = {}
    ssh_available = ssh is not None

    if ssh:
        try:
            from copilot_cli.services.coolify.monitoring.docker_stats import (
                get_service_docker_stats,
            )
            from copilot_cli.services.coolify.monitoring.log_analyzer import analyze_logs
            from copilot_cli.services.coolify.monitoring.service_containers import (
                discover_service_containers,
                get_all_service_logs,
            )

            containers_info = discover_service_containers(ssh, uuid)
            container_stats = get_service_docker_stats(ssh, uuid)
            service_logs = get_all_service_logs(ssh, uuid, 50)

            for container_name, log_text in service_logs.items():
                analysis = analyze_logs(log_text)
                log_analyses[container_name] = {
                    "total_lines": analysis.total_lines,
                    "error_lines": analysis.error_lines,
                    "error_rate": analysis.error_rate,
                    "pattern_counts": analysis.pattern_counts,
                    "recent_errors": analysis.recent_errors,
                }
        except Exception as e:
            errors.append(f"SSH diagnostics: {e}")

    # Health assessment
    issues = []
    health_status = "unknown"
    recommendations = []

    if svc_data:
        status = svc_data.get("status") or ""
        if "running" in status:
            health_status = "healthy"
        elif "exited" in status or "unhealthy" in status or "error" in status:
            health_status = "unhealthy"
            issues.append(f"Status: {status}")

    # Container-level health checks
    for c in containers_info:
        if "exited" in c.status.lower() or "restarting" in c.status.lower():
            health_status = "unhealthy"
            issues.append(f"Container {c.service_component}: {c.status}")

    # Memory pressure detection
    stats_map = {s.name: s for s in container_stats}
    for c in containers_info:
        stat = stats_map.get(c.name)
        if stat and stat.memory_percent > 85:
            if health_status == "healthy":
                health_status = "warning"
            issues.append(f"Container {c.service_component}: memory at {stat.memory_percent:.0f}%")
            recommendations.append(
                {
                    "severity": "warning",
                    "title": "High memory usage",
                    "detail": f"{c.service_component} is using {stat.memory_percent:.0f}% of its memory limit.",
                    "action": "Increase memory limit in Coolify service settings.",
                }
            )

    # OOM detection in logs
    for container_name, analysis in log_analyses.items():
        if analysis.get("pattern_counts", {}).get("oom", 0) > 0:
            health_status = "unhealthy"
            issues.append(f"OOM detected in {container_name} logs")
            recommendations.append(
                {
                    "severity": "critical",
                    "title": "Out-of-memory events detected",
                    "detail": f"Container {container_name} has OOM entries in logs.",
                    "action": "Increase memory limit to at least 2 GiB in Coolify service settings.",
                }
            )

    if not ssh_available:
        recommendations.append(
            {
                "severity": "info",
                "title": "SSH not configured",
                "detail": "Container-level diagnostics require SSH access.",
                "action": "Run 'coolify config init' to configure SSH for full diagnostics.",
            }
        )

    # Build container output
    containers_output = []
    for c in containers_info:
        stat = stats_map.get(c.name)
        containers_output.append(
            {
                "name": c.name,
                "component": c.service_component,
                "image": c.image,
                "status": c.status,
                "cpu_percent": stat.cpu_percent if stat else None,
                "memory_usage": stat.memory_usage if stat else None,
                "memory_percent": stat.memory_percent if stat else None,
            }
        )

    return {
        "service": {
            "uuid": svc_data.get("uuid", ""),
            "name": svc_data.get("name", ""),
            "type": svc_data.get("type"),
            "status": svc_data.get("status", "unknown"),
            "domains": svc_data.get("domains", []),
        }
        if svc_data
        else None,
        "health": {"status": health_status, "issues": issues},
        "environment_variables": {
            "count": len(envvars) if isinstance(envvars, list) else 0,
            "variables": [
                {"key": v.get("key"), "is_build_time": v.get("is_build_time", False)}
                for v in (envvars or [])
                if isinstance(v, dict)
            ],
        },
        "containers": containers_output,
        "logs": log_analyses,
        "recommendations": recommendations,
        "ssh_available": ssh_available,
        "errors": errors if errors else [],
    }


async def _diagnose_server(client, query: str) -> dict:
    """Aggregate server diagnostics."""
    from copilot_cli.services.coolify.core.resolver import resolve_server

    try:
        uuid = await resolve_server(client, query)
    except Exception as e:
        return {
            "server": None,
            "health": {"status": "unknown", "issues": []},
            "resources": [],
            "domains": [],
            "validation": None,
            "errors": [str(e)],
        }

    results = await asyncio.gather(
        client.get_server(uuid),
        client.get_server_resources(uuid),
        client.get_server_domains(uuid),
        client.validate_server(uuid),
        return_exceptions=True,
    )

    errors = []

    def extract(result, name):
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
            return None
        return result

    server = extract(results[0], "server")
    resources = extract(results[1], "resources")
    domains = extract(results[2], "domains")
    validation = extract(results[3], "validation")

    issues = []
    health_status = "unknown"
    if server:
        if server.get("is_reachable") is True:
            health_status = "healthy"
        elif server.get("is_reachable") is False:
            health_status = "unhealthy"
            issues.append("Server is not reachable")
        if server.get("is_usable") is False:
            health_status = "unhealthy"
            issues.append("Server is not usable")

    if resources and isinstance(resources, list):
        unhealthy = [
            r
            for r in resources
            if any(s in (r.get("status") or "") for s in ("exited", "unhealthy", "error"))
        ]
        if unhealthy:
            issues.append(f"{len(unhealthy)} unhealthy resource(s)")

    return {
        "server": {
            "uuid": server.get("uuid", ""),
            "name": server.get("name", ""),
            "ip": server.get("ip", ""),
            "status": server.get("status"),
            "is_reachable": server.get("is_reachable"),
        }
        if server
        else None,
        "health": {"status": health_status, "issues": issues},
        "resources": [
            {
                "uuid": r.get("uuid"),
                "name": r.get("name"),
                "type": r.get("type"),
                "status": r.get("status"),
            }
            for r in (resources or [])
            if isinstance(r, dict)
        ],
        "domains": domains or [],
        "validation": validation,
        "errors": errors if errors else [],
    }


async def _find_issues(client) -> dict:
    """Scan all infrastructure for issues."""
    results = await asyncio.gather(
        client.list_servers(),
        client.list_applications(),
        client.list_databases(),
        client.list_services(),
        return_exceptions=True,
    )

    errors = []
    issues = []

    def extract(result, name):
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
            return []
        return result if isinstance(result, list) else []

    servers = extract(results[0], "servers")
    applications = extract(results[1], "applications")
    databases = extract(results[2], "databases")
    services = extract(results[3], "services")

    for s in servers:
        if s.get("is_reachable") is False:
            issues.append(
                {
                    "type": "server",
                    "uuid": s.get("uuid", ""),
                    "name": s.get("name", ""),
                    "issue": "Server not reachable",
                    "status": s.get("status") or "unreachable",
                }
            )

    for a in applications:
        status = a.get("status") or ""
        if any(s in status for s in ("exited", "unhealthy", "error")) or status == "stopped":
            issues.append(
                {
                    "type": "application",
                    "uuid": a.get("uuid", ""),
                    "name": a.get("name", ""),
                    "issue": f"Status: {status}",
                    "status": status,
                }
            )

    for db in databases:
        status = db.get("status") or ""
        if any(s in status for s in ("exited", "unhealthy", "error")) or status == "stopped":
            issues.append(
                {
                    "type": "database",
                    "uuid": db.get("uuid", ""),
                    "name": db.get("name", ""),
                    "issue": f"Status: {status}",
                    "status": status,
                }
            )

    for svc in services:
        status = svc.get("status") or ""
        if any(s in status for s in ("exited", "unhealthy", "error")) or status == "stopped":
            issues.append(
                {
                    "type": "service",
                    "uuid": svc.get("uuid", ""),
                    "name": svc.get("name", ""),
                    "issue": f"Status: {status}",
                    "status": status,
                }
            )

    return {
        "summary": {
            "total_issues": len(issues),
            "unhealthy_applications": len([i for i in issues if i["type"] == "application"]),
            "unhealthy_databases": len([i for i in issues if i["type"] == "database"]),
            "unhealthy_services": len([i for i in issues if i["type"] == "service"]),
            "unreachable_servers": len([i for i in issues if i["type"] == "server"]),
        },
        "issues": issues,
        "errors": errors if errors else [],
    }


async def _infrastructure_overview(client) -> dict:
    """Get full infrastructure overview."""
    results = await asyncio.gather(
        client.list_servers(),
        client.list_applications(),
        client.list_databases(),
        client.list_services(),
        client.list_projects(),
        return_exceptions=True,
    )

    def extract(result):
        if isinstance(result, Exception):
            return []
        return result if isinstance(result, list) else []

    servers = extract(results[0])
    apps = extract(results[1])
    dbs = extract(results[2])
    services = extract(results[3])
    projects = extract(results[4])

    return {
        "servers": {
            "total": len(servers),
            "reachable": len([s for s in servers if s.get("is_reachable")]),
            "items": servers,
        },
        "applications": {
            "total": len(apps),
            "running": len([a for a in apps if "running" in (a.get("status") or "")]),
            "items": apps,
        },
        "databases": {
            "total": len(dbs),
            "running": len([d for d in dbs if "running" in (d.get("status") or "")]),
            "items": dbs,
        },
        "services": {
            "total": len(services),
            "running": len([s for s in services if "running" in (s.get("status") or "")]),
            "items": services,
        },
        "projects": {"total": len(projects), "items": projects},
    }


@app.command("app")
def diagnose_app(
    query: Annotated[str, typer.Argument(help="App UUID, name, or domain")],
) -> None:
    """Diagnose an application."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(_diagnose_application(client, query))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
            return

        # Application info
        app_info = result.get("application")
        if app_info:
            console.print(
                Panel(
                    f"[bold]{app_info.get('name', '')}[/bold]  {status_badge(app_info.get('status'))}\n"
                    f"UUID: [uuid]{app_info.get('uuid', '')}[/uuid]\n"
                    f"Domain: {app_info.get('fqdn') or '—'}\n"
                    f"Repo: {app_info.get('git_repository') or '—'} ({app_info.get('git_branch') or '—'})",
                    title="Application",
                    border_style="cyan",
                )
            )

        # Health
        health = result.get("health", {})
        health_style = (
            "green"
            if health.get("status") == "healthy"
            else "red"
            if health.get("status") == "unhealthy"
            else "yellow"
        )
        console.print(
            f"\n[{health_style}]Health: {health.get('status', 'unknown')}[/{health_style}]"
        )
        for issue in health.get("issues", []):
            console.print(f"  [warning]⚠ {issue}[/warning]")

        # Env vars
        env_info = result.get("environment_variables", {})
        console.print(f"\n[bold]Environment Variables:[/bold] {env_info.get('count', 0)}")

        # Recent deployments
        deps = result.get("recent_deployments", [])
        if deps:
            console.print("\n[bold]Recent Deployments:[/bold]")
            for d in deps:
                console.print(
                    f"  {status_badge(d.get('status'))}  {relative_time(d.get('created_at'))}"
                )

        if result.get("errors"):
            console.print("\n[error]Errors:[/error]")
            for err in result["errors"]:
                console.print(f"  {err}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("svc")
def diagnose_svc(
    query: Annotated[str, typer.Argument(help="Service UUID or name")],
) -> None:
    """Diagnose a service (compose stack)."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()

        # Try to get SSH client for container-level diagnostics
        ssh = None
        try:
            from copilot_cli.services.coolify.commands.monitor import _get_ssh_client

            ssh = _get_ssh_client()
            if ssh:
                ssh.connect()
        except Exception:
            ssh = None

        try:
            result = run_async(_diagnose_service(client, query, ssh))
        finally:
            if ssh:
                ssh.close()

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
            return

        # Service info
        svc_info = result.get("service")
        if svc_info:
            domains = ", ".join(svc_info.get("domains", [])) or "—"
            console.print(
                Panel(
                    f"[bold]{svc_info.get('name', '')}[/bold]  {status_badge(svc_info.get('status'))}\n"
                    f"UUID: [uuid]{svc_info.get('uuid', '')}[/uuid]\n"
                    f"Type: {svc_info.get('type') or '—'}\n"
                    f"Domains: {domains}",
                    title="Service",
                    border_style="cyan",
                )
            )

        # Health
        health = result.get("health", {})
        health_style = (
            "green"
            if health.get("status") == "healthy"
            else "red"
            if health.get("status") == "unhealthy"
            else "yellow"
        )
        console.print(
            f"\n[{health_style}]Health: {health.get('status', 'unknown')}[/{health_style}]"
        )
        for issue in health.get("issues", []):
            console.print(f"  [warning]⚠ {issue}[/warning]")

        # Containers
        containers = result.get("containers", [])
        if containers:
            table = Table(title="Containers", show_lines=False)
            table.add_column("Component", style="bold")
            table.add_column("Status")
            table.add_column("Image")
            table.add_column("CPU%", justify="right")
            table.add_column("Memory", justify="right")
            table.add_column("Mem%", justify="right")
            for c in containers:
                cpu = f"{c['cpu_percent']:.1f}%" if c.get("cpu_percent") is not None else "—"
                mem = c.get("memory_usage") or "—"
                mem_pct = (
                    f"{c['memory_percent']:.1f}%" if c.get("memory_percent") is not None else "—"
                )
                table.add_row(
                    c.get("component", ""),
                    status_badge(c.get("status", "")),
                    c.get("image", "")[:40],
                    cpu,
                    mem,
                    mem_pct,
                )
            console.print(table)
        elif not result.get("ssh_available"):
            console.print("\n[dim]Container details unavailable (SSH not configured).[/dim]")

        # Env vars
        env_info = result.get("environment_variables", {})
        console.print(f"\n[bold]Environment Variables:[/bold] {env_info.get('count', 0)}")

        # Log analysis
        log_analyses = result.get("logs", {})
        if log_analyses:
            console.print("\n[bold]Log Analysis:[/bold]")
            for container_name, analysis in log_analyses.items():
                error_count = analysis.get("error_lines", 0)
                error_style = "red" if error_count > 0 else "green"
                console.print(
                    f"  {container_name}: [{error_style}]{error_count} errors[/{error_style}] "
                    f"/ {analysis.get('total_lines', 0)} lines ({analysis.get('error_rate', 0)}%)"
                )
                if analysis.get("pattern_counts"):
                    patterns = ", ".join(f"{k}: {v}" for k, v in analysis["pattern_counts"].items())
                    console.print(f"    Patterns: {patterns}")

        # Recommendations
        recommendations = result.get("recommendations", [])
        if recommendations:
            console.print("\n[bold]Recommendations:[/bold]")
            for r in recommendations:
                severity_style = {
                    "critical": "red",
                    "warning": "yellow",
                    "info": "blue",
                }.get(r.get("severity", ""), "white")
                console.print(
                    f"  [{severity_style}]{r.get('severity', '').upper()}[/{severity_style}] "
                    f"{r.get('title', '')}"
                )
                console.print(f"    {r.get('detail', '')}")
                console.print(f"    [bold]Action:[/bold] {r.get('action', '')}")

        if result.get("errors"):
            console.print("\n[error]Errors:[/error]")
            for err in result["errors"]:
                console.print(f"  {err}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("server")
def diagnose_server(
    query: Annotated[str, typer.Argument(help="Server UUID, name, or IP")],
) -> None:
    """Diagnose a server."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(_diagnose_server(client, query))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
            return

        server = result.get("server")
        if server:
            console.print(
                Panel(
                    f"[bold]{server.get('name', '')}[/bold]  {status_badge(server.get('status'))}\n"
                    f"UUID: [uuid]{server.get('uuid', '')}[/uuid]\n"
                    f"IP: {server.get('ip', '')}\n"
                    f"Reachable: {bool_icon(server.get('is_reachable'))}",
                    title="Server",
                    border_style="cyan",
                )
            )

        health = result.get("health", {})
        health_style = (
            "green"
            if health.get("status") == "healthy"
            else "red"
            if health.get("status") == "unhealthy"
            else "yellow"
        )
        console.print(
            f"\n[{health_style}]Health: {health.get('status', 'unknown')}[/{health_style}]"
        )
        for issue in health.get("issues", []):
            console.print(f"  [warning]⚠ {issue}[/warning]")

        resources = result.get("resources", [])
        if resources:
            console.print(f"\n[bold]Resources ({len(resources)}):[/bold]")
            for r in resources:
                console.print(
                    f"  {status_badge(r.get('status'))}  {r.get('name', '')} ({r.get('type', '')})"
                )

        if result.get("errors"):
            console.print("\n[error]Errors:[/error]")
            for err in result["errors"]:
                console.print(f"  {err}")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("issues")
def find_issues() -> None:
    """Scan infrastructure for problems."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(_find_issues(client))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(result, state.output_format)
            return

        summary = result.get("summary", {})
        total = summary.get("total_issues", 0)

        if total == 0:
            console.print("[success]No infrastructure issues found.[/success]")
            return

        console.print(
            Panel(
                f"Total Issues: [bold]{total}[/bold]\n"
                f"  Servers: {summary.get('unreachable_servers', 0)}\n"
                f"  Applications: {summary.get('unhealthy_applications', 0)}\n"
                f"  Databases: {summary.get('unhealthy_databases', 0)}\n"
                f"  Services: {summary.get('unhealthy_services', 0)}",
                title="[error]Infrastructure Issues[/error]",
                border_style="red",
            )
        )

        for issue in result.get("issues", []):
            console.print(
                f"  [error]✗[/error] [{issue.get('type')}] {issue.get('name', '')} — {issue.get('issue', '')}"
            )
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("overview")
def infrastructure_overview() -> None:
    """Infrastructure overview — all resources at a glance."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        result = run_async(_infrastructure_overview(client))

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            # Remove full item lists for JSON overview
            for key in result:
                if isinstance(result[key], dict) and "items" in result[key]:
                    result[key] = {k: v for k, v in result[key].items() if k != "items"}
            output_data(result, state.output_format)
            return

        table = Table(title="Infrastructure Overview", show_lines=True)
        table.add_column("Resource", style="bold")
        table.add_column("Total", justify="right")
        table.add_column("Healthy", justify="right", style="green")

        for key, label in [
            ("servers", "Servers"),
            ("applications", "Applications"),
            ("databases", "Databases"),
            ("services", "Services"),
            ("projects", "Projects"),
        ]:
            data = result.get(key, {})
            total = data.get("total", 0)
            healthy = data.get("running", data.get("reachable", total))
            table.add_row(label, str(total), str(healthy))

        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
