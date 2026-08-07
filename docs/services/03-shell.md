---
title: Shell CLI
category: service-reference
last-updated: 2026-02-21
---

# Shell CLI

**Command:** `copilot shell`
**Source:** `copilot_cli/services/shell/`

## Purpose

Safe shell command execution with security validation and script management.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `shell exec` | Execute a shell command | `COMMAND`, `--timeout`, `--working-dir` |
| `shell run` | Run a named script | `SCRIPT_NAME`, `--timeout` |
| `shell find` | Find scripts by pattern | `--pattern`, `--path` |
| `shell ps` | List running processes | `--pattern`, `--user` |

## Examples

```bash
copilot shell exec "ls -la /tmp"
copilot shell exec "docker compose up -d" --working-dir /opt/apps
copilot shell run backup-db --timeout 600
copilot shell find --pattern "*.sh"
copilot shell ps --pattern "python"
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SHELL_SCRIPTS_PATH` | Base path for named scripts | Required |
| `SHELL_TIMEOUT` | Default command timeout (seconds) | `3600` |

## Health Check

```bash
copilot shell health
```

Checks: Validates that the configured scripts path exists and is accessible.
