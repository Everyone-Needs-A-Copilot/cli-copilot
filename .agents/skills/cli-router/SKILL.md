---
name: cli-router
description: >-
  Master routing table for the copilot CLI — maps business tasks to the right services
  and commands across all 16 services. Use as the first skill when unsure which copilot
  service handles a given task.
triggers:
  keywords: ["which command", "how to", "copilot", "which service", "route", "find command",
             "cli help", "what command", "where to", "copilot command"]
allowed-tools: Read, Bash, Grep, Glob
---

# CLI Router

## Overview

The copilot CLI has 16 services with 250+ commands. This skill is the master routing table — given a business task, it tells you which service and command to use. Load this skill first when you don't know which service handles your task.

## Define Done

Routing is complete when:

- [ ] Correct service identified for the user's task
- [ ] Specific command identified (not just the service)
- [ ] Downstream skill identified for full workflow execution (if applicable)
- [ ] Command verified to exist via `copilot <service> --help`

## Instructions

Use the Service Map and Task Routing Table below to identify the correct service, command, and downstream skill for any task.

### Service Map

| Service | CLI Name | Purpose |
|---------|----------|---------|
| Git | `copilot git` | Repository operations (clone, pull, status, add, commit) |
| Docker | `copilot docker` | Container management (ps, start, stop, restart, info) |
| Shell | `copilot shell` | Command execution (exec, run scripts, find scripts, ps) |
| Filesystem | `copilot fs` | File operations (read, write, delete, cp, mv, ls, mkdir, search) |
| System Services | `copilot services` | launchctl management (list, start, stop, load, unload, processes) |
| PostgreSQL | `copilot db` | Database operations (query, tables, schema, backup, vacuum) |
| NocoDB (CRM) | `copilot crm` | CRM operations (clients, leads, projects, tables, bases) |
| Brevo | `copilot brevo` | Email marketing (contacts, lists, campaigns, templates, send) |
| n8n | `copilot n8n` | Workflow automation (workflows, executions) |
| Documents | `copilot docs` | Document management (search, get, create, update, delete, stats) |
| BI | `copilot bi` | Business intelligence (analyze, patterns, kpis, summary) |
| Monitoring | `copilot monitoring` | System monitoring (status, alerts) |
| Coolify | `copilot coolify` | Infrastructure management (server, app, db, deploy, env, backup) |
| Insights | `copilot insights` | Strategic intelligence (dashboard, forces, articles, reports, dossiers, synthesis) |
| Project Copilot | `copilot project` | Task orchestration (tasks, verify, board, keys, settings) |
| Conversations | `copilot conv` | Relationship management (people, companies, forces, deals, conversations, coach, intel) |

### Task Routing Table

### Infrastructure & Operations

| Task | Command | Skill |
|------|---------|-------|
| Check all services | `copilot health --json` | `infrastructure-health` |
| System CPU/memory/disk | `copilot monitoring status --json` | `infrastructure-health` |
| Active resource alerts | `copilot monitoring alerts --json` | `infrastructure-health` |
| List containers | `copilot docker ps --json` | `infrastructure-health` |
| Restart container | `copilot docker restart --name <name>` | `deploy-product` |
| Server health | `copilot coolify server healthcheck --json` | `infrastructure-health` |
| List Coolify apps | `copilot coolify app list --json` | `deploy-product` |
| Deploy an app | `copilot coolify deploy trigger --app-uuid <uuid> --json` | `deploy-product` |
| Rollback deployment | `copilot coolify deploy rollback --app-uuid <uuid> --json` | `deploy-product` |
| Set env vars | `copilot coolify envvar set --resource-uuid <uuid> --key K --value V` | `deploy-product` |
| View deploy logs | `copilot coolify deploy logs --deployment-id <id>` | `deploy-product` |
| Manage backups | `copilot coolify backup list/create/restore --json` | `deploy-product` |

### Database

| Task | Command | Skill |
|------|---------|-------|
| Check DB connections | `copilot db health --json` | `database-operations` |
| Run SQL query | `copilot db query --database <name> --sql "..." --json` | `database-operations` |
| List tables | `copilot db tables --database <name> --json` | `database-operations` |
| Inspect columns | `copilot db columns --database <name> --table <tbl> --json` | `database-operations` |
| Show relationships | `copilot db relationships --database <name> --table <tbl> --json` | `database-operations` |
| Full schema | `copilot db schema --database <name> --json` | `database-operations` |
| Query plan | `copilot db explain --database <name> --sql "..." --json` | `database-operations` |
| Backup table | `copilot db backup --database <name> --table <tbl> --json` | `database-operations` |
| Optimize | `copilot db vacuum --database <name> --json` | `database-operations` |

### CRM & Sales

| Task | Command | Skill |
|------|---------|-------|
| List clients | `copilot crm clients list --json` | `lead-pipeline` |
| Get client | `copilot crm clients get --id <id> --json` | `lead-pipeline` |
| Create client | `copilot crm clients create --json` | `client-onboarding` |
| Create lead | `copilot crm leads create --json` | `lead-pipeline` |
| Convert lead | `copilot crm leads convert --id <id> --json` | `lead-pipeline` |
| List projects | `copilot crm projects list --json` | `lead-pipeline` |

### Email & Marketing

| Task | Command | Skill |
|------|---------|-------|
| Send email | `copilot brevo send --to <email> --subject "..." --json` | `lead-pipeline` |
| List contacts | `copilot brevo contacts list --json` | `lead-pipeline` |
| Create contact | `copilot brevo contacts create --json` | `lead-pipeline` |
| Campaign stats | `copilot brevo campaigns stats --campaign-id <id> --json` | `intelligence-brief` |
| List templates | `copilot brevo templates list --json` | `lead-pipeline` |

### Strategic Intelligence

| Task | Command | Skill |
|------|---------|-------|
| Dashboard overview | `copilot insights dashboard summary --json` | `intelligence-brief` |
| Strategic signals | `copilot insights dashboard signals --json` | `intelligence-brief` |
| List forces | `copilot insights forces list --json` | `intelligence-brief` |
| List articles | `copilot insights articles list --json` | `intelligence-brief` |
| Generate report | `copilot insights reports from-existing --json` | `intelligence-brief` |
| Run synthesis | `copilot insights synthesis run --json` | `intelligence-brief` |
| Company dossier | `copilot insights dossiers get --id <id> --json` | `intelligence-brief` |
| Prospect priorities | `copilot insights prospects priority --json` | `intelligence-brief` |
| LLM costs | `copilot insights monitoring cost-summary --json` | `intelligence-brief` |

### Relationship Management

| Task | Command | Skill |
|------|---------|-------|
| List people | `copilot conv people list --json` | `conversation-prep` |
| Personality profile | `copilot conv people personality --id <id> --json` | `conversation-prep` |
| List conversations | `copilot conv conversations list --json` | `conversation-prep` |
| Create conversation | `copilot conv conversations create --json` | `conversation-prep` |
| Capture conversation | `copilot conv conversations capture --id <id> --json` | `conversation-prep` |
| Relationship forces | `copilot conv forces list --json` | `conversation-prep` |
| Deal status | `copilot conv deals list --json` | `conversation-prep` |
| Follow-ups | `copilot conv followups list --json` | `conversation-prep` |
| Global search | `copilot conv intel search --query "..." --json` | `conversation-prep` |
| Relationship health | `copilot conv intel health-person --person-id <id> --json` | `conversation-prep` |
| Calendar events | `copilot conv calendar events --json` | `conversation-prep` |
| Coaching feedback | `copilot conv coach feedback-list --json` | `conversation-prep` |

### Automation

| Task | Command | Skill |
|------|---------|-------|
| List workflows | `copilot n8n workflows list --json` | `workflow-automation` |
| Get workflow | `copilot n8n workflows get --id <id> --json` | `workflow-automation` |
| Create workflow | `copilot n8n workflows create --json` | `workflow-automation` |
| Activate workflow | `copilot n8n workflows activate --id <id> --json` | `workflow-automation` |
| Execution history | `copilot n8n executions list --json` | `workflow-automation` |
| Run shell command | `copilot shell exec --command "..." --json` | — |
| Run script | `copilot shell run --name <script> --json` | — |

### Analytics

| Task | Command | Skill |
|------|---------|-------|
| Analyze data file | `copilot bi analyze --file <path> --json` | `intelligence-brief` |
| Data KPIs | `copilot bi kpis --file <path> --json` | `intelligence-brief` |

### Project Management

| Task | Command | Skill |
|------|---------|-------|
| Ready tasks | `copilot project tasks ready --json` | — |
| List tasks | `copilot project tasks list --json` | — |
| Claim task | `copilot project tasks claim --id <id> --json` | — |
| Complete task | `copilot project tasks complete --id <id> --json` | — |
| Task evidence | `copilot project tasks evidence --id <id> --json` | — |
| Review pipeline | `copilot project tasks review-pipeline --id <id> --json` | — |
| Board screenshot | `copilot project board screenshot` | — |

### Development

| Task | Command | Skill |
|------|---------|-------|
| Add new service | (scaffold process) | `new-service-scaffold` |
| Debug service error | (diagnostic process) | `troubleshoot-service` |

### Decision Flowchart

```
Task arrives → What domain?
│
├── Infrastructure/Ops → infrastructure-health or deploy-product
├── Database → database-operations
├── Sales/Leads → lead-pipeline
├── New Client → client-onboarding
├── Intelligence/Reports → intelligence-brief
├── Meeting Prep → conversation-prep
├── Automation → workflow-automation
├── Development → new-service-scaffold or troubleshoot-service
└── Unknown → copilot health --json + this routing table
```

## Quality Tests

### Accuracy Test
- Every command listed in the routing table actually exists
- **PASS:** Running `copilot <service> <command> --help` succeeds for every entry
- **FAIL:** A command in the table returns "No such command"

### Completeness Test
- All 16 services are represented in the routing table
- **PASS:** Every service from `copilot --help` has at least one entry in Task Routing Table
- **FAIL:** A service exists in the CLI but has no routing entry

### Disambiguation Test
- When multiple services could handle a task, the routing table picks the right one
- **PASS:** "send email" routes to `copilot brevo send`, not to `copilot shell exec`
- **FAIL:** Ambiguous tasks have no clear recommendation

### Skill Linkage Test
- Every skill referenced in the routing table exists and is discoverable
- **PASS:** `skill_get({ name: "<skill>" })` succeeds for every skill name in the table
- **FAIL:** A skill name in the table doesn't match any actual skill

## Guidelines

1. This skill is for ROUTING only — it tells you which command/skill to load, not how to execute workflows
2. After identifying the right skill, load it for full workflow instructions
3. When multiple services could work, prefer the business-level service over the infrastructure-level one
4. Always use `--json` flag when output will be parsed by an agent
5. `copilot health --json` is always the first command when you're not sure what's wrong

## References

- All skills in this directory: `.Codex/skills/`
- Command registration: `copilot_cli/main.py`
- Full service list: `copilot --help`
