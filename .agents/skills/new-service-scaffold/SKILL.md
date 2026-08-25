---
name: new-service-scaffold
description: >-
  Add a new service to the copilot CLI — scaffolds directory structure, client, commands,
  config, tests, and docs following the 7-step process.
  Use when adding a new service integration to cli-copilot.
triggers:
  files: ["copilot_cli/services/**", "copilot_cli/main.py"]
  keywords: ["scaffold", "add", "create", "service", "integration", "new",
             "command", "copilot", "redis", "module", "extend"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# New Service Scaffold

## Overview

Scaffold a new service integration for the copilot CLI, following the 7-step process from AGENTS.md. Produces a complete, working service with client, commands, config, tests, and documentation — matching the existing codebase patterns.

## Define Done

A new service scaffold is complete when:

- [ ] Directory created: `copilot_cli/services/<name>/` with `__init__.py`, `client.py`, `commands.py`
- [ ] `health()` command implemented and returning structured output
- [ ] Service registered in `main.py` via `app.add_typer()`
- [ ] Config fields added to `settings.py`
- [ ] Tests created in `tests/test_services/test_<name>.py` and passing
- [ ] Documentation added in `docs/services/XX-<name>.md`
- [ ] All output uses `shared/output.py` helpers, all errors use `shared/errors.py` hierarchy

## Prerequisites

- Development environment set up: `pip install -e ".[dev]"`
- Understanding of the external API or system being integrated
- API credentials (if applicable) for testing

## Instructions

### Step 1: Create Directory Structure (REQUIRED)

```bash
mkdir -p copilot_cli/services/<name>/
touch copilot_cli/services/<name>/__init__.py
touch copilot_cli/services/<name>/client.py
touch copilot_cli/services/<name>/commands.py
```

### Step 2: Implement Commands (REQUIRED) (commands.py)

Choose the pattern based on service type:

**Class-based client pattern** (for API services — used by 11 services):

```python
"""<Name> CLI commands."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


def _client():
    """Lazy client factory."""
    from .client import <Name>Client
    return <Name>Client()


@app.command()
def health() -> None:
    """Check <name> service health."""
    from copilot_cli.shared.output import print_health
    result = _client().health()
    healthy = result.get("healthy", False)
    print_health("<name>", healthy, result if not healthy else None)


@app.command()
def list_items() -> None:
    """List <resources>."""
    from copilot_cli.shared.output import print_table
    data = _client().list_items()
    print_table(data, title="<Resources>")
```

**Module-level pattern** (for local/system services — used by 6 services):

```python
"""<Name> CLI commands."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def health() -> None:
    """Check <name> service health."""
    from copilot_cli.shared.output import print_health
    from .client import health as _health
    result = _health()
    healthy = result.get("healthy", False)
    print_health("<name>", healthy, result if not healthy else None)
```

**Key conventions:**
- Every service MUST have a `health()` command
- Use `from copilot_cli.shared.output import print_table, print_json, print_success, print_error` for output
- Use `from copilot_cli.shared.errors import CopilotError, ConfigError, AuthError, ...` for errors
- Lazy imports inside functions to avoid circular dependencies

### Step 3: Implement Client (REQUIRED) (client.py)

**Class-based client:**

```python
"""<Name> client - business logic and API calls."""
from __future__ import annotations

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import ConfigError, ConnectionError, AuthError
from copilot_cli.shared.http_client import HttpClient


class <Name>Client:
    def __init__(self):
        s = get_settings()
        if not s.<name>_api_key:
            raise ConfigError(
                "Missing <NAME>_API_KEY",
                service="<name>",
                hint="Set <NAME>_API_KEY in .env",
            )
        self._http = HttpClient(
            base_url=s.<name>_base_url,
            headers={"Authorization": f"Bearer {s.<name>_api_key}"},
        )

    def health(self) -> dict:
        try:
            resp = self._http.get("/health")
            return {"healthy": True, **resp}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    def list_items(self) -> list[dict]:
        return self._http.get("/items")
```

**Module-level client:**

```python
"""<Name> client - local system operations."""
from __future__ import annotations


def health() -> dict:
    try:
        # Check system is accessible
        return {"healthy": True}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}
```

### Step 4: Register in main.py (REQUIRED)

Add to `copilot_cli/main.py`:

```python
from .services.<name>.commands import app as <name>_app
app.add_typer(<name>_app, name="<name>", help="<Description>")
```

### Step 5: Add Config Fields to settings.py (REQUIRED)

Add to `copilot_cli/config/settings.py` in the `Settings` class:

```python
# --- <Name> ---
<name>_base_url: str = "https://<name>.example.com"
<name>_api_key: str = ""
```

### Step 6: Add Tests (REQUIRED)

Create `tests/test_services/test_<name>.py`:

```python
"""Tests for <name> service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app

runner = CliRunner()


class TestHealth:
    def test_healthy(self, mock_settings):
        with patch("copilot_cli.services.<name>.client.<Name>Client") as mock:
            mock.return_value.health.return_value = {"healthy": True}
            result = runner.invoke(app, ["<name>", "health"])
            assert result.exit_code == 0


class TestListItems:
    def test_list(self, mock_settings):
        with patch("copilot_cli.services.<name>.client.<Name>Client") as mock:
            mock.return_value.list_items.return_value = [{"id": 1, "name": "test"}]
            result = runner.invoke(app, ["<name>", "list-items"])
            assert result.exit_code == 0
```

All tests mock external dependencies via the `mock_settings` fixture from `conftest.py`.

### Step 7: Add Documentation (REQUIRED)

Create `docs/services/XX-<name>.md` with:
- Service overview
- Configuration requirements
- Command reference
- Examples

## Verification

```bash
# Run the new service's health check
copilot <name> health

# Run tests
pytest tests/test_services/test_<name>.py -v

# Run all tests to check for regressions
pytest tests/ -v

# Verify help text
copilot <name> --help
```

## Examples

### Example: Add a Redis Service

```bash
# 1. Scaffold
mkdir -p copilot_cli/services/redis/
# Create __init__.py, client.py, commands.py

# 2. Add config to settings.py
# redis_url: str = "redis://localhost:6379"

# 3. Register in main.py
# app.add_typer(redis_app, name="redis", help="Redis cache operations")

# 4. Test
copilot redis health
copilot redis --help

# 5. Run tests
pytest tests/test_services/test_redis.py -v
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ImportError` | Service not registered properly | Check `main.py` imports |
| `ConfigError` | Settings field missing | Add to `settings.py` |
| Test failures | Mock not matching | Check `conftest.py` mock_settings fixture |

## Quality Tests

### Convention Compliance Test
- New service follows all established conventions
- **PASS:** Service has `health()` command, uses output helpers, uses error hierarchy, uses lazy imports
- **FAIL:** Service prints directly to stdout instead of using `print_table`/`print_json`

### Pattern Match Test
- Service uses the correct pattern for its type (class-based vs module-level)
- **PASS:** API services use class-based client pattern; local services use module-level pattern
- **FAIL:** API service uses module-level functions instead of a client class with `_client()` factory

### Test Coverage Test
- All commands have corresponding test cases
- **PASS:** `pytest tests/test_services/test_<name>.py -v` passes with tests for health + all commands
- **FAIL:** Health command tested but other commands have no test coverage

### Registration Test
- Service is properly registered and accessible via CLI
- **PASS:** `copilot <name> --help` shows all commands; `copilot health --json` includes the service
- **FAIL:** Service exists but `copilot <name>` returns "No such command"

## Guidelines

1. Match existing patterns — read 2-3 similar services before starting
2. Every service needs a `health()` command
3. All output goes through `shared/output.py` helpers
4. All errors use `shared/errors.py` hierarchy
5. HTTP services use `shared/http_client.py` wrapper
6. All tests mock external dependencies — no real API calls
7. Use sub-Typer apps for nested command groups (see `crm`, `insights`, `conv` for examples)

## References

- Architecture: `AGENTS.md` — "Adding a New Service" section
- Error hierarchy: `copilot_cli/shared/errors.py`
- HTTP client: `copilot_cli/shared/http_client.py`
- Output helpers: `copilot_cli/shared/output.py`
- Settings: `copilot_cli/config/settings.py`
- Test fixtures: `tests/conftest.py`
- Existing services (reference patterns):
  - Class-based: `copilot_cli/services/insights/` (complex API)
  - Module-level: `copilot_cli/services/monitoring/` (local system)
  - Nested commands: `copilot_cli/services/conversations/` (many sub-groups)
