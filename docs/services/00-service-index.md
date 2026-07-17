---
title: Service Index
category: reference
last-updated: 2026-04-13
---

# Service Index

| # | CLI Command | Service | Client Pattern | Config Required |
|---|-------------|---------|---------------|-----------------|
| 01 | `copilot git` | Git (GitPython) | Class-based | `GIT_USER_NAME`, `GIT_USER_EMAIL` |
| 02 | `copilot docker` | Docker SDK | Class-based | `DOCKER_SOCKET` |
| 03 | `copilot shell` | subprocess | Module-level | `SHELL_SCRIPTS_PATH`, `SHELL_TIMEOUT` |
| 04 | `copilot fs` | Local filesystem | Module-level | `ALLOWED_VOLUMES`, `MAX_FILE_SIZE_MB` |
| 05 | `copilot services` | macOS launchctl | Module-level | None |
| 06 | `copilot db` | PostgreSQL (psycopg2) | Class-based | `DATABASE_URL` + per-DB URLs |
| 07 | `copilot crm` | NocoDB API | Class-based | `NOCODB_URL`, `NOCODB_API_KEY`, `NOCODB_BASE_ID` |
| 08 | `copilot brevo` | Brevo API v3 | Class-based | `BREVO_API_KEY` |
| 09 | `copilot n8n` | n8n REST API | Class-based | `N8N_BASE_URL`, `N8N_API_KEY` |
| 10 | `copilot docs` | Local filesystem | Module-level | None |
| 11 | `copilot bi` | Local computation | Module-level | None |
| 12 | `copilot monitoring` | System commands | Module-level | Alert thresholds |
| 13 | `copilot coolify` | Coolify API + SSH | Class-based | `COOLIFY_BASE_URL`, `COOLIFY_ACCESS_TOKEN` |
| 14 | `copilot skill` | Skill Runtime (local filesystem + subprocess) | Class-based | `SKILL_PATHS` (optional) |
| 15 | `copilot uspto` | USPTO ODP + TSDR APIs | Class-based | `USPTO_CLI_BASE_URL`, `USPTO_CLI_API_KEY` |
| 16 | `copilot discord` | Discord handoff threads | Class-based | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `DISCORD_ALLOWED_USER_IDS` |
| 17 | `copilot infisical` | Infisical API (Universal Auth) | Class-based | `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` |

Detailed documentation for each service: see `01-git.md` through `22-discord.md` in this directory (filenames predate this index's own numbering and don't track it 1:1 — pre-existing, out of this cut's scope).
