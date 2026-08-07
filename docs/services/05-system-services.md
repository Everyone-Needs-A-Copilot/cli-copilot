---
title: System Services CLI
category: service-reference
last-updated: 2026-02-21
---

# System Services CLI

**Command:** `copilot services`
**Source:** `copilot_cli/services/system_services/`

## Purpose

macOS launchctl service management and process listing.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `services list` | List services | `--domain` |
| `services status` | Check service status | `SERVICE`, `--domain` |
| `services start` | Start a service | `SERVICE` |
| `services stop` | Stop a service | `SERVICE` |
| `services restart` | Restart a service | `SERVICE` |
| `services load` | Load a service plist | `PATH` |
| `services unload` | Unload a service plist | `PATH` |
| `services ps` | List processes | `--filter` |
| `services proc` | Get process details | `PID` |
| `services health` | Check launchctl availability | — |

## Examples

```bash
copilot services list
copilot services status com.example.myservice
copilot services start com.example.myservice
copilot services restart com.example.myservice
copilot services ps --filter "docker"
```

## Configuration

No configuration required. Uses macOS `launchctl` directly.

## Health Check

```bash
copilot services health
```

Checks: Verifies launchctl is available and responsive.
