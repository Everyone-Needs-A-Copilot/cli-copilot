---
name: REPLACE-skill-name
description: >-
  REPLACE: Action-oriented description. Mention the CLI services used.
  State when to use this skill.
triggers:
  files: ["REPLACE/**"]
  keywords: ["REPLACE", "with", "domain", "terms"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# REPLACE: Skill Name

## Overview

REPLACE: What problem this solves and when an agent should use it. (2-3 sentences)

## Define Done

A successful run of this skill produces:

- [ ] REPLACE: First success criterion — what must be true when done
- [ ] REPLACE: Second success criterion
- [ ] REPLACE: Verification step passes

## Prerequisites

- REPLACE: What must be configured before running
- Environment variables: `REQUIRED_VAR` in `.env`
- Health check: `copilot <service> health`

## Instructions

### Step 1: REPLACE with action verb (REQUIRED)

REPLACE: Specific commands to run. Use decision tables for routing.

```bash
copilot <service> <command> --json
```

### Step 2: REPLACE with next action (REQUIRED)

REPLACE: Continue the workflow sequence.

| Condition | Action |
|-----------|--------|
| If X | Run `copilot ...` |
| If Y | Run `copilot ...` |

### Step 3: REPLACE with optional enrichment (OPTIONAL)

REPLACE: Additional steps that enhance but aren't required.

## Examples

### Example: REPLACE with realistic scenario

```bash
# Step 1: Describe what this does
copilot <service> <command> --json

# Step 2: Continue
copilot <service> <command> --json
```

**Expected output:**
```json
{"status": "ok", "message": "..."}
```

## Error Handling

| Error Type | Cause | Recovery |
|------------|-------|----------|
| ConfigError | Missing env var | Check `.env` for `REQUIRED_VAR` |
| AuthError | Bad credentials | Verify API key, re-generate if expired |
| ConnectionError | Service unreachable | Run `copilot <service> health`, check network |

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

1. REPLACE: Always/never constraints
2. REPLACE: When to escalate or use a different skill

## References

- Related skills: `skill-name`
- CLI docs: `docs/services/XX-service.md`
