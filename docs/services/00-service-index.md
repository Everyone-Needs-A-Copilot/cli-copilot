---
title: Service Index
category: reference
last-updated: 2026-07-18
---

# Service Index

This public foundation ships 12 generic, credential-free service adapters.
`nocodb`/`crm`, `brevo`, `n8n`, `coolify`, and `discord` were org-specific
vendor adapters and have moved to the org-specific `-internal` tier — they
are no longer part of this repo. `uspto` and `infisical` are kept as the two
worked-example adapters (see their entries below, and the README's
"Reference adapters" note) for adopters scaffolding a new one.

| # | CLI Command | Service | Client Pattern | Config Required |
|---|-------------|---------|---------------|-----------------|
| 01 | `copilot git` | Git (GitPython) | Class-based | `GIT_USER_NAME`, `GIT_USER_EMAIL` |
| 02 | `copilot docker` | Docker SDK | Class-based | `DOCKER_SOCKET` |
| 03 | `copilot shell` | subprocess | Module-level | `SHELL_SCRIPTS_PATH`, `SHELL_TIMEOUT` |
| 04 | `copilot fs` | Local filesystem | Module-level | `ALLOWED_VOLUMES`, `MAX_FILE_SIZE_MB` |
| 05 | `copilot services` | macOS launchctl | Module-level | None |
| 06 | `copilot db` | PostgreSQL (psycopg2) | Class-based | `DATABASE_URL` + per-DB URLs |
| 07 | `copilot docs` | Local filesystem | Module-level | None |
| 08 | `copilot bi` | Local computation | Module-level | None |
| 09 | `copilot monitoring` | System commands | Module-level | Alert thresholds |
| 10 | `copilot skill` | Skill Runtime (local filesystem + subprocess) | Class-based | `SKILL_PATHS` (optional) |
| 11 | `copilot uspto` | USPTO ODP + TSDR APIs | Class-based | `USPTO_CLI_BASE_URL`, `USPTO_CLI_API_KEY` |
| 12 | `copilot infisical` | Infisical API (GitHub broker or Universal Auth) | Class-based | Broker config or `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` |

Detailed documentation for each service: see `01-git.md` through `20-uspto.md` in this directory (filenames predate this index's own numbering and don't track it 1:1 — pre-existing, out of this cut's scope).
