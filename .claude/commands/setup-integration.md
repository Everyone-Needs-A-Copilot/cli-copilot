---
name: setup-integration
description: Guided wizard to add a new service integration to the copilot CLI — has the "right conversation", lets you choose Python or Go, teaches the key-storage model, then scaffolds it.
---

# /setup-integration — add an integration

You are guiding an adopter to add their **own** service integration to the `copilot` CLI.
Run the conversation, let them choose the language, teach the key-storage model, then scaffold.
You never hardcode a secret and you never push either language on them.

## 1. The right conversation (elicit everything, one question group at a time)

1. **Service name & purpose** — short `kebab-case` id + one line on what it does.
2. **Auth type** — `api_key` / `oauth2` / `basic` / `mtls` / `none`.
3. **Base URL / endpoints** — the root URL + the specific paths it will call.
4. **Operations to expose** — the verbs/subcommands (e.g. `list`, `create`, `sync`).
5. **Rate limits** — expected req/s + burst, so the scaffold sets sane retry/backoff.
6. **Secret name(s)** — canonical `SERVICENAME_PURPOSE` (e.g. `EXAMPLESERVICE_API_KEY`).
7. **Secret scope, per secret** — **personal** (this user's own key) or **shared** (team/org)?
   This decides *where it's stored*, not the wizard's behavior (see §3).
8. **Output/format defaults** — `json` (machine), `table` (human), or both.
9. **Error handling** — retry count, timeout, fatal vs soft-fail.
10. **Confirm** — echo the full spec back; require an explicit "yes" before generating files.

## 2. Language — Python or Go (present both; recommend neither)

> "**Python** plugs straight into the adapter architecture and reuses the shared HTTP/retry/
> config helpers — the fastest path, and how the 17 built-in adapters work. **Go** is
> supported if you want a standalone, dependency-free binary or raw performance — you'll
> follow the subprocess contract (stdin/stdout JSON, exit codes) instead of the plugin API.
> Which do you want?"

| | **Python** (first-class) | **Go** (documented alternative) |
|---|---|---|
| Path | `new-service-scaffold` → `copilot_cli/services/<name>/` | standalone binary invoked via subprocess |
| Config/secrets | inherits the CLI's settings + secret resolution | reads resolved refs passed in at invocation |
| Today | fully templated | supported pattern + documented contract |

## 3. Key storage — teach this before scaffolding (never weaken it)

- **Personal secrets** → local `.env` (gitignored) and/or the OS keychain. Never shared, never committed.
- **Shared / tier secrets** → a managed secret store; its **endpoint** comes from inherited config
  (the endpoint is not itself a secret), access gated by your own team membership.
- **Resolution:** shared config carries only `requires_secret: <NAME>` — **never a value**. At
  startup `<NAME>` resolves in order: local `.env`/keychain → managed store. Neither → **fail
  closed** with `missing secret <NAME>`, never a silent default.
- **`.env.example` pattern** (committed; values never real):

  ```
  # Personal — get your own key from the service dashboard
  EXAMPLESERVICE_API_KEY=

  # Shared — resolved via the managed store; do not set locally unless overriding
  # requires_secret: EXAMPLESERVICE_SHARED_TOKEN
  ```

- **Never in git, ever:** raw secret values, real `.env`, OAuth/refresh tokens, private keys/certs.

## 4. Scaffold

- **Python:** invoke the `new-service-scaffold` skill with the collected spec — it generates the
  service dir, client, commands, config fields, tests, docs, and registers it in `main.py`.
- **Go:** generate the subprocess-contract stub + a `docs/services/<name>.md` describing the
  stdin/stdout JSON contract; do not register it as a Python plugin.
- Either way: generate a `.env.example` block using the `requires_secret: <NAME>` pattern above —
  **no generated file ever contains a literal secret.** Then tell them how to run it and verify.
