"""Infisical CLI — main entry point."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from copilot_cli.services.infisical.core.api_client import InfisicalClient
from copilot_cli.services.infisical.core.config import load_settings
from copilot_cli.services.infisical.output.console import console, err_console

# ─── Global state ─────────────────────────────────────────────────────────────


class State:
    """Global CLI state shared across Infisical commands."""

    def __init__(self) -> None:
        self.output_format: str = "table"  # table | json | yaml
        self.verbose: bool = False
        self.org_id: str = ""
        self.default_project: str = ""
        self._client: InfisicalClient | None = None

    def get_client(self) -> InfisicalClient:
        """Build (and cache) an API client from current settings."""
        if self._client is not None:
            return self._client

        settings = load_settings()
        if not settings.client_id or not settings.client_secret:
            err_console.print(
                "[error]Infisical credentials not configured.[/error]\n"
                "Set [bold]INFISICAL_CLIENT_ID[/bold] and "
                "[bold]INFISICAL_CLIENT_SECRET[/bold] in your .env."
            )
            raise typer.Exit(1)

        # Propagate org_id hint from settings if the CLI flag wasn't used
        if not self.org_id and settings.org_id:
            self.org_id = settings.org_id

        self._client = InfisicalClient(
            base_url=settings.base_url,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
        )
        return self._client

    def is_json(self) -> bool:
        """Return True when output format is JSON or YAML."""
        return self.output_format in ("json", "yaml")


state = State()


# ─── App ──────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="infisical",
    help="Infisical secrets management.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _global_callback(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    yaml_output: Annotated[bool, typer.Option("--yaml", help="Output as YAML")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colour output")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Verbose output")] = False,
    org_id: Annotated[str, typer.Option("--org-id", help="Organisation ID override")] = "",
) -> None:
    """Process global options before any subcommand runs."""
    if json_output:
        state.output_format = "json"
    elif yaml_output:
        state.output_format = "yaml"
    if no_color:
        console.no_color = True
        err_console.no_color = True
    state.verbose = verbose
    if org_id:
        state.org_id = org_id


app.callback()(_global_callback)


# ─── Async runner ─────────────────────────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro):
    """Run an async coroutine, reusing the event loop so the httpx client survives."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


def handle_error(e: Exception) -> None:
    """Print error to stderr and exit with code 1."""
    if state.verbose:
        err_console.print_exception()
    else:
        err_console.print(f"[error]Error:[/error] {e}")
    raise typer.Exit(1)


# ─── Config subcommands ───────────────────────────────────────────────────────

config_app = typer.Typer(help="Show Infisical configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Show configuration (credentials masked) and verify authentication."""
    settings = load_settings()

    masked_id = (
        settings.client_id[:4] + "***" + settings.client_id[-4:]
        if len(settings.client_id) >= 8
        else "***"
    )

    if state.is_json():
        from copilot_cli.services.infisical.output.json_out import output_data

        data: dict = {
            "base_url": settings.base_url,
            "client_id": masked_id,
            "org_id": settings.org_id or "(auto-discover)",
        }
        # Auth check
        try:
            client = state.get_client()
            name = run_async(client.validate_connection())
            data["auth_status"] = "ok"
            data["identity_name"] = name
        except Exception as e:
            data["auth_status"] = "failed"
            data["auth_error"] = str(e)
        output_data(data, state.output_format)
        return

    from rich.table import Table

    table = Table(title="Infisical Configuration", show_header=False)
    table.add_column("Key", style="label", width=20)
    table.add_column("Value")
    table.add_row("Base URL", settings.base_url)
    table.add_row("Client ID", masked_id)
    table.add_row("Org ID", settings.org_id or "[dim]auto-discover[/dim]")
    console.print(table)

    # Live auth check
    console.print("\n[info]Checking authentication...[/info]")
    try:
        client = state.get_client()
        name = run_async(client.validate_connection())
        console.print(f"[success]Auth OK[/success] — identity: [bold]{name}[/bold]")
    except Exception as e:
        err_console.print(f"[error]Auth FAILED:[/error] {e}")
        raise typer.Exit(1)


# ─── Register subcommand groups ───────────────────────────────────────────────


def _register_commands() -> None:
    """Import and register all command groups."""
    _groups: list[tuple[str, str]] = [
        ("copilot_cli.services.infisical.commands.project", "project"),
        ("copilot_cli.services.infisical.commands.folder", "folder"),
        ("copilot_cli.services.infisical.commands.secret", "secret"),
        ("copilot_cli.services.infisical.commands.identity", "identity"),
        ("copilot_cli.services.infisical.commands.org", "org"),
    ]

    import importlib

    for module_path, name in _groups:
        try:
            mod = importlib.import_module(module_path)
            app.add_typer(mod.app, name=name)
        except (ImportError, AttributeError):
            pass


_register_commands()
