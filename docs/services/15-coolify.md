---
title: Coolify CLI
category: service-reference
last-updated: 2026-07-17
---

# Coolify CLI

**Command:** `copilot coolify`
**Source:** `copilot_cli/services/coolify/`

## Purpose

Full infrastructure management for Coolify-hosted servers — applications, databases, services, deployments, and real-time monitoring via API and SSH.

## Configuration

Coolify is the only service that does **not** use Pydantic Settings from `.env`. Instead, it has a three-layer config system (highest priority wins):

1. **CLI flags** (`--base-url`, `--token`) — override everything, useful for one-off commands
2. **Environment variables** (`COOLIFY_BASE_URL`, `COOLIFY_ACCESS_TOKEN`) — standard for CI/CD and containers
3. **TOML file** (`~/.coolify-cli/config.toml`) — persistent local config created by `copilot coolify config init`

Run `copilot coolify config show` to see which layer is active.

## Setup

```bash
# Interactive setup (discovers credentials from .mcp.json if present)
copilot coolify config init

# Or set environment variables
export COOLIFY_BASE_URL=https://coolify.example.com
export COOLIFY_ACCESS_TOKEN=your-token

# Config is stored at ~/.coolify-cli/config.toml
```

API-only commands (`coolify app`, `coolify db`, `coolify deploy`, `coolify envvar`, `coolify diag issues`, `coolify monitor health`) work as soon as the API token is set. The SSH-backed commands below need the separate setup in the next section.

## SSH Access (required for monitor / svc logs / diag containers)

Despite the wording in some help text, **this is not a tunnel** — `paramiko` opens a direct SSH session to the Coolify server and runs `docker ps`, `docker stats`, `docker logs` remotely. No port-forwarding, VPN, or `ProxyJump` is involved (though a jump host can be layered on top of your own `~/.ssh/config` if your network requires one — that's outside the CLI's concern).

**Commands that require SSH:**

| Command | What it does |
|---|---|
| `coolify monitor docker` | Per-container CPU/memory usage |
| `coolify monitor disk` | Disk usage + cleanup suggestions |
| `coolify monitor dashboard` | Live terminal dashboard |
| `coolify svc logs <uuid>` | Service container logs |
| `coolify diag <uuid>` | Container-level diagnostics (containers, stats, logs) |

Everything else (API calls) works without SSH.

### 1. Generate an SSH keypair (if you don't already have one)

```bash
ssh-keygen -t ed25519 -C "$(whoami)@$(hostname)-coolify" -f ~/.ssh/id_ed25519
# Press Enter twice for no passphrase, or set one and unlock via ssh-agent.
```

### 2. Authorize your key on the Coolify server

> **Coolify's "Private Keys" panel does not grant inbound SSH access to a server.** That panel stores private keys Coolify uses to SSH *outward* into the servers it manages. There is no Coolify API endpoint that writes to a server's `~/.ssh/authorized_keys`. Authorization must happen directly on the server, through a session that already has access (e.g. your cloud provider's console, or an existing authorized machine).

```bash
# From a machine that already has SSH access to the server:
ssh root@<your-server-host> \
  'umask 077 && mkdir -p ~/.ssh && echo "ssh-ed25519 AAAA…your-comment" >> ~/.ssh/authorized_keys && sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys'
```

### 3. Configure the CLI

Run the interactive wizard and answer **yes** when it asks about SSH:

```bash
copilot coolify config init
```

Or create `~/.coolify-cli/config.toml` directly:

```toml
[api]
base_url = "https://coolify.example.com"
access_token = "<your-token>"

[ssh]
host = "<your-server-host>"
user = "root"
port = 22
key_file = "~/.ssh/id_ed25519"
```

Then `chmod 600 ~/.coolify-cli/config.toml`.

> Env-var alternative: `COOLIFY_SSH_HOST`, `COOLIFY_SSH_USER`, `COOLIFY_SSH_PORT`, `COOLIFY_SSH_KEY_FILE` in `.env` work too, and override the TOML. The TOML path is preferred because the SSH block lives in one machine-local file alongside the API creds.

### 4. Verify end-to-end

```bash
copilot coolify config show          # SSH section should show host/user/port/key
copilot coolify monitor docker       # lists container CPU/mem — first SSH-backed call
copilot coolify monitor disk         # disk usage from the server
```

If `monitor docker` returns container rows, you're done. If it errors with `SSH authentication failed` or a connection timeout, see Troubleshooting below.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied (publickey)` | Public key not attached to the server in Coolify | Coolify UI → Servers → your server → Configuration → Private Key → select the key you uploaded |
| `SSH authentication failed` from CLI but raw `ssh root@…` works | `key_file` in config.toml points at the wrong path, or the key has a passphrase and there's no ssh-agent | Confirm the path with `copilot coolify config show`; run `ssh-add ~/.ssh/id_ed25519` if the key is encrypted |
| Connection timeout | Server moved, firewall blocking port 22 from your IP, or you're behind a VPN/proxy that drops outbound 22 | `nc -vz <host> 22` to test reachability; disconnect VPN |
| `Host key verification failed` | Server's host key rotated (rebuild) | `ssh-keygen -R <host>` then retry; paramiko uses `AutoAddPolicy` so a fresh entry is written automatically |
| `coolify monitor docker` says "SSH not configured" | TOML missing `[ssh]` section, or `host = ""` | Re-run `coolify config init` and answer yes to the SSH prompt |

## Periodic Monitoring

Run these checks regularly to catch issues before they become outages.

### Quick Health Check (run daily)

```bash
# Infrastructure issues scan — shows any unhealthy apps, databases, services, or unreachable servers
copilot coolify diag issues

# HTTP health probe all application domains — shows response times and status codes
copilot coolify monitor health
```

**What to look for:**
- Any issues reported by `diag issues` need immediate attention
- Response times above 2000ms in `monitor health` indicate resource pressure
- 503 status codes usually mean a Traefik/SSL cert issue — re-add the domain in the Coolify UI

### Resource Usage Check (run weekly or after deployments)

```bash
# Per-container CPU and memory usage (requires SSH)
copilot coolify monitor docker

# Disk usage with optional cleanup suggestions
copilot coolify monitor disk
copilot coolify monitor disk --cleanup-suggestions
```

**What to look for:**

| Metric | Healthy | Warning | Action Needed |
|--------|---------|---------|---------------|
| Container CPU | < 50% | 50–80% | > 80% sustained |
| Container memory | < 70% of limit | 70–85% | > 85% or no limit set |
| Total server memory | < 70% | 70–85% | > 85% — consider upgrade |
| Disk usage | < 70% | 70–85% | > 85% — run docker prune |

**Red flags in `monitor docker` output:**
- Any container using > 100% CPU sustained (not a brief spike) — likely a runaway process
- Any container using > 2 GiB memory without a limit set — set a `limits_memory` via the API or Coolify UI
- Any container with 0% CPU and 0 MiB that should be running — it crashed

### Deep Diagnostics (when something is wrong)

```bash
# Full infrastructure overview — counts of all resource types
copilot coolify diag overview

# Diagnose a specific application
copilot coolify diag app "App Name"

# Diagnose a specific server
copilot coolify diag server localhost

# Application log analysis — error rate, patterns, recent errors
copilot coolify monitor logs "App Name" --errors

# Deployment success rate and frequency
copilot coolify monitor deployments --days 30

# SSL certificate expiry check
copilot coolify monitor ssl
```

### Live Dashboard (interactive)

```bash
# Real-time terminal dashboard combining system metrics, app status, and deployments
# Requires SSH. Press Ctrl+C to exit.
copilot coolify monitor dashboard

# Live-updating docker stats
copilot coolify monitor docker --follow
```

## Resource Limits

Always set memory limits on containers to prevent a single runaway process from starving the server. Limits are set via the Coolify API or UI.

```bash
# Applications — limits_memory is in MiB
copilot coolify app get "App Name" --json  # check current limits

# Services — add mem_limit to docker compose in Coolify UI or via API
copilot coolify svc get "Service Name" --json
```

## Command Reference

### Server Management (`coolify server`)

| Command | Description |
|---------|-------------|
| `server list` | List all servers |
| `server get <query>` | Detailed server info |
| `server resources <query>` | List resources on a server |
| `server domains <query>` | List domains on a server |
| `server validate <query>` | Validate server connection |

### Application Management (`coolify app`)

| Command | Description |
|---------|-------------|
| `app list` | List all applications |
| `app get <query>` | Detailed application info |
| `app logs <query>` | View application logs |
| `app start/stop/restart <query>` | Lifecycle management |

### Database Management (`coolify db`)

| Command | Description |
|---------|-------------|
| `db list` | List all databases |
| `db get <query>` | Detailed database info |
| `db start/stop/restart <query>` | Lifecycle management |

#### Data transfer, backups, and remote queries — use `copilot db`, not `copilot coolify db`

`copilot coolify db` manages the Coolify resource (start/stop/list). For everything that touches data — dumping, restoring, pulling a remote DB to local, running read-only queries against a remote DB, or transitioning between databases — use the `copilot db` subcommands instead:

| Task | Command |
|------|---------|
| Dump a remote Coolify-managed DB to a local file | `copilot db dump "<coolify-name>"` |
| Pull a remote DB into a local database | `copilot db pull "<coolify-name>" --to <local-name>` |
| Copy one database into another (remote → local or local → local) | `copilot db transition <source> <target>` |
| Run a read-only query against a remote DB | `copilot db remote-query "<coolify-name>" "<sql>"` |
| Restore a dump file to a local database | `copilot db restore <dump-file> --to <local-name>` |

See [06-postgresql.md](./06-postgresql.md) for the full reference, policy details, and worked examples.

> **`coolify db delete` is hard-blocked.** Running `copilot coolify db delete` returns a policy-refusal message and exits without contacting the API. Coolify database resources must be deleted through the Coolify UI. The same block applies to `copilot coolify backup delete`.

### Service Management (`coolify svc`)

| Command | Description |
|---------|-------------|
| `svc list` | List all services |
| `svc get <query>` | Detailed service info |
| `svc start/stop/restart <query>` | Lifecycle management |

### Monitoring (`coolify monitor`)

| Command | Description |
|---------|-------------|
| `monitor dashboard` | Live terminal dashboard (SSH) |
| `monitor docker` | Container resource usage (SSH) |
| `monitor disk` | Disk usage analysis (SSH) |
| `monitor health` | HTTP health probe all domains |
| `monitor ssl` | SSL certificate expiry check |
| `monitor logs <query>` | Log aggregation and analysis |
| `monitor deployments` | Deployment analytics |

### Diagnostics (`coolify diag`)

| Command | Description |
|---------|-------------|
| `diag overview` | Infrastructure overview |
| `diag issues` | Scan for infrastructure problems |
| `diag app <query>` | Diagnose an application |
| `diag server <query>` | Diagnose a server |

### Other Commands

| Command | Description |
|---------|-------------|
| `config init` | Interactive setup wizard |
| `config show` | Show current configuration |
| `config path` | Print config file path |
| `version` | CLI and server versions |
| `deploy`, `project`, `env`, `envvar`, `team`, `key`, `backup`, `batch` | See `--help` for each |

## Global Options

All commands support:

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON |
| `--yaml` | Output as YAML |
| `--no-color` | Disable color output |
| `-v, --verbose` | Verbose error output |
| `--config <path>` | Custom config file path |
| `--base-url <url>` | Override API base URL |
| `--token <token>` | Override API token |
