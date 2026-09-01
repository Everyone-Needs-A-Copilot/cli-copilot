# Service Patterns Reference

Real code patterns from representative copilot CLI services. Use as a reference when scaffolding new services.

## Pattern 1: Class-Based Client (6 services)

Used by: git, docker, postgresql, skill, infisical, uspto

**Best for:** External API services that need authentication and stateful HTTP connections.

### commands.py pattern

```python
"""Widgets CLI commands. (Hypothetical example service — not shipped.)"""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

# Sub-groups for organized command namespaces
catalog_app = typer.Typer(no_args_is_help=True)
orders_app = typer.Typer(no_args_is_help=True)
app.add_typer(catalog_app, name="catalog", help="Catalog operations")
app.add_typer(orders_app, name="orders", help="Order operations")


def _client():
    """Lazy client factory -- avoids import-time side effects."""
    from .client import WidgetsClient
    return WidgetsClient()


@app.command()
def health() -> None:
    """Check widgets service health."""
    from copilot_cli.shared.output import report_health
    # `report_health` guards CONSTRUCTION as well as the probe -- a signed-out
    # credential raises while the client is being built, upstream of
    # `health()`'s own guard. Pass the whole expression, never a bound method.
    report_health("widgets", lambda: _client().health())


@catalog_app.command("summary")
def catalog_summary(json_output: bool = typer.Option(False, "--json")) -> None:
    """Catalog summary."""
    from copilot_cli.shared.output import print_json, print_table
    data = _client().catalog_summary()
    if json_output:
        print_json(data)
    else:
        print_table([data], title="Catalog Summary")
```

**Key patterns:**
- `_client()` factory with lazy import inside function body
- `from __future__ import annotations` at top
- Sub-Typer apps for command grouping
- `--json` option for machine output
- Output helpers from `shared/output.py`

### client.py pattern

```python
"""Widgets client -- business logic and API calls. (Hypothetical example.)"""
from __future__ import annotations

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import ConfigError, ConnectionError, AuthError
from copilot_cli.shared.http_client import HttpClient


class WidgetsClient:
    def __init__(self):
        s = get_settings()
        if not s.widgets_api_key:
            raise ConfigError(
                "Missing WIDGETS_API_KEY",
                service="widgets",
                hint="Set WIDGETS_API_KEY in .env",
            )
        self._http = HttpClient(
            base_url=s.widgets_base_url,
            headers={"Authorization": f"Bearer {s.widgets_api_key}"},
        )

    def health(self) -> dict:
        """Check service health."""
        try:
            resp = self._http.get("/health")
            return {"healthy": True, **resp}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    def catalog_summary(self) -> dict:
        """Get catalog summary."""
        return self._http.get("/catalog/summary")
```

**Key patterns:**
- Constructor validates config and raises `ConfigError` with hint
- Uses `HttpClient` wrapper (handles retries, auth, timeouts)
- `health()` returns dict with `healthy` bool -- never raises
- Business methods return raw data, let commands format output

## Pattern 2: Module-Level Client (6 services)

Used by: shell, filesystem, system_services, document, bi, monitoring

**Best for:** Local system operations that don't need API auth or persistent connections.

### commands.py pattern

```python
"""Monitoring CLI commands."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def health() -> None:
    """Check monitoring service health."""
    from copilot_cli.shared.output import report_health
    from .client import health as _health
    report_health("monitoring", _health)


@app.command()
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    """System resource status (CPU, memory, disk)."""
    from copilot_cli.shared.output import print_json, print_table
    from .client import get_status
    data = get_status()
    if json_output:
        print_json(data)
    else:
        print_table([data], title="System Status")
```

### client.py pattern

```python
"""Monitoring client -- local system operations."""
from __future__ import annotations

import psutil


def health() -> dict:
    """Check monitoring is available."""
    try:
        psutil.cpu_percent()
        return {"healthy": True}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


def get_status() -> dict:
    """Get CPU, memory, disk usage."""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
    }
```

**Key patterns:**
- Plain functions, no class
- No `get_settings()` needed (uses system APIs directly)
- Same `health() -> dict` contract as class-based

## Pattern 3: Nested Command Groups (uspto / infisical)

Used by: `uspto` (most complex service — see `copilot_cli/services/uspto/` for the real code) and `infisical`.

**Best for:** Services with many command groups (uspto: auth, patents, trademarks, assignments, copyright, dossier, watch, sessions, portal, tsdr, discover; infisical: project, folder, secret, identity, org).

### commands.py pattern (abbreviated, modeled on uspto's real structure)

```python
"""Example CLI commands with many nested sub-groups."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

# Many sub-groups
auth_app = typer.Typer(no_args_is_help=True)
patents_app = typer.Typer(no_args_is_help=True)
trademarks_app = typer.Typer(no_args_is_help=True)
dossier_app = typer.Typer(no_args_is_help=True)
watch_app = typer.Typer(no_args_is_help=True)
sessions_app = typer.Typer(no_args_is_help=True)

app.add_typer(auth_app, name="auth", help="Auth requirements and capture instructions")
app.add_typer(patents_app, name="patents", help="Patent search and data access")
app.add_typer(trademarks_app, name="trademarks", help="Trademark search and data access")
app.add_typer(dossier_app, name="dossier", help="Dossier building")
app.add_typer(watch_app, name="watch", help="Watch/alert management")
app.add_typer(sessions_app, name="sessions", help="Session capture")
```

**Key pattern:** Each domain concept gets its own sub-Typer for clean namespacing: `copilot uspto patents search "..."`, `copilot uspto auth show <artifact-id>`, etc.

## When to Use Each Pattern

| Your Service | Pattern | Why |
|-------------|---------|-----|
| External API with auth | Class-based | Needs HttpClient, settings validation, persistent state |
| Local system tool | Module-level | No auth needed, stateless operations |
| API with 3+ command groups | Nested (class-based + sub-Typers) | Keeps CLI organized |
| Simple API with 2-3 commands | Class-based (flat) | Sub-Typers add unnecessary complexity |

## Registration in main.py

```python
# All services follow the same registration pattern:
from .services.uspto.commands import app as uspto_app
app.add_typer(uspto_app, name="uspto", help="USPTO patent and trademark data access")

from .services.monitoring.commands import app as monitoring_app
app.add_typer(monitoring_app, name="monitoring", help="System monitoring")
```

## Test Pattern

```python
"""Tests for a hypothetical widgets service."""
from unittest.mock import patch
from typer.testing import CliRunner
from copilot_cli.main import app

runner = CliRunner()

class TestHealth:
    def test_healthy(self, mock_settings):
        with patch("copilot_cli.services.widgets.client.WidgetsClient") as mock:
            mock.return_value.health.return_value = {"healthy": True}
            result = runner.invoke(app, ["widgets", "health"])
            assert result.exit_code == 0

class TestCatalog:
    def test_summary(self, mock_settings):
        with patch("copilot_cli.services.widgets.client.WidgetsClient") as mock:
            mock.return_value.catalog_summary.return_value = {"items": 5}
            result = runner.invoke(app, ["widgets", "catalog", "summary", "--json"])
            assert result.exit_code == 0
```

**Key pattern:** All tests use `mock_settings` fixture from `conftest.py`. External APIs are patched at the client class level.
