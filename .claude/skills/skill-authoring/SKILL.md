---
name: skill-authoring
description: >-
  Create new skills that teach agents how to orchestrate CLI commands for business workflows.
  Use when building skills for copilot CLI, other CLI tools, or any repeatable agent workflow.
triggers:
  files: ["**/.claude/skills/**", "**/SKILL.md"]
  keywords: ["create skill", "new skill", "skill template", "skill authoring", "teach agent"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Skill Authoring

## Overview

A repeatable framework for creating skills that teach agents how to orchestrate CLI commands for real business workflows. Skills are the intelligence layer that tells agents WHERE to find capabilities and HOW to chain them across services.

## Define Done

A skill is complete when:

- [ ] Discoverable: `skill_evaluate` matches the skill for its intended queries
- [ ] Actionable: every instruction contains specific commands, not vague advice
- [ ] Tested: quality tests defined and passing
- [ ] Error-aware: failure modes mapped to recovery actions
- [ ] Cross-referenced: related skills linked, not duplicated

## Two Skill Archetypes

| Aspect | CLI Orchestration | Knowledge/Methodology |
|--------|------------------|----------------------|
| Purpose | Chain CLI commands into multi-step workflows | Teach frameworks, patterns, or decision criteria |
| Has `scripts/` | Yes — executable bash scripts for common workflows | Rarely |
| Has `reference/` | Sometimes — catalogs, inventories | Often — templates, checklists, catalogs |
| Body sections | Prerequisites → Instructions → Examples → Error Handling | Prerequisites → Framework → Instructions → Examples |
| Template | `templates/CLI-WORKFLOW-TEMPLATE.md` | `templates/KNOWLEDGE-SKILL-TEMPLATE.md` |
| Examples | `infrastructure-health`, `deploy-product` | Forces analysis, design patterns |

Choose the archetype before writing. Most copilot CLI skills are CLI Orchestration. Most knowledge-copilot skills are Knowledge/Methodology.

## Prerequisites

- Access to the target CLI's command tree (run `<cli> --help` and `<cli> <service> --help`)
- Understanding of the business workflow the skill will encode
- The skills-copilot MCP server configured with `LOCAL_SKILLS_PATH`

## Instructions

### Step 0: Define Done (REQUIRED)

Before writing anything, define what success looks like:

1. **Success criteria** — what must be true when the skill's workflow completes?
2. **Quality tests** — domain-specific, falsifiable tests (see Quality Tests section below)
3. **Edge cases** — what could go wrong? How should the skill handle it?

Write these as a `## Define Done` checklist and `## Quality Tests` section in the skill BEFORE writing instructions. This prevents scope creep and ensures every instruction exists for a reason.

### Step 1: Define the Skill Boundary (REQUIRED)

Answer these questions before writing anything:

| Question | Why It Matters |
|----------|---------------|
| What business outcome does this skill produce? | Skills encode workflows, not features |
| Which CLI services does it span? | Determines command coverage needed |
| When should an agent load this skill? | Drives frontmatter keywords and triggers |
| What must be true before it can run? | Prerequisites section |
| What errors are likely and how to recover? | Error handling section |

**Naming rule:** Use the business workflow name, not the service name.
- Good: `deploy-product`, `database-operations`, `workflow-automation`
- Bad: `coolify-commands`, `nocodb-helpers`, `brevo-utils`

### Step 2: Write the Frontmatter (REQUIRED)

The skills-copilot evaluation engine weights frontmatter fields:

| Field | Weight | Guidance |
|-------|--------|----------|
| `name` | 0.40 | kebab-case, action-oriented, 2-3 words |
| `triggers.keywords` | 0.35 | Domain terms an agent would use when searching |
| `triggers.files` | 0.25 | File patterns that indicate this skill is relevant |
| `description` | 0.15 | 1-2 sentences: what it does + when to use it |

```yaml
---
name: my-skill-name
description: >-
  Action-oriented description. Mention the CLI services used.
  State when to use this skill. (category)
triggers:
  files: ["relevant/file/patterns/**"]
  keywords: ["domain", "specific", "terms", "agents", "would", "search"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---
```

**Keyword optimization:**
- Include the CLI tool name (e.g., "copilot")
- Include service names the skill uses (e.g., "coolify", "docker", "crm")
- Include business domain terms (e.g., "deploy", "onboard", "lead")
- Include synonyms agents might use (e.g., "ship" for deploy, "prospect" for lead)

### Step 3: Write the Body (REQUIRED)

Follow this section order:

1. **Overview** (2-3 sentences) — What problem, when to use
2. **Define Done** — Success criteria checklist
3. **Prerequisites** — Config, env vars, health checks required
4. **Instructions** — Numbered steps with decision tables and actual CLI commands
5. **Examples** — Full worked scenarios with real commands
6. **Error Handling** — Map failures to recovery actions
7. **Quality Tests** — Domain-specific, falsifiable tests
8. **Guidelines** — Always/never constraints
9. **References** — Related skills and docs

**Mark steps as required or optional:**
- Number required steps: `### Step 1: Do This (REQUIRED)`
- Suffix optional steps: `### Step 6: Enrich Data (OPTIONAL)`

**For CLI orchestration skills, use the CLI Workflow Template:**
`templates/CLI-WORKFLOW-TEMPLATE.md`

**For knowledge/methodology skills, use the Knowledge Skill Template:**
`templates/KNOWLEDGE-SKILL-TEMPLATE.md`

### Step 4: Add Scripts (OPTIONAL — CLI Orchestration skills)

When a skill has a multi-step workflow that users run frequently, add executable scripts in `scripts/`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Load environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../.env"; set +a
fi

# Required arguments
NAME="${1:?Usage: $0 <name>}"

# Stderr for progress logs, stdout for results
echo "Starting workflow for ${NAME}..." >&2

# ... workflow commands ...

echo '{"status": "ok", "name": "'"${NAME}"'"}'
```

**Bash conventions (from reference skills):**
- Shebang: `#!/usr/bin/env bash`
- Safety: `set -euo pipefail`
- Load .env: `set -a; source .env; set +a`
- Required args: `${1:?Usage: $0 <arg>}`
- Logs to stderr: `echo "msg" >&2`
- Results to stdout (JSON when possible)
- In `knowledge-copilot/`: use `.sh.md` extension (Obsidian compatibility)
- In `cli-copilot/.claude/skills/`: use plain `.sh` (executable)

### Step 5: Add Reference Materials (OPTIONAL — complex skills)

When a skill references large catalogs, templates, or decision criteria, extract them to `reference/`:

| Goes in `reference/` | Stays in `SKILL.md` |
|----------------------|---------------------|
| Full command inventories | Summary routing tables |
| Error catalogs with all variants | Top 5 most common errors |
| Code templates and patterns | When to use each pattern |
| Decision criteria checklists | High-level decision flowchart |

Reference files are loaded by the agent when needed, keeping SKILL.md scannable.

### Step 6: Register and Verify (REQUIRED)

```bash
# Clear cache so new skills are discoverable
# skill_discover({ clearCache: true })

# Verify skill loads
# skill_get({ name: "my-skill-name" })

# Test evaluation engine matches for expected queries
# skill_evaluate({ text: "description of when skill should activate" })
```

### Step 7: Iterate — The Fix Loop (REQUIRED)

Building a great skill is iterative, not one-shot:

```
1. DEFINE DONE    → Success criteria + quality tests
2. BUILD          → Scaffold from template
3. FIRST TEST     → Run with a real agent workflow
4. FIX LOOP       → Read error → Fix SKILL.md → Retest
5. EDGE CASES     → Stress-test unusual inputs, missing config
6. SHIP           → Verify discovery, cross-references, clean up
```

After initial creation:
1. Test with real agent workflows — does the skill produce the right command sequences?
2. Check for missing error paths — what happens when a command fails mid-workflow?
3. Verify cross-references — do `Related skills` links resolve?
4. Optimize keywords — run `skill_evaluate` with various phrasings to ensure discovery
5. Add scripts for workflows you run more than twice

## Quality Tests

Domain-specific, falsifiable tests for authored skills. Each test has a clear PASS/FAIL criteria:

### Discoverability Test
- Run `skill_evaluate({ text: "<3 different phrasings>" })` — skill appears in top 3 results for each
- **FAIL:** Skill not found for its primary use case phrasing

### Command Accuracy Test
- Every CLI command in the skill exists: `copilot <service> --help` confirms it
- **FAIL:** A command shown in the skill returns "No such command"

### Completeness Test
- Every step has: (a) a specific command, (b) expected output format, (c) what to do next
- **FAIL:** A step says "check the results" without specifying what to look for

### Error Recovery Test
- Every error in the Error Handling table has a recovery command that actually resolves it
- **FAIL:** Recovery says "check configuration" without naming the specific env var

### Frontmatter Optimization Test
- `name` is 2-3 words, action-oriented, kebab-case
- `description` mentions specific services
- `keywords` include both technical terms and business synonyms
- **FAIL:** Keywords are generic ("manage", "handle") instead of domain-specific

## Cross-CLI Portability

Skills can work across multiple CLI tools when they:
1. Reference commands by their business intent, not just syntax
2. Include a "CLI Commands" table mapping intent → command for each CLI tool
3. Use `--json` output mode for parseable results
4. Are symlinked across CLI tool `.claude/skills/` directories via `scripts/sync-skills.sh`

## References

- Skill template: `templates/SKILL-TEMPLATE.md`
- CLI workflow template: `templates/CLI-WORKFLOW-TEMPLATE.md`
- Knowledge skill template: `templates/KNOWLEDGE-SKILL-TEMPLATE.md`
- Annotated good example: `examples/good-skill.md`
- Annotated bad example: `examples/bad-skill.md`
- Sync script: `scripts/sync-skills.sh`
- Audit script: `scripts/audit-skill.sh`
- Batch audit: `scripts/audit-all-skills.sh`
- Skills-copilot MCP: configured via `.mcp.json` → `LOCAL_SKILLS_PATH`
