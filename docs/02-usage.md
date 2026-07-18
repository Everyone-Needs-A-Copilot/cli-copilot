---
title: Usage Guide
category: usage
last-updated: 2026-02-21
---

# Usage Guide

## Command Structure

```
copilot <service> [subgroup] <command> [options]
```

Examples:
```bash
copilot docker ps --all              # Simple command
copilot db query nocodb "SELECT 1"   # Command with args
copilot uspto auth show <artifact>   # Nested subgroup
copilot infisical secret get <name>  # Get by ID
```

## Global Patterns

### Help
Every command and subgroup supports `--help`:
```bash
copilot --help
copilot docker --help
copilot db query --help
```

### Version
```bash
copilot --version
```

### Health Checks
```bash
copilot health              # All services
copilot docker health       # Single service
copilot db health           # Database connectivity
```

## Output Format

All commands use Rich for formatted output:
- **Tables** for list results
- **JSON panels** for detailed objects
- **Health panels** with status indicators
- **Success/error messages** with consistent formatting

## Service Quick Reference

| Service | Common Commands |
|---------|----------------|
| `git` | `clone`, `pull`, `status`, `add`, `commit` |
| `docker` | `ps`, `start`, `stop`, `restart`, `info` |
| `shell` | `exec`, `run`, `find`, `ps` |
| `fs` | `read`, `write`, `ls`, `search`, `cp`, `mv` |
| `services` | `list`, `status`, `start`, `stop`, `restart` |
| `db` | `query`, `tables`, `columns`, `schema`, `health` |
| `docs` | `search`, `get`, `create`, `update`, `delete` |
| `bi` | `analyze`, `patterns`, `kpis`, `summary` |
| `monitoring` | `status`, `alerts`, `health` |
| `infisical` | `secret list/get/set/delete`, `project list`, `folder list` |
| `skill` | `list`, `show`, `plan`, `run`, `verify`, `audit`, `health` |
| `uspto` | `auth list/show/status`, `patents search`, `trademarks status` |
