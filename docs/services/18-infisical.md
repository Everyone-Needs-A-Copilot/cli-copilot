---
title: Infisical CLI
category: service-reference
last-updated: 2026-10-06
---

# Infisical CLI

**Command:** `copilot infisical`
**Source:** `copilot_cli/services/infisical/`

## Purpose

Infisical secrets management — projects (workspaces), folders, secrets,
machine identities, and organisation admin. Interactive Macs authenticate
through the organization's GitHub-authorized OIDC assertion broker and receive
only a short-lived access token. Universal Auth remains available for explicitly
configured headless or legacy actors. The service owns no secret values.

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
| `infisical access` | `verify` | Prove an authorized read and an out-of-scope denial without returning names or values | `--project`, `--env`, `--path`, `--negative-path`, `--scope` |

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
| `INFISICAL_BROKER_URL` | Organization-operated assertion broker HTTPS origin | Optional; enables the interactive path |
| `INFISICAL_BROKER_ISSUER` | Exact OIDC issuer; must match the broker origin | Required with broker |
| `INFISICAL_BROKER_AUDIENCE` | Exact Infisical origin and assertion audience | Required with broker |
| `INFISICAL_BROKER_ORG` | GitHub organization and Infisical organization slug | Required with broker |
| `INFISICAL_STORE_SCOPE` | Protected broker scope | `shared` |
| `INFISICAL_SSH_PUBLIC_KEY` | Existing Copilot device public key | `~/.ssh/id_ed25519_copilot.pub` |
| `INFISICAL_AUTH_ROOT` | Directory containing the non-secret GitHub identity pointer | `~/.copilot/auth` |
| `INFISICAL_ADMIN_PROJECT` | Project ID holding the ecosystem-admin credentials used for writes | `458e8f7a-3d53-4e72-9d1c-718956463e2f` (copilot-ecosystem) |
| `INFISICAL_ADMIN_ENV` | Environment slug holding those credentials | `prod` |
| `INFISICAL_ADMIN_PATH` | Secret path holding those credentials | `/shared` |

The broker fields are non-secret and normally arrive through the inherited
organization overlay. When a broker URL is configured, the client never reads
or falls back to `INFISICAL_CLIENT_ID`/`INFISICAL_CLIENT_SECRET`. The SSH private
key remains encrypted and agent-backed; the broker receives only a signature.
The resulting Infisical token is cached in a mode-0600 file only within its
server-issued lifetime, which must not exceed 15 minutes. Broker sessions are
read-only in the client as well as in Infisical policy.

## Read and write paths

Reads use the broker path: an interactive session authenticates through the GitHub-authorized broker and receives a short-lived, read-only token. Nothing needs to be configured per session, and `secret list` and `secret get` work immediately.

Writes (`secret set`/`delete`, `folder create`, `project create`/`delete`, `identity create`, `org disable-signup`) are automatic and need no setup. Because a broker session is read-only in the client and in Infisical policy, these commands call `State.get_write_client()`, which reads the ecosystem-admin Universal Auth pair through the read session and logs in with it. The admin client is cached for the process and the credential values are never printed or logged.

The ecosystem-admin pair lives in Infisical, project `copilot-ecosystem` (`458e8f7a-3d53-4e72-9d1c-718956463e2f`), environment `prod`, path `/shared`, as `INFISICAL_ECOSYSTEM_ADMIN_CLIENT_ID` and `INFISICAL_ECOSYSTEM_ADMIN_KEY`. Override the location with `INFISICAL_ADMIN_PROJECT`, `INFISICAL_ADMIN_ENV`, and `INFISICAL_ADMIN_PATH`, or with the same keys in the nearest tier overlay `config:` block as `infisical_admin_project`, `infisical_admin_env`, and `infisical_admin_path`.

An explicit `INFISICAL_CLIENT_ID` and `INFISICAL_CLIENT_SECRET` (environment, `.env`, or Keychain) always wins over the admin lookup for writes. If the admin pair cannot be read, the command fails with a `ConfigError` naming the missing key and location; do not ask the user to re-create it, check the location above first.

## Where other shared secrets live

`OPENROUTER_MGMT_KEY` is an OpenRouter management key: it can administer keys and credits but cannot run inference. `OPENROUTER_STORYBOARD_KEY` is the inference key for the journey-storyboard work, with a $25 spend cap. Both are stored in Infisical and are found by name with `copilot infisical secret list`.

The macOS Keychain is the per-user fallback for secrets that must exist before Infisical is reachable. Service `copilot-cli` holds `OPENROUTER_API_KEY`, and also the bootstrap `INFISICAL_CLIENT_ID`/`INFISICAL_CLIENT_SECRET` pair when a headless actor uses Universal Auth directly. Environment values win over Keychain values.

## Health Check

```bash
copilot health
```

`copilot health` uses the selected authentication mode and confirms an identity
can be resolved. `copilot infisical --json access verify ...` is the stronger
operational proof: it requires one permitted read and one denied path.
