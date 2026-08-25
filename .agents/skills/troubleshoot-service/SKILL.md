---
name: troubleshoot-service
description: >-
  Debug copilot service connectivity, authentication, and configuration issues.
  Use when a service health check fails, commands return errors, or behavior is unexpected.
triggers:
  keywords: ["troubleshoot", "debug", "fix", "error", "broken", "not working", "503",
             "401", "timeout", "connection refused", "unhealthy", "config error",
             "auth error", "service down"]
allowed-tools: Read, Bash, Grep, Glob
---

# Troubleshoot Service

## Overview

Systematic debugging of copilot service issues using the CopilotError hierarchy, health commands, and configuration checks. Start with the error type, trace to root cause, apply the fix.

## Define Done

Troubleshooting is complete when:

- [ ] Error type identified (mapped to CopilotError hierarchy)
- [ ] Root cause found (not just the symptom)
- [ ] Fix applied and the failing command now succeeds
- [ ] Full health check passes with no cascading issues

## Prerequisites

- `copilot` CLI installed
- Access to `.env` file for configuration review
- Basic understanding of which service is failing

## Instructions

### Step 1: Identify the Error Type (REQUIRED)

Run the failing command with `--json` to get structured error output:

```bash
copilot <service> <command> --json
```

Map the error to the CopilotError hierarchy:

| Error Type | Message Pattern | Root Cause |
|------------|----------------|------------|
| `ConfigError` | "Missing or invalid configuration" | Env var not set or wrong format |
| `AuthError` | "Authentication failure" / 401 / 403 | Bad API key or expired token |
| `ConnectionError` | "Cannot reach service" / connection refused | Service not running or network issue |
| `NotFoundError` | "Resource does not exist" / 404 | Wrong ID or resource deleted |
| `ValidationError` | "Input failed validation" | Bad parameter format |
| `TimeoutError` | "Operation exceeded time limit" | Service overloaded or hanging |
| `RateLimitError` | "Rate limit exceeded" / 429 | Too many requests |

### Step 2: Run Targeted Health Check (REQUIRED)

```bash
# Master health check (all services)
copilot health --json

# Service-specific health
copilot <service> health --json
```

### Step 3: Diagnose by Error Type (REQUIRED)

#### ConfigError — Check Configuration

```bash
# Read .env to verify the variable exists and has a value
# Check settings.py for the expected variable name
```

| Service | Required Env Vars |
|---------|-------------------|
| n8n | `N8N_BASE_URL`, `N8N_API_KEY` |
| NocoDB (CRM) | `NOCODB_URL`, `NOCODB_API_KEY`, `NOCODB_BASE_ID` |
| Brevo | `BREVO_API_KEY` |
| PostgreSQL | `DATABASE_URL` (+ per-database URLs) |
| Insights | `INSIGHTS_BASE_URL`, `INSIGHTS_API_KEY` |
| Project Copilot | `PROJECT_COPILOT_BASE_URL`, `PROJECT_COPILOT_API_KEY` |
| Conversations | `CONVERSATIONS_BASE_URL`, `CONVERSATIONS_API_TOKEN` |
| Coolify | `COOLIFY_BASE_URL`, `COOLIFY_ACCESS_TOKEN` |
| Docker | `DOCKER_SOCKET` (default: /var/run/docker.sock) |
| Monitoring | No required vars (uses system APIs) |
| Filesystem | `ALLOWED_VOLUMES` (default: /tmp) |

#### AuthError — Verify Credentials

```bash
# Test with a simple read-only command
copilot <service> health --json

# For Coolify: check key validity
copilot coolify key list --json

# For Conversations: re-authenticate
copilot conv auth login --json
copilot conv auth me --json

# For Project Copilot: verify identity
copilot project identity --json
```

#### ConnectionError — Check Infrastructure

```bash
# Is Docker running? (most services run in containers)
copilot docker info --json
copilot docker ps --json

# Is the service container running?
copilot docker ps --json
# → Look for the service container

# Is Coolify managing the service?
copilot coolify app list --json
# → Check app status

# Is the server reachable?
copilot coolify server healthcheck --json

# Check system resources (service may have crashed due to OOM)
copilot monitoring status --json
copilot monitoring alerts --json
```

#### TimeoutError — Check Load

```bash
# System resource pressure
copilot monitoring status --json
# → CPU > 80%, Memory > 85%, Disk > 90% = problem

# Database connection exhaustion
copilot db stats --json
# → High active connections = problem

# Check for stuck processes
copilot services list --json
copilot shell ps --json
```

#### NotFoundError — Verify Resource Exists

```bash
# List resources to find the correct ID
copilot <service> <resource> list --json

# Common: wrong database name
copilot db tables --database nocodb --json
# Valid names: main, nocodb, n8n, formbricks
```

### Step 4: Apply Fix and Verify (REQUIRED)

After fixing the root cause:

```bash
# Re-run health check
copilot <service> health --json

# Re-run the original failing command
copilot <service> <command> --json

# Run full health check to confirm no side effects
copilot health --json
```

## Examples

### Example: Insights Copilot Returns 401

```bash
# 1. Identify: AuthError
copilot insights health --json
# → {"healthy": false, "error": "AuthError: 401 Unauthorized"}

# 2. Check config
# → INSIGHTS_API_KEY exists in .env but may be expired

# 3. Test with basic call
copilot insights version --json
# → Same 401

# 4. Fix: regenerate API key in Insights admin, update .env
# → Set INSIGHTS_API_KEY=new_key_value

# 5. Verify
copilot insights health --json
# → {"healthy": true}
```

### Example: CRM Connection Refused

```bash
# 1. Identify: ConnectionError
copilot crm health --json
# → {"healthy": false, "error": "ConnectionError: Connection refused"}

# 2. Check infrastructure
copilot docker ps --json
# → NocoDB container not listed (crashed or stopped)

# 3. Check Coolify
copilot coolify app list --json
# → NocoDB app status: "stopped"

# 4. Fix: restart via Coolify
copilot coolify app restart --uuid "nocodb-app-uuid"

# 5. Verify
copilot crm health --json
# → {"healthy": true}
```

### Example: Database Timeout

```bash
# 1. Identify: TimeoutError
copilot db query --database nocodb --sql "SELECT count(*) FROM large_table" --json
# → TimeoutError

# 2. Check resources
copilot monitoring status --json
# → {"cpu_percent": 92, "memory_percent": 88}

# 3. Check connections
copilot db stats --json
# → High active connections

# 4. Fix: vacuum to reclaim space, or check for long-running queries
copilot db query --database nocodb --sql "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active'" --json
copilot db vacuum --database nocodb --json

# 5. Verify
copilot db health --json
```

## Error Handling

This skill IS the error handling skill. When troubleshooting fails:

1. Check if the service is managed by Coolify → restart via `copilot coolify app restart`
2. Check Docker containers → restart via `copilot docker restart`
3. Check system resources → if disk full, clean up; if memory full, restart services
4. If nothing works → check Coolify deployment logs: `copilot coolify deploy list --json`

## Quality Tests

### Root Cause Test
- Fix addresses the actual root cause, not just the immediate symptom
- **PASS:** ConnectionError traced to stopped Docker container and restarted, not just retried
- **FAIL:** ConnectionError "fixed" by retrying the same command — it'll fail again

### Recovery Command Test
- Every error type has a specific, executable recovery command
- **PASS:** Each row in the error handling table includes a `copilot ...` command to run
- **FAIL:** Recovery advice says "check the configuration" without naming the specific variable

### No-Regression Test
- Fix doesn't break other services
- **PASS:** `copilot health --json` shows all previously-healthy services still healthy after fix
- **FAIL:** Fixing one service caused another to become unhealthy (dependency issue)

### Reproducibility Test
- The diagnostic steps can reliably reproduce and isolate the issue
- **PASS:** Following Steps 1-3 consistently identifies the same root cause
- **FAIL:** Diagnostic steps are vague ("look at logs") and don't isolate the problem

## Guidelines

1. Always start with `--json` output — structured errors are easier to diagnose
2. Follow the error type → diagnosis → fix → verify pattern
3. Check infrastructure (Docker/Coolify) before checking application config
4. After fixing, always run `copilot health --json` to verify no cascading issues
5. If a service keeps failing, check its Coolify deployment logs for build errors

## References

- Related skills: `infrastructure-health`, `deploy-product`
- Error hierarchy: `copilot_cli/shared/errors.py`
- Config reference: `copilot_cli/config/settings.py`
- All service health commands: see `cli-router` skill
