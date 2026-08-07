---
title: Document CLI
category: service-reference
last-updated: 2026-02-21
---

# Document CLI

**Command:** `copilot docs`
**Source:** `copilot_cli/services/document/`

## Purpose

Local document management — CRUD operations, search, and collection management.

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `docs search` | Search documents | `QUERY` |
| `docs get` | Get document by path | `PATH` |
| `docs create` | Create a document | `PATH`, `CONTENT` |
| `docs update` | Update a document | `PATH`, `CONTENT` |
| `docs delete` | Delete a document | `PATH` |
| `docs collections` | List document collections | `--base-path` |
| `docs stats` | Show document statistics | — |
| `docs health` | Check storage accessibility | — |

## Examples

```bash
copilot docs search "API documentation"
copilot docs get /path/to/document.md
copilot docs create /path/to/new.md "# New Document"
copilot docs collections --base-path /Volumes/Dev/docs
copilot docs stats
```

## Configuration

No external configuration required. Operates on the local filesystem.

## Health Check

```bash
copilot docs health
```

Checks: Verifies document storage paths are accessible.
