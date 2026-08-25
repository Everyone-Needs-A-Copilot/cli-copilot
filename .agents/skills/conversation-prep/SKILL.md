---
name: conversation-prep
description: >-
  Prepare for client conversations using copilot CLI — Conversations Copilot for history,
  personality, and forces; Insights for dossiers; CRM for client data.
  Use when preparing for meetings, calls, or any client interaction.
triggers:
  keywords: ["conversation prep", "meeting prep", "call prep", "client meeting",
             "personality", "relationship", "forces", "followup", "coaching",
             "conversation review", "discovery call"]
allowed-tools: Read, Bash, Grep, Glob
---

# Conversation Prep

## Overview

Prepare for any client interaction by gathering relationship history, personality insights, active forces, deal status, and follow-up items from Conversations Copilot, with enrichment from Insights dossiers and CRM data.

## Define Done

Conversation prep is complete when:

- [ ] Person identified with personality profile retrieved
- [ ] Relationship history reviewed (recent conversations, health score, energy trends)
- [ ] Active forces surfaced and understood
- [ ] Outstanding deals and follow-ups identified
- [ ] Enrichment from Insights and CRM gathered (if available)

## Prerequisites

- Conversations Copilot configured: `CONVERSATIONS_BASE_URL`, `CONVERSATIONS_API_TOKEN` in `.env`
- Authenticated: `copilot conv auth me --json` returns current user
- For full prep, also configure: Insights Copilot, CRM (NocoDB)

## Instructions

### Step 1: Identify the Person and Company (REQUIRED)

```bash
# Search across all conversation data
copilot conv intel search --query "Person Name" --json

# Get person details
copilot conv people get --id "$PERSON_ID" --json

# Get personality profile
copilot conv people personality --id "$PERSON_ID" --json

# Get company details
copilot conv companies get --id "$COMPANY_ID" --json
```

### Step 2: Review Relationship History (REQUIRED)

```bash
# List conversations with this person
copilot conv conversations list --json
# → Filter for conversations involving this person

# Get details on recent conversations (participants, forces, key moments, follow-ups)
copilot conv conversations get --id "$CONVERSATION_ID" --json

# Check relationship health
copilot conv intel health-person --person-id "$PERSON_ID" --json

# Energy trends
copilot conv intel energy-person --person-id "$PERSON_ID" --json
```

### Step 3: Understand Active Forces (REQUIRED)

```bash
# List forces related to this person/company
copilot conv forces list --json

# Get details on specific forces
copilot conv forces get --id "$FORCE_ID" --json

# Check force validation status
# Forces marked as validated have been human-verified
```

### Step 4: Review Deals and Follow-Ups (REQUIRED)

```bash
# Active deals
copilot conv deals list --json
copilot conv deals get --id "$DEAL_ID" --json

# Outstanding follow-ups
copilot conv followups list --json
# → Filter for items related to this person/company
```

### Step 5: Get Coaching Guidance (OPTIONAL)

```bash
# Current coaching config
copilot conv coach config --json

# Available coaching personas
copilot conv coach personas --json

# Coaching skills
copilot conv coach skills --json

# Previous coaching feedback for context
copilot conv coach feedback-list --json
```

### Step 6: Enrich from Other Sources (OPTIONAL)

```bash
# Company dossier from Insights
copilot insights dossiers get --id "$DOSSIER_ID" --json

# Strategic forces from Insights (market-level, not relationship-level)
copilot insights forces list --json

# CRM client record
copilot crm clients get --id "$CLIENT_ID" --json

# Calendar events (upcoming meetings)
copilot conv calendar events --json
```

### Step 7: Review Discovery Questions (OPTIONAL)

```bash
# List discovery questions for the conversation type
copilot conv questions list --json
```

## Examples

### Example: Prepare for Quarterly Review

```bash
# 1. Person & personality
copilot conv people get --id "person-123" --json
copilot conv people personality --id "person-123" --json
# → Communication style, decision patterns, motivations

# 2. Recent conversations (last quarter)
copilot conv conversations list --json
# → Last 3-4 conversations

copilot conv conversations get --id "conv-recent" --json
# → Key moments, forces surfaced, follow-ups agreed

# 3. Active forces
copilot conv forces list --json
# → Tensions, unspoken truths, external/internal forces

# 4. Relationship health
copilot conv intel health-person --person-id "person-123" --json
# → Health score, trend, risk indicators

copilot conv intel energy-person --person-id "person-123" --json
# → Engagement energy trend

# 5. Outstanding follow-ups
copilot conv followups list --json
# → What was promised, what's overdue

# 6. Company intelligence
copilot insights dossiers get --id "dossier-abc" --json
# → Market position, competitive landscape, recent news
```

### Example: Prepare for Discovery Call (New Prospect)

```bash
# 1. Search for any existing data
copilot conv intel search --query "Prospect Name Company" --json
# → May find previous touchpoints

# 2. Company enrichment
copilot conv intel enrich-company --company-id "company-456" --json

# 3. Company dossier from Insights
copilot insights dossiers create --company "Prospect Company" --json
copilot insights dossiers enrich --id "new-dossier-id" --json

# 4. Prep discovery questions
copilot conv questions list --json

# 5. Get coaching setup
copilot conv coach config --json
```

### Example: Post-Conversation Capture

After the meeting, capture what happened:

```bash
# 1. Create conversation record
copilot conv conversations create \
  --title "Q4 Review: Company Name" \
  --json

# 2. Upload transcript if available
copilot conv transcripts upload \
  --conversation-id "$CONV_ID" \
  --file "transcript.txt" \
  --json

# 3. Complete capture phase
copilot conv conversations capture --id "$CONV_ID" --json

# 4. Complete review phase
copilot conv conversations review --id "$CONV_ID" --json

# 5. Submit human signals
copilot conv conversations signal --id "$CONV_ID" --json

# 6. Get coaching feedback
copilot conv coach feedback-create --conversation-id "$CONV_ID" --json

# 7. Validate new forces
copilot conv forces validate --id "$FORCE_ID" --json
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing CONVERSATIONS_API_TOKEN" | Add token to `.env` |
| `AuthError` | 401/403 | Re-authenticate: `copilot conv auth login --json` then `copilot conv auth refresh` |
| `NotFoundError` | Person/conversation not found | Search first: `copilot conv intel search` |
| `ConnectionError` | Can't reach Conversations API | Check service: `copilot health --json` |

## Quality Tests

### Coverage Test
- All relevant data sources consulted, not just Conversations Copilot
- **PASS:** Prep includes data from Conv (person, forces, deals), Insights (dossier), and CRM (client record)
- **FAIL:** Prep only uses Conv data when Insights dossier and CRM data are available

### Recency Test
- Prep reflects the most recent interactions, not stale data
- **PASS:** Most recent conversation reviewed is within the last 30 days (or the last interaction)
- **FAIL:** Prep references conversations from 6+ months ago without noting the gap

### Follow-Up Accountability Test
- Outstanding follow-ups from previous conversations are surfaced
- **PASS:** `copilot conv followups list --json` checked and overdue items highlighted
- **FAIL:** Previous commitments not mentioned, risking trust damage

### Personality Alignment Test
- Prep recommendations align with the person's communication style
- **PASS:** Personality profile consulted and approach tailored to their preferences
- **FAIL:** Generic meeting approach that ignores known personality traits

## Guidelines

1. Always start with personality profile — it shapes how you approach the conversation
2. Review forces before meetings — they reveal what's really going on
3. Check follow-ups — nothing damages trust more than forgetting commitments
4. Use relationship health score to gauge engagement risk
5. After conversations, always run the capture → review → signal pipeline
6. Cross-reference Conversations forces with Insights forces for full picture

## References

- Related skills: `lead-pipeline`, `client-onboarding`, `intelligence-brief`
- Conversations docs: `docs/services/18-conversations.md`
- Insights docs: `docs/services/16-insights.md`
