# Meeting Types Prep Checklist

Per-meeting-type checklists for conversation preparation. Each type has different data priorities and preparation depth.

## Quarterly Business Review

**Priority data:** Relationship health, force progression, deal status, deliverables
**Prep depth:** Deep --- review all available data

| Check | Command | Priority |
|-------|---------|----------|
| Person profile & personality | `copilot conv people get --id <id> --json` + `personality` | Required |
| Last 3 months of conversations | `copilot conv conversations list --json` (filter by date) | Required |
| Relationship health score | `copilot conv intel health-person --person-id <id> --json` | Required |
| Energy trends | `copilot conv intel energy-person --person-id <id> --json` | Required |
| Active forces | `copilot conv forces list --json` | Required |
| Deal status | `copilot conv deals get --id <id> --json` | Required |
| Outstanding follow-ups | `copilot conv followups list --json` | Required |
| Company dossier | `copilot insights dossiers get --id <id> --json` | Recommended |
| CRM record | `copilot crm clients get --id <id> --json` | Recommended |
| Campaign engagement | `copilot brevo contacts get --email <email> --json` | Optional |

**Key questions to answer:**
- How has the relationship health trended this quarter?
- What forces have emerged, resolved, or intensified?
- Are all follow-ups from last quarter completed?
- What's the deal trajectory (growing, stable, at risk)?

## Discovery Call (New Prospect)

**Priority data:** Company background, any existing touchpoints, competitive landscape
**Prep depth:** Moderate --- may have limited existing data

| Check | Command | Priority |
|-------|---------|----------|
| Search for existing data | `copilot conv intel search --query "<name> <company>" --json` | Required |
| Company enrichment | `copilot conv intel enrich-company --company-id <id> --json` | Required |
| Create/get company dossier | `copilot insights dossiers create --company "<name>" --json` | Required |
| Enrich dossier | `copilot insights dossiers enrich --id <id> --json` | Recommended |
| Discovery questions | `copilot conv questions list --json` | Required |
| Coaching setup | `copilot conv coach config --json` | Optional |
| Market forces (their industry) | `copilot insights forces list --json` | Optional |

**Key questions to answer:**
- Do we have any prior touchpoint with this person or company?
- What does their company do and what challenges do they face?
- What discovery questions should we prioritize?

## Renewal Conversation

**Priority data:** Engagement history, value delivered, forces affecting renewal
**Prep depth:** Deep --- review full relationship

| Check | Command | Priority |
|-------|---------|----------|
| Full person profile | `copilot conv people get --id <id> --json` + `personality` | Required |
| All conversations | `copilot conv conversations list --json` | Required |
| Relationship health | `copilot conv intel health-person --person-id <id> --json` | Required |
| Active forces (especially exit forces) | `copilot conv forces list --json` | Required |
| Deal details | `copilot conv deals get --id <id> --json` | Required |
| Follow-up completion rate | `copilot conv followups list --json` | Required |
| CRM project record | `copilot crm projects list --json` | Required |
| Company dossier (competitive moves) | `copilot insights dossiers get --id <id> --json` | Required |
| Coaching feedback history | `copilot conv coach feedback-list --json` | Recommended |

**Key questions to answer:**
- What value have we delivered during this engagement?
- Are there unresolved forces that might push them away?
- What follow-ups did we miss (trust damage)?
- What's their competitive landscape --- are alternatives viable?

## Escalation Meeting

**Priority data:** Recent issues, force intensity, immediate actions needed
**Prep depth:** Focused --- zero in on the problem

| Check | Command | Priority |
|-------|---------|----------|
| Person profile & personality | `copilot conv people get --id <id> --json` + `personality` | Required |
| Most recent conversations | `copilot conv conversations list --json` (last 2-3) | Required |
| Active forces (high intensity) | `copilot conv forces list --json` | Required |
| Follow-ups (overdue items) | `copilot conv followups list --json` | Required |
| Relationship health (is it declining?) | `copilot conv intel health-person --person-id <id> --json` | Required |
| Deal at risk? | `copilot conv deals get --id <id> --json` | Required |
| CRM notes | `copilot crm clients get --id <id> --json` | Recommended |

**Key questions to answer:**
- What triggered the escalation?
- Which forces are driving this (validated vs unvalidated)?
- What's our credibility --- have we kept our commitments?
- What can we commit to right now to de-escalate?

## Check-In Call (Regular Touchpoint)

**Priority data:** Recent activity, outstanding follow-ups, quick wins
**Prep depth:** Light --- focus on continuity

| Check | Command | Priority |
|-------|---------|----------|
| Person profile | `copilot conv people get --id <id> --json` | Required |
| Last conversation | `copilot conv conversations get --id <latest> --json` | Required |
| Outstanding follow-ups | `copilot conv followups list --json` | Required |
| Active forces | `copilot conv forces list --json` | Recommended |
| Relationship health | `copilot conv intel health-person --person-id <id> --json` | Recommended |
| Company dossier updates | `copilot insights dossiers get --id <id> --json` | Optional |

**Key questions to answer:**
- What did we commit to last time? Is it done?
- Any new forces or changes since last check-in?
- What's one value-add we can offer today?

## Post-Conversation Capture Checklist

After ANY meeting type, run the capture pipeline:

```bash
# 1. Create conversation record
copilot conv conversations create --title "Meeting Type: Company" --json

# 2. Upload transcript (if available)
copilot conv transcripts upload --conversation-id <id> --file transcript.txt --json

# 3. Run capture phase
copilot conv conversations capture --id <id> --json

# 4. Run review phase
copilot conv conversations review --id <id> --json

# 5. Submit human signals
copilot conv conversations signal --id <id> --json

# 6. Get coaching feedback
copilot conv coach feedback-create --conversation-id <id> --json

# 7. Validate any new forces
copilot conv forces validate --id <force_id> --json
```
