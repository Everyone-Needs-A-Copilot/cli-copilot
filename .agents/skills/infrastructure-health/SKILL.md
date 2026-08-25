---
name: infrastructure-health
description: >-
  Comprehensive health check and triage across all copilot services — monitoring, docker,
  system services, databases, APIs, and Coolify infrastructure.
  Use when diagnosing outages, verifying system status, or running pre-deployment checks.
triggers:
  keywords: ["health", "infrastructure", "status", "outage", "down", "unhealthy",
             "monitoring", "diagnostics", "triage", "system", "check", "uptime"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  steps:
    - name: full-health-check
      script: scripts/full-health-check.sh
      description: Run copilot health, drill into unhealthy services, check resources, produce triage report
  verify:
    - name: copilot-health
      command: copilot health
      expect: 'exit_code == 0'
    - name: monitoring-status
      command: copilot monitoring status --json
      expect: 'exit_code == 0'
---

# Infrastructure Health

## Overview

Run a comprehensive health check across all copilot-managed services, then triage any failures by severity and dependency order. This skill orchestrates individual service health commands into a single diagnostic workflow.

## Define Done

This health check is complete when:

- [ ] All 3 infrastructure layers checked: infrastructure (Coolify/Docker), databases (PostgreSQL), services (APIs)
- [ ] Failures triaged by dependency order (infrastructure → databases → core services → product APIs → external APIs)
- [ ] Each unhealthy service has a specific diagnosis and next action
- [ ] System resource thresholds verified (CPU < 80%, Memory < 85%, Disk < 90%)
- [ ] Report produced with clear severity per finding

## Prerequisites

- `copilot` CLI installed and configured (`pip install -e .`)
- `.env` file with credentials for services you want to check
- Run from the project root (where `.env` is located)

## Instructions

### Step 1: Run the Master Health Check (REQUIRED)

```bash
copilot health --json
```

This checks all 16 services in sequence. Parse the JSON output to categorize results:

| Status | Meaning | Action |
|--------|---------|--------|
| `healthy` | Service responding normally | No action |
| `unhealthy` | Service reachable but failing | Investigate details |
| `skipped` | Service not configured | Check `.env` if unexpected |

### Step 2: Drill Into Unhealthy Services (REQUIRED)

For each unhealthy service, run its specific health command for detailed diagnostics:

| Service | Drill-Down Command |
|---------|-------------------|
| Docker | `copilot docker info --json` then `copilot docker ps --json` |
| PostgreSQL | `copilot db health --json` then `copilot db stats --json` |
| System services | `copilot services list --json` |
| Monitoring | `copilot monitoring status --json` then `copilot monitoring alerts --json` |
| Coolify | `copilot coolify server healthcheck --json` then `copilot coolify monitor dashboard --json` |
| NocoDB (CRM) | `copilot crm health --json` |
| Brevo | `copilot brevo health --json` |
| n8n | `copilot n8n health --json` |
| Insights | `copilot insights health --json` then `copilot insights version --json` |
| Project Copilot | `copilot project health --json` then `copilot project identity --json` |
| Conversations | `copilot conv auth me --json` |

### Step 3: Check System Resources (REQUIRED)

```bash
# CPU, memory, disk usage
copilot monitoring status --json

# Active alerts (thresholds: CPU 80%, memory 85%, disk 90%)
copilot monitoring alerts --json
```

### Step 4: Check Infrastructure Layer (Coolify) (OPTIONAL)

```bash
# Server health
copilot coolify server healthcheck --json

# Running applications
copilot coolify app list --json

# Running databases
copilot coolify db list --json

# Active services
copilot coolify svc list --json

# Recent deployments (check for failures)
copilot coolify deploy list --json
```

### Step 5: Check Database Connections (OPTIONAL)

```bash
# All configured database connections
copilot db health --json

# Connection pool stats (look for exhaustion)
copilot db stats --json

# Individual databases: nocodb, n8n, formbricks, main
copilot db tables --database nocodb --json
```

### Step 6: Triage and Report (REQUIRED)

Prioritize failures by dependency order:

1. **Infrastructure** (Coolify servers, Docker) — everything depends on this
2. **Databases** (PostgreSQL) — most services need DB access
3. **Core services** (n8n, NocoDB) — automation and data layer
4. **Product APIs** (Insights, Project, Conversations) — user-facing
5. **External APIs** (Brevo) — third-party integrations

## Examples

### Example: Morning Infrastructure Check

```bash
# 1. Quick overview
copilot health --json
# → Shows all 16 services status

# 2. System resources
copilot monitoring status --json
# → {"cpu_percent": 45, "memory_percent": 72, "disk_percent": 61}

# 3. No alerts
copilot monitoring alerts --json
# → {"alerts": []}

# 4. All Coolify apps running
copilot coolify app list --json
# → Lists all applications with status
```

### Example: Diagnosing an Outage

```bash
# 1. Master health shows Insights unhealthy
copilot health --json
# → {"service": "insights", "status": "unhealthy", "details": {"error": "ConnectionError"}}

# 2. Check if it's the service or infrastructure
copilot coolify server healthcheck --json
# → {"healthy": true} — server is fine

# 3. Check the specific app
copilot coolify app get --name "insights-api" --json
# → Shows app status, might be stopped

# 4. Check deployment logs
copilot coolify deploy list --json
# → Recent deploy failed

# 5. View deploy logs for error
copilot coolify deploy logs --deployment-id "<id>"
# → Shows the actual error

# 6. Restart if needed
copilot coolify app restart --uuid "<app-uuid>"

# 7. Verify recovery
copilot insights health --json
# → {"healthy": true}
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing or invalid configuration" | Check `.env` — service env vars not set |
| `AuthError` | 401/403 from any API | Regenerate API key for that service |
| `ConnectionError` | "Cannot reach service" | Check Docker (`copilot docker ps`), check Coolify app status |
| `TimeoutError` | Health check hangs | Service may be overloaded — check `copilot monitoring status` |

## Quality Tests

### Completeness Test
- All 16 configured services checked, not just the ones that were healthy last time
- **PASS:** `copilot health --json` output shows a status for every configured service
- **FAIL:** Any configured service is missing from the health report

### Dependency Triage Test
- Failures are ordered by infrastructure dependency, not alphabetically
- **PASS:** Infrastructure failures (Coolify, Docker) listed before service failures (Insights, Brevo)
- **FAIL:** A database failure is reported after an API failure that depends on that database

### Actionability Test
- Every unhealthy finding has a specific next command, not just "investigate"
- **PASS:** Each unhealthy service entry includes a drill-down command from Step 2
- **FAIL:** Report says "Service X is unhealthy" without a recovery command

### Resource Headroom Test
- System resources checked against defined thresholds, not just "looks okay"
- **PASS:** CPU, memory, and disk percentages compared against 80/85/90% thresholds
- **FAIL:** Resource check says "resources look fine" without specific numbers

## Guidelines

1. Always run `copilot health` first — it's the fastest way to find problems
2. Use `--json` for all diagnostic commands — parse don't read
3. Follow dependency order when triaging — fix infrastructure before services
4. Check Coolify deployment logs for recently broken services
5. Monitor resource thresholds: CPU > 80%, Memory > 85%, Disk > 90%

## References

- Related skills: `troubleshoot-service`, `deploy-product`
- Error hierarchy: `copilot_cli/shared/errors.py`
- Monitoring thresholds: `copilot_cli/config/settings.py` (cpu/memory/disk_alert_threshold)
