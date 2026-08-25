# Annotated Example: What Makes a Skill Effective

This is a walkthrough of a well-crafted CLI orchestration skill, with annotations explaining why each part works.

---

## Frontmatter

```yaml
---
name: deploy-product                          # [1] Action-oriented, 2 words
description: >-
  End-to-end product deployment via copilot CLI — git, docker, coolify, monitoring.
  Use when shipping code to production or staging.  # [2] Mentions services + trigger
triggers:
  keywords: ["deploy", "ship", "release", "production", "staging", "rollback",
             "coolify", "docker"]              # [3] Domain terms + synonyms
allowed-tools: Read, Bash, Grep, Glob         # [4] Only tools actually needed
---
```

**Why this works:**
- [1] `name` carries 40% of evaluation weight — "deploy-product" is what agents search for
- [2] `description` names the 4 services involved so agents know scope at a glance
- [3] `keywords` include both technical ("coolify") and business ("ship", "release") terms
- [4] `allowed-tools` is minimal — this skill reads and executes, doesn't create files

---

## Good: Concrete Commands with Context

```markdown
### Step 2: Trigger Deployment

\`\`\`bash
copilot coolify deploy trigger --app-uuid "$APP_UUID" --json
\`\`\`

Monitor until complete:
\`\`\`bash
copilot coolify deploy list --app-uuid "$APP_UUID" --json | head -1
\`\`\`
```

**Why this works:**
- Uses actual `copilot` commands, not pseudocode
- Shows `--json` for machine-parseable output
- Explains what to do with the output (monitor)

---

## Bad: Vague Instructions

```markdown
### Step 2: Deploy

Deploy the application using the appropriate deployment method.
Check that it succeeded.
```

**Why this fails:**
- No specific commands — agent doesn't know which CLI to use
- "Appropriate method" is undefined — agent has to guess
- No output parsing guidance

---

## Good: Decision Table for Routing

```markdown
| Condition | Command | Rationale |
|-----------|---------|-----------|
| Coolify-managed app | `copilot coolify deploy trigger` | Uses Coolify's deploy pipeline |
| Docker Compose app | `copilot docker restart <name>` | Direct container restart |
| Static site | `copilot git push` then Coolify auto-deploys | Git-triggered deploy |
```

**Why this works:**
- Agent can match its situation to the right row
- Each path has a specific command
- Rationale explains WHY, not just WHAT

---

## Good: Error Handling Mapped to Error Hierarchy

```markdown
| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing COOLIFY_BASE_URL" | Add to `.env` |
| `AuthError` | 401 from Coolify API | Regenerate token: `copilot coolify key create` |
| `ConnectionError` | "Cannot reach service" | `copilot coolify server healthcheck` |
```

**Why this works:**
- Maps to the actual `CopilotError` hierarchy in `shared/errors.py`
- Each error has a specific recovery command, not "check configuration"
- Agent can automate recovery for known error types

---

## Good: Full Worked Example

```markdown
### Example: Deploy Insights Copilot to Production

\`\`\`bash
# 1. Verify services
copilot coolify server healthcheck --json
copilot insights health --json

# 2. Check current deployment
copilot coolify app get --uuid "insights-api-uuid" --json

# 3. Trigger deploy
copilot coolify deploy trigger --app-uuid "insights-api-uuid" --json
# → {"id": "deploy-123", "status": "queued"}

# 4. Monitor
copilot coolify deploy logs --deployment-id "deploy-123"

# 5. Verify
copilot insights health --json
# → {"healthy": true, "version": "2.1.0"}
\`\`\`
```

**Why this works:**
- Uses a real product name (Insights Copilot), not "my-app"
- Shows the full command chain from start to verification
- Includes expected output so agent knows what success looks like
- 5 steps spanning 2 services — shows orchestration

---

## Checklist for Reviewing Skills

Use this when reviewing a skill before committing:

- [ ] Every command shown actually exists (verify with `copilot <service> --help`)
- [ ] `--json` flag used where output feeds into subsequent steps
- [ ] Error handling references specific `CopilotError` subtypes
- [ ] Examples use real product/service names, not placeholders
- [ ] Prerequisites list specific env vars and health checks
- [ ] Keywords include both technical and business domain terms
- [ ] Cross-references to related skills use correct names
