#!/usr/bin/env bash
set -euo pipefail

# capture-lead.sh — Capture a new lead across CRM, Conversations, and Brevo
#
# Usage: bash capture-lead.sh <name> <email> <company>
# Example: bash capture-lead.sh "Sarah Chen" "sarah@techcorp.com" "TechCorp"
#
# Steps: CRM create -> Conv search -> Brevo contact -> initial email
#
# Requires: copilot CLI with NOCODB_*, CONVERSATIONS_*, BREVO_* configured

NAME="${1:?Usage: $0 <name> <email> <company>}"
EMAIL="${2:?Usage: $0 <name> <email> <company>}"
COMPANY="${3:?Usage: $0 <name> <email> <company>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Capturing Lead ===" >&2
echo "Name: $NAME | Email: $EMAIL | Company: $COMPANY" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "" >&2

# Step 1: Create lead in CRM
echo "[1/4] Creating CRM lead record..." >&2
CRM_RESULT=$(copilot crm leads create \
    --name "$NAME" \
    --email "$EMAIL" \
    --company "$COMPANY" \
    --source "manual-capture" \
    --json 2>/dev/null || echo '{"error": "CRM lead creation failed"}')
echo "  CRM: done" >&2

# Step 2: Search Conversations for existing relationship
echo "[2/4] Searching Conversations Copilot..." >&2
CONV_RESULT=$(copilot conv intel search --query "$NAME $COMPANY" --json 2>/dev/null || echo '{"error": "conv search failed"}')
echo "  Conv search: done" >&2

# Step 3: Create Brevo contact
echo "[3/4] Creating Brevo contact..." >&2

# Parse name into first/last
FIRST_NAME=$(echo "$NAME" | awk '{print $1}')
LAST_NAME=$(echo "$NAME" | awk '{$1=""; print $0}' | xargs)

BREVO_RESULT=$(copilot brevo contacts create \
    --email "$EMAIL" \
    --first-name "$FIRST_NAME" \
    --last-name "$LAST_NAME" \
    --json 2>/dev/null || echo '{"error": "Brevo contact creation failed"}')
echo "  Brevo: done" >&2

# Step 4: Send initial outreach (if template configured)
echo "[4/4] Checking for outreach template..." >&2
EMAIL_RESULT='{"status": "skipped", "reason": "no template ID configured"}'
if [[ -n "${LEAD_WELCOME_TEMPLATE_ID:-}" ]]; then
    EMAIL_RESULT=$(copilot brevo send \
        --to "$EMAIL" \
        --subject "Welcome from Everyone Needs a Copilot" \
        --template-id "$LEAD_WELCOME_TEMPLATE_ID" \
        --json 2>/dev/null || echo '{"error": "email send failed"}')
    echo "  Email: sent" >&2
else
    echo "  Email: skipped (set LEAD_WELCOME_TEMPLATE_ID to enable)" >&2
fi

echo "" >&2
echo "=== Lead Captured ===" >&2

cat <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "lead": {
    "name": "$NAME",
    "email": "$EMAIL",
    "company": "$COMPANY"
  },
  "crm": $CRM_RESULT,
  "conversations": $CONV_RESULT,
  "brevo": $BREVO_RESULT,
  "outreach": $EMAIL_RESULT
}
EOF
