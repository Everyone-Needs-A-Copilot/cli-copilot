"""Service health assessment and actionable recommendations."""

from __future__ import annotations

from copilot_cli.services.coolify.monitoring.docker_stats import ContainerStats
from copilot_cli.services.coolify.monitoring.log_analyzer import LogAnalysis


def assess_service_health(
    service_data: dict,
    containers: list[ContainerStats],
    log_analyses: dict[str, LogAnalysis],
) -> list[dict]:
    """Generate actionable recommendations for a service.

    Returns list of {"severity": str, "title": str, "detail": str, "action": str}.
    """
    recommendations: list[dict] = []

    # Check for OOM in logs
    for container_name, analysis in log_analyses.items():
        if analysis.pattern_counts.get("oom", 0) > 0:
            recommendations.append(
                {
                    "severity": "critical",
                    "title": "Out-of-memory events detected",
                    "detail": f"Container {container_name} has OOM entries in logs.",
                    "action": "Increase memory limit to at least 2 GiB in Coolify service settings.",
                }
            )

    # Check memory pressure
    for c in containers:
        if c.memory_percent > 85:
            recommendations.append(
                {
                    "severity": "warning",
                    "title": "High memory usage",
                    "detail": f"Container {c.name} is using {c.memory_percent:.0f}% of its memory limit ({c.memory_usage} / {c.memory_limit}).",
                    "action": "Increase memory limit in Coolify service settings.",
                }
            )

    # Check for exited/restarting containers
    for c in containers:
        status_lower = c.status.lower()
        if "exited" in status_lower:
            recommendations.append(
                {
                    "severity": "critical",
                    "title": "Container exited",
                    "detail": f"Container {c.name} has exited: {c.status}.",
                    "action": "Check container logs and add restart policy (restart: unless-stopped) in Coolify.",
                }
            )
        elif "restarting" in status_lower:
            recommendations.append(
                {
                    "severity": "warning",
                    "title": "Container restarting",
                    "detail": f"Container {c.name} is in a restart loop: {c.status}.",
                    "action": "Check container logs for crash cause. Consider increasing memory or fixing startup errors.",
                }
            )

    # Check for high error rates in logs
    for container_name, analysis in log_analyses.items():
        if analysis.total_lines > 0 and analysis.error_rate > 20:
            recommendations.append(
                {
                    "severity": "warning",
                    "title": "High error rate in logs",
                    "detail": f"Container {container_name} has {analysis.error_rate}% error rate ({analysis.error_lines}/{analysis.total_lines} lines).",
                    "action": "Investigate error patterns and recent changes.",
                }
            )

    # Service status check
    status = service_data.get("status") or ""
    if "exited" in status or "error" in status:
        recommendations.append(
            {
                "severity": "critical",
                "title": "Service is down",
                "detail": f"Service status: {status}.",
                "action": "Restart the service via 'copilot coolify svc restart' and investigate root cause.",
            }
        )

    return recommendations
