"""Infisical CLI — main entry point."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from copilot_cli.services.infisical.core.api_client import InfisicalClient
from copilot_cli.services.infisical.core.config import (
    ADMIN_CLIENT_ID_KEY,
    ADMIN_CLIENT_SECRET_KEY,
    _keychain_lookup,
    broker_config,
    load_settings,
)
from copilot_cli.services.infisical.core.exceptions import ConfigError
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
        self._write_client: InfisicalClient | None = None

    def get_client(self) -> InfisicalClient:
        """Build (and cache) an API client from current settings."""
        if self._client is not None:
            return self._client

        settings = load_settings()
        broker_url = getattr(settings, "broker_url", "")
        if isinstance(broker_url, str) and broker_url.strip():
            from copilot_cli.config.broker_auth import (
                BrokerUnavailable,
                acquire_access_grant,
            )

            try:
                grant = run_async(acquire_access_grant(broker_config(settings)))
            except BrokerUnavailable as exc:
                err_console.print(f"[error]Shared access unavailable:[/error] {exc}")
                raise typer.Exit(1) from exc
            self._client = InfisicalClient(
                base_url=settings.base_url,
                access_token=grant.token,
                read_only=True,
            )
            return self._client

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

    def get_write_client(self) -> InfisicalClient:
        """Return a client that may write (create/update/delete).

        Precedence: explicit ``INFISICAL_CLIENT_ID``/``_SECRET`` (env, ``.env``,
        or keychain) always win. Otherwise a broker session is read-only, so the
        ecosystem-admin Universal Auth pair is read through the read client from
        the configured Infisical location (see ``INFISICAL_ADMIN_*`` settings)
        and used to log in. Raises ``ConfigError`` with a fix hint when the pair
        is missing. Credential values are never printed or logged.
        """
        if self._write_client is not None:
            return self._write_client

        settings = load_settings()
        client_id = settings.client_id or _keychain_lookup("INFISICAL_CLIENT_ID")
        client_secret = settings.client_secret or _keychain_lookup("INFISICAL_CLIENT_SECRET")
        if client_id and client_secret:
            self._write_client = InfisicalClient(
                base_url=settings.base_url, client_id=client_id, client_secret=client_secret
            )
            return self._write_client

        broker_url = getattr(settings, "broker_url", "")
        if not (isinstance(broker_url, str) and broker_url.strip()):
            # Non-broker sessions are already Universal Auth and writable.
            return self.get_client()

        reader = self.get_client()
        location = (settings.admin_project, settings.admin_env, settings.admin_path)
        values: dict[str, str] = {}
        for key in (ADMIN_CLIENT_ID_KEY, ADMIN_CLIENT_SECRET_KEY):
            try:
                secret = run_async(reader.get_secret(*location[:2], key, location[2]))
            except Exception as exc:
                raise ConfigError(
                    f"Writes need the ecosystem-admin credentials, but {key} could not be "
                    f"read from project {location[0]} env {location[1]} path {location[2]}: {exc}",
                    hint="Check INFISICAL_ADMIN_PROJECT/_ENV/_PATH, or set "
                    "INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET explicitly.",
                ) from exc
            value = secret.get("secretValue", "") if isinstance(secret, dict) else ""
            if not value:
                raise ConfigError(
                    f"Writes need the ecosystem-admin credentials, but {key} is empty or "
                    f"missing at project {location[0]} env {location[1]} path {location[2]}.",
                    hint="Store the ecosystem-admin Universal Auth pair there, or set "
                    "INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET explicitly.",
                )
            values[key] = value

        self._write_client = InfisicalClient(
            base_url=settings.base_url,
            client_id=values[ADMIN_CLIENT_ID_KEY],
            client_secret=values[ADMIN_CLIENT_SECRET_KEY],
        )
        return self._write_client

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
            "auth_mode": "github-broker" if settings.broker_url else "universal-auth",
            "store_scope": settings.store_scope if settings.broker_url else None,
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
    table.add_row("Auth mode", "GitHub broker" if settings.broker_url else "Universal Auth")
    if not settings.broker_url:
        table.add_row("Client ID", masked_id)
    else:
        table.add_row("Store scope", settings.store_scope)
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
        ("copilot_cli.services.infisical.commands.access", "access"),
    ]

    import importlib

    for module_path, name in _groups:
        try:
            mod = importlib.import_module(module_path)
            app.add_typer(mod.app, name=name)
        except (ImportError, AttributeError):
            pass


_register_commands()
