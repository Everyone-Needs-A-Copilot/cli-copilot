---
name: lead-pipeline
description: >-
  Manage leads from Forces Assessment through to client conversion via copilot CLI —
  crm (NocoDB), brevo (email), conv (Conversations Copilot).
  Use when processing new leads, nurturing prospects, or converting leads to clients.
triggers:
  keywords: ["lead", "prospect", "pipeline", "conversion", "assessment", "nurture",
             "crm", "brevo", "nocodb", "forces", "sales", "funnel", "inbound", "qualify"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  params:
    - name: name
      type: string
      required: true
      description: Lead full name
    - name: email
      type: string
      required: true
      description: Lead email address
    - name: company
      type: string
      required: true
      description: Lead company name
  steps:
    - name: capture-lead
      script: scripts/capture-lead.sh
      args:
        - "{{ params.name }}"
        - "{{ params.email }}"
        - "{{ params.company }}"
      description: Create CRM lead, search Conversations, create Brevo contact, send initial outreach
  verify:
    - name: crm-healthy
      command: copilot crm health --json
      expect: 'exit_code == 0'
    - name: brevo-healthy
      command: copilot brevo health --json
      expect: 'exit_code == 0'
---

# Lead Pipeline

## Overview

Orchestrate the full lead lifecycle from Forces Assessment submission through nurture to client conversion. Spans CRM (NocoDB) for lead data, Brevo for email communications, and Conversations Copilot for relationship intelligence.

## Define Done

A lead pipeline action is complete when:

- [ ] Lead record exists in CRM with correct status
- [ ] Contact exists in Brevo with appropriate list membership
- [ ] Relationship record exists in Conversations Copilot (if person data available)
- [ ] Pipeline status updated to reflect current stage
- [ ] No duplicate records across systems

## Prerequisites

- NocoDB configured: `NOCODB_URL`, `NOCODB_API_KEY`, `NOCODB_BASE_ID` in `.env`
- Brevo configured: `BREVO_API_KEY` in `.env`
- Conversations Copilot configured: `CONVERSATIONS_BASE_URL`, `CONVERSATIONS_API_TOKEN` in `.env`
- Verify services: `copilot crm health --json && copilot brevo health --json`

## Instructions

### Step 1: Capture New Lead (REQUIRED)

When a new lead comes in (typically from Forces Assessment):

```bash
# Create lead record in CRM
copilot crm leads create \
  --name "Contact Name" \
  --email "email@company.com" \
  --company "Company Name" \
  --source "forces-assessment" \
  --json
```

### Step 2: Enrich Lead Data (OPTIONAL)

```bash
# Check if person exists in Conversations Copilot
copilot conv people list --json
# → Search results for matching name/email

# Check if company exists
copilot conv companies list --json
# → Search for matching company

# If person exists, get their profile and forces
copilot conv people get --id "$PERSON_ID" --json
copilot conv people personality --id "$PERSON_ID" --json
copilot conv forces list --json
# → Filter for forces related to this person/company
```

### Step 3: Add to Email List (REQUIRED)

```bash
# Create or add to Brevo contact
copilot brevo contacts create \
  --email "email@company.com" \
  --first-name "First" \
  --last-name "Last" \
  --json

# Add to appropriate nurture list
copilot brevo lists list --json
# → Find the right list ID

copilot brevo contacts update \
  --email "email@company.com" \
  --attributes '{"LISTS": [list_id]}' \
  --json
```

### Step 4: Send Initial Outreach (REQUIRED)

```bash
# Send transactional email (e.g., assessment results)
copilot brevo send \
  --to "email@company.com" \
  --subject "Your Forces Assessment Results" \
  --template-id "$TEMPLATE_ID" \
  --json
```

### Step 5: Track Pipeline Progress (REQUIRED)

```bash
# List all leads
copilot crm leads list --json

# Update lead status
copilot crm clients update --id "$LEAD_ID" --data '{"status": "contacted"}' --json

# Check deals in Conversations Copilot
copilot conv deals list --json
copilot conv deals get --id "$DEAL_ID" --json
```

### Step 6: Convert Lead to Client (OPTIONAL)

When a lead is ready to convert:

```bash
# Convert lead to client record
copilot crm leads convert --id "$LEAD_ID" --json
# → Creates a client record from the lead

# Verify client was created
copilot crm clients list --json

# Update deal status in Conversations
copilot conv deals update --id "$DEAL_ID" --status "won" --json
```

After conversion, hand off to `client-onboarding` skill.

## Examples

### Example: New Forces Assessment Lead

```bash
# 1. Lead comes in from Forces Assessment
copilot crm leads create \
  --name "Sarah Chen" \
  --email "sarah@techcorp.com" \
  --company "TechCorp" \
  --source "forces-assessment" \
  --json
# → {"id": "lead-123", "status": "new"}

# 2. Check Conversations for existing relationship
copilot conv intel search --query "Sarah Chen TechCorp" --json
# → Shows any existing people, companies, conversations

# 3. Add to Brevo
copilot brevo contacts create \
  --email "sarah@techcorp.com" \
  --first-name "Sarah" \
  --last-name "Chen" \
  --json

# 4. Send assessment results email
copilot brevo send \
  --to "sarah@techcorp.com" \
  --subject "Your Forces Assessment Results" \
  --template-id 42 \
  --json

# 5. Track in pipeline
copilot crm clients update --id "lead-123" --data '{"status": "contacted"}' --json
```

### Example: Check Pipeline Health

```bash
# All leads by status
copilot crm leads list --json
# → Filter by status: new, contacted, qualified, converted

# Campaign performance
copilot brevo campaigns stats --campaign-id "$CAMPAIGN_ID" --json

# Deals in flight
copilot conv deals list --json

# Follow-ups due
copilot conv followups list --json
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing NOCODB_API_KEY" | Add NocoDB credentials to `.env` |
| `ConfigError` | "Missing BREVO_API_KEY" | Add Brevo API key to `.env` |
| `AuthError` | 401 from NocoDB | Check `NOCODB_API_KEY` is valid |
| `NotFoundError` | "Lead not found" | Verify lead ID: `copilot crm leads list --json` |
| `ValidationError` | "Invalid email" | Check email format before creating contact |
| `RateLimitError` | 429 from Brevo | Wait 60s, reduce batch size for bulk operations |

## Quality Tests

### Deduplication Test
- Before creating any record, check if it already exists
- **PASS:** `copilot crm clients list --json` and `copilot conv intel search --query "<name>" --json` checked before creating
- **FAIL:** Duplicate lead created because existing records weren't searched first

### Email Deliverability Test
- Email address validated before adding to Brevo
- **PASS:** `copilot brevo contacts create` succeeds with valid email format
- **FAIL:** Invalid email format causes silent failure in nurture campaigns

### Cross-System Consistency Test
- Lead exists in all required systems with matching data
- **PASS:** CRM lead ID, Brevo contact, and Conv person all reference the same individual
- **FAIL:** Lead exists in CRM but missing from Brevo, or different email addresses across systems

### Pipeline Stage Test
- Lead status reflects the actual pipeline position
- **PASS:** Status progression follows: new → contacted → qualified → converted
- **FAIL:** Lead marked "contacted" but no email was actually sent

## Guidelines

1. Always create the CRM lead record first — it's the system of record
2. Check Conversations Copilot for existing relationships before creating new records
3. Use Brevo templates for consistent email communication
4. Update lead status at each pipeline stage for tracking
5. After conversion, immediately hand off to `client-onboarding` skill
6. Use `copilot conv intel search` for cross-system lead enrichment

## References

- Related skills: `client-onboarding`, `conversation-prep`, `intelligence-brief`
- CRM docs: `docs/services/07-nocodb.md`
- Brevo docs: `docs/services/08-brevo.md`
- Conversations docs: `docs/services/18-conversations.md`
