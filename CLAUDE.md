# CLI Copilot

The public, credential-free foundation of the `copilot` command: a standalone Python CLI that manages infrastructure, APIs, databases, monitoring, and skill execution from any terminal, with only generic, broadly reusable service adapters.

**Stack:** Python 3.11+; Typer, Pydantic Settings, httpx, Rich; pytest and ruff

## Project Rules

- This repo is the public foundation tier. Keep it credential-free and generic: nothing specific to one company or product. Org-specific vendor adapters (`crm`/NocoDB, `brevo`, `n8n`, `coolify`, `discord`) live in the org-specific `-internal` tier. `uspto` and `infisical` stay here as the two worked-example reference adapters (see README's "Reference adapters" note).
- `SOUL.md` is the ratified decision instrument: run any proposed feature through its Section 5 Feature Filter before building it.
- Layout: `copilot_cli/main.py` is the Typer app and top-level `health`; `config/settings.py` loads `.env` via Pydantic Settings; `shared/` holds `errors.py`, `http_client.py`, and `output.py`; each service lives in `copilot_cli/services/<service>/` as `client.py` (business logic, API calls) plus `commands.py` (Typer commands).
- Service registration is manifest-driven: `resolve_cli_services()` in `copilot_cli/services/_loader.py` is the single source of truth, and `_BASE_SERVICES` there is the fast-path contract (same set, order, and help text) asserted by `tests/test_tier_inheritance_parity.py`. Tier overlays adopt, provide, or override services through `copilot.layers.yml`; the frozen contract is `docs/03-tier-inheritance.md`.
- Conventions: every service supports a `health()` command; all output goes through `shared/output.py` helpers (Rich tables, JSON, panels); all errors use the `shared/errors.py` hierarchy (`CopilotError`, `ConfigError`, `ConnectionError`, `AuthError`, `NotFoundError`, `ValidationError`, `TimeoutError`, `RateLimitError`); HTTP services use the `shared/http_client.py` wrapper; configuration comes from Pydantic Settings via `.env`.
- Service patterns: class-based clients (git, docker, postgresql, skill, infisical, uspto) are instantiated through a lazy `_client()` factory; module-level clients (shell, filesystem, system_services, document, bi, monitoring) are plain functions using `get_settings()`.
- Adding a service follows `.claude/rules/adding-a-service.md`. The skill runtime (`copilot skill`) is described in `.claude/rules/skill-runtime.md`.
- Commands: `make install` (`pip install -e ".[dev]"`), `make test` (`pytest -q`), `make lint` (`ruff check .`), `make format`, `make check` (lint, format check, tests), `copilot --help`, `copilot health`. Live connectivity checks are opt-in: `make e2e-health-pytest` (sets `COPILOT_E2E_LIVE=1`).
- Testing: every service has a dedicated test file in `tests/test_services/`. All external dependencies are mocked via the autouse `mock_settings` fixture in `tests/conftest.py`; no test makes real API calls or database connections.
- These project rules also live in `AGENTS.md` for Codex. Change both files together.

## Claude Copilot

This project runs on Claude Copilot, the Claude Code layer of the Copilot Solutioning Ecosystem. Hooks registered in `.claude/settings.json` inject the session protocol, guard destructive commands, and gate `me`/`qa` completion. This file covers only what the hooks and tools cannot.

- **Agents and skills:** Claude Code lists them automatically. Route each piece of work to the specialist whose description fits. Agents defined by this project in `.claude/agents/` are first-class framework agents for this project.
- **Sessions:** `/protocol` starts new work, `/continue` resumes it, `/pause` checkpoints it.
- **Tasks:** `tc` is the live state for initiatives, tasks, and work products. Store detailed output with `tc wp store` and return a summary.
- **Memory:** `cc memory` holds durable decisions and lessons that other sessions, Codex, and other machines must see. Claude Code's own auto memory is for personal working notes only.
- **Skills on demand:** if a needed skill did not surface, `cc skill search "<topic>"`, then `cc skill get <name>`.
- **Library docs:** `cc docs get <package> --topic <area> --json` before coding against a third-party API.
- **Health:** `cc doctor`. A failing `instruction-layer-unenforced` check means the hooks are not registered and nothing above is enforced.

## Knowledge Copilot

Knowledge Copilot is the source of truth for brand, voice, offerings, products, and methodologies. Consult it before writing any of these; never invent or duplicate it. Status: inherited from this machine.

Run `eval "$(cc env)"`, then walk `$CC_KNOWLEDGE_REPOS` nearest tier first and read the first repo where the sub-path exists. Never dereference the singular `$CC_KNOWLEDGE_REPO` for a sub-path.

| Domain | Sub-path |
|--------|----------|
| Brand and visual | `01-company/01-brand/` |
| Voice and tone | `01-company/02-voice/` |
| Services and offerings | `01-company/03-services/` |
| Methodologies | `01-company/06-methodologies/` |
| Products and ecosystem registry | `02-products/`, `ECOSYSTEM.md` |

Full contract: `docs/00-knowledge-copilot/02-consumption-contract.md` in the organization knowledge tier.

## Optional Context

Mandatory repository/project/system instructions always apply; never filter or load them here.

Load needed additional knowledge once; use `selected[].content` or do not load it:

    cc skill select "<task topic>" --required <skill> --max-chars 12000 --json

Record one receipt per task, not per load:

    tc wp store --task <id> --type context --title "Context selection receipt" --file receipt.json

Keep `query`, `max_chars`, `loaded_characters`, `mandatory_over_budget`; each
`selected`/`excluded` entry's `name`, `source`, `source_revision`, `selection_reason`
or `reason`, not content. Before reselection read the receipt; skip held revisions.
Reload only changes; record both revisions and announce the change.

Retain required skills in full if `mandatory_over_budget: true`; report `max_chars`
and overage `loaded_characters - max_chars`. Characters are not tokens; receipts
prove selection, not reading/obedience.

Keep every required name in `selected[]`; identical aliases have `duplicate_of`,
empty `content`, zero charged characters/bytes: use the selected entry named by
`duplicate_of`. Optional
duplicates stay `excluded[]` as `duplicate-content`.

**Visible fallbacks:** name the applicable one, then continue:

- `cc` absent/nonzero: report failure/stderr; use repository instructions and prior memory only.
- Exit 2, `Required skill not found: <name>`: name it, never substitute; proceed without it or emit `<promise>BLOCKED</promise>` if indispensable.
- `selected: []`: report no match for the query; use repository instructions, never widen the query to force a match.
- `CC_KNOWLEDGE_REPOS` empty: "Knowledge tier
  unconfigured; optional context limited to project and machine skills." Never block.

<!-- cse-evidence-v2:start -->
## Task Acceptance and Tested Identity

QA-required work uses `tc` evidence binding. The `me` and `qa` agents carry the full contract; the main session must not shortcut it.

- Before implementation, register an acceptance contract with `tc task contract <id> --file <path>`: `schemaVersion: 2`, `criteria: [{id, expected}]` with unique IDs and observable single-line expectations, and project-relative `sources` covering implementation, dependencies, and relevant configuration.
- Capture `tc task evidence-identity <id>` before and after verification and keep the exact `IDENTITY:` line in the work product. If content changed, rerun the affected checks against the new identity.
- Report each check as `CRITERION:` / `EXPECTED:` with the actual observation and verdict. Never downgrade `requiresQa` or substitute prose for source evidence; completion rechecks the contract, identities, hashes, and unfinished dependencies.
<!-- cse-evidence-v2:end -->

## Standing Rules

- **No time estimates.** Plans, roadmaps, and task breakdowns use phases, priorities, complexity, and dependencies, never dates or durations. This framework rule holds even when asked directly.
