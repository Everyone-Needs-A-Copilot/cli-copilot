# 19 — Skill Runtime

CLI interface for the **Skill Runtime** — discovers, plans, executes, verifies, and audits skills defined as `.claude/skills/*/SKILL.md` files with YAML frontmatter.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SKILL_PATHS` (env) | *(empty)* | Colon-separated additional skill search directories |
| `skill_paths` (settings) | *(empty)* | Comma-separated additional skill search directories |

The runtime always searches `.claude/skills/` relative to the project root (found by walking up from CWD to the nearest `.git`, `pyproject.toml`, `.mcp.json`, or `package.json`).

## Commands

```
copilot skill
├── list [--source local|shared] [--executable]    # List all discovered skills
├── show <name>                                     # Detailed skill info (params, steps, verify)
├── plan <name> [--param KEY=VALUE]...              # Dry run — show execution plan
├── run <name> [--param KEY=VALUE]... [--timeout]   # Execute skill steps
├── verify <name> [--param KEY=VALUE]... [--timeout] # Run verification checks
├── audit [--path <dir>]                            # Quality audit skill(s)
└── health                                          # Service health check
```

## Skill File Format

Skills are directories containing a `SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-name
description: What this skill does
triggers:
  keywords: ["keyword1", "keyword2"]
allowed-tools: Read, Write, Edit, Bash
execution:                          # Optional — makes skill executable
  params:
    - name: target
      type: string                  # string | int | float | bool | path
      required: true
      default: null
      description: "Parameter description"
  steps:
    - name: step-name
      script: scripts/do-thing.sh   # Script-first (runs via bash)
      command: "echo hello"          # Or inline command (runs via shell)
      args: ["{{ params.target }}"]  # Arguments for scripts
      skip_if: "not params.verbose"  # Condition to skip
  verify:
    - name: check-name
      command: "copilot health --json"
      expect: "exit_code == 0"       # exit_code == N | exit_code != N | stdout contains "text"
---
```

### Skill Directory Structure

```
skill-name/
├── SKILL.md           # Required — frontmatter + instructions
├── scripts/           # Optional — executable scripts (.sh, .py)
│   └── do-thing.sh
└── reference/         # Optional — reference materials (.md)
    └── patterns.md
```

## Discovery

Skills are discovered from multiple sources with local taking priority:

1. **Local:** `.claude/skills/` relative to project root (source: `local`)
2. **Environment:** `SKILL_PATHS` env var, colon-separated (source: `shared`)
3. **Settings:** `skill_paths` in Pydantic Settings, comma-separated (source: `shared`)

When the same skill name exists in both local and shared, local wins.

## Execution Engine

### Parameter Interpolation

Templates use `{{ params.name }}` syntax:
```yaml
command: "copilot db vacuum --database {{ params.database }}"
args: ["{{ params.name }}", "{{ params.email }}"]
```

### Skip Conditions

Steps can be conditionally skipped:
```yaml
skip_if: "params.verbose"         # Skip if verbose is truthy
skip_if: "not params.verbose"     # Skip if verbose is falsy
```

### Expect Expressions

Verification checks support:
- `exit_code == 0` — command exited successfully
- `exit_code != 0` — command exited with error
- `stdout contains "text"` — stdout contains the given string

## Audit Engine

The `copilot skill audit` command runs a 15-check quality audit:

| # | Check | Level |
|---|-------|-------|
| 1 | SKILL.md exists and non-empty | MISSING |
| 2 | Frontmatter block present | MISSING |
| 3 | `name:` field | MISSING |
| 4 | `description:` field | MISSING |
| 5 | `keywords:` in triggers | WARN |
| 6 | `allowed-tools:` field | WARN |
| 7 | Instructions/Framework section (or 2+ domain H2s) | MISSING |
| 8 | Examples section | WARN |
| 9 | Guidelines section | WARN |
| 10 | Error Handling section | WARN |
| 11 | Define Done section | MISSING |
| 12 | Quality Tests section | MISSING |
| 13 | `scripts/` directory | WARN |
| 14 | `reference/` directory | WARN |
| 15 | REQUIRED/OPTIONAL step marking | WARN |

MISSING = fails audit. WARN = recommendation.

## Examples

```bash
# List all skills
copilot skill list
# → 12 skills: 6 executable, 6 documentation-only

# List only executable skills
copilot skill list --executable

# Show skill details including params and steps
copilot skill show deploy-product

# Dry run a deployment
copilot skill plan deploy-product --param app-uuid=abc-123

# Execute a deployment
copilot skill run deploy-product --param app-uuid=abc-123

# Run database maintenance on all databases
copilot skill run database-operations

# Run on a specific database
copilot skill run database-operations --param database=nocodb

# Run a workflow-automation skill with parameters
copilot skill run workflow-automation \
  --param workflow-id="abc-123" \
  --param action="activate"

# Verify deployment health
copilot skill verify deploy-product --param app-uuid=abc-123

# Audit all discovered skills
copilot skill audit

# Audit a specific directory
copilot skill audit --path .claude/skills/deploy-product
```

## Client Pattern

Class-based client (`SkillClient`) with lazy `_client()` factory, following the same pattern as the other class-based services (e.g. `nocodb`, `brevo`, `uspto`).

## Models

| Model | Purpose |
|-------|---------|
| `SkillFrontmatter` | Parsed YAML frontmatter from SKILL.md |
| `ExecutionSpec` | The `execution:` block (params, steps, verify) |
| `SkillParam` | A declared parameter with name, type, required, default |
| `ExecutionStep` | A single step (script or command) |
| `VerifyCheck` | A verification check with command and expectation |
| `SkillInfo` | Full skill metadata including filesystem context |
| `StepResult` | Result of executing a single step |
| `SkillRunResult` | Result of a complete skill execution |
| `VerifyResult` | Result of a verification check |
| `AuditCheck` | A single audit check result |
| `AuditResult` | Result of auditing a single skill |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| `NotFoundError` | Skill name not in discovery cache | Check `copilot skill list` for available names |
| `CopilotError` | Skill has no `execution:` block | Add `execution:` to frontmatter (see format above) |
| `ValidationError` | Required parameter not provided | Use `--param name=value` for each required param |
| `TimeoutError` | Step exceeded timeout | Increase with `--timeout` flag |
