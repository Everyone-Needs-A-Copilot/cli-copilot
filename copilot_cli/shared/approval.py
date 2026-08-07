"""Shared approval guardrails for irreversible CLI operations."""

from __future__ import annotations

import typer

from copilot_cli.shared.output import print_error


def require_destructive_confirmation(
    action: str,
    target: str,
    *,
    approved: bool = False,
    approval_hint: str = "--force",
) -> None:
    """Require explicit approval before a destructive operation runs."""
    if approved:
        return

    if typer.confirm(f"{action} {target}? This is destructive.", default=False):
        return

    print_error(
        f"Cancelled: {action.lower()} was not approved.",
        hint=f"Re-run with {approval_hint} only when you intend to perform this operation.",
    )
    raise typer.Abort()
