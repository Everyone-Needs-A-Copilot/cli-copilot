# CLI Service Inventory

Complete command tree for all 16 copilot CLI services. Auto-generatable via `copilot <service> --help`.

## git
```
copilot git status [--json]
copilot git add --path <path>
copilot git commit --message <msg>
copilot git pull [--json]
copilot git clone --url <url> [--json]
copilot git health [--json]
```

## docker
```
copilot docker ps [--json]
copilot docker info [--json]
copilot docker start --name <name> [--json]
copilot docker stop --name <name> [--json]
copilot docker restart --name <name> [--json]
copilot docker health [--json]
```

## shell
```
copilot shell exec --command <cmd> [--json]
copilot shell run --name <script> [--json]
copilot shell find [--json]
copilot shell ps [--json]
copilot shell health [--json]
```

## fs (filesystem)
```
copilot fs read --path <path> [--json]
copilot fs write --path <path> --content <content> [--json]
copilot fs delete --path <path> [--json]
copilot fs cp --source <src> --destination <dst> [--json]
copilot fs mv --source <src> --destination <dst> [--json]
copilot fs ls --path <path> [--json]
copilot fs mkdir --path <path> [--json]
copilot fs search --pattern <pattern> [--path <path>] [--json]
copilot fs health [--json]
```

## services (system services)
```
copilot services list [--json]
copilot services start --name <name> [--json]
copilot services stop --name <name> [--json]
copilot services load --path <plist> [--json]
copilot services unload --path <plist> [--json]
copilot services processes [--json]
copilot services health [--json]
```

## db (PostgreSQL)
```
copilot db health [--json]
copilot db stats [--json]
copilot db tables --database <name> [--json]
copilot db columns --database <name> --table <tbl> [--json]
copilot db relationships --database <name> --table <tbl> [--json]
copilot db schema --database <name> [--json]
copilot db query --database <name> --sql <sql> [--json]
copilot db explain --database <name> --sql <sql> [--json]
copilot db backup --database <name> [--table <tbl>] [--json]
copilot db vacuum --database <name> [--table <tbl>] [--json]
```

## crm (NocoDB)
```
copilot crm health [--json]
copilot crm clients list [--json]
copilot crm clients get --id <id> [--json]
copilot crm clients create --name <name> --email <email> --company <company> [--json]
copilot crm clients update --id <id> --data <json> [--json]
copilot crm leads list [--json]
copilot crm leads create --name <name> --email <email> --company <company> --source <src> [--json]
copilot crm leads convert --id <id> [--json]
copilot crm projects list [--json]
copilot crm projects create --name <name> --client-id <id> [--json]
copilot crm tables list [--json]
copilot crm bases list [--json]
```

## brevo
```
copilot brevo health [--json]
copilot brevo contacts list [--json]
copilot brevo contacts get --email <email> [--json]
copilot brevo contacts create --email <email> --first-name <first> --last-name <last> [--json]
copilot brevo contacts update --email <email> --attributes <json> [--json]
copilot brevo lists list [--json]
copilot brevo campaigns list [--json]
copilot brevo campaigns stats --campaign-id <id> [--json]
copilot brevo templates list [--json]
copilot brevo send --to <email> --subject <subj> --template-id <id> [--json]
```

## n8n
```
copilot n8n health [--json]
copilot n8n workflows list [--json]
copilot n8n workflows get --id <id> [--json]
copilot n8n workflows create --name <name> [--json]
copilot n8n workflows activate --id <id> [--json]
copilot n8n workflows deactivate --id <id> [--json]
copilot n8n workflows delete --id <id> [--json]
copilot n8n executions list [--json]
copilot n8n executions get --id <id> [--json]
```

## docs (documents)
```
copilot docs health [--json]
copilot docs search --query <query> [--json]
copilot docs get --id <id> [--json]
copilot docs create --title <title> --content <content> [--json]
copilot docs update --id <id> --content <content> [--json]
copilot docs delete --id <id> [--json]
copilot docs stats [--json]
```

## bi (business intelligence)
```
copilot bi health [--json]
copilot bi analyze --file <path> [--json]
copilot bi patterns --file <path> [--json]
copilot bi kpis --file <path> [--json]
copilot bi summary --file <path> [--json]
```

## monitoring
```
copilot monitoring health [--json]
copilot monitoring status [--json]
copilot monitoring alerts [--json]
```

## coolify
```
copilot coolify server healthcheck [--json]
copilot coolify app list [--json]
copilot coolify app get --uuid <uuid> [--json]
copilot coolify app restart --uuid <uuid> [--json]
copilot coolify db list [--json]
copilot coolify svc list [--json]
copilot coolify svc restart --uuid <uuid> [--json]
copilot coolify deploy list [--json]
copilot coolify deploy get --deployment-id <id> [--json]
copilot coolify deploy trigger --app-uuid <uuid> [--json]
copilot coolify deploy rollback --app-uuid <uuid> [--json]
copilot coolify deploy logs --deployment-id <id>
copilot coolify envvar list --resource-uuid <uuid> [--json]
copilot coolify envvar set --resource-uuid <uuid> --key <key> --value <val>
copilot coolify backup list [--json]
copilot coolify backup create [--json]
copilot coolify backup restore --id <id> [--json]
copilot coolify key list [--json]
copilot coolify key create [--json]
copilot coolify monitor dashboard [--json]
```

## insights
```
copilot insights health [--json]
copilot insights version [--json]
copilot insights dashboard summary [--json]
copilot insights dashboard signals [--json]
copilot insights dashboard activity [--json]
copilot insights dashboard latest-report [--json]
copilot insights forces list [--json]
copilot insights forces get --id <id> [--json]
copilot insights forces stats [--json]
copilot insights articles list [--json]
copilot insights articles get --id <id> [--json]
copilot insights articles stats [--json]
copilot insights articles similar --id <id> [--json]
copilot insights articles generate-intel --id <id> [--json]
copilot insights reports from-existing [--json]
copilot insights reports topical --topic <topic> [--json]
copilot insights reports from-scan [--json]
copilot insights reports article-centric --article-id <id> [--json]
copilot insights dossiers list [--json]
copilot insights dossiers get --id <id> [--json]
copilot insights dossiers create --company <name> [--json]
copilot insights dossiers enrich --id <id> [--json]
copilot insights prospects priority [--json]
copilot insights synthesis run [--json]
copilot insights synthesis forces [--json]
copilot insights synthesis correlations [--json]
copilot insights synthesis patterns [--json]
copilot insights synthesis status [--json]
copilot insights monitoring cost-summary [--json]
copilot insights monitoring cost-by-provider [--json]
copilot insights monitoring cost-trend [--json]
copilot insights monitoring performance [--json]
```

## project (Project Copilot)
```
copilot project health [--json]
copilot project identity [--json]
copilot project tasks list [--status <status>] [--json]
copilot project tasks ready [--json]
copilot project tasks claim --id <id> [--json]
copilot project tasks complete --id <id> [--json]
copilot project tasks evidence --id <id> [--json]
copilot project tasks review-pipeline --id <id> [--json]
copilot project tasks log [--json]
copilot project board screenshot
copilot project keys list [--json]
copilot project settings [--json]
copilot project verify [--json]
```

## conv (Conversations Copilot)
```
copilot conv auth me [--json]
copilot conv auth login [--json]
copilot conv auth refresh
copilot conv health [--json]
copilot conv people list [--json]
copilot conv people get --id <id> [--json]
copilot conv people personality --id <id> [--json]
copilot conv companies list [--json]
copilot conv companies get --id <id> [--json]
copilot conv conversations list [--json]
copilot conv conversations get --id <id> [--json]
copilot conv conversations create --title <title> [--json]
copilot conv conversations capture --id <id> [--json]
copilot conv conversations review --id <id> [--json]
copilot conv conversations signal --id <id> [--json]
copilot conv forces list [--json]
copilot conv forces get --id <id> [--json]
copilot conv forces validate --id <id> [--json]
copilot conv deals list [--json]
copilot conv deals get --id <id> [--json]
copilot conv deals update --id <id> --status <status> [--json]
copilot conv followups list [--json]
copilot conv intel search --query <query> [--json]
copilot conv intel health-person --person-id <id> [--json]
copilot conv intel energy-person --person-id <id> [--json]
copilot conv intel infer-personality --person-id <id> [--json]
copilot conv intel enrich-company --company-id <id> [--json]
copilot conv coach config [--json]
copilot conv coach personas [--json]
copilot conv coach skills [--json]
copilot conv coach feedback-list [--json]
copilot conv coach feedback-create --conversation-id <id> [--json]
copilot conv transcripts upload --conversation-id <id> --file <path> [--json]
copilot conv calendar events [--json]
copilot conv questions list [--json]
```

## Quick Reference: 16 Services by Category

| Category | Services |
|----------|----------|
| **Infrastructure** | coolify, docker, monitoring, services |
| **Data** | db (PostgreSQL), crm (NocoDB), bi |
| **Communication** | brevo, docs |
| **Intelligence** | insights, conv (Conversations) |
| **Automation** | n8n, shell |
| **Development** | git, fs |
| **Orchestration** | project (Project Copilot) |
