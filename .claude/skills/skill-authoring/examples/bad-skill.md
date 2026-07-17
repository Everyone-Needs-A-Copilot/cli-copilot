# Annotated Example: Common Skill Mistakes

This walkthrough shows what NOT to do when writing skills, with explanations of why each pattern fails.

---

## Mistake 1: Vague Frontmatter

```yaml
---
name: helper
description: >-
  Helps with various tasks.
triggers:
  keywords: ["help", "do", "run", "manage"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---
```

**Problems:**
- `name` is generic — "helper" matches nothing specific (40% of eval weight wasted)
- `description` says nothing about WHAT it helps with or WHICH services
- `keywords` are too broad — "help", "do", "run" match everything and nothing
- `allowed-tools` grants all tools when the skill only needs Read and Bash

**Fix:** Name it after the business workflow: `deploy-product`, `database-operations`, etc.

---

## Mistake 2: No Define Done Section

```markdown
## Instructions

### Step 1: Check things
Run some health checks to make sure everything is working.

### Step 2: Do the thing
Deploy the application using the appropriate method.

### Step 3: Verify
Make sure it worked.
```

**Problems:**
- No success criteria defined — how does the agent know when it's done?
- "Check things" is not actionable — which things? Which commands?
- "Appropriate method" is undefined — agent has to guess
- "Make sure it worked" — how? What does success look like?

**Fix:** Add `## Define Done` with specific, checkable criteria before writing any instructions.

---

## Mistake 3: Generic Commands Instead of Specific Ones

```markdown
### Step 2: Deploy

Deploy the application:
```
deploy <app>
```

Check the status:
```
status <app>
```
```

**Problems:**
- `deploy` and `status` aren't real commands — agent will fail
- No `--json` flag for machine-parseable output
- No error handling for when deploy fails
- Missing the actual CLI tool name (`copilot`)

**Fix:** Use exact, verified commands:
```bash
copilot coolify deploy trigger --app-uuid "$APP_UUID" --json
copilot coolify app get --uuid "$APP_UUID" --json
```

---

## Mistake 4: No Error Handling

```markdown
## Error Handling

If something goes wrong, check the logs and try again.
```

**Problems:**
- "Something goes wrong" doesn't map to any specific error type
- "Check the logs" — which logs? Where?
- "Try again" — the same failing command? That won't fix the root cause
- Doesn't use the CopilotError hierarchy

**Fix:** Map each error type to a specific recovery:

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing COOLIFY_BASE_URL" | Add to `.env` |
| `AuthError` | 401 from Coolify API | `copilot coolify key create --json` |
| `ConnectionError` | Can't reach server | `copilot coolify server healthcheck --json` |

---

## Mistake 5: No Quality Tests

```markdown
## Guidelines

- Make sure everything works
- Follow best practices
- Be careful with production
```

**Problems:**
- "Make sure everything works" is not falsifiable — how do you check?
- "Follow best practices" — which ones? For what?
- "Be careful with production" — what specific safeguards?
- No domain-specific tests an agent can actually run

**Fix:** Add falsifiable quality tests:

### Rollback Readiness Test
- Before deploying, verify rollback command is available: `copilot coolify deploy rollback --app-uuid "$APP_UUID" --json`
- **PASS:** Command returns previous deployment ID
- **FAIL:** No previous deployment exists (first deploy has no rollback)

---

## Mistake 6: Missing Required/Optional Distinction

```markdown
### Step 1: Pre-checks
### Step 2: Deploy
### Step 3: Monitor logs
### Step 4: Run full regression tests
### Step 5: Update documentation
### Step 6: Notify stakeholders
### Step 7: Archive old version
```

**Problems:**
- Agent doesn't know which steps are critical vs nice-to-have
- Steps 4-7 are probably optional but treated the same as Steps 1-2
- Agent might skip essential steps or waste time on optional ones

**Fix:** Mark clearly:
- `### Step 1: Pre-checks (REQUIRED)`
- `### Step 2: Deploy (REQUIRED)`
- `### Step 3: Monitor logs (REQUIRED)`
- `### Step 4: Run regression tests (OPTIONAL)`
- `### Step 5: Update documentation (OPTIONAL)`

---

## Mistake 7: Duplicating Instead of Cross-Referencing

```markdown
## How to Check Infrastructure
(copies 50 lines from infrastructure-health skill)

## How to Troubleshoot
(copies 40 lines from troubleshoot-service skill)
```

**Problems:**
- Duplicated content goes stale when the source skill is updated
- Makes this skill unnecessarily long
- Agent loads duplicate instructions, wasting context

**Fix:** Cross-reference instead:
```markdown
If infrastructure check fails, load skill: `infrastructure-health`
If troubleshooting is needed, load skill: `troubleshoot-service`
```

---

## Quick Checklist: Spot a Bad Skill

- [ ] Name is generic ("helper", "utils", "manager")
- [ ] Description doesn't mention specific services or tools
- [ ] Keywords are vague ("manage", "handle", "process")
- [ ] No `## Define Done` section
- [ ] No `## Quality Tests` section
- [ ] Instructions use pseudocode instead of real commands
- [ ] Error handling says "check the logs" without specifics
- [ ] Steps aren't marked required vs optional
- [ ] Content is duplicated from other skills instead of cross-referenced
