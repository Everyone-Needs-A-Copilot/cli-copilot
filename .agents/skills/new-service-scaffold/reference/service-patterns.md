# Service Patterns Reference

Real code patterns from representative copilot CLI services. Use as a reference when scaffolding new services.

## Pattern 1: Class-Based Client (11 services)

Used by: git, docker, postgresql, nocodb, brevo, n8n, insights, project_copilot, conversations

**Best for:** External API services that need authentication and stateful HTTP connections.

### commands.py pattern

```python
"""Insights CLI commands."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

# Sub-groups for organized command namespaces
dashboard_app = typer.Typer(no_args_is_help=True)
forces_app = typer.Typer(no_args_is_help=True)
app.add_typer(dashboard_app, name="dashboard", help="Dashboard operations")
app.add_typer(forces_app, name="forces", help="Strategic forces")


def _client():
    """Lazy client factory -- avoids import-time side effects."""
    from .client import InsightsClient
    return InsightsClient()


@app.command()
def health() -> None:
    """Check insights service health."""
    from copilot_cli.shared.output import print_health
    result = _client().health()
    healthy = result.get("healthy", False)
    print_health("insights", healthy, result if not healthy else None)


@dashboard_app.command("summary")
def dashboard_summary(json_output: bool = typer.Option(False, "--json")) -> None:
    """Dashboard summary."""
    from copilot_cli.shared.output import print_json, print_table
    data = _client().dashboard_summary()
    if json_output:
        print_json(data)
    else:
        print_table([data], title="Dashboard Summary")
```

**Key patterns:**
- `_client()` factory with lazy import inside function body
- `from __future__ import annotations` at top
- Sub-Typer apps for command grouping
- `--json` option for machine output
- Output helpers from `shared/output.py`

### client.py pattern

```python
"""Insights client -- business logic and API calls."""
from __future__ import annotations

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import ConfigError, ConnectionError, AuthError
from copilot_cli.shared.http_client import HttpClient


class InsightsClient:
    def __init__(self):
        s = get_settings()
        if not s.insights_api_key:
            raise ConfigError(
                "Missing INSIGHTS_API_KEY",
                service="insights",
                hint="Set INSIGHTS_API_KEY in .env",
            )
        self._http = HttpClient(
            base_url=s.insights_base_url,
            headers={"Authorization": f"Bearer {s.insights_api_key}"},
        )

    def health(self) -> dict:
        """Check service health."""
        try:
            resp = self._http.get("/health")
            return {"healthy": True, **resp}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    def dashboard_summary(self) -> dict:
        """Get dashboard summary."""
        return self._http.get("/dashboard/summary")
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
    from copilot_cli.shared.output import print_health
    from .client import health as _health
    result = _health()
    healthy = result.get("healthy", False)
    print_health("monitoring", healthy, result if not healthy else None)


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

## Pattern 3: Nested Command Groups (conversations)

Used by: conversations (most complex service)

**Best for:** Services with many command groups (people, companies, forces, deals, conversations, coach, intel, transcripts, calendar, questions).

### commands.py pattern (abbreviated)

```python
"""Conversations CLI commands."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

# Many sub-groups
people_app = typer.Typer(no_args_is_help=True)
companies_app = typer.Typer(no_args_is_help=True)
forces_app = typer.Typer(no_args_is_help=True)
deals_app = typer.Typer(no_args_is_help=True)
conversations_app = typer.Typer(no_args_is_help=True)
coach_app = typer.Typer(no_args_is_help=True)
intel_app = typer.Typer(no_args_is_help=True)
auth_app = typer.Typer(no_args_is_help=True)

app.add_typer(people_app, name="people", help="People management")
app.add_typer(companies_app, name="companies", help="Company management")
app.add_typer(forces_app, name="forces", help="Force management")
app.add_typer(deals_app, name="deals", help="Deal management")
app.add_typer(conversations_app, name="conversations", help="Conversation management")
app.add_typer(coach_app, name="coach", help="Coaching features")
app.add_typer(intel_app, name="intel", help="Intelligence features")
app.add_typer(auth_app, name="auth", help="Authentication")
```

**Key pattern:** Each domain concept gets its own sub-Typer for clean namespacing: `copilot conv people list`, `copilot conv forces list`, etc.

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
from .services.insights.commands import app as insights_app
app.add_typer(insights_app, name="insights", help="Strategic intelligence")

from .services.monitoring.commands import app as monitoring_app
app.add_typer(monitoring_app, name="monitoring", help="System monitoring")
```

## Test Pattern

```python
"""Tests for insights service."""
from unittest.mock import patch
from typer.testing import CliRunner
from copilot_cli.main import app

runner = CliRunner()

class TestHealth:
    def test_healthy(self, mock_settings):
        with patch("copilot_cli.services.insights.client.InsightsClient") as mock:
            mock.return_value.health.return_value = {"healthy": True}
            result = runner.invoke(app, ["insights", "health"])
            assert result.exit_code == 0

class TestDashboard:
    def test_summary(self, mock_settings):
        with patch("copilot_cli.services.insights.client.InsightsClient") as mock:
            mock.return_value.dashboard_summary.return_value = {"signals": 5}
            result = runner.invoke(app, ["insights", "dashboard", "summary", "--json"])
            assert result.exit_code == 0
```

**Key pattern:** All tests use `mock_settings` fixture from `conftest.py`. External APIs are patched at the client class level.
