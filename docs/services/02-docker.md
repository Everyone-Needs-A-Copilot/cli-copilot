---
title: Docker CLI
category: service-reference
last-updated: 2026-02-21
---

# Docker CLI

**Command:** `copilot docker`
**Source:** `copilot_cli/services/docker/`

## Purpose

Docker container lifecycle management via Docker SDK for Python.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `docker ps` | List containers | `--all` |
| `docker start` | Start a container | `ID` |
| `docker stop` | Stop a container | `ID`, `--timeout` |
| `docker restart` | Restart a container | `ID`, `--timeout` |
| `docker info` | Show Docker system info | — |
| `docker health` | Check Docker daemon | — |

## Examples

```bash
copilot docker ps --all
copilot docker start my-container
copilot docker stop my-container --timeout 30
copilot docker restart my-container
copilot docker info
copilot docker health
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCKER_SOCKET` | Docker daemon socket path | `/var/run/docker.sock` |

## Health Check

```bash
copilot docker health
```

Checks: Pings the Docker daemon to verify connectivity.
