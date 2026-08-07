---
title: Monitoring CLI
category: service-reference
last-updated: 2026-02-21
---

# Monitoring CLI

**Command:** `copilot monitoring`
**Source:** `copilot_cli/services/monitoring/`

## Purpose

System monitoring — CPU, memory, and disk metrics with configurable threshold alerts.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `monitoring status` | Show current system metrics | — |
| `monitoring alerts` | Show active threshold alerts | — |
| `monitoring health` | Check monitoring system | — |

## Examples

```bash
copilot monitoring status
copilot monitoring alerts
copilot monitoring health
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CPU_ALERT_THRESHOLD` | CPU usage alert threshold (%) | `80` |
| `MEMORY_ALERT_THRESHOLD` | Memory usage alert threshold (%) | `85` |
| `DISK_ALERT_THRESHOLD` | Disk usage alert threshold (%) | `90` |

## Health Check

```bash
copilot monitoring health
```

Checks: Verifies system metric collection is working and reports current CPU, memory, and disk usage.
