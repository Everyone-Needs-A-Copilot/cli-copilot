"""Deployment analytics — frequency, success rate, duration trends."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DeploymentAnalytics:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    deployments_per_day: float = 0.0
    by_app: dict[str, dict] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    daily_counts: dict[str, int] = field(default_factory=dict)


def analyze_deployments(deployments: list[dict], days: int = 30) -> DeploymentAnalytics:
    """Analyze deployment data."""
    result = DeploymentAnalytics()
    result.total = len(deployments)

    if not deployments:
        return result

    status_counter: Counter[str] = Counter()
    app_counter: dict[str, dict] = {}
    daily_counter: Counter[str] = Counter()
    durations: list[float] = []

    for dep in deployments:
        status = dep.get("status", "unknown")
        status_counter[status] += 1

        app_name = dep.get("application_name") or dep.get("application_uuid") or "unknown"
        if app_name not in app_counter:
            app_counter[app_name] = {"total": 0, "succeeded": 0, "failed": 0}
        app_counter[app_name]["total"] += 1
        if status == "finished":
            app_counter[app_name]["succeeded"] += 1
        elif status == "failed":
            app_counter[app_name]["failed"] += 1

        # Daily count
        created = dep.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                daily_counter[dt.strftime("%Y-%m-%d")] += 1
            except (ValueError, TypeError):
                pass

        # Duration estimate (created_at to updated_at)
        updated = dep.get("updated_at", "")
        if created and updated and status in ("finished", "failed"):
            try:
                start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                duration = (end - start).total_seconds()
                if 0 < duration < 7200:  # Reasonable range: 0-2 hours
                    durations.append(duration)
            except (ValueError, TypeError):
                pass

    result.succeeded = status_counter.get("finished", 0)
    result.failed = status_counter.get("failed", 0)
    result.cancelled = status_counter.get("cancelled", 0)
    result.success_rate = round(result.succeeded / max(result.total, 1) * 100, 1)
    result.avg_duration_seconds = (
        round(sum(durations) / max(len(durations), 1), 1) if durations else 0.0
    )
    result.deployments_per_day = round(result.total / max(days, 1), 1)
    result.by_app = app_counter
    result.by_status = dict(status_counter)
    result.daily_counts = dict(daily_counter)

    return result
