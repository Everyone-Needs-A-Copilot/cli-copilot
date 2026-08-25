---
name: deploy-product
description: >-
  End-to-end product deployment via copilot CLI — git, docker, coolify, monitoring.
  Use when shipping code to production or staging, triggering deployments, or rolling back.
triggers:
  keywords: ["deploy", "ship", "release", "production", "staging", "rollback",
             "coolify", "docker", "deployment", "live", "push", "insights", "restart"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  params:
    - name: app-uuid
      type: string
      required: true
      description: Coolify application UUID to deploy
  steps:
    - name: deploy
      script: scripts/deploy.sh
      args:
        - "{{ params.app-uuid }}"
      description: Pre-check, trigger deploy, monitor, health verify, auto-rollback on failure
  verify:
    - name: server-healthy
      command: copilot coolify server healthcheck --json
      expect: 'exit_code == 0'
    - name: monitoring-ok
      command: copilot monitoring status --json
      expect: 'exit_code == 0'
---

# Deploy Product

## Overview

Orchestrate a full deployment from code commit through infrastructure deploy to post-deploy verification. Covers Coolify-managed applications (primary) and Docker Compose stacks, spanning git, coolify, docker, and monitoring services.

## Define Done

A deployment is complete when:

- [ ] Pre-deploy checks pass (server healthy, resources have headroom, code committed)
- [ ] Deployment triggered and completed without build errors
- [ ] Post-deploy health check passes for the deployed application
- [ ] No new alerts triggered in monitoring
- [ ] Rollback path verified (previous deployment ID known)

## Prerequisites

- Git changes committed and pushed to the deployment branch
- Coolify configured: `COOLIFY_BASE_URL`, `COOLIFY_ACCESS_TOKEN` in `.env`
- Run pre-deploy health check: `copilot coolify server healthcheck --json`

Required environment variables:
| Variable | Service | Purpose |
|----------|---------|---------|
| `COOLIFY_BASE_URL` | coolify | Coolify API endpoint |
| `COOLIFY_ACCESS_TOKEN` | coolify | Coolify API authentication |

## Instructions

### Step 1: Pre-Deploy Checks (REQUIRED)

```bash
# Verify infrastructure is healthy
copilot coolify server healthcheck --json

# Check system resources (ensure headroom for deployment)
copilot monitoring status --json
# → Verify CPU < 80%, Memory < 85%, Disk < 90%

# Check current app status
copilot coolify app get --uuid "$APP_UUID" --json
```

### Step 2: Verify Code is Ready (REQUIRED)

```bash
# Check git status — ensure clean working tree
copilot git status --json

# Verify on correct branch
copilot git status --json
```

If changes need committing:
```bash
copilot git add --path "."
copilot git commit --message "feat: description of changes"
```

### Step 3: Set Environment Variables (OPTIONAL)

```bash
# List current env vars
copilot coolify envvar list --resource-uuid "$APP_UUID" --json

# Set new env var
copilot coolify envvar set --resource-uuid "$APP_UUID" --key "NEW_VAR" --value "value"
```

### Step 4: Trigger Deployment (REQUIRED)

**Decision routing:**

| Deployment Type | Command | When |
|----------------|---------|------|
| Coolify app (git-triggered) | `copilot coolify deploy trigger --app-uuid "$APP_UUID" --json` | Standard deploy |
| Coolify rollback | `copilot coolify deploy rollback --app-uuid "$APP_UUID" --json` | Reverting a bad deploy |
| Docker container restart | `copilot docker restart --name "$CONTAINER" --json` | Local/compose stacks |
| Coolify service restart | `copilot coolify svc restart --uuid "$SVC_UUID" --json` | Dependent services |

Standard Coolify deployment:
```bash
copilot coolify deploy trigger --app-uuid "$APP_UUID" --json
# → Returns deployment ID
```

### Step 5: Monitor Deployment (REQUIRED)

```bash
# Watch deployment logs
copilot coolify deploy logs --deployment-id "$DEPLOY_ID"

# Check deployment status
copilot coolify deploy get --deployment-id "$DEPLOY_ID" --json
```

### Step 6: Post-Deploy Verification (REQUIRED)

```bash
# Check app is running
copilot coolify app get --uuid "$APP_UUID" --json

# Run product-specific health check
copilot insights health --json     # for Insights Copilot
copilot project health --json      # for Project Copilot
copilot conv auth me --json        # for Conversations Copilot

# Check system resources post-deploy
copilot monitoring status --json

# Check for new alerts
copilot monitoring alerts --json
```

### Step 7: Rollback (OPTIONAL)

If post-deploy checks fail:

```bash
# Rollback to previous deployment
copilot coolify deploy rollback --app-uuid "$APP_UUID" --json

# Verify rollback succeeded
copilot coolify app get --uuid "$APP_UUID" --json

# Re-run health check
copilot health --json
```

## Examples

### Example: Deploy Insights Copilot to Production

```bash
# 1. Pre-deploy
copilot coolify server healthcheck --json
# → {"healthy": true, "version": "4.x"}

copilot monitoring status --json
# → {"cpu_percent": 35, "memory_percent": 62, "disk_percent": 55}

# 2. Trigger deploy
copilot coolify deploy trigger --app-uuid "insights-api-uuid" --json
# → {"id": "deploy-abc123", "status": "queued"}

# 3. Monitor
copilot coolify deploy logs --deployment-id "deploy-abc123"
# → Streaming logs...

# 4. Verify
copilot insights health --json
# → {"healthy": true}

copilot insights version --json
# → {"version": "2.1.0"}
```

### Example: Emergency Rollback

```bash
# Deploy broke something
copilot insights health --json
# → {"healthy": false, "error": "Internal Server Error"}

# Rollback immediately
copilot coolify deploy rollback --app-uuid "insights-api-uuid" --json

# Verify recovery
copilot insights health --json
# → {"healthy": true}
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing COOLIFY_BASE_URL" | Add Coolify credentials to `.env` |
| `AuthError` | 401 from Coolify API | Regenerate: `copilot coolify key create --json` |
| `ConnectionError` | Can't reach Coolify server | Check server: `copilot coolify server healthcheck` |
| `TimeoutError` | Deploy hangs | Check logs: `copilot coolify deploy logs --deployment-id <id>` |
| Deploy fails | Build error in logs | Fix code, push, re-trigger |
| App unhealthy post-deploy | Health check fails | Rollback: `copilot coolify deploy rollback` |

## Quality Tests

### Rollback Readiness Test
- Before deploying, verify a rollback target exists
- **PASS:** `copilot coolify deploy list --app-uuid "$APP_UUID" --json` returns at least one previous deployment
- **FAIL:** First-ever deployment with no rollback available (proceed with extra caution)

### Smoke Test
- After deployment, the application responds to its primary health endpoint
- **PASS:** `copilot <product> health --json` returns `{"healthy": true}` within 60 seconds
- **FAIL:** Health check fails or times out after deployment

### Resource Headroom Test
- System has sufficient resources before deploying
- **PASS:** `copilot monitoring status --json` shows CPU < 80%, Memory < 85%, Disk < 90%
- **FAIL:** Any resource above threshold — deploy risks causing an outage

### Zero-Alert Test
- No new monitoring alerts appear within 5 minutes of deployment
- **PASS:** `copilot monitoring alerts --json` shows no new alerts post-deploy
- **FAIL:** New alerts triggered after deployment — investigate or rollback

## Guidelines

1. Always run pre-deploy health checks — deploy into a healthy system
2. Always run post-deploy verification — don't assume success
3. Use `--json` for all commands when scripting deployments
4. Keep rollback as the first response to a failed deploy — debug after rolling back
5. Check monitoring alerts after deploy — resource spikes indicate problems

## References

- Related skills: `infrastructure-health`, `troubleshoot-service`
- Coolify service docs: `docs/services/15-coolify.md`
- Deployment config: `.Codex/memory/coolify-deployments.md`
