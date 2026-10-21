# Agent Instructions

## Project Overview

- Project: `CLI Copilot`
- Description: The public, credential-free foundation of the `copilot` command: a standalone Python CLI that manages infrastructure, APIs, databases, monitoring, and skill execution from any terminal, with only generic, broadly reusable service adapters.
- Stack: Python 3.11+; Typer, Pydantic Settings, httpx, Rich; pytest and ruff

## Project-Specific Rules

- This repo is the public foundation tier. Keep it credential-free and generic: nothing specific to one company or product. Org-specific vendor adapters (`crm`/NocoDB, `brevo`, `n8n`, `coolify`, `discord`) live in the org-specific `-internal` tier. `uspto` and `infisical` stay here as the two worked-example reference adapters (see README's "Reference adapters" note).
- `SOUL.md` is the ratified decision instrument: run any proposed feature through its Section 5 Feature Filter before building it.
- Layout: `copilot_cli/main.py` is the Typer app and top-level `health`; `config/settings.py` loads `.env` via Pydantic Settings; `shared/` holds `errors.py`, `http_client.py`, and `output.py`; each service lives in `copilot_cli/services/<service>/` as `client.py` (business logic, API calls) plus `commands.py` (Typer commands).
- Service registration is manifest-driven: `resolve_cli_services()` in `copilot_cli/services/_loader.py` is the single source of truth, and `_BASE_SERVICES` there is the fast-path contract (same set, order, and help text) asserted by `tests/test_tier_inheritance_parity.py`. Tier overlays adopt, provide, or override services through `copilot.layers.yml`; the frozen contract is `docs/03-tier-inheritance.md`.
- Conventions: every service supports a `health()` command; all output goes through `shared/output.py` helpers (Rich tables, JSON, panels); all errors use the `shared/errors.py` hierarchy (`CopilotError`, `ConfigError`, `ConnectionError`, `AuthError`, `NotFoundError`, `ValidationError`, `TimeoutError`, `RateLimitError`); HTTP services use the `shared/http_client.py` wrapper; configuration comes from Pydantic Settings via `.env`.
- Service patterns: class-based clients (git, docker, postgresql, skill, infisical, uspto) are instantiated through a lazy `_client()` factory; module-level clients (shell, filesystem, system_services, document, bi, monitoring) are plain functions using `get_settings()`.
- Adding a service follows `.claude/rules/adding-a-service.md`. The skill runtime (`copilot skill`) is described in `.claude/rules/skill-runtime.md`.
- Commands: `make install` (`pip install -e ".[dev]"`), `make test` (`pytest -q`), `make lint` (`ruff check .`), `make format`, `make check` (lint, format check, tests), `copilot --help`, `copilot health`. Live connectivity checks are opt-in: `make e2e-health-pytest` (sets `COPILOT_E2E_LIVE=1`).
- Testing: every service has a dedicated test file in `tests/test_services/`. All external dependencies are mocked via the autouse `mock_settings` fixture in `tests/conftest.py`; no test makes real API calls or database connections.
- Keep shared project requirements consistent between CLAUDE.md and AGENTS.md; preserve their scope and keep tool-specific instructions in the appropriate entrypoint.

- Before work in a domain named above, read its referenced `.claude/rules/` document. Where it declares `paths:`, apply it only to those paths; where it names a workflow, apply it only during that workflow. Those conditions require explicit reading in Codex, not Claude-style automatic loading.

## Project Commands

- From the repository root with Python 3.11+, `make install`, `make test`, `make lint`, and `make check` are defined in `Makefile`; dependencies and focused-test configuration are in `pyproject.toml`. See `README.md`, `Development`, for opt-in live checks. `copilot health` can contact configured services.

## Instruction Scope

- Check applicable nested `AGENTS.md` / `AGENTS.override.md` before working in a subtree. Preserve scoped rules; references and Claude `paths:` frontmatter are not automatic Codex imports.
- Keep shared project requirements consistent with `CLAUDE.md` when present; preserve scope and keep tool-specific routing separate. Do not import either whole entrypoint into the other.

## Codex Copilot

- Use relevant skills exposed in this session. `$protocol` and specialist names are shorthand, not shell commands or requests to spawn agents. Read only task-relevant skills/references.
- Start with `$protocol` unless the specialist is obvious; use `$launcher` when routing is unclear. Apply playbooks locally; use the globally installed `codex-copilot` skills and their supplied source paths. This repository does not provide the base plugin files locally; report missing capabilities rather than inventing local paths.

## Output Contract

- Lead with the answer, decision, result, or blocker. Default to 6 sentences or 5 bullets; expand when completeness requires it. Preserve findings, uncertainty, citations, QA evidence, safety warnings, Task/WP identifiers, and blockers.
- For real decisions, give 2–3 concrete outcome options and a short question. Do not manufacture decisions or ask again for authorized work.
- Keep progress brief and material. Report outcome, changed scope, verification, and limitations at completion; store detail in `tc` work products.

## `cc` CLI

- Use `cc` for memory, skills, Live Docs, and configuration; `tc` for tasks/work products. The retired Copilot MCP servers and their `initiative_*`, `memory_*`, and `skill_*` tools do not exist.
- Prefer `$HOME/.local/bin/cc`; verify bare `cc` is not the C compiler. Source: Claude Copilot `tools/cc/`. Config: `.claude/cc/config.json`; memory: `.claude/memory/entries/`.
- When configuration is needed, run `eval "$($HOME/.local/bin/cc env)"`; use returned values instead of machine-specific paths.

## Live Docs

- Before planning or implementing against an installed third-party package API, run `$HOME/.local/bin/cc docs get <package> --topic <area> --json`.
- If `cc docs` is unavailable, state the limitation and verify against local package files or official documentation before coding.

## Knowledge and Optional Context

- For brand, voice, product, or methodology knowledge, hydrate `cc env`; follow project consumption-contract pointers through comma-separated `CC_KNOWLEDGE_REPOS`, nearest tier first, reading the first matching sub-path. Never use singular `CC_KNOWLEDGE_REPO` for sub-path lookup. Report missing sources; never invent company facts.
- Before `cc skill select`, read the globally installed specialist-agents skill’s `references/shared-behaviors.md`, section `Optional Context`. Follow its load-once, receipt, and fallback rules; mandatory instructions are never relevance-filtered.

## Task Management

- Track substantial work in `tc` PRDs/tasks and store detailed work products there; create missing records. Use `cc memory` for durable decisions and lessons.
- Prefer `tc`, then `./.venv-tc/bin/tc`; use `--json` where supported. Read the globally installed `codex-copilot:task-copilot` skill when managing tasks.
- Batch three or more related operations using `tc.api`, or separately `cc.api`, with a verified interpreter. Never mix these APIs in one process.
- Formal initiatives belong in `docs/40-initiatives/NN-slug/`, indexed in `docs/40-initiatives/README.md` (create the index when the first initiative needs it), with `README.md`, `phases/`, `decisions/`, and `retrospectives/`. Markdown holds durable rationale/evidence; `tc` owns live state. Never create `docs/initiatives/`.

### QA Gate Convention

- For verification-required implementation, set `metadata.requiresQa=true` and register observable criteria and source scope with `tc task contract <id> --file <path>` (`schemaVersion: 2`) before implementing.
- `$me` stores implementation evidence; `$qa` verifies it. Read their installed evidence contracts for those tasks.
- Capture `tc task evidence-identity <id>` before and after checks, preserve the exact `IDENTITY:` line, and rerun affected checks if the tested content changes.
- Store a task-bound `test` work product with matching `CRITERION:` / `EXPECTED:`, actual observations, inspectable `ARTIFACT:` evidence, untested scope, and one `VERDICT:`. Missing required behavior, bare markers, or stale evidence cannot support approval.
- Before completion, run `tc task check-qa <id> --json` ; this repository has no local `copilot-gate.sh`, so use the authoritative tc gate. Never remove `requiresQa` to bypass QA; installed hooks alone prove neither enforcement nor approval.

## Framework Rules

- Experience work starts with `$sd` / `$uxd`; visual direction uses `$uids` before `$uid`. Architecture and non-trivial technical work use `$ta`; `$me` implements and `$qa` verifies.
- Bugs follow `$qa -> $me -> $qa`; security-sensitive work includes `$sec`; infrastructure changes needing implementation follow `$do -> $me -> $qa`.
- Keep changes focused, preserve user work, omit time estimates, and respect the user's authorization and review boundaries.
- Use `spawn_agent` only when the user explicitly requests delegation, subagents, or parallel agent work.

### Delegating to Subagents

- Do not end a subagent prompt with an enumerated reporting checklist.
- The standing return contract is at most three sentences: outcome, root cause if known, and anything anomalous or requiring a decision. Put full evidence in a file and return its path.
- Surface every safety-relevant anomaly in those three sentences; never bury it only in the evidence file.
- Request more depth only when the decision genuinely depends on it.

## Debugging Discipline

When an explanation conflicts with a measurement, follow the measurement and narrow the investigation.

1. Confirm a mechanism exists in the relevant environment, plan, or account before naming it as the cause.
2. State what every diagnostic exercised, including the selected key, config, binary, branch, interpreter, and working directory when relevant.
3. Count failures through one shared dependency as one observation unless that dependency is varied.
4. After two hypotheses are falsified, stop hypothesizing. Read the code that enforces the behavior and cite `file:line`.

## Decision Instruments

- Read `SOUL.md` before substantial product-facing work to decide whether the direction belongs here; report missing or unfilled purpose rather than inventing it.
- Read `docs/01-architecture/12-architecture-guiding-principles.md` for durable architecture, migration, data, security, performance, or AI pipeline decisions. Report a missing reference and use verified project authority.
- When either instrument changes the route, state that before continuing.
