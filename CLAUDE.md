# CLAUDE.md

## What This Repository Does

CLI Copilot is a standalone Python CLI tool with 12 service integrations. It provides the `copilot` command for managing infrastructure, APIs, databases, monitoring, and skill execution from any terminal. This repo is the public foundation; five org-specific vendor adapters (`crm`/NocoDB, `brevo`, `n8n`, `coolify`, `discord`) have moved to the org-specific `-internal` tier. `uspto` and `infisical` are kept as the two worked-example adapters — see README's "Reference adapters" note.

## Architecture

```
copilot_cli/
├── main.py          # Typer app — registers 12 subcommands + health
├── config/
│   └── settings.py  # Pydantic Settings — loads .env automatically
├── shared/
│   ├── errors.py    # CopilotError exception hierarchy
│   ├── http_client.py  # httpx wrapper with retry/auth/timeout
│   └── output.py    # Rich output helpers (tables, JSON, health)
└── services/
    └── <service>/
        ├── client.py    # Business logic, API calls
        └── commands.py  # Typer CLI commands
```

### Adding a New Service

1. Create `copilot_cli/services/<name>/` with `__init__.py`, `client.py`, `commands.py`
2. In `commands.py`: create a Typer sub-app, add commands
3. In `client.py`: implement business logic
4. In `main.py`: import and register with `app.add_typer()`
5. Add config fields to `config/settings.py` if needed
6. Add tests in `tests/test_services/test_<name>.py`
7. Add docs in `docs/services/XX-<name>.md`

### Service Patterns

- **Class-based clients** (6 services): git, docker, postgresql, skill, infisical, uspto — instantiated via `_client()` factory with lazy init
- **Module-level clients** (6 services): shell, filesystem, system_services, document, bi, monitoring — plain functions using `get_settings()`

### Skill Runtime (Model 2)

The `skill` service is a skill runtime engine. Skills are `.claude/skills/*/SKILL.md` files with YAML frontmatter that define executable workflows. The runtime provides:

- **Discovery:** finds skills in `.claude/skills/`, `SKILL_PATHS` env var, and `skill_paths` setting
- **Execution:** runs multi-step workflows with parameter interpolation (`{{ params.x }}`)
- **Verification:** runs check commands with exit code/stdout expectations
- **Auditing:** 15-check quality audit against skill standards

Skills with an `execution:` block in their frontmatter are executable via `copilot skill run`. Skills without it are documentation-only (still listable, showable, and auditable).

Key files:
- `copilot_cli/services/skill/models.py` — 11 Pydantic models (SkillFrontmatter, ExecutionSpec, etc.)
- `copilot_cli/services/skill/client.py` — SkillClient with discovery, parsing, execution, verification, audit
- `copilot_cli/services/skill/commands.py` — 7 CLI commands (list, show, plan, run, verify, audit, health)

### Key Conventions

- All services support a `health()` command
- All output uses `shared/output.py` helpers (Rich tables, JSON, panels)
- All errors use `shared/errors.py` hierarchy (CopilotError, ConfigError, ConnectionError, AuthError, NotFoundError, ValidationError, TimeoutError, RateLimitError)
- HTTP services use `shared/http_client.py` wrapper
- Configuration via Pydantic Settings from `.env`

## Commands

```bash
pip install -e ".[dev]"    # Install with dev deps
pytest tests/              # Run all tests
copilot --help             # Show all subcommands
copilot health             # Run all health checks
```

## Testing

Every service has a dedicated test file in `tests/test_services/`. All external dependencies are mocked via the autouse `mock_settings` fixture in `conftest.py`. No test makes real API calls or database connections.
