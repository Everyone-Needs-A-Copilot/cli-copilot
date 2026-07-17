---
title: Infisical CLI
category: service-reference
last-updated: 2026-07-13
---

# Infisical CLI

**Command:** `copilot infisical`
**Source:** `copilot_cli/services/infisical/`

## Purpose

Infisical secrets management — projects (workspaces), folders, secrets,
machine identities, and organisation admin. This service fronts the
Infisical REST API via Universal Auth (machine-to-machine OAuth); it owns
no secret values of its own and never persists them to disk.

## Commands

| Subgroup | Command | Description | Key Options |
|----------|---------|-------------|-------------|
| `infisical` | `config show` | Show configuration (credentials masked) and verify auth | — |
| `infisical project` | `list` | List projects | — |
| `infisical project` | `get` | Get a project | `PROJECT_ID` |
| `infisical project` | `create` | Create a project | `NAME` |
| `infisical project` | `delete` | Delete a project | `PROJECT_ID`, `--force` |
| `infisical folder` | `list` | List folders | `--project`, `--env`, `--path` |
| `infisical folder` | `create` | Create a folder | `NAME`, `--project`, `--env`, `--path` |
| `infisical secret` | `list` | List secret keys (values hidden) | `--project`, `--env`, `--path` |
| `infisical secret` | `get` | Get a secret value | `KEY`, `--project`, `--env`, `--path` |
| `infisical secret` | `set` | Create or update a secret | `KEY`, `VALUE`, `--project`, `--env`, `--path` |
| `infisical secret` | `delete` | Delete a secret | `KEY`, `--project`, `--env`, `--path`, `--force` |
| `infisical identity` | `list` | List machine identities | `--org-id` |
| `infisical identity` | `create` | Create a machine identity | `NAME`, `--org-id`, `--role` |
| `infisical identity` | `delete` | Delete a machine identity | `IDENTITY_ID` |
| `infisical org` | `disable-signup` | Disable open registration (super-admin only) | `--force` |

## Examples

```bash
copilot infisical config show
copilot infisical project list
copilot infisical secret list --project <project-id> --env dev
copilot infisical secret set API_KEY supersecret --project <project-id> --env prod
copilot infisical secret get API_KEY --project <project-id> --env prod
```

Set a default project once per session with `--project`/`-p` on each command,
or start every command with `--org-id` to override the auto-discovered
organisation.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `INFISICAL_CLIENT_ID` | Universal Auth client ID | Required |
| `INFISICAL_CLIENT_SECRET` | Universal Auth client secret | Required |
| `INFISICAL_BASE_URL` | API base URL | `https://app.infisical.com` |
| `INFISICAL_ORG_ID` | Organisation ID | Auto-discovered from the authenticated identity if unset |

No persistent config file is used — all credentials are read from the
environment (`.env`), keeping secrets out of the filesystem.

## Health Check

```bash
copilot health
```

`copilot health` includes `infisical` in its check list: it authenticates via
Universal Auth and confirms an identity can be resolved. Reports unhealthy
(without a network call) when `INFISICAL_CLIENT_ID`/`INFISICAL_CLIENT_SECRET`
are missing.
