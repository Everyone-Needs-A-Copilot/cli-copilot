"""Coolify CLI — main entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from copilot_cli.services.coolify import __version__
from copilot_cli.services.coolify.core.api_client import CoolifyClient
from copilot_cli.services.coolify.core.config import (
    find_mcp_credentials,
    get_config_path,
    load_settings,
    save_toml_config,
)
from copilot_cli.services.coolify.output.console import console, err_console

# ─── Global state ─────────────────────────────────────────────────────────────


class State:
    """Global CLI state shared across commands."""

    def __init__(self) -> None:
        self.config_path: Path | None = None
        self.base_url: str | None = None
        self.token: str | None = None
        self.output_format: str = "table"  # table, json, yaml
        self.verbose: bool = False

    def get_settings(self):
        """Load settings with CLI flag overrides applied."""

        return load_settings(
            config_path=self.config_path,
            base_url_override=self.base_url,
            token_override=self.token,
        )

    def get_client(self) -> CoolifyClient:
        """Build an API client from current settings.

        Prints an error and exits if credentials are missing.
        """
        settings = self.get_settings()
        if not settings.api.base_url or not settings.api.access_token:
            err_console.print(
                "[error]No API configuration found.[/error]\n"
                "Run [bold]coolify config init[/bold] to set up, "
                "or provide --base-url and --token flags."
            )
            raise typer.Exit(1)
        return CoolifyClient(settings.api.base_url, settings.api.access_token)

    def is_json(self) -> bool:
        """Return True when the requested output format is structured (JSON/YAML)."""
        return self.output_format in ("json", "yaml")


state = State()


# ─── App ──────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="coolify",
    help="Coolify infrastructure management CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _global_callback(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    yaml_output: Annotated[bool, typer.Option("--yaml", help="Output as YAML")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable color output")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Verbose output")] = False,
    config_path: Annotated[Path | None, typer.Option("--config", help="Config file path")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Coolify API base URL")] = None,
    token: Annotated[str | None, typer.Option("--token", help="Coolify API token")] = None,
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
    state.config_path = config_path
    state.base_url = base_url
    state.token = token


app.callback()(_global_callback)


# ─── Helper to run async commands ─────────────────────────────────────────────


_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro):
    """Run an async coroutine, reusing the event loop so httpx clients survive."""
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


# ─── Version command ──────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Show CLI and Coolify server versions."""
    console.print(f"[bold]coolify-cli[/bold] v{__version__}")
    try:
        client = state.get_client()
        server_version = run_async(client.validate_connection())
        console.print(f"[bold]Coolify server[/bold] v{server_version}")
    except SystemExit:
        raise
    except Exception as e:
        err_console.print(f"[warning]Could not connect to server:[/warning] {e}")


# ─── Config subcommands ──────────────────────────────────────────────────────

config_app = typer.Typer(help="Manage CLI configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("path")
def config_path_cmd() -> None:
    """Print the config file location."""
    console.print(str(get_config_path()))


@config_app.command("show")
def config_show() -> None:
    """Show current configuration (secrets redacted)."""
    settings = state.get_settings()

    if state.is_json():
        from copilot_cli.services.coolify.output.json_out import output_data

        data = {
            "api": {
                "base_url": settings.api.base_url,
                "access_token": (
                    "***" + settings.api.access_token[-4:] if settings.api.access_token else ""
                ),
            },
            "ssh": {
                "host": settings.ssh.host,
                "user": settings.ssh.user,
                "port": settings.ssh.port,
                "key_file": settings.ssh.key_file,
            },
            "defaults": {
                "output_format": settings.defaults.output_format,
                "page_size": settings.defaults.page_size,
                "log_lines": settings.defaults.log_lines,
            },
            "monitoring": {
                "dashboard_refresh": settings.monitoring.dashboard_refresh,
                "health_check_interval": settings.monitoring.health_check_interval,
                "ssl_warn_days": settings.monitoring.ssl_warn_days,
            },
        }
        output_data(data, state.output_format)
        return

    table = Table(title="Configuration", show_header=False)
    table.add_column("Key", style="label", width=25)
    table.add_column("Value")

    table.add_row("Config file", str(get_config_path()))
    table.add_row("", "")
    table.add_row("[bold]API[/bold]", "")
    table.add_row("  Base URL", settings.api.base_url or "[dim]not set[/dim]")
    token = settings.api.access_token
    table.add_row("  Token", f"***{token[-4:]}" if token else "[dim]not set[/dim]")
    table.add_row("", "")
    table.add_row("[bold]SSH[/bold]", "")
    table.add_row("  Host", settings.ssh.host or "[dim]not set[/dim]")
    table.add_row("  User", settings.ssh.user)
    table.add_row("  Port", str(settings.ssh.port))
    table.add_row("  Key File", settings.ssh.key_file)
    table.add_row("", "")
    table.add_row("[bold]Defaults[/bold]", "")
    table.add_row("  Output Format", settings.defaults.output_format)
    table.add_row("  Page Size", str(settings.defaults.page_size))
    table.add_row("  Log Lines", str(settings.defaults.log_lines))

    console.print(table)


@config_app.command("init")
def config_init() -> None:
    """Interactive setup wizard."""
    console.print(Panel("[bold]Coolify CLI Setup Wizard[/bold]", border_style="cyan"))

    # Check for MCP credentials
    mcp_creds = find_mcp_credentials()
    base_url = ""
    access_token = ""

    if mcp_creds:
        console.print("\n[success]Found Coolify credentials in .mcp.json[/success]")
        console.print(f"  Base URL: {mcp_creds['base_url']}")
        console.print(f"  Token: ***{mcp_creds['access_token'][-4:]}")
        use_mcp = typer.confirm("Use these credentials?", default=True)
        if use_mcp:
            base_url = mcp_creds["base_url"]
            access_token = mcp_creds["access_token"]

    if not base_url:
        base_url = typer.prompt("Coolify API base URL", default="https://coolify.example.com")
    if not access_token:
        access_token = typer.prompt("API access token")

    # Validate connection
    console.print("\n[info]Validating connection...[/info]")
    try:
        client = CoolifyClient(base_url, access_token)
        server_version = run_async(client.validate_connection())
        console.print(f"[success]Connected to Coolify v{server_version}[/success]")
    except Exception as e:
        err_console.print(f"[error]Connection failed:[/error] {e}")
        if not typer.confirm("Save configuration anyway?", default=False):
            raise typer.Exit(1)

    # SSH configuration (optional)
    ssh_host = ""
    ssh_user = "root"
    ssh_port = 22
    ssh_key = str(Path.home() / ".ssh" / "id_ed25519")

    if typer.confirm("\nConfigure SSH for server monitoring?", default=False):
        ssh_host = typer.prompt("SSH host (same as Coolify server IP)", default="")
        ssh_user = typer.prompt("SSH user", default="root")
        ssh_port = int(typer.prompt("SSH port", default="22"))
        ssh_key = typer.prompt("SSH key file", default=ssh_key)

    # Save config
    config_data = {
        "api": {
            "base_url": base_url,
            "access_token": access_token,
        },
        "ssh": {
            "host": ssh_host,
            "user": ssh_user,
            "port": ssh_port,
            "key_file": ssh_key,
        },
        "defaults": {
            "output_format": "table",
            "page_size": 50,
            "log_lines": 100,
        },
        "monitoring": {
            "dashboard_refresh": 2,
            "health_check_interval": 30,
            "ssl_warn_days": 30,
            "cpu_threshold": 80,
            "memory_threshold": 85,
            "disk_threshold": 90,
            "response_time_ms": 2000,
        },
    }

    path = save_toml_config(config_data)
    console.print(f"\n[success]Configuration saved to {path}[/success]")
    console.print("[dim]File permissions set to 600 (owner read/write only)[/dim]")


# ─── Register subcommand groups ───────────────────────────────────────────────


def _register_commands() -> None:
    """Import and register all command groups.

    Imports are wrapped individually so the CLI remains functional even
    when some command modules have not been created yet.
    """
    _groups: list[tuple[str, str]] = [
        ("copilot_cli.services.coolify.commands.server", "server"),
        ("copilot_cli.services.coolify.commands.app", "app"),
        ("copilot_cli.services.coolify.commands.database", "db"),
        ("copilot_cli.services.coolify.commands.service", "svc"),
        ("copilot_cli.services.coolify.commands.project", "project"),
        ("copilot_cli.services.coolify.commands.env", "env"),
        ("copilot_cli.services.coolify.commands.envvar", "envvar"),
        ("copilot_cli.services.coolify.commands.deploy", "deploy"),
        ("copilot_cli.services.coolify.commands.team", "team"),
        ("copilot_cli.services.coolify.commands.key", "key"),
        ("copilot_cli.services.coolify.commands.github_app", "github-app"),
        ("copilot_cli.services.coolify.commands.backup", "backup"),
        ("copilot_cli.services.coolify.commands.diag", "diag"),
        ("copilot_cli.services.coolify.commands.batch", "batch"),
        ("copilot_cli.services.coolify.commands.monitor", "monitor"),
    ]

    import importlib

    for module_path, name in _groups:
        try:
            mod = importlib.import_module(module_path)
            app.add_typer(mod.app, name=name)
        except (ImportError, AttributeError):
            # Command module not yet implemented — skip silently
            pass


_register_commands()
