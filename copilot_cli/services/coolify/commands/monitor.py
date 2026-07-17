"""Monitoring commands — live dashboard, health probes, SSL checks, log analysis."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC
from typing import Annotated

import typer
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from copilot_cli.services.coolify.output.console import console
from copilot_cli.services.coolify.output.formatters import (
    bool_icon,
)

app = typer.Typer(help="Infrastructure monitoring.", no_args_is_help=True)


def _get_deps():
    from copilot_cli.services.coolify.main import handle_error, run_async, state

    return state, run_async, handle_error


def _get_ssh_client():
    """Create SSH client from config."""
    from copilot_cli.services.coolify.main import state

    settings = state.get_settings()
    if not settings.ssh.host:
        return None
    from copilot_cli.services.coolify.core.ssh_client import SSHClient

    return SSHClient(
        host=settings.ssh.host,
        user=settings.ssh.user,
        port=settings.ssh.port,
        key_file=settings.ssh.key_file if settings.ssh.key_file else None,
    )


@app.command("dashboard")
def dashboard(
    refresh: Annotated[int, typer.Option("--refresh", "-r", help="Refresh interval (seconds)")] = 2,
) -> None:
    """Live terminal dashboard with system metrics and app status."""
    state, run_async, handle_error = _get_deps()
    from copilot_cli.services.coolify.output.dashboard import build_dashboard_layout

    try:
        client = state.get_client()
        ssh = _get_ssh_client()
        if ssh:
            ssh.connect()

        console.print("[info]Starting dashboard... Press Ctrl+C to exit.[/info]\n")

        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                system_stats = None
                docker_containers = None

                # SSH metrics
                if ssh and ssh.is_connected():
                    try:
                        from copilot_cli.services.coolify.monitoring.system_stats import (
                            get_system_stats,
                        )

                        system_stats = get_system_stats(ssh)
                    except Exception:
                        pass
                    try:
                        from copilot_cli.services.coolify.monitoring.docker_stats import (
                            get_docker_stats,
                        )

                        docker_containers = get_docker_stats(ssh)
                    except Exception:
                        pass

                # API metrics
                apps = []
                deployments = []
                try:
                    apps = run_async(client.list_applications())
                except Exception:
                    pass
                try:
                    deployments = run_async(client.list_deployments(per_page=10))
                except Exception:
                    pass

                layout = build_dashboard_layout(
                    system_stats=system_stats,
                    docker_containers=docker_containers,
                    apps=apps,
                    deployments=deployments,
                )
                live.update(layout)
                time.sleep(refresh)

    except KeyboardInterrupt:
        console.print("\n[info]Dashboard stopped.[/info]")
    except Exception as e:
        handle_error(e)
    finally:
        if ssh:
            ssh.close()


@app.command("docker")
def docker_stats(
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Continuously refresh")] = False,
    interval: Annotated[int, typer.Option("--interval", "-i", help="Refresh interval")] = 2,
) -> None:
    """Docker container resource usage (requires SSH)."""
    state, _run_async, handle_error = _get_deps()
    try:
        ssh = _get_ssh_client()
        if not ssh:
            console.print(
                "[error]SSH not configured. Run 'coolify config init' to set up SSH.[/error]"
            )
            raise typer.Exit(1)

        from copilot_cli.services.coolify.monitoring.docker_stats import get_docker_stats

        with ssh:
            if follow:
                console.print("[info]Streaming docker stats... Press Ctrl+C to stop.[/info]\n")
                try:
                    with Live(console=console, refresh_per_second=1) as live:
                        while True:
                            containers = get_docker_stats(ssh)
                            table = Table(title="Docker Containers", show_lines=False)
                            table.add_column("Name", style="bold")
                            table.add_column("CPU%", justify="right")
                            table.add_column("Memory", justify="right")
                            table.add_column("Mem%", justify="right")
                            table.add_column("Net I/O")
                            table.add_column("Block I/O")
                            for c in containers:
                                table.add_row(
                                    c.name,
                                    f"{c.cpu_percent:.1f}%",
                                    c.memory_usage,
                                    f"{c.memory_percent:.1f}%",
                                    c.net_io,
                                    c.block_io,
                                )
                            live.update(table)
                            time.sleep(interval)
                except KeyboardInterrupt:
                    pass
            else:
                containers = get_docker_stats(ssh)
                if state.is_json():
                    from copilot_cli.services.coolify.output.json_out import output_data

                    output_data(
                        [
                            {
                                "name": c.name,
                                "cpu_percent": c.cpu_percent,
                                "memory_usage": c.memory_usage,
                                "memory_percent": c.memory_percent,
                            }
                            for c in containers
                        ],
                        state.output_format,
                    )
                else:
                    table = Table(title="Docker Containers", show_lines=False)
                    table.add_column("Name", style="bold")
                    table.add_column("CPU%", justify="right")
                    table.add_column("Memory", justify="right")
                    table.add_column("Mem%", justify="right")
                    table.add_column("Net I/O")
                    table.add_column("Block I/O")
                    for c in containers:
                        table.add_row(
                            c.name,
                            f"{c.cpu_percent:.1f}%",
                            c.memory_usage,
                            f"{c.memory_percent:.1f}%",
                            c.net_io,
                            c.block_io,
                        )
                    console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("disk")
def disk_stats(
    cleanup: Annotated[
        bool, typer.Option("--cleanup-suggestions", help="Show cleanup suggestions")
    ] = False,
) -> None:
    """Disk usage analysis (requires SSH)."""
    state, _run_async, handle_error = _get_deps()
    try:
        ssh = _get_ssh_client()
        if not ssh:
            console.print("[error]SSH not configured.[/error]")
            raise typer.Exit(1)

        from copilot_cli.services.coolify.monitoring.system_stats import get_system_stats

        with ssh:
            stats = get_system_stats(ssh)
            settings = state.get_settings()

            if state.is_json():
                from copilot_cli.services.coolify.output.json_out import output_data

                output_data(
                    {"disks": stats.disks, "root_percent": stats.disk_percent}, state.output_format
                )
                return

            table = Table(title="Disk Usage", show_lines=False)
            table.add_column("Device", style="bold")
            table.add_column("Mount")
            table.add_column("Total", justify="right")
            table.add_column("Used", justify="right")
            table.add_column("Usage", justify="right")

            for disk in stats.disks:
                pct = disk["percent"]
                color = (
                    "green"
                    if pct < 70
                    else "yellow"
                    if pct < settings.monitoring.disk_threshold
                    else "red"
                )
                table.add_row(
                    disk["device"],
                    disk["mount"],
                    f"{disk['total_gb']:.1f}G",
                    f"{disk['used_gb']:.1f}G",
                    f"[{color}]{pct:.1f}%[/{color}]",
                )
            console.print(table)

            if cleanup:
                console.print("\n[bold]Cleanup Suggestions:[/bold]")
                # Check for docker cleanup
                try:
                    docker_usage = ssh.execute(
                        "docker system df --format '{{.Type}}: {{.Size}} (reclaimable: {{.Reclaimable}})'"
                    )
                    console.print("\n[bold]Docker disk usage:[/bold]")
                    console.print(docker_usage)
                    console.print(
                        "\n[info]Run 'docker system prune -a' on the server to free space.[/info]"
                    )
                except Exception:
                    pass
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("health")
def health_check(
    interval: Annotated[
        int, typer.Option("--interval", "-i", help="Check interval (seconds, 0 for once)")
    ] = 0,
) -> None:
    """HTTP health probe all application domains."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        from copilot_cli.services.coolify.monitoring.http_probes import (
            probe_domains,
            public_probe_url,
        )

        async def _probe():
            apps, services = await asyncio.gather(
                client.list_applications(),
                client.list_services(),
                return_exceptions=True,
            )
            domains = []
            domain_to_resource = {}
            if isinstance(apps, list):
                for a in apps:
                    fqdn = a.get("fqdn", "")
                    if fqdn:
                        for d in fqdn.split(","):
                            d = d.strip()
                            if d:
                                public_url = public_probe_url(d)
                                domains.append(public_url)
                                domain_to_resource[public_url] = {
                                    "name": a.get("name", ""),
                                    "type": "app",
                                }
            if isinstance(services, list):
                for svc in services:
                    for d in svc.get("domains") or []:
                        d = d.strip()
                        if d:
                            public_url = public_probe_url(d)
                            domains.append(public_url)
                            domain_to_resource[public_url] = {
                                "name": svc.get("name", ""),
                                "type": "service",
                            }
            if not domains:
                return [], {}
            results = await probe_domains(domains)
            return results, domain_to_resource

        def _display(results, domain_to_resource):
            settings = state.get_settings()
            threshold = settings.monitoring.response_time_ms

            if state.is_json():
                from copilot_cli.services.coolify.output.json_out import output_data

                output_data(
                    [
                        {
                            "url": r.url,
                            "resource": next(
                                (
                                    info["name"]
                                    for d, info in domain_to_resource.items()
                                    if d in r.url
                                ),
                                "",
                            ),
                            "type": next(
                                (
                                    info["type"]
                                    for d, info in domain_to_resource.items()
                                    if d in r.url
                                ),
                                "",
                            ),
                            "status": r.status_code,
                            "time_ms": r.response_time_ms,
                            "healthy": r.healthy,
                            "error": r.error,
                        }
                        for r in results
                    ],
                    state.output_format,
                )
                return

            table = Table(title="Health Check Results", show_lines=False)
            table.add_column("Resource", style="bold")
            table.add_column("Type")
            table.add_column("URL")
            table.add_column("Status", justify="center")
            table.add_column("Time (ms)", justify="right")
            table.add_column("Healthy")

            for r in results:
                resource_name = ""
                resource_type = ""
                for d, info in domain_to_resource.items():
                    if d in r.url:
                        resource_name = info["name"]
                        resource_type = info["type"]
                        break
                time_color = (
                    "green"
                    if r.response_time_ms < threshold * 0.5
                    else "yellow"
                    if r.response_time_ms < threshold
                    else "red"
                )
                healthy_icon = (
                    "[green]\u2713[/green]" if r.healthy else f"[red]\u2717 {r.error}[/red]"
                )
                table.add_row(
                    resource_name[:20],
                    resource_type,
                    r.url[:40],
                    str(r.status_code) if r.status_code else "\u2014",
                    f"[{time_color}]{r.response_time_ms:.0f}[/{time_color}]"
                    if r.response_time_ms
                    else "\u2014",
                    healthy_icon,
                )
            console.print(table)

        if interval > 0:
            console.print(
                f"[info]Health checking every {interval}s... Press Ctrl+C to stop.[/info]\n"
            )
            try:
                while True:
                    results, d2a = run_async(_probe())
                    _display(results, d2a)
                    time.sleep(interval)
            except KeyboardInterrupt:
                pass
        else:
            results, d2a = run_async(_probe())
            if not results:
                console.print("[dim]No domains found to probe.[/dim]")
                return
            _display(results, d2a)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("ssl")
def ssl_check(
    warn_days: Annotated[int, typer.Option("--warn-days", help="Days before expiry to warn")] = 30,
) -> None:
    """Check SSL certificate expiry for all domains."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()

        async def _get_domains():
            apps, services = await asyncio.gather(
                client.list_applications(),
                client.list_services(),
                return_exceptions=True,
            )
            domains = set()
            if isinstance(apps, list):
                for a in apps:
                    fqdn = a.get("fqdn", "")
                    if fqdn:
                        for d in fqdn.split(","):
                            d = d.strip()
                            if d:
                                domains.add(d)
            if isinstance(services, list):
                for svc in services:
                    for d in svc.get("domains") or []:
                        d = d.strip()
                        if d:
                            domains.add(d)
            return list(domains)

        domains = run_async(_get_domains())
        if not domains:
            console.print("[dim]No domains found.[/dim]")
            return

        from copilot_cli.services.coolify.monitoring.ssl_checker import check_ssl_batch

        results = check_ssl_batch(domains, warn_days=warn_days)

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(
                [
                    {
                        "domain": r.domain,
                        "valid": r.valid,
                        "issuer": r.issuer,
                        "expires": r.expires,
                        "days_remaining": r.days_remaining,
                        "error": r.error,
                    }
                    for r in results
                ],
                state.output_format,
            )
            return

        table = Table(title="SSL Certificate Status", show_lines=False)
        table.add_column("Domain", style="bold")
        table.add_column("Valid")
        table.add_column("Issuer")
        table.add_column("Expires")
        table.add_column("Days Left", justify="right")

        for r in results:
            if r.error:
                table.add_row(r.domain, "[red]\u2717[/red]", "", "", f"[red]{r.error}[/red]")
            else:
                days_color = (
                    "green"
                    if r.days_remaining > warn_days
                    else "yellow"
                    if r.days_remaining > 7
                    else "red"
                )
                table.add_row(
                    r.domain,
                    bool_icon(r.valid),
                    r.issuer[:30],
                    r.expires[:10] if r.expires else "\u2014",
                    f"[{days_color}]{r.days_remaining}[/{days_color}]",
                )
        console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("logs")
def log_analysis(
    query: Annotated[str, typer.Argument(help="App/service UUID, name, or domain")] = "",
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of log lines")] = 200,
    errors_only: Annotated[bool, typer.Option("--errors", help="Show only error lines")] = False,
    resource_type: Annotated[
        str, typer.Option("--type", "-t", help="Resource type: app, service, or auto")
    ] = "auto",
) -> None:
    """Log aggregation and error analysis for applications and services."""
    state, run_async, handle_error = _get_deps()
    try:
        if not query:
            console.print("[error]Provide an app/service name, UUID, or domain.[/error]")
            raise typer.Exit(1)

        client = state.get_client()
        from copilot_cli.services.coolify.monitoring.log_analyzer import analyze_logs

        resolved_type = resource_type
        uuid = None

        if resolved_type in ("app", "auto"):
            try:
                from copilot_cli.services.coolify.core.resolver import resolve_application

                uuid = run_async(resolve_application(client, query))
                resolved_type = "app"
            except Exception:
                if resolved_type == "app":
                    raise
                resolved_type = "service"

        if resolved_type == "service":
            from copilot_cli.services.coolify.core.resolver import resolve_service

            uuid = run_async(resolve_service(client, query))

            # Service logs require SSH
            ssh = _get_ssh_client()
            if not ssh:
                console.print(
                    "[error]SSH not configured. Service logs require SSH access.[/error]\n"
                    "[dim]Run 'coolify config init' to set up SSH.[/dim]"
                )
                raise typer.Exit(1)

            from copilot_cli.services.coolify.monitoring.service_containers import (
                get_all_service_logs,
            )

            with ssh:
                service_logs = get_all_service_logs(ssh, uuid, lines)

            if not service_logs:
                console.print("[dim]No logs found for this service.[/dim]")
                return

            if state.is_json():
                from copilot_cli.services.coolify.output.json_out import output_data

                all_analyses = {}
                for container_name, log_text in service_logs.items():
                    analysis = analyze_logs(log_text)
                    all_analyses[container_name] = {
                        "total_lines": analysis.total_lines,
                        "error_lines": analysis.error_lines,
                        "error_rate": analysis.error_rate,
                        "pattern_counts": analysis.pattern_counts,
                        "recent_errors": analysis.recent_errors,
                    }
                output_data(all_analyses, state.output_format)
                return

            for container_name, log_text in service_logs.items():
                analysis = analyze_logs(log_text)
                console.print(
                    Panel(
                        f"Total lines: {analysis.total_lines}\n"
                        f"Error lines: [{'red' if analysis.error_lines > 0 else 'green'}]{analysis.error_lines}[/{'red' if analysis.error_lines > 0 else 'green'}]\n"
                        f"Error rate: {analysis.error_rate}%",
                        title=f"Log Analysis: {container_name}",
                        border_style="cyan",
                    )
                )
                if analysis.top_errors:
                    console.print("[bold]Error Patterns:[/bold]")
                    for pattern, count in analysis.top_errors:
                        console.print(f"  {pattern}: {count}")
                if errors_only and analysis.recent_errors:
                    console.print("[bold]Recent Errors:[/bold]")
                    for err in analysis.recent_errors:
                        console.print(f"  [red]{err}[/red]")
                console.print()
            return

        # Application path (existing behavior)
        logs = run_async(client.get_application_logs(uuid, lines))
        from copilot_cli.services.coolify.monitoring.log_analyzer import extract_log_text

        log_text = extract_log_text(logs)
        analysis = analyze_logs(log_text)

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(
                {
                    "total_lines": analysis.total_lines,
                    "error_lines": analysis.error_lines,
                    "error_rate": analysis.error_rate,
                    "pattern_counts": analysis.pattern_counts,
                    "recent_errors": analysis.recent_errors,
                },
                state.output_format,
            )
            return

        console.print(
            Panel(
                f"Total lines: {analysis.total_lines}\n"
                f"Error lines: [{'red' if analysis.error_lines > 0 else 'green'}]{analysis.error_lines}[/{'red' if analysis.error_lines > 0 else 'green'}]\n"
                f"Error rate: {analysis.error_rate}%",
                title="Log Analysis",
                border_style="cyan",
            )
        )

        if analysis.top_errors:
            console.print("\n[bold]Error Patterns:[/bold]")
            for pattern, count in analysis.top_errors:
                console.print(f"  {pattern}: {count}")

        if errors_only and analysis.recent_errors:
            console.print("\n[bold]Recent Errors:[/bold]")
            for err in analysis.recent_errors:
                console.print(f"  [red]{err}[/red]")
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("deployments")
def deployment_analytics(
    days: Annotated[int, typer.Option("--days", "-d", help="Analysis window in days")] = 30,
) -> None:
    """Deployment frequency, success rate, and duration analytics."""
    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        deployments = run_async(client.list_deployments(per_page=200))

        from copilot_cli.services.coolify.monitoring.deploy_analytics import analyze_deployments

        analytics = analyze_deployments(deployments, days=days)

        if state.is_json():
            from copilot_cli.services.coolify.output.json_out import output_data

            output_data(
                {
                    "total": analytics.total,
                    "succeeded": analytics.succeeded,
                    "failed": analytics.failed,
                    "success_rate": analytics.success_rate,
                    "avg_duration_seconds": analytics.avg_duration_seconds,
                    "deployments_per_day": analytics.deployments_per_day,
                    "by_app": analytics.by_app,
                },
                state.output_format,
            )
            return

        console.print(
            Panel(
                f"Total Deployments: [bold]{analytics.total}[/bold]\n"
                f"Succeeded: [green]{analytics.succeeded}[/green]\n"
                f"Failed: [red]{analytics.failed}[/red]\n"
                f"Cancelled: [dim]{analytics.cancelled}[/dim]\n"
                f"Success Rate: [{'green' if analytics.success_rate > 90 else 'yellow' if analytics.success_rate > 70 else 'red'}]{analytics.success_rate}%[/]\n"
                f"Avg Duration: {analytics.avg_duration_seconds:.0f}s\n"
                f"Per Day: {analytics.deployments_per_day}",
                title=f"Deployment Analytics ({days} days)",
                border_style="cyan",
            )
        )

        if analytics.by_app:
            console.print("\n[bold]By Application:[/bold]")
            table = Table(show_header=True, show_lines=False)
            table.add_column("App", style="bold")
            table.add_column("Total", justify="right")
            table.add_column("Success", justify="right", style="green")
            table.add_column("Failed", justify="right", style="red")
            for app_name, data in sorted(
                analytics.by_app.items(), key=lambda x: x[1]["total"], reverse=True
            ):
                table.add_row(
                    app_name[:30], str(data["total"]), str(data["succeeded"]), str(data["failed"])
                )
            console.print(table)
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)


@app.command("watch")
def watch(
    interval: Annotated[
        int, typer.Option("--interval", "-i", help="Check interval in seconds")
    ] = 60,
    services_only: Annotated[
        bool, typer.Option("--services-only", help="Only monitor services")
    ] = False,
    output_file: Annotated[
        str, typer.Option("--output", "-o", help="Write JSON status to file")
    ] = "",
) -> None:
    """Continuous health monitoring with machine-readable output."""
    import json
    from datetime import datetime

    state, run_async, handle_error = _get_deps()
    try:
        client = state.get_client()
        settings = state.get_settings()

        is_json = state.is_json()
        if not is_json:
            console.print(
                f"[info]Watching infrastructure every {interval}s... Press Ctrl+C to stop.[/info]\n"
            )

        ssh = _get_ssh_client()

        try:
            if ssh:
                ssh.connect()

            while True:
                # Gather infrastructure issues
                from copilot_cli.services.coolify.commands.diag import _find_issues

                issues_result = run_async(_find_issues(client))

                # Gather docker stats if SSH available
                alerts: list[dict] = []
                container_stats: list[dict] = []

                if ssh:
                    from copilot_cli.services.coolify.monitoring.docker_stats import (
                        get_docker_stats,
                    )

                    stats = get_docker_stats(ssh)
                    for s in stats:
                        container_stats.append(
                            {
                                "name": s.name,
                                "cpu_percent": s.cpu_percent,
                                "memory_usage": s.memory_usage,
                                "memory_percent": s.memory_percent,
                                "status": s.status,
                            }
                        )
                        if s.memory_percent > settings.monitoring.memory_threshold:
                            alerts.append(
                                {
                                    "type": "memory_high",
                                    "resource": s.name,
                                    "value": s.memory_percent,
                                    "threshold": settings.monitoring.memory_threshold,
                                }
                            )
                        if s.cpu_percent > settings.monitoring.cpu_threshold:
                            alerts.append(
                                {
                                    "type": "cpu_high",
                                    "resource": s.name,
                                    "value": s.cpu_percent,
                                    "threshold": settings.monitoring.cpu_threshold,
                                }
                            )

                # Probe domains
                domain_results: list[dict] = []
                try:
                    from copilot_cli.services.coolify.monitoring.http_probes import (
                        probe_domains,
                    )

                    async def _get_all_domains():
                        apps, services = await asyncio.gather(
                            client.list_applications(),
                            client.list_services(),
                            return_exceptions=True,
                        )
                        domains = []
                        if isinstance(apps, list) and not services_only:
                            for a in apps:
                                fqdn = a.get("fqdn", "")
                                if fqdn:
                                    for d in fqdn.split(","):
                                        d = d.strip()
                                        if d:
                                            domains.append(d)
                        if isinstance(services, list):
                            for svc in services:
                                for d in svc.get("domains") or []:
                                    d = d.strip()
                                    if d:
                                        domains.append(d)
                        return domains

                    domains = run_async(_get_all_domains())
                    if domains:
                        probes = run_async(probe_domains(domains))
                        for p in probes:
                            domain_results.append(
                                {
                                    "url": p.url,
                                    "status": p.status_code,
                                    "healthy": p.healthy,
                                    "time_ms": p.response_time_ms,
                                    "error": p.error,
                                }
                            )
                            if not p.healthy:
                                alerts.append(
                                    {
                                        "type": "domain_down",
                                        "resource": p.url,
                                        "error": p.error or f"HTTP {p.status_code}",
                                    }
                                )
                except Exception:
                    pass

                # Determine overall status
                total_issues = issues_result.get("summary", {}).get("total_issues", 0)
                critical_alerts = [a for a in alerts if a["type"] in ("memory_high", "domain_down")]
                if total_issues > 0 or critical_alerts:
                    overall = (
                        "critical" if total_issues > 2 or len(critical_alerts) > 1 else "degraded"
                    )
                else:
                    overall = "healthy"

                status_doc = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "overall_status": overall,
                    "issues": issues_result.get("issues", []),
                    "alerts": alerts,
                    "domains": domain_results,
                    "containers": container_stats,
                    "ssh_available": ssh is not None and ssh.is_connected(),
                }

                if is_json:
                    print(json.dumps(status_doc))
                else:
                    # Rich display
                    status_style = {
                        "healthy": "green",
                        "degraded": "yellow",
                        "critical": "red",
                    }.get(overall, "white")
                    console.print(
                        f"[{status_style}][bold]{overall.upper()}[/bold][/{status_style}] "
                        f"— {datetime.now(UTC).strftime('%H:%M:%S UTC')}"
                    )
                    if issues_result.get("issues"):
                        for issue in issues_result["issues"]:
                            console.print(
                                f"  [red]✗[/red] [{issue.get('type')}] {issue.get('name', '')} — {issue.get('issue', '')}"
                            )
                    if alerts:
                        for a in alerts:
                            console.print(f"  [yellow]⚠[/yellow] {a['type']}: {a['resource']}")
                    if not issues_result.get("issues") and not alerts:
                        console.print("  All systems operational.")
                    console.print()

                if output_file:
                    with open(output_file, "w") as f:
                        json.dump(status_doc, f, indent=2)

                time.sleep(interval)

        except KeyboardInterrupt:
            if not is_json:
                console.print("\n[info]Watch stopped.[/info]")
        finally:
            if ssh:
                ssh.close()
    except SystemExit:
        raise
    except Exception as e:
        handle_error(e)
