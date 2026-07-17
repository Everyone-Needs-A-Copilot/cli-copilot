---
title: NocoDB (CRM) CLI
category: service-reference
last-updated: 2026-02-21
---

# NocoDB (CRM) CLI

**Command:** `copilot crm`
**Source:** `copilot_cli/services/nocodb/`

## Purpose

NocoDB-backed CRM operations — clients, projects, leads, and table management.

## Commands

| Subgroup | Command | Description | Key Options |
|----------|---------|-------------|-------------|
| `crm clients` | `list` | List all clients | `--limit`, `--offset` |
| `crm clients` | `get` | Get client by ID | `ID` |
| `crm clients` | `create` | Create a client | `--name`, `--email` |
| `crm clients` | `update` | Update a client | `ID`, `--fields` |
| `crm clients` | `delete` | Delete a client | `ID` |
| `crm projects` | `list` | List projects | `--limit` |
| `crm projects` | `get` | Get project by ID | `ID` |
| `crm projects` | `create` | Create a project | `--name` |
| `crm leads` | `create` | Create a lead | `--name`, `--email` |
| `crm leads` | `convert` | Convert lead to client | `ID` |
| `crm tables` | `list` | List all tables | — |
| `crm tables` | `create` | Create a table | `--name` |
| `crm tables` | `delete` | Delete a table | `NAME` |
| `crm bases` | `list` | List all bases | — |

## Examples

```bash
copilot crm clients list --limit 50
copilot crm clients get 123
copilot crm clients create --name "Acme Corp" --email "contact@acme.com"
copilot crm projects list
copilot crm tables list
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `NOCODB_URL` | NocoDB instance URL | Required |
| `NOCODB_API_KEY` | NocoDB API key | Required |
| `NOCODB_BASE_ID` | Default base ID | Required |

## Health Check

```bash
copilot crm health
```

Checks: Pings the NocoDB API to verify connectivity and authentication.
