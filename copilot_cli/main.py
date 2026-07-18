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
#
# Manifest-driven: `resolve_cli_services()` returns the base 12 services in
# this same order when no `copilot.layers.yml` resolves a `cli` chain (the
# Phase-1 back-compat fast path -- see services/_loader.py), or the composed
# base+overlay set once a tier adopts/provides/overrides a service.

from .services._loader import resolve_cli_services

for _svc in resolve_cli_services():
    app.add_typer(_svc.app, name=_svc.name, help=_svc.help)


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


# --- Tier-inheritance introspection (WS-A: `copilot --json layers`) ---

LAYERS_SCHEMA_VERSION = 1


def _build_layers_payload() -> dict:
    """Build the `copilot layers` payload -- parse-not-compute friendly for
    Control Tower (invariant #1): every field here is already resolved by
    `config.layers`/`services._loader`, never recomputed by a renderer.

    See `docs/schemas/layers.schema.json` for the frozen JSON Schema this
    payload conforms to.
    """
    from .config.layers import find_layers_manifest, resolve_cli_layer_chain
    from .services._loader import resolve_cli_services

    manifest_path = find_layers_manifest()
    chain = resolve_cli_layer_chain()
    services = resolve_cli_services()

    return {
        "schema_version": LAYERS_SCHEMA_VERSION,
        "component": "cli",
        "manifest": {
            "path": str(manifest_path) if manifest_path else None,
            "cli_layers_resolved": chain is not None,
        },
        "chain": [
            {
                "id": layer.id,
                "role": layer.role,
                "rank": layer.rank,
                "repo": layer.repo,
                "ref": layer.ref,
                "auth": layer.auth,
                "unit": layer.unit,
            }
            for layer in (chain or [])
        ],
        "services": [
            {"name": svc.name, "help": svc.help, "tier": svc.tier, "mode": svc.mode}
            for svc in services
        ],
    }


@app.command()
def layers() -> None:
    """Show the resolved CLI tier chain and per-service provenance.

    With no `copilot.layers.yml` resolving a `component: cli` chain, this
    reports an empty chain and the base 12 services, each `tier:
    foundation, mode: base` -- the inert Phase-1 state. Control Tower calls
    this with `--json` and renders it (invariant #1: parse, never compute).
    """
    from .shared.output import is_json_mode, print_json

    payload = _build_layers_payload()

    if is_json_mode():
        print_json(payload)
        return

    if payload["manifest"]["cli_layers_resolved"]:
        console.print(f"[bold]CLI tier chain[/bold] (manifest: {payload['manifest']['path']})\n")
        for layer in payload["chain"]:
            console.print(f"  rank {layer['rank']:>4}  {layer['id']} ({layer['role']})")
    else:
        console.print("[bold]CLI tier chain[/bold]\n")
        console.print(
            "[dim]No copilot.layers.yml resolved a 'cli' component chain -- "
            "running the base foundation only.[/dim]"
        )
    console.print()
    for svc in payload["services"]:
        provenance = svc["tier"] if svc["mode"] == "base" else f"{svc['tier']} ({svc['mode']})"
        console.print(f"  {svc['name']:.<20s} {provenance}")
