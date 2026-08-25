---
name: client-onboarding
description: >-
  Set up a new client across all copilot-managed systems — CRM, Project Copilot,
  Conversations Copilot, and Brevo.
  Use when onboarding a new client after lead conversion or contract signing.
triggers:
  keywords: ["onboard", "onboarding", "new client", "client setup", "welcome",
             "account setup", "kickoff", "client creation", "contract signed"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  params:
    - name: name
      type: string
      required: true
      description: Client full name
    - name: email
      type: string
      required: true
      description: Client email address
    - name: company
      type: string
      required: true
      description: Client company name
  steps:
    - name: onboard-client
      script: scripts/onboard.sh
      args:
        - "{{ params.name }}"
        - "{{ params.email }}"
        - "{{ params.company }}"
      description: Create records in CRM, Conversations, Brevo, then verify all systems
  verify:
    - name: crm-healthy
      command: copilot crm health --json
      expect: 'exit_code == 0'
    - name: brevo-healthy
      command: copilot brevo health --json
      expect: 'exit_code == 0'
    - name: conv-healthy
      command: copilot conv health --json
      expect: 'exit_code == 0'
---

# Client Onboarding

## Overview

Set up a new client across all business systems after lead conversion or contract signing. Creates records in CRM, Project Copilot, Conversations Copilot, and Brevo — ensuring the client exists everywhere before the engagement begins.

## Define Done

Client onboarding is complete when:

- [ ] Client record active in CRM (NocoDB)
- [ ] Person and company exist in Conversations Copilot
- [ ] Contact active in Brevo with correct list membership
- [ ] Welcome email sent successfully
- [ ] Cross-system verification passes (all systems have matching client data)

## Prerequisites

- Client information (name, email, company, engagement type)
- Lead converted in CRM (via `lead-pipeline` skill) or contract signed
- All services healthy: `copilot crm health --json && copilot project health --json`

Required environment variables:
| Variable | Service | Purpose |
|----------|---------|---------|
| `NOCODB_URL`, `NOCODB_API_KEY`, `NOCODB_BASE_ID` | CRM | Client records |
| `PROJECT_COPILOT_BASE_URL`, `PROJECT_COPILOT_API_KEY` | Project | Task management |
| `CONVERSATIONS_BASE_URL`, `CONVERSATIONS_API_TOKEN` | Conversations | Relationship tracking |
| `BREVO_API_KEY` | Brevo | Email communications |

## Instructions

### Step 1: Create/Verify CRM Record (REQUIRED)

```bash
# Check if client already exists (from lead conversion)
copilot crm clients list --json
# → Search for matching name/company

# If not exists, create client record
copilot crm clients create \
  --name "Client Name" \
  --email "client@company.com" \
  --company "Company Name" \
  --json
# → {"id": "client-123", ...}

# Create project record linked to client
copilot crm projects create \
  --name "Engagement Name" \
  --client-id "$CLIENT_ID" \
  --json
```

### Step 2: Set Up Client Workspace (REQUIRED)

> Note: Notion was retired 2026-06-29; this step needs a replacement (TBD by owner).

### Step 3: Set Up in Conversations Copilot (REQUIRED)

```bash
# Check if person/company exists
copilot conv people list --json
copilot conv companies list --json

# Create initial conversation record (kickoff meeting)
copilot conv conversations create \
  --title "Kickoff: Company Name" \
  --json

# Run personality inference if data available
copilot conv intel infer-personality --person-id "$PERSON_ID" --json

# Run company enrichment
copilot conv intel enrich-company --company-id "$COMPANY_ID" --json
```

### Step 4: Set Up Email Communication (REQUIRED)

```bash
# Ensure contact exists in Brevo
copilot brevo contacts create \
  --email "client@company.com" \
  --first-name "First" \
  --last-name "Last" \
  --json

# Add to client contact list
copilot brevo contacts update \
  --email "client@company.com" \
  --attributes '{"LISTS": [client_list_id], "CLIENT_STATUS": "active"}' \
  --json

# Send welcome email
copilot brevo send \
  --to "client@company.com" \
  --subject "Welcome to Everyone Needs a Copilot" \
  --template-id "$WELCOME_TEMPLATE_ID" \
  --json
```

### Step 5: Create Project Tasks (OPTIONAL)

```bash
# List onboarding task templates (if they exist as READY tasks)
copilot project tasks list --status "READY" --json

# Verify project is set up
copilot project health --json
copilot project identity --json
```

### Step 6: Verify Complete Setup (REQUIRED)

Run a cross-system verification:

```bash
# CRM
copilot crm clients get --id "$CLIENT_ID" --json

# Conversations
copilot conv people get --id "$PERSON_ID" --json

# Brevo
copilot brevo contacts get --email "client@company.com" --json

# All healthy
copilot health --json
```

## Examples

### Example: Onboard After Forces Assessment Conversion

```bash
# 1. Lead was converted (from lead-pipeline skill)
copilot crm clients get --id "client-456" --json
# → {"name": "Sarah Chen", "company": "TechCorp", "status": "active"}

# 2. Set up in Conversations
copilot conv conversations create \
  --title "Kickoff: TechCorp Strategic Transformation" \
  --json

copilot conv intel enrich-company --company-id "techcorp-id" --json

# 3. Welcome email
copilot brevo send \
  --to "sarah@techcorp.com" \
  --subject "Welcome to Everyone Needs a Copilot" \
  --template-id 15 \
  --json

# 4. Verify
copilot crm clients get --id "client-456" --json
copilot conv people get --id "sarah-id" --json
# → Both show active client
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | Missing service credentials | Check `.env` for the specific service |
| `ValidationError` | Duplicate client in CRM | Search first: `copilot crm clients list --json` |
| `AuthError` | 401 from any service | Re-verify API keys for that service |
| `ConnectionError` | Service unreachable | Run `copilot health --json`, fix infrastructure first |

## Quality Tests

### Cross-System Consistency Test
- Client data matches across all 4 systems
- **PASS:** Name, email, and company identical in CRM, Conversations, and Brevo
- **FAIL:** Different email address or misspelled name across systems

### Rollback Test
- If any system fails mid-onboarding, partial records can be identified and cleaned up
- **PASS:** Each step logs the created record ID, allowing cleanup of partial onboarding
- **FAIL:** Onboarding fails at Step 3 but Steps 1-2 left orphaned records with no cleanup path

### Welcome Email Test
- Welcome email only sent after all systems are set up
- **PASS:** Brevo send command runs after all other steps verify
- **FAIL:** Welcome email sent before Conv records exist

### No-Duplicate Test
- Existing records found and reused instead of creating duplicates
- **PASS:** `copilot crm clients list --json` checked before creating; existing record updated
- **FAIL:** Second client record created for same person/company

## Guidelines

1. Always create CRM record first — it's the authoritative client record
2. Check for existing records before creating — avoid duplicates
3. Run company enrichment in Conversations early — it informs all other setup
4. Send welcome email only after all systems are set up
5. Verify across all systems at the end — catch partial setup failures
6. This skill runs after `lead-pipeline` conversion — don't duplicate lead steps

## References

- Related skills: `lead-pipeline`, `conversation-prep`, `intelligence-brief`
- CRM docs: `docs/services/07-nocodb.md`
- Conversations docs: `docs/services/18-conversations.md`
