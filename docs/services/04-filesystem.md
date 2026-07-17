---
title: Filesystem CLI
category: service-reference
last-updated: 2026-02-21
---

# Filesystem CLI

**Command:** `copilot fs`
**Source:** `copilot_cli/services/filesystem/`

## Purpose

File and directory operations within allowed volumes, with size limits and path validation.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `fs read` | Read file contents | `PATH` |
| `fs write` | Write content to file | `PATH`, `CONTENT` |
| `fs delete` | Delete a file | `PATH` |
| `fs cp` | Copy a file | `SRC`, `DEST` |
| `fs mv` | Move/rename a file | `SRC`, `DEST` |
| `fs ls` | List directory contents | `PATH`, `--recursive`, `--hidden` |
| `fs mkdir` | Create a directory | `PATH` |
| `fs search` | Search files | `PATH`, `--name`, `--content` |
| `fs checksum` | Calculate file checksum | `PATH`, `--algorithm` |
| `fs meta` | Show file metadata | `PATH` |
| `fs volumes` | List allowed volumes | — |
| `fs health` | Check volume accessibility | — |

## Examples

```bash
copilot fs ls /Volumes/DockerApps
copilot fs read /Volumes/DockerApps/config.yml
copilot fs search /Volumes/Dev --name "*.py" --content "import typer"
copilot fs checksum /path/to/file --algorithm sha256
copilot fs volumes
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_VOLUMES` | Comma-separated allowed paths | Required |
| `MAX_FILE_SIZE_MB` | Maximum file size for operations | `10` |

## Health Check

```bash
copilot fs health
```

Checks: Verifies each allowed volume is accessible.
