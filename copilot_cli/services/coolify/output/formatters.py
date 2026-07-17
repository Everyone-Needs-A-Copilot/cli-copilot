"""Output formatters — status badges, time formatting, byte sizes."""

from __future__ import annotations

from datetime import UTC, datetime


def status_badge(status: str | None) -> str:
    """Return a Rich-styled status badge."""
    if not status:
        return "[dim]unknown[/dim]"
    s = status.lower()
    if "running" in s or "healthy" in s:
        return f"[status.running]{status}[/status.running]"
    if "stopped" in s or "exited" in s:
        return f"[status.stopped]{status}[/status.stopped]"
    if "error" in s or "unhealthy" in s or "failed" in s:
        return f"[status.error]{status}[/status.error]"
    if "building" in s or "deploying" in s or "in_progress" in s or "queued" in s:
        return f"[status.building]{status}[/status.building]"
    if "finished" in s:
        return f"[status.finished]{status}[/status.finished]"
    if "cancelled" in s:
        return f"[status.cancelled]{status}[/status.cancelled]"
    return f"[dim]{status}[/dim]"


def relative_time(timestamp: str | None) -> str:
    """Format a timestamp as relative time (e.g., '5m ago')."""
    if not timestamp:
        return "[dim]\u2014[/dim]"
    try:
        # Handle various formats
        ts = timestamp.replace("Z", "+00:00")
        if "." in ts:
            # Truncate microseconds to 6 digits
            parts = ts.split(".")
            frac_and_tz = parts[1]
            # Find where the timezone starts
            for i, c in enumerate(frac_and_tz):
                if c in ("+", "-") and i > 0:
                    frac = frac_and_tz[:i][:6]
                    tz = frac_and_tz[i:]
                    ts = f"{parts[0]}.{frac}{tz}"
                    break
            else:
                ts = f"{parts[0]}.{frac_and_tz[:6]}"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "[dim]just now[/dim]"
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        days = seconds // 86400
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return f"[dim]{timestamp}[/dim]"


def format_bytes(size: int | float | None) -> str:
    """Format bytes to human-readable size."""
    if size is None:
        return "\u2014"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def truncate(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "\u2026"


def deployment_status_icon(status: str | None) -> str:
    """Return a simple icon for deployment status."""
    if not status:
        return "?"
    s = status.lower()
    if "finished" in s:
        return "\u2713"
    if "failed" in s:
        return "\u2717"
    if "in_progress" in s or "building" in s:
        return "\u25d0"
    if "queued" in s:
        return "\u25cc"
    if "cancelled" in s:
        return "\u2298"
    return "?"


def bool_icon(value: bool | None) -> str:
    """Return a checkmark or cross for boolean values."""
    if value is None:
        return "[dim]\u2014[/dim]"
    return "[green]\u2713[/green]" if value else "[red]\u2717[/red]"
