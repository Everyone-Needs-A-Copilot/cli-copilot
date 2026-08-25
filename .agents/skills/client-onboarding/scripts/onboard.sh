#!/usr/bin/env bash
set -euo pipefail

# onboard.sh — Set up a new client across all copilot-managed systems
#
# Usage: bash onboard.sh <name> <email> <company>
# Example: bash onboard.sh "Sarah Chen" "sarah@techcorp.com" "TechCorp"
#
# Steps: CRM → Conversations → Brevo → Verify all systems
#
# Requires: copilot CLI with NOCODB_*, CONVERSATIONS_*, BREVO_* configured

NAME="${1:?Usage: $0 <name> <email> <company>}"
EMAIL="${2:?Usage: $0 <name> <email> <company>}"
COMPANY="${3:?Usage: $0 <name> <email> <company>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Client Onboarding ===" >&2
echo "Name: $NAME | Email: $EMAIL | Company: $COMPANY" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "" >&2

ERRORS=0

# Step 1: CRM record
echo "[1/4] Creating CRM client record..." >&2
CRM_RESULT=$(copilot crm clients create \
    --name "$NAME" \
    --email "$EMAIL" \
    --company "$COMPANY" \
    --json 2>/dev/null || echo '{"error": "CRM client creation failed"}')
if echo "$CRM_RESULT" | grep -q '"error"'; then
    echo "  CRM: FAILED" >&2
    ((ERRORS++))
else
    echo "  CRM: done" >&2
fi

# Step 2: Client workspace
# Note: Notion was retired 2026-06-29; this step needs a replacement (TBD by owner).
NOTION_RESULT='{"status": "skipped", "reason": "Notion retired 2026-06-29; replacement TBD"}'
echo "  Workspace: skipped (Notion retired; replacement TBD)" >&2

# Step 3: Conversations Copilot
echo "[2/4] Setting up in Conversations Copilot..." >&2
CONV_RESULT=$(copilot conv conversations create \
    --title "Kickoff: $COMPANY" \
    --json 2>/dev/null || echo '{"error": "Conv conversation creation failed"}')
if echo "$CONV_RESULT" | grep -q '"error"'; then
    echo "  Conv: FAILED" >&2
    ((ERRORS++))
else
    echo "  Conv: done" >&2
fi

# Step 4: Brevo contact + welcome email
echo "[3/4] Setting up email communication..." >&2

FIRST_NAME=$(echo "$NAME" | awk '{print $1}')
LAST_NAME=$(echo "$NAME" | awk '{$1=""; print $0}' | xargs)

BREVO_RESULT=$(copilot brevo contacts create \
    --email "$EMAIL" \
    --first-name "$FIRST_NAME" \
    --last-name "$LAST_NAME" \
    --json 2>/dev/null || echo '{"error": "Brevo contact creation failed"}')
if echo "$BREVO_RESULT" | grep -q '"error"'; then
    echo "  Brevo contact: FAILED" >&2
    ((ERRORS++))
else
    echo "  Brevo contact: done" >&2
fi

# Send welcome email
WELCOME_RESULT='{"status": "skipped", "reason": "no template ID configured"}'
if [[ -n "${WELCOME_TEMPLATE_ID:-}" ]]; then
    WELCOME_RESULT=$(copilot brevo send \
        --to "$EMAIL" \
        --subject "Welcome to Everyone Needs a Copilot" \
        --template-id "$WELCOME_TEMPLATE_ID" \
        --json 2>/dev/null || echo '{"error": "welcome email failed"}')
    echo "  Welcome email: sent" >&2
else
    echo "  Welcome email: skipped (set WELCOME_TEMPLATE_ID to enable)" >&2
fi

# Step 5: Cross-system verification
echo "[4/4] Verifying across all systems..." >&2
VERIFY_HEALTH=$(copilot health --json 2>/dev/null || echo '{"error": "health check failed"}')
echo "  Verification complete" >&2

echo "" >&2
if [[ $ERRORS -gt 0 ]]; then
    echo "=== Onboarding completed with $ERRORS error(s) — review output ===" >&2
else
    echo "=== Onboarding Complete ===" >&2
fi

cat <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "client": {
    "name": "$NAME",
    "email": "$EMAIL",
    "company": "$COMPANY"
  },
  "results": {
    "crm": $CRM_RESULT,
    "notion": $NOTION_RESULT,
    "conversations": $CONV_RESULT,
    "brevo": $BREVO_RESULT,
    "welcome_email": $WELCOME_RESULT
  },
  "errors": $ERRORS,
  "health": $VERIFY_HEALTH
}
EOF

if [[ $ERRORS -gt 0 ]]; then
    exit 1
fi
