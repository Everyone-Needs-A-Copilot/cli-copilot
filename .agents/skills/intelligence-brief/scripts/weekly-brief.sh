#!/usr/bin/env bash
set -euo pipefail

# weekly-brief.sh — Generate a weekly strategic intelligence brief
#
# Usage: bash weekly-brief.sh
#
# Steps: Dashboard signals -> Force stats -> Synthesis -> Report generation
#
# Requires: copilot CLI installed and configured with INSIGHTS_BASE_URL, INSIGHTS_API_KEY

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Weekly Intelligence Brief ===" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "" >&2

# Step 1: Dashboard signals
echo "[1/6] Gathering dashboard signals..." >&2
SIGNALS=$(copilot insights dashboard signals --json 2>/dev/null || echo '{"error": "signals unavailable"}')
ACTIVITY=$(copilot insights dashboard activity --json 2>/dev/null || echo '{"error": "activity unavailable"}')
SUMMARY=$(copilot insights dashboard summary --json 2>/dev/null || echo '{"error": "summary unavailable"}')
echo "  Dashboard data collected" >&2

# Step 2: Force landscape
echo "[2/6] Analyzing force landscape..." >&2
FORCES=$(copilot insights forces stats --json 2>/dev/null || echo '{"error": "forces unavailable"}')
echo "  Forces analyzed" >&2

# Step 3: Run synthesis
echo "[3/6] Running synthesis pipeline..." >&2
SYNTHESIS=$(copilot insights synthesis run --json 2>/dev/null || echo '{"error": "synthesis failed"}')
PATTERNS=$(copilot insights synthesis patterns --json 2>/dev/null || echo '{"error": "patterns unavailable"}')
CORRELATIONS=$(copilot insights synthesis correlations --json 2>/dev/null || echo '{"error": "correlations unavailable"}')
echo "  Synthesis complete" >&2

# Step 4: Generate report
echo "[4/6] Generating report..." >&2
REPORT=$(copilot insights reports from-existing --json 2>/dev/null || echo '{"error": "report generation failed"}')
echo "  Report generated" >&2

# Step 5: Campaign data (supplemental)
echo "[5/6] Checking campaign data..." >&2
CAMPAIGNS=$(copilot brevo campaigns list --json 2>/dev/null || echo '{"error": "campaigns unavailable"}')
echo "  Campaign data collected" >&2

# Step 6: Cost check
echo "[6/6] Checking intelligence costs..." >&2
COSTS=$(copilot insights monitoring cost-summary --json 2>/dev/null || echo '{"error": "costs unavailable"}')
echo "  Costs checked" >&2

echo "" >&2
echo "=== Brief Complete ===" >&2

cat <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "type": "weekly_brief",
  "dashboard": {
    "signals": $SIGNALS,
    "activity": $ACTIVITY,
    "summary": $SUMMARY
  },
  "forces": $FORCES,
  "synthesis": {
    "result": $SYNTHESIS,
    "patterns": $PATTERNS,
    "correlations": $CORRELATIONS
  },
  "report": $REPORT,
  "campaigns": $CAMPAIGNS,
  "costs": $COSTS
}
EOF
