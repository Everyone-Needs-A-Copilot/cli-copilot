---
title: Brevo (Email Marketing) CLI
category: service-reference
last-updated: 2026-02-21
---

# Brevo (Email Marketing) CLI

**Command:** `copilot brevo`
**Source:** `copilot_cli/services/brevo/`

## Purpose

Brevo email marketing — contacts, lists, campaigns, templates, and transactional email.

## Commands

| Subgroup | Command | Description | Key Options |
|----------|---------|-------------|-------------|
| `brevo contacts` | `list` | List contacts | `--limit`, `--offset` |
| `brevo contacts` | `get` | Get contact by ID | `ID` |
| `brevo contacts` | `create` | Create a contact | `--email`, `--attributes` |
| `brevo contacts` | `update` | Update a contact | `ID`, `--attributes` |
| `brevo contacts` | `delete` | Delete a contact | `ID` |
| `brevo lists` | `list` | List contact lists | — |
| `brevo lists` | `create` | Create a list | `--name` |
| `brevo campaigns` | `list` | List campaigns | — |
| `brevo campaigns` | `create` | Create a campaign | `--name`, `--subject` |
| `brevo campaigns` | `send` | Send a campaign | `ID` |
| `brevo campaigns` | `stats` | Campaign statistics | `ID` |
| `brevo templates` | `list` | List email templates | — |
| `brevo templates` | `create` | Create a template | `--name`, `--content` |
| `brevo send` | — | Send transactional email | `--to`, `--subject`, `--content` |

## Examples

```bash
copilot brevo contacts list --limit 100
copilot brevo contacts create --email "user@example.com"
copilot brevo campaigns list
copilot brevo campaigns stats 42
copilot brevo templates list
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BREVO_API_KEY` | Brevo API key (supports base64-wrapped) | Required |

## Health Check

```bash
copilot brevo health
```

Checks: Pings the Brevo API to verify connectivity and authentication.
