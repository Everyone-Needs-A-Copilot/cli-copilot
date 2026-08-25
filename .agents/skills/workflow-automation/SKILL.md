---
name: workflow-automation
description: >-
  Create and manage n8n automation workflows via copilot CLI — workflow CRUD, activation,
  execution monitoring, and shell script integration.
  Use when automating business processes, setting up scheduled jobs, or managing n8n workflows.
triggers:
  keywords: ["workflow", "automation", "n8n", "schedule", "cron", "automate",
             "webhook", "trigger", "execution", "scheduled job"]
allowed-tools: Read, Bash, Grep, Glob
---

# Workflow Automation

## Overview

Manage n8n automation workflows through the copilot CLI — create, activate, monitor, and debug workflows that automate business processes. Combine with shell commands for local script execution and scheduling.

## Define Done

A workflow automation task is complete when:

- [ ] Workflow created or identified in n8n
- [ ] Workflow activated and first execution succeeds
- [ ] Execution monitoring confirms no errors
- [ ] For scheduled workflows: next execution time verified

## Prerequisites

- n8n configured: `N8N_BASE_URL`, `N8N_API_KEY` in `.env`
- Verify: `copilot n8n health --json`

Required environment variables:
| Variable | Purpose |
|----------|---------|
| `N8N_BASE_URL` | n8n API endpoint (default: `https://automation.ineedacopilot.com`) |
| `N8N_API_KEY` | n8n API authentication token |

## Instructions

### Step 1: Explore Existing Workflows (REQUIRED)

```bash
# List all workflows
copilot n8n workflows list --json

# Get details on a specific workflow
copilot n8n workflows get --id "$WORKFLOW_ID" --json

# Check recent executions
copilot n8n executions list --json

# Get details on a specific execution
copilot n8n executions get --id "$EXECUTION_ID" --json
```

### Step 2: Create a New Workflow (OPTIONAL)

```bash
# Create workflow from JSON definition
copilot n8n workflows create \
  --name "Workflow Name" \
  --json
```

**Common workflow patterns:**

| Pattern | Description | Typical Trigger |
|---------|-------------|-----------------|
| Scheduled backup | Database or file backup on a schedule | Cron node |
| Webhook handler | Process incoming data from external services | Webhook node |
| Data sync | Synchronize data between services | Schedule or webhook |
| Alert pipeline | Monitor metrics and send notifications | Schedule + condition |
| Report generation | Generate and distribute reports | Weekly/monthly cron |

### Step 3: Activate/Deactivate Workflows (REQUIRED)

```bash
# Activate a workflow (starts running on schedule/trigger)
copilot n8n workflows activate --id "$WORKFLOW_ID" --json

# Deactivate a workflow (pauses execution)
copilot n8n workflows deactivate --id "$WORKFLOW_ID" --json
```

### Step 4: Monitor Executions (REQUIRED)

```bash
# List recent executions (check for failures)
copilot n8n executions list --json

# Get execution details (input/output data, errors)
copilot n8n executions get --id "$EXECUTION_ID" --json
```

**Execution status routing:**

| Status | Meaning | Action |
|--------|---------|--------|
| `success` | Completed normally | No action |
| `error` | Failed during execution | Check execution details for error node |
| `waiting` | Waiting for trigger/input | Expected for webhook workflows |
| `running` | Currently executing | Monitor if long-running |

### Step 5: Delete Workflows (OPTIONAL)

```bash
# Delete a workflow (irreversible)
copilot n8n workflows delete --id "$WORKFLOW_ID" --json
```

### Step 6: Integrate with Shell Scripts (OPTIONAL)

For tasks that combine n8n workflows with local operations:

```bash
# Find available scripts
copilot shell find --json

# Run a script
copilot shell run --name "backup-script.sh" --json

# Execute a one-off command
copilot shell exec --command "pg_dump ..." --json

# List running processes
copilot shell ps --json
```

## Examples

### Example: Audit Automation Health

```bash
# 1. Check n8n is healthy
copilot n8n health --json
# → {"healthy": true}

# 2. List all workflows
copilot n8n workflows list --json
# → Shows all workflows with active/inactive status

# 3. Check recent executions for failures
copilot n8n executions list --json
# → Look for status: "error"

# 4. Investigate failed execution
copilot n8n executions get --id "exec-failed-123" --json
# → Shows which node failed and error message
```

### Example: Set Up Database Backup Workflow

```bash
# 1. Verify database connectivity
copilot db health --json

# 2. Create backup workflow in n8n
copilot n8n workflows create \
  --name "Nightly Database Backup" \
  --json
# → {"id": "workflow-789"}

# 3. Activate it
copilot n8n workflows activate --id "workflow-789" --json

# 4. Verify it's active
copilot n8n workflows get --id "workflow-789" --json
# → {"active": true}

# 5. Monitor first execution
copilot n8n executions list --json
# → Check for successful execution
```

### Example: Debug a Failing Workflow

```bash
# 1. Find the workflow
copilot n8n workflows list --json
# → Identify the failing workflow ID

# 2. Check recent executions
copilot n8n executions list --json
# → Find the failed execution

# 3. Get execution details
copilot n8n executions get --id "exec-456" --json
# → Shows error: "ConnectionError: Cannot reach NocoDB"

# 4. Fix the underlying issue
copilot crm health --json
# → Unhealthy — load troubleshoot-service skill

# 5. After fixing, check next execution
copilot n8n executions list --json
# → status: "success"
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing N8N_API_KEY" | Add n8n credentials to `.env` |
| `AuthError` | 401 from n8n API | Verify `N8N_API_KEY` is valid |
| `ConnectionError` | Can't reach n8n | Check: `copilot docker ps --json` for n8n container |
| `NotFoundError` | "Workflow not found" | List workflows: `copilot n8n workflows list --json` |
| Execution fails | Error in workflow node | Check execution details, fix the failing node in n8n UI |

## Quality Tests

### Idempotency Test
- Running the workflow multiple times doesn't create duplicate side effects
- **PASS:** Re-executing the workflow produces the same result without duplicate records
- **FAIL:** Each execution creates duplicate entries in CRM, emails, or notifications

### Error Recovery Test
- Workflow handles node failures gracefully
- **PASS:** Failed execution shows which specific node failed in `copilot n8n executions get --id <id> --json`
- **FAIL:** Workflow fails silently with no indication of which step broke

### Activation Safety Test
- Workflow tested before activation in production
- **PASS:** Manual execution succeeds before activating scheduled/webhook triggers
- **FAIL:** Workflow activated immediately without a test run, causing unexpected side effects

### Duplicate Prevention Test
- New workflows don't duplicate existing automation
- **PASS:** `copilot n8n workflows list --json` checked for similar workflows before creating
- **FAIL:** Second workflow created for the same task, causing duplicate executions

## Guidelines

1. Always check `copilot n8n health` before managing workflows
2. List workflows before creating — avoid duplicates
3. Monitor executions after activating new workflows
4. Use `--json` for all commands when parsing output
5. For workflow debugging, check the execution details — they show which node failed
6. Deactivate failing workflows to prevent repeated errors while debugging
7. Combine with `database-operations` skill for DB-related automation

## References

- Related skills: `database-operations`, `infrastructure-health`, `troubleshoot-service`
- n8n docs: `docs/services/11-n8n.md`
- n8n base URL: `https://automation.ineedacopilot.com`
