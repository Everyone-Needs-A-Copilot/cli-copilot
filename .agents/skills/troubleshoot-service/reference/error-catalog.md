# CopilotError Catalog

Complete catalog of every CopilotError subtype from `copilot_cli/shared/errors.py` with specific messages, common causes, and recovery commands.

## Error Hierarchy

```
CopilotError (base)
├── ConfigError
├── ConnectionError
├── AuthError
├── NotFoundError
├── ValidationError
├── TimeoutError
└── RateLimitError
```

## ConfigError

Missing or invalid configuration. Always a local fix (`.env` file).

| Message Pattern | Service | Cause | Recovery |
|----------------|---------|-------|----------|
| "Missing or invalid configuration" | Any | Env var not set | Check `.env` for required vars |
| "Missing COOLIFY_BASE_URL" | coolify | Coolify not configured | Add `COOLIFY_BASE_URL=https://...` to `.env` |
| "Missing COOLIFY_ACCESS_TOKEN" | coolify | Coolify auth not set | Add `COOLIFY_ACCESS_TOKEN=...` to `.env` |
| "Missing NOCODB_URL" | crm | NocoDB not configured | Add `NOCODB_URL=https://...` to `.env` |
| "Missing NOCODB_API_KEY" | crm | NocoDB auth not set | Add `NOCODB_API_KEY=...` to `.env` |
| "Missing NOCODB_BASE_ID" | crm | NocoDB base not set | Add `NOCODB_BASE_ID=...` to `.env` |
| "Missing BREVO_API_KEY" | brevo | Brevo not configured | Add `BREVO_API_KEY=...` to `.env` |
| "Missing N8N_BASE_URL" | n8n | n8n not configured | Add `N8N_BASE_URL=https://...` to `.env` |
| "Missing N8N_API_KEY" | n8n | n8n auth not set | Add `N8N_API_KEY=...` to `.env` |
| "Missing DATABASE_URL" | db | PostgreSQL not configured | Add `DATABASE_URL=postgresql://...` to `.env` |
| "Missing INSIGHTS_BASE_URL" | insights | Insights not configured | Add `INSIGHTS_BASE_URL=https://...` to `.env` |
| "Missing INSIGHTS_API_KEY" | insights | Insights auth not set | Add `INSIGHTS_API_KEY=...` to `.env` |
| "Missing PROJECT_COPILOT_BASE_URL" | project | Project not configured | Add `PROJECT_COPILOT_BASE_URL=https://...` to `.env` |
| "Missing PROJECT_COPILOT_API_KEY" | project | Project auth not set | Add `PROJECT_COPILOT_API_KEY=...` to `.env` |
| "Missing CONVERSATIONS_BASE_URL" | conv | Conv not configured | Add `CONVERSATIONS_BASE_URL=https://...` to `.env` |
| "Missing CONVERSATIONS_API_TOKEN" | conv | Conv auth not set | Add `CONVERSATIONS_API_TOKEN=...` to `.env` |

**Diagnosis command:** Read `.env` and cross-reference with `copilot_cli/config/settings.py`.

## AuthError

Authentication or authorization failure. Usually expired/invalid API keys.

| Message Pattern | HTTP Code | Service | Recovery |
|----------------|-----------|---------|----------|
| "Authentication failure" | 401 | Any API service | Regenerate API key |
| "Unauthorized" | 401 | coolify | `copilot coolify key create --json` |
| "Forbidden" | 403 | Any | Check API key permissions/scope |
| "Token expired" | 401 | conv | `copilot conv auth login --json` then `copilot conv auth refresh` |
| "Invalid API key" | 401 | insights | Regenerate in Insights admin panel |

**Diagnosis commands:**
```bash
copilot <service> health --json        # Quick auth test
copilot coolify key list --json        # List Coolify API keys
copilot conv auth me --json            # Check Conv auth status
copilot project identity --json        # Check Project auth status
```

## ConnectionError

Service unreachable. Check infrastructure (Docker, Coolify, network).

| Message Pattern | Service | Cause | Recovery |
|----------------|---------|-------|----------|
| "Cannot reach service" | Any | Service down | Check Docker/Coolify |
| "Connection refused" | Any | Port not listening | `copilot docker ps --json` -- is container running? |
| "Name resolution failed" | Any | DNS issue | Check URL in `.env` is correct |
| "SSL certificate error" | Any | Cert expired | Check Coolify SSL settings |

**Diagnosis commands:**
```bash
copilot docker ps --json               # Is container running?
copilot docker info --json             # Is Docker daemon running?
copilot coolify app list --json        # Is Coolify managing this app?
copilot coolify server healthcheck --json  # Is the server reachable?
copilot monitoring status --json       # Is system overloaded (OOM crash)?
```

## NotFoundError

Resource doesn't exist. Usually wrong ID or deleted resource.

| Message Pattern | HTTP Code | Service | Recovery |
|----------------|-----------|---------|----------|
| "Resource does not exist" | 404 | Any | List resources first |
| "Client not found" | 404 | crm | `copilot crm clients list --json` |
| "Lead not found" | 404 | crm | `copilot crm leads list --json` |
| "Workflow not found" | 404 | n8n | `copilot n8n workflows list --json` |
| "Article not found" | 404 | insights | `copilot insights articles list --json` |
| "Dossier not found" | 404 | insights | `copilot insights dossiers list --json` |
| "Person not found" | 404 | conv | `copilot conv people list --json` |

**Diagnosis:** Always list the resource type first, then use the correct ID.

## ValidationError

Invalid input parameters.

| Message Pattern | Service | Cause | Recovery |
|----------------|---------|-------|----------|
| "Input failed validation" | Any | Bad parameter format | Check parameter types |
| "Invalid email" | brevo, crm | Malformed email address | Validate format before submitting |
| "Invalid SQL" | db | Syntax error in query | Check SQL syntax |
| "Invalid JSON" | Any | Malformed JSON in --data | Validate JSON structure |
| "Invalid database name" | db | Unknown database | Use: main, nocodb, n8n, formbricks |

## TimeoutError

Operation took too long. Usually service overload.

| Message Pattern | Service | Cause | Recovery |
|----------------|---------|-------|----------|
| "Operation exceeded time limit" | Any | Service overloaded | Check `copilot monitoring status --json` |
| Query timeout | db | Long-running query | Use `copilot db explain` first; check for locks |
| Synthesis timeout | insights | LLM processing slow | `copilot insights synthesis status --json` |
| Deploy timeout | coolify | Build hung | Check `copilot coolify deploy logs --deployment-id <id>` |

**Diagnosis commands:**
```bash
copilot monitoring status --json       # Check CPU/memory/disk
copilot db stats --json                # Check connection pool
copilot shell ps --json                # Check for stuck processes
```

## RateLimitError

Too many requests. Back off and retry.

| Message Pattern | HTTP Code | Service | Recovery |
|----------------|-----------|---------|----------|
| "Rate limit exceeded" | 429 | brevo | Wait 60 seconds, reduce batch size |
| "Too many requests" | 429 | Any API | Implement exponential backoff |

**Recovery pattern:** Wait -> reduce batch size -> retry with smaller scope.

## Service-Specific Required Environment Variables

| Service | Variables | Verify With |
|---------|-----------|-------------|
| coolify | `COOLIFY_BASE_URL`, `COOLIFY_ACCESS_TOKEN` | `copilot coolify server healthcheck --json` |
| crm | `NOCODB_URL`, `NOCODB_API_KEY`, `NOCODB_BASE_ID` | `copilot crm health --json` |
| brevo | `BREVO_API_KEY` | `copilot brevo health --json` |
| n8n | `N8N_BASE_URL`, `N8N_API_KEY` | `copilot n8n health --json` |
| db | `DATABASE_URL` (+ per-DB URLs) | `copilot db health --json` |
| insights | `INSIGHTS_BASE_URL`, `INSIGHTS_API_KEY` | `copilot insights health --json` |
| project | `PROJECT_COPILOT_BASE_URL`, `PROJECT_COPILOT_API_KEY` | `copilot project health --json` |
| conv | `CONVERSATIONS_BASE_URL`, `CONVERSATIONS_API_TOKEN` | `copilot conv auth me --json` |
| docker | `DOCKER_SOCKET` (optional, default: /var/run/docker.sock) | `copilot docker info --json` |
| monitoring | None required | `copilot monitoring status --json` |
| fs | `ALLOWED_VOLUMES` (optional, default: /tmp) | `copilot fs health --json` |
| shell | None required | `copilot shell health --json` |
| services | None required | `copilot services health --json` |
| git | None required | `copilot git health --json` |
| docs | Depends on backend | `copilot docs health --json` |
| bi | None required | `copilot bi health --json` |
