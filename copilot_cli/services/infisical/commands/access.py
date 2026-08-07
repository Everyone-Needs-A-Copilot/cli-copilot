"""Evidence-backed verification of the interactive shared-store path."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated, Any

import typer

from copilot_cli.config.broker_auth import (
    BrokerUnavailable,
    acquire_access_grant,
)
from copilot_cli.services.infisical.core.api_client import InfisicalClient
from copilot_cli.services.infisical.core.config import broker_config, load_settings
from copilot_cli.services.infisical.core.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
)

app = typer.Typer(help="Verify short-lived shared-store access.", no_args_is_help=True)


def _report(
    *,
    result: str,
    detail: str,
    positive_read: bool,
    negative_denied: bool,
    secret_count: int | None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "result": result,
        "detail": detail,
        "auth_mode": "github-broker",
        "positive_read": positive_read,
        "negative_denied": negative_denied,
        "secret_count": secret_count,
        "read_only": positive_read and negative_denied,
    }


def _render(report: dict[str, Any]) -> None:
    from copilot_cli.services.infisical.main import state

    if state.is_json():
        from copilot_cli.services.infisical.output.json_out import output_data

        output_data(report, state.output_format)
        return
    from copilot_cli.services.infisical.output.console import console, err_console

    target = console if report["result"] == "ready" else err_console
    target.print(report["detail"])


@app.command("verify")
def verify(
    project: Annotated[str, typer.Option("--project", "-p", help="Project ID")],
    env: Annotated[str, typer.Option("--env", "-e", help="Environment slug")] = "prod",
    path: Annotated[str, typer.Option("--path", help="Authorized secret path")] = "/shared",
    negative_path: Annotated[
        str,
        typer.Option("--negative-path", help="Path that must be denied"),
    ] = "/__control_tower_denied__",
    scope: Annotated[
        str,
        typer.Option("--scope", help="Broker scope to prove (defaults to inherited config)"),
    ] = "",
) -> None:
    """Prove one authorized read and one out-of-scope denial.

    The report contains a count only. Secret names and values never leave the
    Infisical client, and this command refuses the legacy Universal Auth path.
    """
    from copilot_cli.services.infisical.main import run_async

    settings = load_settings()
    if not settings.broker_url:
        report = _report(
            result="unavailable",
            detail="GitHub-authorized shared access is not configured on this Mac.",
            positive_read=False,
            negative_denied=False,
            secret_count=None,
        )
        _render(report)
        raise typer.Exit(1)
    normalized = path.rstrip("/") or "/"
    negative = negative_path.rstrip("/") or "/"
    if (
        not project
        or not path.startswith("/")
        or not negative_path.startswith("/")
        or normalized == "/"
        or negative == normalized
        or negative.startswith(f"{normalized}/")
    ):
        report = _report(
            result="invalid-config",
            detail="The verification paths do not prove a narrower read-only boundary.",
            positive_read=False,
            negative_denied=False,
            secret_count=None,
        )
        _render(report)
        raise typer.Exit(1)

    async def _verify() -> dict[str, Any]:
        config = broker_config(settings)
        if scope:
            config = replace(config, scope=scope)
        grant = await acquire_access_grant(config)
        client = InfisicalClient(
            settings.base_url,
            access_token=grant.token,
            read_only=True,
        )
        try:
            items = await client.list_secrets(project, env, normalized)
            try:
                await client.list_secrets(project, env, negative)
            except AuthenticationError as exc:
                if "access denied" not in str(exc).casefold():
                    raise
                return _report(
                    result="ready",
                    detail="Shared access is ready and limited to the approved path.",
                    positive_read=True,
                    negative_denied=True,
                    secret_count=len(items),
                )
            return _report(
                result="unsafe",
                detail="Shared access reached a path that should have been denied.",
                positive_read=True,
                negative_denied=False,
                secret_count=len(items),
            )
        finally:
            await client.close()

    try:
        report = run_async(_verify())
    except (BrokerUnavailable, APIError, AuthenticationError, ConnectionError):
        report = _report(
            result="unavailable",
            detail="The complete GitHub-to-store access path could not be verified.",
            positive_read=False,
            negative_denied=False,
            secret_count=None,
        )
    _render(report)
    if report["result"] != "ready":
        raise typer.Exit(1)
