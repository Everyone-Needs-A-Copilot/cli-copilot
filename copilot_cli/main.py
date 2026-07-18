"""Copilot CLI - Unified CLI for infrastructure, APIs, databases, and monitoring."""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .shared import usage_ledger

app = typer.Typer(
    name="copilot",
    help="Unified CLI for infrastructure, APIs, databases, and monitoring.",
    no_args_is_help=True,
)

console = Console()

# Opt-in usage ledger (COPILOT_USAGE_LOG=1). See shared/usage_ledger.py and
# SOUL.md's "The Stateful Store" anti-pattern for the documented exception.
usage_ledger.install()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"copilot-cli {__version__}")
        raise typer.Exit()


def _json_callback(value: bool) -> None:
    if value:
        from .shared.output import set_json_mode

        set_json_mode(True)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=_version_callback, is_eager=True
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        callback=_json_callback,
        is_eager=True,
        help="Output as JSON instead of Rich tables.",
    ),
) -> None:
    """Copilot CLI - manage infrastructure from your terminal."""


# --- Register service subcommands ---

from .services.bi.commands import app as bi_app
from .services.docker.commands import app as docker_app
from .services.document.commands import app as docs_app
from .services.filesystem.commands import app as fs_app
from .services.git.commands import app as git_app
from .services.infisical.main import app as infisical_app
from .services.monitoring.commands import app as monitoring_app
from .services.postgresql.commands import app as db_app
from .services.shell.commands import app as shell_app
from .services.skill.commands import app as skill_app
from .services.system_services.commands import app as services_app
from .services.uspto.commands import app as uspto_app

app.add_typer(git_app, name="git", help="Git repository operations")
app.add_typer(docker_app, name="docker", help="Docker container management")
app.add_typer(shell_app, name="shell", help="Shell command execution")
app.add_typer(fs_app, name="fs", help="File system operations")
app.add_typer(services_app, name="services", help="System service management (launchctl)")
app.add_typer(db_app, name="db", help="PostgreSQL database operations")
app.add_typer(docs_app, name="docs", help="Document management")
app.add_typer(bi_app, name="bi", help="Business intelligence")
app.add_typer(monitoring_app, name="monitoring", help="System monitoring")
app.add_typer(infisical_app, name="infisical", help="Infisical secrets management")
app.add_typer(skill_app, name="skill", help="Skill runtime — discover, execute, verify skills")
app.add_typer(uspto_app, name="uspto", help="USPTO patent and trademark data access")


# --- Top-level health command ---


def _collect_health_checks() -> tuple[list[tuple[str, callable]], list[str]]:
    """Build the (name, check_fn) registry for every importable service.

    Split out from the `health` command so it can be unit tested without
    executing any check (import/registration is verified without making a
    single network call, filesystem probe, or subprocess).
    """
    checks: list[tuple[str, callable]] = []
    skipped: list[str] = []

    # Collect health check functions from each service
    try:
        from .services.docker.client import DockerClient

        checks.append(("docker", lambda: DockerClient().health()))
    except (ImportError, ModuleNotFoundError):
        skipped.append("docker")

    try:
        from .services.filesystem.client import health as fs_health

        checks.append(("filesystem", fs_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("filesystem")

    try:
        from .services.system_services.client import health as sysservices_health

        checks.append(("system_services", sysservices_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("system_services")

    try:
        from .services.postgresql.client import PostgreSQLClient

        checks.append(("postgresql", lambda: PostgreSQLClient().health()))
    except (ImportError, ModuleNotFoundError):
        skipped.append("postgresql")

    try:
        from .services.document.client import health as doc_health

        checks.append(("document", doc_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("document")

    try:
        from .services.bi.client import health as bi_health

        checks.append(("bi", bi_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("bi")

    try:
        from .services.monitoring.client import health as monitoring_health

        checks.append(("monitoring", monitoring_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("monitoring")

    try:
        from .services.skill.client import SkillClient

        checks.append(("skill", lambda: SkillClient().health()))
    except (ImportError, ModuleNotFoundError):
        skipped.append("skill")

    try:
        from .services.uspto.client import USPTOClient

        checks.append(("uspto", lambda: USPTOClient().health()))
    except (ImportError, ModuleNotFoundError):
        skipped.append("uspto")

    try:
        from .services.git.client import health as git_health

        checks.append(("git", git_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("git")

    try:
        from .services.shell.client import health as shell_health

        checks.append(("shell", shell_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("shell")

    try:
        import asyncio

        from .services.infisical.core.api_client import InfisicalClient
        from .services.infisical.core.config import load_settings as load_infisical_settings

        def _infisical_health():
            settings = load_infisical_settings()
            if not settings.client_id or not settings.client_secret:
                return {
                    "healthy": False,
                    "error": "Missing INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET",
                }

            async def _check():
                client = InfisicalClient(
                    settings.base_url, settings.client_id, settings.client_secret
                )
                try:
                    identity = await client.validate_connection()
                    return {"healthy": True, "identity": identity}
                finally:
                    await client.close()

            return asyncio.run(_check())

        checks.append(("infisical", _infisical_health))
    except (ImportError, ModuleNotFoundError):
        skipped.append("infisical")

    return checks, skipped


@app.command()
def health() -> None:
    """Run health checks across all services."""
    from .shared.output import print_health

    console.print("[bold]Copilot Health Check[/bold]\n")

    checks, skipped = _collect_health_checks()

    if not checks and not skipped:
        console.print("[dim]No services configured.[/dim]")
        return

    for name, check_fn in checks:
        try:
            result = check_fn()
            healthy = result.get("healthy", result.get("status") == "healthy")
            print_health(name, healthy, result if not healthy else None)
        except Exception as exc:
            print_health(name, False, {"error": str(exc)})

    for name in skipped:
        print_health(name, False, skipped=True)

    console.print()
