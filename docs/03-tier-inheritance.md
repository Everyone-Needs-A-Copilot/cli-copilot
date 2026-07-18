---
title: CLI Tier Inheritance (Phase 1)
category: architecture
last-updated: 2026-07-18
---

# CLI Tier Inheritance — Phase 1

Status: **Phase 1 shipped, inert.** With no `copilot.layers.yml` present
anywhere the CLI looks, `copilot` behaves byte-for-byte as it did before
this change (v1.4.5): the same 12 services, in the same order, with the
same help text, and `Settings` resolves through the exact same source
tuple as before (`_find_env_file()` untouched, `COPILOT_ENV_FILE` honored).
See the Phase-1 parity fitness test:
`tests/test_tier_inheritance_parity.py`.

This is the foundation-repo half of the ratified CLI tier-inheritance
model. It extends the same `copilot.layers.yml` manifest + nearest-wins
precedence resolver the content components (claude/knowledge/codex)
already use to the CLI (a code component), without ever forking the base
package. Full design rationale lives in the tier-inheritance design doc
(owner-ratified D1–D6); this file documents the frozen, implemented
contract.

## The two manifests

### `copilot.layers.yml` — the tier chain

One manifest, shared across all four CSE components, filtered here to
`component: cli` entries. See `copilot_cli/config/layers.py`'s module
docstring for the full annotated example. Precedence is nearest-wins:
**PERSONAL > DEPARTMENT > ORG > FOUNDATION**, expressed as ascending
`rank` (lower rank = higher precedence). A duplicate rank among `cli`
entries is a hard error at resolution time (`LayersManifestError`), never
silently resolved by list order.

Resolution (`resolve_cli_layer_chain()` in `config/layers.py`):

1. Find the manifest: `COPILOT_LAYERS_FILE` override → walk up from CWD to
   the first project-root marker → standard `$HOME`-relative locations.
2. Filter to `component: cli`. Parse each entry's `id`, `role`, `rank`,
   `source.repo`, `source.ref`, `auth`, optional `unit`/`activation`.
3. Sort ascending by `rank`; hard-error on a duplicate.
4. Return `None` if no manifest resolves, or the manifest has zero `cli`
   entries — this `None` is the fast-path trigger consumed by both
   `config/settings.py` and `services/_loader.py`.

Each resolved layer's local mirror root is
`~/.copilot/mirrors/cli/<id>` by convention (namespaced by component so a
`cli` layer id can never collide with another component's layer sharing
the same id). Materializing that mirror (`copilot update`'s pull-only
sync) is **out of Phase-1 scope** — Phase 1 ships the loader and layered
config inert, not the sync path.

### `cli.overlay.yml` — one tier's service declarations

Lives at a tier's mirror root. Declares three, and only three, operations
(`copilot_cli/config/layers.py`'s `TierOverlay`/`OverlayAdopt`/
`OverlayProvide`/`OverlayOverride`):

| Key | Effect | Code required |
|---|---|---|
| `adopt` | Turn ON a **base** service with this tier's config/secrets only | None — the base module runs unchanged |
| `provides` | ADD a **new** service this tier's own package implements | Yes — a module in the tier's own top-level namespace |
| `override` | REPLACE a base service's command with this tier's own implementation | Yes — same command name, different code |

An **undeclared** shadowing module is refused: `provides` hard-errors if
the service name collides with an existing one that isn't also declared
under `override` in the same file. This is what makes drift structurally
impossible for adopted (config-only) connectors — see the design's §6.4
red-team finding.

```yaml
# cli.overlay.yml
version: 1

adopt:
  - service: uspto
    config:
      uspto_cli_base_url: https://internal-uspto-proxy.acme.example
    requires_secret:
      - USPTO_CLI_API_KEY

provides:
  - service: coolify
    module: copilot_overlay_internal.services.coolify.commands
    help: "Coolify infrastructure operations"
    requires_secret:
      - COOLIFY_API_TOKEN

override:
  - service: db
    module: copilot_overlay_internal.services.db_coolify.commands
```

## Config + secret resolution (`config/settings.py`)

`Settings.settings_customise_sources()` is gated entirely behind
`resolve_cli_layer_chain()`:

- **No manifest resolves** (Phase 1's only reachable state today): returns
  the identical `(init_settings, env_settings, dotenv_settings,
  file_secret_settings)` tuple as before. `_find_env_file()` — baked into
  `model_config.env_file` at class-body eval time — is reached completely
  unchanged; `COPILOT_ENV_FILE` keeps working exactly as it always has.
- **A manifest resolves**: builds `(init_settings, env_settings,
  <DotEnvSettingsSource per tier, personal→…→foundation>,
  SecretRefSource)`. Each tier's `DotEnvSettingsSource` carries **non-secret
  config only**. `SecretRefSource` (in the same file) is the single place a
  `requires_secret` name resolves to a real value, via the credential
  ladder (`config/secrets_ladder.py`) — fail-closed: a declared secret that
  misses every ladder rung raises `SecretResolutionError`, never silently
  leaves the field at its `""` default.

The credential ladder (`credentials-and-boundary.md` §1.6.3), in order:
managed shared secret store → OS keychain → interactive device-code flow →
one-time secure paste. Rungs 1 and 3 are stubbed cleanly in this
foundation (no store client, no device-flow auth exist yet) — they fall
through rather than pretending to succeed. Rung 2 (macOS keychain) is
implemented for real.

## Service discovery (`services/_loader.py`)

`resolve_cli_services()` is the single source of truth for what `copilot`
registers:

- **No manifest resolves**: returns exactly the base 12 `ServiceEntry`
  tuples — same names, same order, same help text `main.py` used to
  hardcode.
- **A manifest resolves**: folds `chain` (foundation → … → personal) onto
  the base 12; each tier's `adopt`/`provides`/`override` applies in
  ascending-precedence order so a later, higher-precedence tier naturally
  wins.

`main.py` registers whatever `resolve_cli_services()` returns:

```python
for svc in resolve_cli_services():
    app.add_typer(svc.app, name=svc.name, help=svc.help)
```

`load_service(name)` is the cross-service adapter lookup used by
`postgresql/commands.py`'s optional Coolify remote adapter: instead of a
hardcoded `from copilot_cli.services.coolify...` import, `db` asks
`load_service("coolify")` and gets back a `ServiceEntry` (or `None`) it can
pull specific submodules from via `.submodule("core.api_client")` etc. A
tier that wants remote-DB support simply **adds** a `coolify` service via
`provides:` — no `postgresql` fork required.

## `copilot --json layers`

New top-level command (`main.py`). Reports the resolved chain and
per-service provenance — see `docs/schemas/layers.schema.json` for the
frozen JSON Schema. Parse-not-compute friendly: every field is already
resolved by `config/layers.py`/`services/_loader.py`; a consumer (e.g.
Control Tower) only ever renders it.

This is a **cli-copilot-local** contract, distinct from
`copilot-control-tower`'s own `layers [join]` schema (department/org
entitlement discovery for the content components, on a different CLI
program). The two share a command name and nothing else — see that
repo's `docs/01-architecture/schemas/layers.schema.json` if reconciling
the two is ever in scope.

## What's NOT in Phase 1

- `copilot update` syncing tier mirrors onto disk (mirror roots are a
  documented convention, not yet materialized by anything in this repo).
- The `-internal` extraction/reconciliation (Phase 2) and cutover gated by
  a golden-output oracle (Phase 3).
- A real managed-secret-store client and device-code auth flow (ladder
  rungs 1 and 3) — cleanly stubbed, fall through by design.
- `cc`/Control Tower rendering this payload — this doc only covers the
  CLI-side contract; wiring a renderer is out of scope here.
