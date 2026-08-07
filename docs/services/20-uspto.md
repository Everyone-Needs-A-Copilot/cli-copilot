---
title: USPTO Service
category: reference
last-updated: 2026-04-03
---

# USPTO Service

`copilot uspto` provides authenticated access to the USPTO Open Data Portal (ODP) and the Trademark Status and Document Retrieval (TSDR) APIs, plus an automated contract discovery system for capturing API contracts from USPTO product web UIs.

## What This Service Is Trying To Do

The goal of `copilot uspto` is to give you one CLI surface for:

- Patent and trademark clearance research
- Ownership and assignment review
- Dossier and watchlist generation
- Authenticated portal retrieval where public APIs are insufficient
- Automated API contract discovery for products whose backend contract is not yet pinned

To do that safely, the CLI needs stable source contracts. A source contract means:

- the real API endpoint
- HTTP method
- request payload or query params
- auth/header requirements
- response structure

If USPTO publishes that contract clearly, the CLI can implement a direct adapter. If USPTO only exposes a browser UI, the `discover` subsystem can automate the capture.

## What Is Already Automated

Already implemented and working:

- USPTO readiness checks
- Auth instructions and session capture/import
- Generic ODP request support
- TSDR status, docs, and image retrieval
- Office Action fields endpoint
- Office Action records endpoint
- Dossier build, export, and watchlist workflows
- Session-backed portal fetch
- Automated API contract discovery via Playwright network interception
- Code generation of client/command/test stubs from captured contracts

You can inspect readiness any time with:

```bash
copilot uspto auth status
```

## Configuration

Required:

- `USPTO_CLI_API_KEY`
- `USPTO_CLI_BASE_URL`

Optional:

- `USPTO_TSDR_BASE_URL` — defaults to `https://tsdrapi.uspto.gov`
- `COPILOT_USPTO_DATA_DIR` — local data root; defaults to `~/.copilot-cli/uspto`

## Commands

| Command | What it does |
|---|---|
| `copilot uspto health` | Checks config and validates the API key against a sample TSDR request |
| `copilot uspto auth list` | Lists required auth artifacts and shows step-by-step acquisition instructions |
| `copilot uspto auth show <artifact_id>` | Shows detailed instructions for one auth artifact |
| `copilot uspto auth status` | Shows what is implemented and what configuration/session gaps remain |
| `copilot uspto products` | Shows the official USPTO capability areas you should plan around |
| `copilot uspto request <path>` | Makes a generic authenticated ODP request |
| `copilot uspto patents search <query>` | Patent search handoff |
| `copilot uspto patents application <id>` | Patent application handoff |
| `copilot uspto patents office-actions [query]` | Search Office Action records via the live API |
| `copilot uspto patents office-action-fields` | Fetch the Office Action field schema from the live API |
| `copilot uspto patents ptab <query>` | PTAB handoff |
| `copilot uspto trademarks search <query>` | Trademark search handoff |
| `copilot uspto trademarks status <id>` | Fetches normalized trademark status |
| `copilot uspto trademarks tmog <query>` | Trademark Official Gazette handoff |
| `copilot uspto trademarks id-manual <query>` | ID Manual handoff |
| `copilot uspto trademarks design-codes <query>` | Design Search Code Manual handoff |
| `copilot uspto trademarks proceedings <query>` | TTAB proceedings handoff |
| `copilot uspto assignments search <query>` | Assignment search handoff |
| `copilot uspto copyright search <query>` | Copyright public-records handoff |
| `copilot uspto dossier build <name> <seeds>` | Build and save a cross-source dossier |
| `copilot uspto dossier show <name>` | Show a saved dossier |
| `copilot uspto dossier list` | List saved dossiers |
| `copilot uspto dossier export <name> <output>` | Export a dossier to disk |
| `copilot uspto watch create <name> <seeds>` | Create a watchlist |
| `copilot uspto watch list` | List watchlists |
| `copilot uspto watch run <name>` | Run a saved watchlist |
| `copilot uspto sessions import <name> <file>` | Import a portal session |
| `copilot uspto sessions capture <name> <url>` | Open a browser and capture authenticated storage state |
| `copilot uspto sessions list` | List imported sessions |
| `copilot uspto portal fetch <url>` | Use imported Playwright storage state to fetch a protected portal page |
| `copilot uspto tsdr status <id>` | Fetches trademark case status |
| `copilot uspto tsdr docs <id>` | Fetches trademark document bundles/metadata |
| `copilot uspto tsdr image <serial>` | Fetches a trademark image |
| `copilot uspto discover products` | Show all product recipes and their confirmation status |
| `copilot uspto discover auto <product>` | Run automated discovery using a saved recipe |
| `copilot uspto discover manual <url>` | Open a headed browser, intercept requests, save contract |
| `copilot uspto discover list` | List all saved contracts |
| `copilot uspto discover show <product>` | Show a saved contract |
| `copilot uspto discover generate <product>` | Generate adapter stubs from a saved contract |

---

## Contract Discovery System

The discovery subsystem automates the process of capturing API contracts from USPTO product web UIs using Playwright network interception. It replaces the manual DevTools workflow that was previously required.

### Source Files

| File | Purpose |
|---|---|
| `copilot_cli/services/uspto/models.py` | `CapturedContract` and `ProductRecipe` Pydantic models |
| `copilot_cli/services/uspto/discovery.py` | `ContractDiscoverer` class — Playwright interception engine |
| `copilot_cli/services/uspto/recipes.py` | Pre-configured `ProductRecipe` instances for 6 products |
| `copilot_cli/services/uspto/codegen.py` | `AdapterGenerator` — produces client/command/test stubs |
| `copilot_cli/services/uspto/commands.py` | CLI wiring for `copilot uspto discover *` |

### Data Storage

Contracts are saved as JSON files at:

```
~/.copilot-cli/uspto/contracts/<product>.json
```

Override the root with `COPILOT_USPTO_DATA_DIR`.

---

## Models

### CapturedContract

Represents one captured API request/response pair from a product web UI.

| Field | Type | Description |
|---|---|---|
| `product` | `str` | Product name (matches the recipe or `--product` flag) |
| `captured_at` | `str` | ISO 8601 UTC timestamp of capture |
| `url` | `str` | Full request URL |
| `method` | `str` | HTTP method (`GET`, `POST`, etc.) |
| `request_headers` | `dict` | Request headers; sensitive values masked as `[MASKED]` |
| `request_content_type` | `str \| None` | Value of the request `content-type` header |
| `request_body` | `Any` | Raw POST body string or parsed dict; `None` for GET |
| `response_status` | `int` | HTTP response status code |
| `response_content_type` | `str \| None` | Value of the response `content-type` header |
| `response_headers` | `dict` | Response headers; sensitive values masked as `[MASKED]` |
| `response_body_sample` | `Any` | Parsed JSON body or truncated string (max 100 KB stored, 10 KB sampled) |
| `response_body_size` | `int` | Actual response body size in bytes |
| `sample_query` | `str` | The query string used when the capture was made |
| `notes` | `list[str]` | Auto-generated observations (e.g., "Response is JSON.", "Request method is POST.") |

Sensitive headers masked: `cookie`, `authorization`, `x-api-key`, `set-cookie`.

### ProductRecipe

Describes how to drive a product web UI for automated discovery.

| Field | Type | Default | Description |
|---|---|---|---|
| `product` | `str` | — | Product identifier (must be unique in the registry) |
| `url` | `str` | — | Full URL of the product's search page |
| `search_selector` | `str \| None` | — | CSS selector for the search input field; `None` for pages with no input |
| `submit_selector` | `str \| None` | — | CSS selector for the submit button; `None` for pages with no button |
| `sample_query` | `str` | — | Default search term to type into the search field |
| `wait_for` | `str` | `"networkidle"` | Either `"networkidle"` or a CSS selector to wait for after clicking submit |
| `confirmed` | `bool` | `False` | `True` once the recipe's selectors have been verified against the live product |

---

## Product Recipe Registry

Defined in `copilot_cli/services/uspto/recipes.py`. Access via `copilot uspto discover products`.

| Product | URL | Search Selector | Submit Selector | Sample Query | Confirmed |
|---|---|---|---|---|---|
| `ptab` | `https://developer.uspto.gov/ptab-web/#/search/decisions` | `input[type='text']` | `button[type='submit']` | `IPR2020-00001` | No |
| `trademark_search` | `https://tmsearch.uspto.gov/search/search-information` | `input#search-text` | `button#search-submit` | `NIKE` | No |
| `tmog` | `https://tmog.uspto.gov/#` | `input[type='text']` | `button[type='submit']` | `clothing` | No |
| `id_manual` | `https://idm-tmng.uspto.gov/id-master-list-public.html` | `input#search` | `button#searchBtn` | `software` | No |
| `design_search` | `https://www.uspto.gov/trademarks/search/design-search-codes` | (none) | (none) | (none) | No |
| `assignment_search` | `https://assignment.uspto.gov/patent/index.html#/patent/search` | `input#query` | `button.search-btn` | `Google` | No |

`confirmed: False` means the CSS selectors have not yet been validated against a live session. If auto discovery captures 0 requests, verify the selectors against the live page and update `recipes.py`.

---

## Discover Commands — Full Reference

### `copilot uspto discover products`

Shows all product recipes and their confirmation status. No arguments.

```bash
copilot uspto discover products
```

Output: Rich table with columns `product`, `url`, `search_selector`, `sample_query`, `confirmed`.

---

### `copilot uspto discover auto`

Runs automated discovery for one product using its saved recipe. Opens a Chromium window (headed), fills the search field, clicks submit, waits for network idle, then saves the highest-scoring contract.

```
copilot uspto discover auto <product> [--session <name>] [--query <text>]
```

| Argument/Option | Required | Description |
|---|---|---|
| `product` | Yes | Product name from the recipe registry (e.g. `ptab`, `trademark_search`) |
| `--session`, `-s` | No | Imported session name; loads storage state from `~/.copilot-cli/uspto/session_states/<name>.json` |
| `--query`, `-q` | No | Override the recipe's `sample_query` for this run |

Saves the top-ranked contract to `~/.copilot-cli/uspto/contracts/<product>.json`.

Output JSON:

```json
{
  "product": "ptab",
  "captured": 4,
  "top_url": "https://developer.uspto.gov/ptab-api/...",
  "top_method": "GET",
  "response_status": 200,
  "saved_to": "/Users/you/.copilot-cli/uspto/contracts/ptab.json"
}
```

Exit code 1 if: product not in registry, zero requests captured, or Playwright error.

---

### `copilot uspto discover manual`

Opens a headed Chromium browser at the given URL, intercepts all XHR/fetch requests while you interact, then saves the highest-scoring contract when you press Enter in the terminal.

```
copilot uspto discover manual <url> [--session <name>] [--product <label>] [--query <text>] [--timeout <seconds>]
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `url` | Yes | — | Full URL to open in the browser |
| `--session`, `-s` | No | — | Imported session name for auth |
| `--product`, `-p` | No | `"unknown"` | Product label saved into the contract and used as the filename |
| `--query`, `-q` | No | `""` | Sample query label embedded in the captured contract |
| `--timeout`, `-t` | No | `120` | Seconds the browser stays open before timing out |

The browser stays open until you press Enter in the terminal. Perform your search in the browser window first, then press Enter.

Saves the top-ranked contract to `~/.copilot-cli/uspto/contracts/<product>.json`.

Output JSON: same shape as `discover auto`.

---

### `copilot uspto discover list`

Lists all product names that have a saved contract on disk.

```bash
copilot uspto discover list
```

Output: Rich table with a `product` column. Empty JSON `{"contracts": []}` if none exist.

---

### `copilot uspto discover show`

Displays the full `CapturedContract` JSON for a saved product.

```
copilot uspto discover show <product>
```

| Argument | Required | Description |
|---|---|---|
| `product` | Yes | Product name matching a saved contract file |

Output: Full `CapturedContract` dict. Exit code 1 if no contract found.

---

### `copilot uspto discover generate`

Generates three Python stub files from a saved contract and writes them to a directory.

```
copilot uspto discover generate <product> [--output-dir <path>]
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `product` | Yes | — | Product name matching a saved contract |
| `--output-dir`, `-o` | No | `.` (current directory) | Directory to write generated files into |

Generated files:

| File | Contents |
|---|---|
| `client_<product>.py` | Client method stub with correct URL, method, headers, and body/params |
| `command_<product>.py` | Typer command stub with arguments derived from request body keys |
| `test_<product>.py` | Pytest stub with a placeholder test for the client method |

Output JSON:

```json
{
  "ptab": {
    "client": "/path/to/client_ptab.py",
    "command": "/path/to/command_ptab.py",
    "test": "/path/to/test_ptab.py"
  }
}
```

---

## Request Ranking Logic

When multiple requests are captured in a single session, `ContractDiscoverer._rank_captures()` scores each `CapturedContract` and returns them sorted highest first. The scoring rules:

| Signal | Score adjustment |
|---|---|
| Response `content-type` contains `json` | +10 |
| Request method is `POST` | +5 |
| URL contains `/api/`, `/search/`, `/records/`, or `/query/` | +3 each |
| Response body size > 1 KB | +2 |
| URL contains `analytics`, `tracking`, `beacon`, `telemetry`, or `metrics` | -5 |

The `discover auto` and `discover manual` commands save only the top-ranked contract. The full ranked list is available programmatically via `ContractDiscoverer.discover_auto()` and `ContractDiscoverer.discover_manual()`.

### Noise Filtering

Requests are excluded before scoring if they match any of the following:

- Resource type is `stylesheet`, `image`, `font`, `media`, or `script`
- Hostname is a known analytics domain (Google Analytics, Google Tag Manager, DoubleClick, etc.)
- URL path has a static file extension (`.js`, `.css`, `.png`, `.svg`, `.woff2`, `.gif`, `.jpg`, `.ico`, `.woff`, `.ttf`, `.eot`)

---

## Code Generation Details

`AdapterGenerator` in `copilot_cli/services/uspto/codegen.py` derives adapter code from `CapturedContract` fields.

### Parameter extraction

The generator reads `request_body` to derive argument names:

1. If `request_body` is a `dict` — uses the dict keys directly.
2. If `request_body` is a JSON string — parses it and uses the keys.
3. If `request_body` is a form-encoded string — splits on `&`, extracts the left side of each `=`.
4. If none of the above — falls back to a single `query` argument.

### Naming conventions

| Input `product` | Client method name | Python class name |
|---|---|---|
| `ptab` | `search_ptab` | `PtabClient` |
| `trademark_search` | `search_trademark_search` | `TrademarkSearchClient` |
| `assignment_search` | `search_assignment_search` | `AssignmentSearchClient` |
| `id_manual` | `search_id_manual` | `IdManualClient` |

The slug function lowercases the product name, replaces all non-alphanumeric characters with `_`, and collapses repeated underscores.

### What the stubs are NOT

Generated stubs are starting points, not working adapters. Each stub:

- Has a `_client()` function that raises `NotImplementedError` — you must wire up a real client class.
- Uses the exact URL, method, and masked headers from the capture.
- Leaves the test as a `pass` with a `TODO` comment.

Promote a stub to a real adapter by instantiating a proper client class, injecting the API key from settings, and writing real tests.

---

## End-to-End Workflow: Adding a New Adapter

This is the full process for turning a USPTO product that currently has no adapter into a working one.

### Step 1 — Check what is already done

```bash
copilot uspto auth status
copilot uspto discover list
copilot uspto discover products
```

`auth status` shows which products are implemented. `discover list` shows which have saved contracts. `discover products` shows which recipes are available.

### Step 2 — Run automated discovery

If the product is in the recipe registry:

```bash
copilot uspto discover auto ptab
```

If you need an authenticated session:

```bash
copilot uspto sessions capture my-session https://developer.uspto.gov/ptab-web/
copilot uspto discover auto ptab --session my-session
```

If the recipe selectors fail (zero captures), try manual discovery:

```bash
copilot uspto discover manual https://developer.uspto.gov/ptab-web/#/search/decisions \
  --product ptab \
  --query "IPR2020-00001"
```

Interact with the browser, press Enter when done.

### Step 3 — Inspect the contract

```bash
copilot uspto discover show ptab
```

Verify:

- `url` is the real data endpoint (not the UI shell)
- `method` is correct (`GET` or `POST`)
- `request_body` or query params look right
- `response_body_sample` contains actual data (not HTML or an error page)
- `response_status` is `200`

If the contract looks wrong, repeat Step 2 with a different query or verify the recipe selectors.

### Step 4 — Generate stubs

```bash
copilot uspto discover generate ptab --output-dir copilot_cli/services/uspto/
```

This writes:

- `copilot_cli/services/uspto/client_ptab.py`
- `copilot_cli/services/uspto/command_ptab.py`
- `copilot_cli/services/uspto/test_ptab.py`

### Step 5 — Promote to a real adapter

1. Move the client method from `client_ptab.py` into `copilot_cli/services/uspto/client.py` as a method on `USPTOClient`.
2. Replace the hardcoded headers with settings-based auth (API key from `self._settings.uspto_cli_api_key`).
3. Move the command from `command_ptab.py` into `copilot_cli/services/uspto/commands.py` under `patents_app` or `trademarks_app`.
4. Write real tests in `tests/test_services/test_uspto.py`, replacing the stub placeholder.
5. Update `recipes.py` to set `confirmed=True` for the product.
6. Update this doc's product status table.

---

## Product Status Table

| Product | Adapter Status | Contract Source | Recipe Confirmed |
|---|---|---|---|
| ODP Patent File Wrapper | Handoff only | — | — |
| Patent Public Search | Handoff only | — | — |
| Patent Center | Session-backed portal fetch | Playwright session | — |
| Office Actions fields | Live API | Published ODP endpoint | — |
| Office Actions records | Live API | Captured `POST /records` | — |
| PTAB | No adapter | Recipe available | No |
| TSDR status/docs/image | Live API | Published TSDR endpoint | — |
| Trademark Search | Handoff only | Recipe available | No |
| TMOG | Handoff only | Recipe available | No |
| ID Manual | Handoff only | Recipe available | No |
| Design Search Codes | Handoff only | Recipe available (no selectors) | No |
| Assignment Search | Handoff only | Recipe available | No |
| Copyright | Out of scope | — | — |

---

## What Still Needs To Happen

The remaining work is to run `discover auto` for each unconfirmed recipe, verify the captured contracts, generate stubs, and promote them to real adapters in `client.py` and `commands.py`.

Priority order based on clearance workflow importance:

1. **PTAB** — post-grant proceedings affect freedom-to-operate
2. **Trademark Search** — primary clearance search
3. **Assignment Search** — ownership chain verification
4. **TMOG** — opposition window monitoring
5. **ID Manual** — goods/services class normalization
6. **Design Search Codes** — no known backing API; confirm or document as web-only

For each, the contract discovery command will give you the exact endpoint. If `discover auto` captures zero results or wrong results, use `discover manual` with the same URL.

The manual DevTools workflow described in previous versions of this document is no longer needed. Use `copilot uspto discover` instead.

---

## Notes

- ODP uses the `X-Api-Key` header.
- TSDR uses the `USPTO-API-KEY` header.
- TSDR XML responses are normalized to JSON-shaped output by default when you request `--format json`.
- Local dossier/watch/session/contract data is stored under `~/.copilot-cli/uspto` by default. Set `COPILOT_USPTO_DATA_DIR` to override it.
- Session import accepts Playwright storage-state JSON or a raw cookie array.
- `sessions capture` opens a local browser so you can complete login yourself, then saves storage state for reuse.
- Portal fetch is retrieval-only. It does not automate credential entry or MFA.
- Copyright searching is outside USPTO scope and needs separate official sources.
- Playwright must be installed for any `discover` command: `pip install playwright && playwright install chromium`.
- All discovery runs open a headed (visible) Chromium window. Headless mode is not used.
- Sensitive headers (`cookie`, `authorization`, `x-api-key`, `set-cookie`) are masked as `[MASKED]` in saved contracts. You must re-inject auth at runtime via settings.

## Implementation Status

Implemented now:

- USPTO health, auth guidance, readiness status, and generic ODP request support
- Patent, trademark, assignment, and copyright handoff commands with normalized JSON envelopes
- Live Office Action field-schema retrieval via the published ODP endpoint
- Live Office Action record search via the published form-encoded ODP endpoint
- TSDR status/doc/image support with XML normalized to JSON by default
- Dossier build/show/list/export
- Watch create/list/run
- Session import/capture/list and session-backed portal fetch
- Contract discovery engine (`discover auto`, `discover manual`, `discover list`, `discover show`)
- Product recipe registry for 6 USPTO products
- Code generation of client/command/test stubs from captured contracts (`discover generate`)

Still dependent on your setup:

- `USPTO_CLI_API_KEY`
- `USPTO_CLI_BASE_URL`
- Playwright installed with Chromium binaries (`playwright install chromium`)
- Imported authenticated sessions for Patent Center, Trademark Center, or Assignment Center when you want protected portal access

Not yet promoted to real API adapters (stubs can be generated via `discover generate`):

- PTAB
- Trademark Search
- TMOG
- ID Manual
- Design Search Codes
- Assignment Search
