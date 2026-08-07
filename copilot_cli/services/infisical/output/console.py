"""Rich Console singleton and brand theme.

Historical note: this module was originally borrowed from
``copilot_cli.services.coolify.output.console`` (identical content, renamed
theme). When the ``coolify`` adapter moved to the org-specific ``-internal``
tier, ``infisical`` -- a service meant to stand as a public foundation
reference adapter -- could no longer depend on it, so this small, fully
generic Rich console helper was copied here rather than left as a dangling
cross-service import.
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

# Brand theme
INFISICAL_THEME = Theme(
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
console = Console(theme=INFISICAL_THEME)
err_console = Console(stderr=True, theme=INFISICAL_THEME)
