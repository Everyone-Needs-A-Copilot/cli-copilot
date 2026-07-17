---
title: Setup & Installation
category: getting-started
last-updated: 2026-02-21
---

# Setup & Installation

## Prerequisites

- Python 3.11+
- pip
- Access to services you want to use (APIs, databases, Docker, etc.)

## Install

### Standalone
```bash
git clone https://github.com/<your-org>/cli-copilot.git
cd cli-copilot
cp .env.example .env   # Edit with your credentials
pip install -e .
```

### As Dependency
```bash
pip install git+https://github.com/<your-org>/cli-copilot.git
```

## Configuration

Copy `.env.example` to `.env` and fill in credentials for the services you use. Services with missing config will error only when invoked — you don't need all credentials to use some services.

### .env Resolution

The CLI finds `.env` in this order:
1. `COPILOT_ENV_FILE` env var (explicit path)
2. Walk up from CWD looking for `.env`, stopping at project root markers (`.git`, `pyproject.toml`, `.mcp.json`, `package.json`)
3. Fall back to `.env` in current directory

### Embedded Usage

When installed in another project, set:
```bash
export COPILOT_ENV_FILE=/path/to/project/.env
```

Or just run `copilot` from within the project directory — it will find the project's `.env` automatically.

## Verification

```bash
copilot --help       # Shows all 19 subcommands
copilot --version    # Shows current version
copilot health       # Checks all services
```

## Development Setup

```bash
pip install -e ".[dev]"
pytest tests/
pytest tests/ --cov     # With coverage
```
