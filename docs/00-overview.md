---
title: CLI Copilot Overview
category: architecture
last-updated: 2026-02-21
---

# CLI Copilot Overview

## What It Is

CLI Copilot is a unified Python command-line tool providing 12 service integrations under a single `copilot` command. <!-- claim-check: cli-copilot-service-count --> It gives every service the same uniform façade — one grammar, one `--json` contract, one portable `.env` — instead of a bespoke MCP server or client per service. Whether that one-grammar/portable approach beats per-service MCP servers on token economics is a measured claim, not an assumed one: internal benchmarking found the advantage is real but conditional on shipping the CLI's usage prose (agents need to be told the grammar exists before they use it over ad hoc tool calls).

This repo is the **public foundation**: only generic, broadly-reusable service adapters, never anything specific to one company or product. Five org-specific vendor adapters that used to live here (`crm`/NocoDB, `brevo`, `n8n`, `coolify`, `discord`) have moved to the org-specific `-internal` tier. `uspto` and `infisical` are kept as the two worked-example adapters for adopters scaffolding a new one — see the README's "Reference adapters" note.

## Architecture

**Package:** `copilot-cli` (Python 3.11+) <!-- claim-check: cli-copilot-python-version -->
**Entry point:** `copilot` command
**Framework:** Typer (CLI) + Rich (output) + httpx (HTTP) + psycopg2 (PostgreSQL)

### Service Categories

| Category | Services |
|----------|----------|
| Local Infrastructure | git, docker, shell, filesystem, system-services |
| Databases | postgresql (multi-DB pooling) |
| Analytics & Monitoring | document, bi, monitoring |
| Infrastructure | infisical (secrets) |
| Skill Runtime | skill (discovery, execution, verification, auditing) |
| Research & Intelligence | uspto |

> **Note:** All 12 shipped services use Pydantic Settings (`.env`). (Coolify's own three-layer config — CLI flags → environment variables → TOML file — was the one tolerated exception; it moved to the `-internal` tier along with the adapter itself.) <!-- claim-check: cli-copilot-service-count -->

### Package Structure

Each service has two files:
- `client.py` — Business logic, API calls, data transformation
- `commands.py` — Typer CLI commands that call the client

Shared utilities:
- `config/settings.py` — Pydantic Settings loading from `.env`
- `shared/errors.py` — Exception hierarchy
- `shared/http_client.py` — httpx wrapper
- `shared/output.py` — Rich output formatting

## Design Decisions

1. **Single package, not microservices** — One install, one command, zero coordination
2. **Pydantic Settings for config** — Type-safe, validates on startup, loads from `.env`
3. **Lazy client instantiation** — Services only connect when invoked
4. **Rich output everywhere** — Consistent tables, JSON, health panels
5. **Dual-mode .env** — Works standalone or embedded in host projects
