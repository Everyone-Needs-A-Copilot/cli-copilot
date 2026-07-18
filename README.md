# CLI Copilot

Unified command-line interface for infrastructure, APIs, databases, monitoring, and skill execution. One CLI, 12 services, portable across all Copilot projects. <!-- claim-check: cli-copilot-service-count -->

This repo is the **public base** for the `copilot` integration CLI: a credential-free foundation containing only generic, broadly-reusable service adapters (git, Docker, Postgres, and so on) — never anything specific to one company or product. It's a starting point for adopters who want the generic adapters plus a clear, guided pattern for adding their own. See "How This Fits in the Ecosystem" below for how a private, organization-specific layer builds on top of this foundation.

## Quick Start

```bash
# Install
pip install -e .

# Verify
copilot --help
copilot --version
cli_copilot --help

# Check all services
copilot health
```

If `copilot` is already taken by a shell alias or another tool on your machine, use `cli_copilot` instead.

## Installation

### Standalone (this repo)
```bash
cd cli-copilot
cp .env.example .env    # Fill in your credentials
pip install -e .
```

### As a dependency (other projects)
```bash
pip install git+https://github.com/<your-org>/cli-copilot.git
```

Set `COPILOT_ENV_FILE` to point to your project's `.env`, or the CLI will walk up from CWD to find the nearest `.env` file automatically. <!-- claim-check: cli-copilot-env-file-autodiscovery -->

If you add the new script after an existing install, refresh the console entry points with:
```bash
pip install -e .
```

## Available Services

| Command | Service | What It Does |
|---------|---------|-------------|
| `copilot git` | Git | Clone, pull, status, add, commit |
| `copilot docker` | Docker | Container lifecycle, system info |
| `copilot shell` | Shell | Execute commands, run scripts, find scripts, list processes |
| `copilot fs` | Filesystem | Read, write, delete, copy, move, list, search files |
| `copilot services` | System Services | macOS launchctl service management |
| `copilot db` | PostgreSQL | Multi-database queries, schema introspection, backups |
| `copilot docs` | Documents | Document CRUD, search, collections |
| `copilot bi` | Business Intelligence | Data analysis, pattern detection, KPIs |
| `copilot monitoring` | Monitoring | System metrics, alerts, health checks |
| `copilot infisical` | Infisical | Secrets management — projects, folders, secrets, machine identities |
| `copilot skill` | Skill Runtime | Discover, plan, execute, verify, and audit skills |
| `copilot uspto` | USPTO | Patent/trademark data access, TSDR retrieval, ODP requests |

Five org-specific vendor adapters that used to ship here (`crm`/NocoDB, `brevo`, `n8n`, `coolify`, `discord`) have moved to the org-specific `-internal` tier — see "Reference adapters" below.

Every service supports `--help`:
```bash
copilot docker --help
copilot db query --help
copilot uspto patents search --help
cli_copilot uspto health
```

## Adding Your Own Integration

This foundation ships 12 generic service adapters. To add your own — a private API, an internal tool, anything not already covered — run the guided wizard from Claude Code:

```
/setup-integration
```

It has the "right conversation" (service name, auth type, endpoints, operations, rate limits, secret names/scope), lets you choose **Python** (first-class — plugs straight into this repo's adapter architecture and is how all 12 built-in adapters work) or **Go** (a standalone binary via a documented stdin/stdout JSON subprocess contract), teaches the key-storage model (below), and then scaffolds the service — client, commands, config fields, tests, and docs — registering it in `main.py` for you. See [`.claude/commands/setup-integration.md`](.claude/commands/setup-integration.md) for the full wizard script.

**Reference adapters:** Before scaffolding, skim two existing adapters as worked examples — `uspto` (`copilot_cli/services/uspto/`, [`docs/services/20-uspto.md`](docs/services/20-uspto.md)) for an **unauthenticated external REST API** (read pattern), and `infisical` (`copilot_cli/services/infisical/`, [`docs/services/18-infisical.md`](docs/services/18-infisical.md)) for an **authenticated API that implements the `requires_secret` secrets contract** (auth + secret pattern). The `/setup-integration` wizard and the `new-service-scaffold` skill ([`.claude/skills/new-service-scaffold/`](.claude/skills/new-service-scaffold/)) both model a new adapter on these same two shapes. The secrets *contract* — `requires_secret: <NAME>` plus keychain/managed-store resolution — is the foundational principle; `infisical` is one example implementation of it, not the only valid choice (Vault, 1Password, and AWS Secrets Manager are equally valid backends for the same contract).

## How This Fits in the Ecosystem

This repo is the **public foundation** — the generic, credential-free base for the `copilot` CLI. It contains only adapters for broadly reusable services and never an adapter, endpoint, or credential specific to one company or product.

Organizations that adopt this foundation typically layer a private, org-scoped repo on top of it (an `-internal` tier) that adds their own proprietary adapters — internal APIs, customer-specific integrations — using the same `/setup-integration` pattern. That private tier inherits everything in this foundation and extends it; it never forks or replaces it, so upstream fixes and new generic adapters stay pullable.

Secrets never live in either repo. Adapters reference credentials by name only (`requires_secret: <NAME>` in config, never a value), and the name resolves at runtime from:
1. A per-user OS keychain entry (personal secrets), or
2. A managed, tier-scoped secret store (shared/team secrets) — whose *endpoint*, not the secret itself, comes from inherited config, gated by your own team membership.

If a secret can't be resolved, the command fails closed with `missing secret <NAME>` — never a silent default. See [`.claude/commands/setup-integration.md`](.claude/commands/setup-integration.md) (§3, "Key storage") for the full model.

## Usage Examples

```bash
# Docker
copilot docker ps --all
copilot docker restart my-container

# Database (nocodb/n8n here are example logical db names, not services)
copilot db query nocodb "SELECT * FROM clients LIMIT 10"
copilot db tables n8n
copilot db schema nocodb

# Secrets (Infisical)
copilot infisical secret list --project <project-id>
copilot infisical project list

# System
copilot monitoring status
copilot fs ls /Volumes/DockerApps
copilot services list

# Skills
copilot skill list                          # Discover all skills
copilot skill show deploy-product           # Detailed skill info
copilot skill plan deploy-product -p app-uuid=abc123   # Dry run
copilot skill run deploy-product -p app-uuid=abc123    # Execute
copilot skill verify deploy-product -p app-uuid=abc123 # Verify
copilot skill audit                         # Quality audit all skills

# USPTO
cli_copilot uspto health
cli_copilot uspto auth list
cli_copilot uspto auth status
cli_copilot uspto auth show patent_center_session
cli_copilot uspto products
cli_copilot uspto request patent/applications --params '{"searchText":"battery"}'
cli_copilot uspto patents search "battery enclosure"
cli_copilot uspto patents office-actions "*:*" --rows 5
cli_copilot uspto patents office-action-fields
cli_copilot uspto patents ptab "IPR2024"
cli_copilot uspto trademarks status 78787878
cli_copilot uspto trademarks tmog "ACME"
cli_copilot uspto trademarks id-manual "software as a service"
cli_copilot uspto dossier build acme "ACME,72131351"
cli_copilot uspto watch create acme-watch "ACME,72131351"
cli_copilot uspto sessions capture patent-center https://patentcenter.uspto.gov/
cli_copilot uspto tsdr docs 72131351 --query-type sn --format json
```

For the full USPTO integration strategy, including what is already automated, why some remaining adapters still require source-contract discovery, and the minimum artifact needed to finish them safely, see:

- [`docs/services/20-uspto.md`](docs/services/20-uspto.md)

## Configuration

All configuration is loaded from a `.env` file via Pydantic Settings. See `.env.example` for all available variables.

### .env Resolution Order

1. `COPILOT_ENV_FILE` environment variable (explicit path)
2. Walk up from current directory to find nearest `.env`
3. Fall back to `.env` in current directory

### MCP Servers (optional)

If you use Claude Code with MCP servers:
```bash
cp .mcp.json.example .mcp.json
# Edit .mcp.json — replace YOUR_HOME with your actual home directory path
```

### Usage Ledger (opt-in)

Set `COPILOT_USAGE_LOG=1` to append one JSON line per invocation to
`~/.copilot-cli/usage.jsonl` (override the path with `COPILOT_USAGE_LOG_PATH`):

```json
{"ts": "2026-07-12T15:57:02.694324Z", "cmd": "git status", "exit_code": 0, "duration_ms": 85, "version": "1.4.5"}
```

`cmd` is the resolved command path only (group + subcommand names) — never
argument or option values, and never environment contents. It is **off by
default**; a failure to write the ledger never breaks or slows the command
it's observing. See `SOUL.md`'s "The Stateful Store" anti-pattern for why
this is a documented, narrowly-scoped exception.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=copilot_cli

# Run live end-to-end connectivity checks across CLIs
make e2e-health
```

## Tech Stack

- **CLI Framework:** [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/)
- **HTTP Client:** [httpx](https://www.python-httpx.org/)
- **Configuration:** [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Database:** [psycopg2](https://www.psycopg.org/)
- **Docker:** [Docker SDK for Python](https://docker-py.readthedocs.io/)
- **Git:** [GitPython](https://gitpython.readthedocs.io/)
