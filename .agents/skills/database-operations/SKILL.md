---
name: database-operations
description: >-
  Common database maintenance tasks via copilot CLI — PostgreSQL queries, schema inspection,
  backups, vacuum, and scheduled jobs via n8n.
  Use when managing databases, running queries, inspecting schemas, or setting up maintenance jobs.
triggers:
  keywords: ["database", "postgresql", "postgres", "sql", "query", "schema", "backup",
             "vacuum", "tables", "columns", "migration", "db maintenance", "copilot db"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  params:
    - name: database
      type: string
      required: false
      default: all
      description: "Target database (main, nocodb, n8n, formbricks) or 'all'"
  steps:
    - name: maintenance
      script: scripts/maintenance.sh
      args:
        - "{{ params.database }}"
      description: Health check, vacuum, and post-maintenance stats for target database(s)
  verify:
    - name: db-healthy
      command: copilot db health --json
      expect: 'exit_code == 0'
---

# Database Operations

## Overview

Manage all PostgreSQL databases through the copilot CLI — run queries, inspect schemas, perform backups, optimize tables, and set up automated maintenance via n8n workflows. The CLI manages 4 named databases: main, nocodb, n8n, formbricks.

## Define Done

A database operation is complete when:

- [ ] Target database healthy and reachable (`copilot db health --json`)
- [ ] Operation completed successfully (query returned results, vacuum ran, backup saved)
- [ ] Database stats verified post-operation (`copilot db stats --json`)
- [ ] No connection pool exhaustion or lock contention

## Prerequisites

- At least one `*_DATABASE_URL` configured in `.env`
- Verify connectivity: `copilot db health --json`

Required environment variables:
| Variable | Database | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | main | Primary application database |
| `NOCODB_DATABASE_URL` | nocodb | CRM/NocoDB backend |
| `N8N_DATABASE_URL` | n8n | Workflow automation backend |
| `FORMBRICKS_DATABASE_URL` | formbricks | Survey/assessment backend |

## Instructions

### Step 1: Check Database Health (REQUIRED)

```bash
# Health check all configured databases
copilot db health --json

# Connection pool statistics (look for exhaustion)
copilot db stats --json
```

### Step 2: Explore Schema (OPTIONAL)

```bash
# List all tables in a database
copilot db tables --database nocodb --json

# List columns for a specific table
copilot db columns --database nocodb --table "clients" --json

# Show foreign key relationships
copilot db relationships --database nocodb --table "clients" --json

# Full schema introspection
copilot db schema --database nocodb --json
```

**Database routing:**

| Task | Database |
|------|----------|
| CRM data (clients, leads, projects) | `nocodb` |
| Workflow execution history | `n8n` |
| Survey/assessment results | `formbricks` |
| Application data | `main` |

### Step 3: Run Queries (REQUIRED)

```bash
# Execute a read query
copilot db query --database nocodb --sql "SELECT * FROM clients LIMIT 10" --json

# Check query performance
copilot db explain --database nocodb --sql "SELECT * FROM clients WHERE status = 'active'" --json
```

### Step 4: Backup Data (OPTIONAL)

```bash
# Backup a table as JSON
copilot db backup --database nocodb --table "clients" --json

# Backup multiple tables
copilot db backup --database nocodb --table "clients" --json
copilot db backup --database nocodb --table "projects" --json
copilot db backup --database nocodb --table "leads" --json
```

### Step 5: Optimize Tables (OPTIONAL)

```bash
# Vacuum and analyze a specific table
copilot db vacuum --database nocodb --table "clients" --json

# Vacuum entire database
copilot db vacuum --database nocodb --json
```

### Step 6: Set Up Automated Maintenance via n8n (OPTIONAL)

```bash
# List existing n8n workflows (look for backup/maintenance jobs)
copilot n8n workflows list --json

# Check recent executions of maintenance workflows
copilot n8n executions list --json
```

## Examples

### Example: Investigate Slow Queries

```bash
# 1. Check connection pool health
copilot db stats --json
# → Look for high active connections

# 2. Explain the slow query
copilot db explain --database nocodb --sql "SELECT c.*, p.* FROM clients c JOIN projects p ON c.id = p.client_id WHERE c.status = 'active'" --json
# → Shows execution plan, look for sequential scans

# 3. Check table sizes
copilot db query --database nocodb --sql "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC" --json
```

### Example: Pre-Migration Schema Audit

```bash
# 1. Full schema of target database
copilot db schema --database nocodb --json

# 2. Check specific table structure
copilot db columns --database nocodb --table "clients" --json

# 3. Understand relationships before altering
copilot db relationships --database nocodb --table "clients" --json

# 4. Backup table before migration
copilot db backup --database nocodb --table "clients" --json
```

### Example: Database Maintenance Routine

```bash
# 1. Health check
copilot db health --json

# 2. Vacuum all databases
copilot db vacuum --database nocodb --json
copilot db vacuum --database n8n --json
copilot db vacuum --database formbricks --json

# 3. Check stats after vacuum
copilot db stats --json
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing DATABASE_URL" | Add connection string to `.env` |
| `ConnectionError` | "Cannot reach database" | Check Docker: `copilot docker ps --json`, look for postgres container |
| `AuthError` | "Authentication failed" | Verify credentials in connection string |
| `TimeoutError` | Query hangs | Check for locks: `copilot db query --database <name> --sql "SELECT * FROM pg_locks WHERE NOT granted"` |
| `ValidationError` | "Invalid SQL" | Check query syntax |

## Quality Tests

### Backup Integrity Test
- Before any destructive operation, a backup exists for affected tables
- **PASS:** `copilot db backup --database <name> --table <tbl> --json` succeeds before running DDL
- **FAIL:** Running ALTER/DROP without a backup of the affected table

### Vacuum Effectiveness Test
- After vacuum, dead tuple count decreases
- **PASS:** `copilot db stats --json` shows reduced dead tuples compared to pre-vacuum
- **FAIL:** Dead tuple count unchanged — vacuum may have been blocked by open transactions

### Connection Safety Test
- Operations don't exhaust the connection pool
- **PASS:** `copilot db stats --json` shows active connections < 80% of max
- **FAIL:** Active connections near max after running queries — connection leak possible

### Query Safety Test
- Expensive queries are explained before execution
- **PASS:** `copilot db explain` run before any query on tables with > 100K rows
- **FAIL:** Running a full table scan on a large table without checking the plan first

## Guidelines

1. Always use `--database <name>` to target the correct database
2. Use `--json` for all queries when parsing output programmatically
3. Run `copilot db explain` before executing expensive queries
4. Backup tables before schema changes or bulk updates
5. Run `copilot db vacuum` after large deletes or updates
6. Never run DDL (CREATE/ALTER/DROP) without backing up first

## References

- Related skills: `infrastructure-health`, `troubleshoot-service`
- Database config: `copilot_cli/config/settings.py` (get_database_configs)
- PostgreSQL docs: `docs/services/06-postgresql.md`
