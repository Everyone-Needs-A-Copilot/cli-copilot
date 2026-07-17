---
name: REPLACE-workflow-name
description: >-
  REPLACE: What business workflow this orchestrates. Mention copilot services used.
  Use when REPLACE: trigger condition.
triggers:
  keywords: ["REPLACE", "copilot", "service-names", "business-terms"]
allowed-tools: Read, Bash, Grep, Glob
---

# REPLACE: Workflow Name

## Overview

REPLACE: Business outcome this workflow produces. (2-3 sentences)

## Define Done

This workflow is complete when:

- [ ] REPLACE: Primary outcome achieved
- [ ] REPLACE: Verification check passes
- [ ] REPLACE: No errors in final health check

## Prerequisites

Run these checks before starting:

```bash
# Verify required services are healthy
copilot <service1> health
copilot <service2> health

# Verify required env vars are set (non-empty output = configured)
copilot health --json | grep '"<service>"'
```

Required environment variables:
| Variable | Service | Purpose |
|----------|---------|---------|
| `REPLACE_VAR` | service | What it's used for |

## Instructions

### Step 1: REPLACE — Gather Context (REQUIRED)

```bash
# Always use --json for parseable output when chaining commands
copilot <service> <command> --json
```

Parse the JSON output to extract values needed for subsequent steps.

### Step 2: REPLACE — Execute Core Action (REQUIRED)

```bash
copilot <service> <command> --json
```

**Decision routing:**

| Condition | Command | Rationale |
|-----------|---------|-----------|
| If condition A | `copilot <svc> <cmd>` | Why this path |
| If condition B | `copilot <svc> <cmd>` | Why this path |
| If neither | Load skill: `troubleshoot-service` | Escalation path |

### Step 3: REPLACE — Verify Result (REQUIRED)

```bash
# Confirm the action succeeded
copilot <service> <command> --json

# Cross-check in a related service
copilot <other-service> <command> --json
```

### Step 4: REPLACE — Enrich (OPTIONAL)

REPLACE: Additional enrichment steps that enhance but aren't required for success.

## Examples

### Example: REPLACE — Happy Path

```bash
# 1. Check preconditions
copilot <service> health --json
# → {"service": "<name>", "status": "healthy"}

# 2. Execute
copilot <service> <command> --json
# → {"status": "ok", "data": {...}}

# 3. Verify
copilot <service> <verify-command> --json
# → confirms success
```

### Example: REPLACE — Error Recovery

```bash
# 1. Command fails
copilot <service> <command> --json
# → {"status": "error", "message": "ConnectionError: ..."}

# 2. Diagnose
copilot <service> health --json
# → {"service": "<name>", "status": "unhealthy", "details": {...}}

# 3. Recover (based on error type)
# ConfigError → check .env
# AuthError → verify/regenerate credentials
# ConnectionError → check service is running
```

## Error Handling

Map failures to the CopilotError hierarchy:

| Error Type | Symptom | Recovery Command | Escalation |
|------------|---------|-----------------|------------|
| `ConfigError` | "Missing or invalid configuration" | Check `.env` for required vars | Load `troubleshoot-service` |
| `AuthError` | "Authentication failure" / 401/403 | Verify API key in `.env` | Regenerate key |
| `ConnectionError` | "Cannot reach service" | `copilot <svc> health` | Check Docker/Coolify |
| `NotFoundError` | "Resource does not exist" / 404 | Verify ID/name is correct | List resources first |
| `TimeoutError` | "Operation exceeded time limit" | Retry with smaller scope | Check service load |
| `RateLimitError` | "Rate limit exceeded" / 429 | Wait and retry | Reduce batch size |

## Quality Tests

### REPLACE Test Name
- REPLACE: What to verify and how
- **PASS:** REPLACE: Specific observable success
- **FAIL:** REPLACE: Specific observable failure

### REPLACE Test Name
- REPLACE: Second domain-specific test
- **PASS:** REPLACE
- **FAIL:** REPLACE

## Guidelines

1. REPLACE: Always/never constraints specific to this workflow
2. Always use `--json` flag when output feeds into next command
3. Run health checks before multi-step workflows to fail fast
4. Log progress for long-running workflows (e.g., `copilot project tasks log`)

## References

- Related skills: `cli-router`, `troubleshoot-service`
- Error hierarchy: `copilot_cli/shared/errors.py`
- Output modes: `copilot_cli/shared/output.py`

## Scripts

If this skill has frequently-run workflows, see `scripts/` for executable bash wrappers:
- `scripts/REPLACE.sh` — REPLACE: what it does
