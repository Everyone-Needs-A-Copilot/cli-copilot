"""Rich Console singleton and brand theme."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

# Brand theme
COOLIFY_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "heading": "bold magenta",
        "label": "dim",
        "uuid": "dim cyan",
        "status.running": "green",
        "status.stopped": "red",
        "status.error": "red bold",
        "status.building": "yellow",
        "status.deploying": "yellow",
        "status.healthy": "green",
        "status.unhealthy": "red",
        "status.unknown": "dim",
        "status.queued": "cyan",
        "status.finished": "green",
        "status.failed": "red",
        "status.cancelled": "dim",
    }
)

# Singleton console
console = Console(theme=COOLIFY_THEME)
err_console = Console(stderr=True, theme=COOLIFY_THEME)
