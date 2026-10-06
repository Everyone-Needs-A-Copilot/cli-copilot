---
paths:
  - "copilot_cli/services/skill/**"
  - "tests/test_services/test_skill.py"
---

# Skill runtime (Model 2)

The `skill` service is a skill runtime engine. Skills are `.claude/skills/*/SKILL.md` files with YAML frontmatter that define executable workflows. The runtime provides:

- **Discovery:** finds skills in `.claude/skills/`, the `SKILL_PATHS` env var, and the `skill_paths` setting.
- **Execution:** runs multi-step workflows with parameter interpolation (`{{ params.x }}`).
- **Verification:** runs check commands with exit code and stdout expectations.
- **Auditing:** a quality audit against skill standards.

Skills with an `execution:` block in their frontmatter are executable via `copilot skill run`. Skills without it are documentation-only (still listable, showable, and auditable).

Key files:

- `copilot_cli/services/skill/models.py`: the Pydantic models (`SkillFrontmatter`, `ExecutionSpec`, and the rest).
- `copilot_cli/services/skill/client.py`: `SkillClient` with discovery, parsing, execution, verification, and audit.
- `copilot_cli/services/skill/commands.py`: the CLI commands (`list`, `show`, `plan`, `run`, `verify`, `audit`, `health`).
