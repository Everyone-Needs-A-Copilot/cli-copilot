# CLI Copilot — SOUL

> **The decision instrument. When in doubt, consult this file.**
> This is not a vision statement or a mission poster. It is the tool you use to
> decide whether a proposed feature *belongs* in this product — by staying true
> to its purpose.
>
> **How to use it:** Run any feature, request, or "wouldn't it be cool if…"
> through **Section 5: Feature Filter**. Pass the gates in order. If a feature
> can't survive the filter in under a minute, the answer is **no**.
>
> **It is living.** It changes only when real evidence says the product changed —
> and every change is logged in **Section 10: Evolution**.

> **STATUS: RATIFIED v1.0 — 2026-06-28.** Owner-ratified at read-back: priority order confirmed, anti-pattern lines in the sand set, and Coolify confirmed as the single non-precedent config exception. Evidenced inferences confirmed.

---

## 1. The Job

**When** an agent or developer needs to act on the ecosystem's many external services — infra, databases, Discord, skills, USPTO, CRM — from inside any Copilot project,
**they want to** reach all of them through one consistent command instead of wiring up a bespoke client or MCP server per service per project,
**so they can** operate the whole ecosystem from a terminal, anywhere, without re-implementing integrations every time.

**The struggling moment:**
Before this binary, every project that needed Docker, a database, Notion, or a Discord handoff had to stand up its own integration — its own MCP server, its own client code, its own config. Twenty services meant twenty bespoke surfaces, each with a different shape, each to be maintained, each unable to be reused by the next project or scripted by an agent. The friction is *re-wiring the same plumbing over and over*, and the inconsistency that follows: no two services were invoked, configured, or failed the same way.

**Who this serves:**

| User | What they need |
|------|---------------|
| **The agent in a session** (primary) | One scriptable, machine-readable (`--json`) way to operate any service, plus the Discord handoff flow to hand work between sessions |
| **The developer at a terminal** | A single `copilot <service> <verb>` grammar that's learnable by analogy, with honest errors that say what to fix |
| **The next Copilot project** | To `pip install` the binary and point `COPILOT_ENV_FILE` at its own `.env` — and have every service work unchanged |

---

## 2. The Essence

**Soul statement:**
One binary that gives every Copilot project and agent a single, consistent, scriptable way to operate ~20 external services from the terminal — a uniform façade, never the services themselves.

**The deeper aim:**
Integration stops being per-project work. The ecosystem becomes operable from one place, by humans and agents alike, so attention goes to the work — not to re-plumbing the same connections.

**As a person, this product would be:**
A terse, reliable operations technician at a switchboard. Knows every line, speaks plainly, prefixes every result with its status, and when something fails hands you a hint about what to fix. Does exactly one thing per call and then stops. Never editorializes, never hypes, never keeps you waiting.

**Would NOT be:**
A chatty assistant, a long-running daemon that hovers in the background, or a platform that hosts and owns things. Not a server waiting for requests; a tool you pick up, use, and put down.

| It IS | It IS NOT |
|-------|-----------|
| A thin client that fronts external services from the terminal | The service itself — it does not host Docker, the DB, or Coolify; it *calls* them |
| A terminal CLI binary invoked per-command | An MCP server, HTTP API, webhook host, or background daemon |
| The skill **runtime** (discover / plan / run / verify / audit) | The skill **author** — skill content lives elsewhere (`.claude/skills`) |
| Portable via `.env` (`COPILOT_ENV_FILE` → walk-up → CWD) | A stateful store — it owns no database and remembers nothing between runs |
| A uniform façade: one command shape, one output format | A home for service-specific business logic or domain workflows (those live in the products it fronts) |
| Scriptable and machine-readable (`--json`) | A conversational or graphical interface |

**Key boundary — read this twice:**
The line is **client vs. owner**. CLI Copilot *fronts* services; it never *becomes* one. If a capability requires hosting state, owning data, running a server, or holding a workflow's business logic, it belongs in the service it calls — or in whatever agent-framework layer owns memory, agents, and MCP for your setup — not here. The moment the CLI starts persisting, serving, or deciding, it has crossed the line.

---

## 3. Design Principles

### Principle 1: One Binary, One Grammar
**Meaning:** Every service is `copilot <service> <verb>`. Every service exposes `health()`. Every output goes through `shared/output.py` and honors the global `--json` flag. If you know one service, you can use any other.
**Rejection:** We reject any service that invents its own output format, its own config mechanism, or skips `health()` — even when its upstream API is awkward. (Coolify's three-layer config is the single *documented, tolerated* exception, not a precedent.)
**Test:** "Does it look, configure, and fail like every other subcommand — same verb shape, same `--json`, same `health`?"

### Principle 2: Client, Never Server
**Meaning:** It runs for the duration of one command and then exits. It connects to things; it does not host, persist, daemonize, or listen.
**Rejection:** We reject exposing tools over MCP/HTTP, background daemons, `--serve` modes, webhook listeners, and warm connection pools held across calls.
**Test:** "Does this run only for the life of a single command, and store nothing of its own?"

### Principle 3: Portable by Configuration
**Meaning:** The binary is byte-for-byte identical in every project. Only the `.env` changes. Resolution is `COPILOT_ENV_FILE` → nearest `.env` walking up → `.env` in CWD.
**Rejection:** We reject hardcoded machine paths, project-specific behavior baked into the code, and per-project forks of the CLI.
**Test:** "Will this exact command work in every Copilot project given only a different `.env`?"

### Principle 4: Honest Failure
**Meaning:** Errors raise the `CopilotError` hierarchy carrying a `service` and an actionable `hint`. `--json` returns a structured error object. Failure tells you what broke and what to do next.
**Rejection:** We reject swallowed errors, fake success, and bare stack-trace dumps with no next step.
**Test:** "When this fails, does it name the service, the cause, and the fix?"

### Principle 5: Lazy & Mockable
**Meaning:** Clients instantiate lazily — importing a service connects to nothing. Every service has a test file that mocks all external calls; no test touches a real API or DB.
**Rejection:** We reject connecting at import time, and any feature that can't be tested without live credentials.
**Test:** "Can this be imported without connecting, and tested without a real call?"

### When Principles Conflict
*Settle the priority order in advance, so a live argument doesn't have to.*

Priority order: **Client, Never Server > Portable by Configuration > One Binary, One Grammar > Honest Failure > Lazy & Mockable.**

*Client, Never Server* sits on top because it is the identity line — cross it and this stops being a CLI and becomes a service. *One Binary, One Grammar* yields only to the one documented Coolify-style upstream exception.

---

## 4. Anti-Patterns


### The Daemon
**Drift:** "It'd be faster if it just stayed running / exposed its tools over MCP / had a `--serve` mode / kept the connections warm."
**Why it kills us:** It stops being a tool you pick up and becomes a service to maintain. Portability and statelessness — the whole point — are gone, and it now duplicates what the agent-framework layer already owns (MCP, agents).
**Early warning:** "let's expose this over MCP," "add a server mode," "keep a pool warm across calls," "have it listen for webhooks."
**Line in the sand:** No `--serve` mode, no MCP server, no daemon, no warm pools held across calls. It runs for one command and exits. Per the ecosystem rule, MCP belongs to applications serving external users — internal connection is CLI.

### The Smart Client
**Drift:** "Just put the whole workflow logic in the CLI — the CLI should decide X."
**Why it kills us:** Business and domain logic accretes in the façade instead of in the products it fronts. The CLI becomes the place where ecosystem logic rots, duplicating responsibilities that belong to the services it fronts.
**Early warning:** "the CLI should orchestrate this," "add the decision logic here," "let the command figure out the right thing to do."
**Line in the sand:** Workflow and domain logic live in the products the CLI fronts, never in the CLI. The façade routes and formats; it never decides the business outcome.

### The Snowflake Service
**Drift:** "This API is special — let it print its own way / use its own config / skip health."
**Why it kills us:** Erodes the one-grammar promise that makes the whole binary learnable by analogy. Coolify is already the tolerated exception; a second snowflake makes "exception" the rule.
**Early warning:** "just this once," "its output doesn't fit a table," "it doesn't need a health check."
**Line in the sand:** Every service uses the one grammar — `<service> <verb>`, `health()`, `--json`, `.env` config. Coolify is the single documented exception; there is never a second.

### The Stateful Store
**Drift:** "Cache results in a local DB / remember the last run / keep a little state between calls."
**Why it kills us:** It owns no data by design. Memory and persistence belong to the agent-framework layer, not the CLI. A local store makes the binary non-portable and turns a stateless tool into something with its own truth to keep consistent.
**Early warning:** "store it locally," "remember between runs," "add a cache/DB of our own."
**Line in the sand:** The binary owns no data and remembers nothing between runs, by default. Persistence and memory belong to the agent-framework layer. **Exception:** the opt-in usage ledger (`COPILOT_USAGE_LOG=1`, default off) is the second and only other documented exception, alongside Coolify's config persistence — command-path-only, privacy-scoped (no argument/option values, ever), engineered to never break or slow the command it observes, and required so the binary's own utilization is knowable. Not a precedent for further local state.

---

## 5. Feature Filter

Use these gates **in order**. A feature must pass **all** of them.

### Gate 1: Façade Test
> "Does this front an external service from the terminal — or is it trying to *be* the service?"

If it hosts state, owns data, runs a server, or holds a workflow's business logic → it belongs in the service or in the agent-framework layer. **Stop.**

### Gate 2: Uniform Test
> "Does it fit `copilot <service> <verb>`, expose `health()`, honor `--json`, and configure through `.env` — and will the exact command work in any project with only a different `.env`?"

If it needs a new config mechanism, its own output format, or project/machine-specific code → redesign it to fit the grammar, or it doesn't belong.

### Gate 3: Principle Test
> "Does it survive every principle in Section 3?"

One violation → redesign or reject.

### Gate 4: Anti-Pattern Test
> "Does building this drift toward The Daemon, The Smart Client, The Snowflake Service, or The Stateful Store?"

If yes → reject, or redesign until it doesn't.

### Case Law (In / Out)


| Feature | Verdict | Gate | Reasoning |
|---------|---------|------|-----------|
| Discord handoff (`handoff` / `notify` / `listen` / `wait`) | **IN** | Façade / Uniform | Fronts Discord as per-call terminal commands for inter-agent handoff; polling is per-invocation, no daemon. |
| Skill runtime (`run` / `verify` / `audit`) | **IN** | Façade | Runs skill workflows; it is a *runtime*, not an author — skill content lives in `.claude/skills`. |
| Global `--json` flag | **IN** | Uniform | Makes every service machine-readable for agents; directly serves the one-grammar promise. |
| USPTO Playwright session capture | **IN** *(borderline)* | Façade | Heavy dependency, but still client-only and per-invocation — fronts an external source, owns nothing. |
| Coolify three-layer config (CLI → env → TOML) | **IN** *(tolerated exception)* | Uniform | Breaks the `.env` grammar; admitted only because the upstream tool demands it, and documented as the *one* exception. |
| Opt-in usage ledger (`COPILOT_USAGE_LOG=1`, command path only) | **IN** *(tolerated exception)* | Façade | Breaks statelessness; admitted only because the CLI's own utilization is otherwise unknowable, and documented as the second and only other Stateful Store exception — off by default, no argument/option values ever recorded. |
| MCP server mode / expose tools over MCP | **OUT** | Façade / Anti-Pattern (The Daemon) | It is a client, not a server. MCP belongs to the agent-framework layer. |
| A local cache / DB to remember runs | **OUT** | Façade / Anti-Pattern (The Stateful Store) | Owns no data by design; persistence belongs to the agent-framework layer. |

---

## 6. Quality Bar

**The standard:**
A service is *done* — not merely working — when it behaves exactly like every other service: same command shape, a `health()`, clean `--json`, hint-bearing errors — and can be exercised end-to-end without touching anything real.

**Non-negotiables:**

- [ ] Service exposes `health()`; `copilot health` includes it
- [ ] All output flows through `shared/output.py`; `--json` yields clean machine-readable output with no Rich markup leakage
- [ ] Errors raise the `CopilotError` hierarchy with a `service` and an actionable `hint`
- [ ] Client instantiates lazily — importing the module connects to nothing
- [ ] A dedicated test file mocks every external call; no live API/DB in tests
- [ ] Config flows through Pydantic Settings / `.env`, documented in `.env.example` and `docs/services/`
- [ ] Works identically standalone and embedded via `COPILOT_ENV_FILE`

**Taste test:**
A new service should be learnable purely by analogy. If you know one service, you can use any other without reading its `--help` twice. If a service needs special explanation to operate, it broke the grammar.

**Quality failure modes:**

| Failure | Symptom |
|---------|---------|
| Snowflake output | `--json` returns Rich-styled text or an inconsistent shape across services |
| Mute failure | An error surfaces a stack trace with no `service` and no `hint` |
| Eager connection | `copilot --help` is slow or errors because a misconfigured service connected at import time |

---

## 7. Voice & Tone

**Character:**
A terse operations technician. States facts, prefixes status (`OK`, `Error:`, `Warning:`), always offers a `Hint:` on failure, never chats, never hypes. Lowercase service names, padded dotted health lines, uppercase `OK`. Speaks to be parsed by an agent as readily as read by a human.

**Language rules:**

| We Say | We Don't Say |
|--------|--------------|
| `Error: cannot reach nocodb` + `Hint: check NOCODB_BASE_URL` | "Oops! Something went wrong 😬" |
| `healthy` / `unhealthy` / `skipped` | "Everything looks great!" |
| `OK restarted my-container` | "Successfully completed your request!" |
| `No results.` | "We couldn't find anything for you right now." |
| `service........... healthy` | Decorative banners or ASCII art |

**Tone shifts:**

| Context | Tone |
|---------|------|
| Error | Name the service, name the cause, give a `Hint:` for the fix |
| Empty result | Flat `No results.` — no apology |
| Success | `OK <what happened>`, past tense, terse |
| `--json` mode | No prose at all — a structured object only |

---

## 8. Success Signals

**Positive signals (we're on track):**

- "I never think about *how* to call a service — it's just `copilot <it>`."
- "I dropped it into a new project, pointed `COPILOT_ENV_FILE` at the `.env`, and everything worked."
- "When it failed it told me exactly which env var to fix."
- "Our agents script against `--json` and nothing surprises them."

**Drift signals (we're losing the soul):**

| Signal | What it means |
|--------|---------------|
| "Wait, which config does *this* service use?" | The grammar is eroding — a Snowflake slipped in |
| "Let's just leave it running in the background" | Daemon drift |
| "Put the workflow logic in the CLI" | Smart Client drift |
| A service merged without a test file or without `health()` | The quality bar is slipping |

**Recovery questions:**

1. Is this command a *client* to something, or is it trying to *be* the thing?
2. Would this exact command work in another project with only a different `.env`?
3. Does it look, configure, and fail like every other service?

---

## 9. Founding Decisions

1. **Single package, not microservices.** One install, one command, zero coordination.
2. **Pydantic Settings + `.env` for config.** Type-safe, validates on startup, dual-mode (standalone or embedded).
3. **Lazy client instantiation.** Services connect only when invoked.
4. **Rich output everywhere + global `--json`.** Consistent tables, JSON, health panels.
5. **It is a client, not a server.** No MCP server, no HTTP API, no webhooks of its own. Per the ecosystem MCP/CLI rule, internal connection is always CLI; MCP is reserved for app-level servers serving external users.
6. **Coolify is the one tolerated, non-precedent config exception.** Settled — a second snowflake is never admitted.
7. **Priority order is settled:** Client, Never Server > Portable by Configuration > One Binary, One Grammar > Honest Failure > Lazy & Mockable.
8. **The anti-patterns are named and kept:** The Daemon, The Smart Client, The Snowflake Service, The Stateful Store — each with the line in the sand ratified in Section 4.

---

## 10. Evolution

This file changes only when:
- Real user outcomes shift what the product is for
- We learn something durable that contradicts a current principle or boundary
- The product's place in its ecosystem changes (another product takes over a job)

When updated, add the rationale to the changelog below.

### Changelog

| Date | Version | Change & rationale |
|------|---------|--------------------|
| 2026-06-28 | v1.0 | **Ratified** on Discord read-back. Confirmed the priority order (Client, Never Server on top as the identity line), set the four anti-pattern lines in the sand, and confirmed Coolify as the single non-precedent config exception. Reaffirmed against the ecosystem MCP/CLI rule. |
| 2026-06-28 | v0.1 | Drafted as a root-level decision instrument, retrofitted from the repo (README, CLAUDE.md, `pyproject.toml`, `main.py`, `shared/`, `docs/`) and the product dossier. Inferences marked `CONFIRM`; owner-only calls (anti-pattern lines in the sand, founding-decision rationale, priority order) flagged `TODO: owner`. Pending owner ratification. |
