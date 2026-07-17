---
title: PostgreSQL CLI
category: service-reference
last-updated: 2026-02-21
---

# PostgreSQL CLI

**Command:** `copilot db`
**Source:** `copilot_cli/services/postgresql/`

## Purpose

Multi-database PostgreSQL operations with connection pooling. Supports 4 named databases: main, nocodb, n8n, formbricks.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `db query` | Execute SQL query | `DATABASE`, `SQL` |
| `db tables` | List tables | `DATABASE`, `--schema` |
| `db columns` | Show table columns | `DATABASE`, `TABLE` |
| `db relationships` | Show table relationships | `DATABASE`, `TABLE` |
| `db schema` | Dump full schema | `DATABASE` |
| `db explain` | Explain query plan | `DATABASE`, `SQL` |
| `db stats` | Show database statistics | `DATABASE` |
| `db backup` | Backup a table | `DATABASE`, `TABLE` |
| `db vacuum` | Vacuum a table | `DATABASE`, `TABLE` |
| `db health` | Test all database connections | — |

## Examples

```bash
copilot db query nocodb "SELECT * FROM clients LIMIT 10"
copilot db tables n8n
copilot db columns nocodb clients
copilot db schema nocodb
copilot db explain n8n "SELECT * FROM workflow_entity"
copilot db health
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Main database connection URL | Required |
| `NOCODB_DATABASE_URL` | NocoDB database URL | Optional |
| `N8N_DATABASE_URL` | n8n database URL | Optional |
| `FORMBRICKS_DATABASE_URL` | Formbricks database URL | Optional |

## Health Check

```bash
copilot db health
```

Checks: Tests connection to each configured database and reports status.

---

## Database Transfers

### Destructive-operations policy

Destructive SQL (DROP / TRUNCATE / DELETE FROM / ALTER … DROP) is **never allowed on remote or tunneled-remote databases**. On a local database these operations require an explicit per-call confirmation token that equals the database's short-name.

Rationale: this tool is not authorised to delete production data. Destructive operations on remote databases are refused unconditionally at the client layer, regardless of credentials or flags.

The same policy applies to `copilot coolify db delete` and `copilot coolify backup delete` — both are hard-blocked with a refusal message.

### What counts as "local"

The connection URL host must be `localhost` or `127.0.0.1` for a database to be treated as local. Any other host — including a Coolify-managed DB URL or a tunneled URL — is treated as remote and writes are refused.

### Backup directory

Dump files are written to `BACKUP_DIR` (`.env` setting). Default: `~/copilot-backups`. The directory is created automatically on first use.

### Configuring local databases

Local databases are resolved by their short-name from `*_DATABASE_URL` env vars in `.env`:

| Short-name | Env var |
|-----------|---------|
| `main` (or bare `DATABASE_URL`) | `DATABASE_URL` |
| `nocodb` | `NOCODB_DATABASE_URL` |
| `n8n` | `N8N_DATABASE_URL` |
| `formbricks` | `FORMBRICKS_DATABASE_URL` |

Any URL whose host is not `localhost` / `127.0.0.1` is rejected as a restore or transition target.

### Commands

| Command | Description | Key options |
|---------|-------------|-------------|
| `db dump <coolify-name>` | Stream pg_dump of a remote Coolify-managed DB to a local file | `--out PATH`, `--schema-only`, `--data-only`, `--table T`, `--format custom\|plain` |
| `db restore <dump-file>` | Restore a dump to a LOCAL database | `--to <local-name>`, `--clean`, `--confirm-token TOKEN` |
| `db pull <coolify-name>` | Dump remote, restore to local (convenience wrapper) | `--to <local-name>`, `--keep-dump`, `--clean/--no-clean`, `--confirm-token TOKEN` |
| `db transition <source> <target>` | Copy source DB into target; source can be a Coolify name or local short-name, target must be local | same options as `db pull` |
| `db remote-query <coolify-name> <sql>` | Open SSH tunnel, run query, tear down; destructive SQL refused | — |
| `db query <local-name> <sql>` | Query a local database; destructive SQL requires `--confirm-token` | `--confirm-token TOKEN` |

The `db dump` SSH command runs `docker exec <uuid> pg_dump …` on the VPS so the pg_dump binary version always matches the server's Postgres version.

### Worked examples

#### Dump a remote database to a local file

```bash
copilot db dump "app-db" --out ~/backups/app-db.dump
# Output: ~/backups/app-db.dump (custom format by default)

# Schema only, plain text
copilot db dump "app-db" --out ~/backups/app-db.sql --schema-only --format plain

# Single table, custom format
copilot db dump "app-db" --out ~/backups/orders.dump --table orders
```

#### Pull a remote database into a local dev database

Assumes `DATABASE_URL=postgresql://you@localhost:5432/dev` (or whichever `*_DATABASE_URL` maps to your local DB short-name) is set in `.env` and the target database already exists locally.

Interactive prompt (omit `--confirm-token`):

```bash
copilot db pull "app-db" --to dev
# Confirm destructive restore to database 'dev'? Type 'dev' to confirm: dev
# Pulling app-db → dev …
```

Non-interactive (CI or scripted):

```bash
copilot db pull "app-db" --to dev --confirm-token dev
```

Keep the intermediate dump file after the restore:

```bash
copilot db pull "app-db" --to dev --keep-dump --confirm-token dev
```

#### Copy one local database into another (transition)

```bash
copilot db transition staging dev --confirm-token dev
```

`source` can also be a Coolify name (remote → local):

```bash
copilot db transition "app-db" dev --confirm-token dev
```

#### Run a read-only query against a remote database

```bash
copilot db remote-query "app-db" "SELECT count(*) FROM orders"
#  count
# -------
#  4820
```

Attempting a destructive statement is refused:

```bash
copilot db remote-query "app-db" "DROP TABLE orders"
# Error: destructive SQL (DROP) is not permitted on remote or tunneled databases.
```

#### Query a local database (with destructive-op guard)

```bash
# Read-only — no token needed
copilot db query dev "SELECT count(*) FROM users"

# Destructive — token must match database short-name
copilot db query dev "DELETE FROM sessions WHERE expired = true" --confirm-token dev
```
