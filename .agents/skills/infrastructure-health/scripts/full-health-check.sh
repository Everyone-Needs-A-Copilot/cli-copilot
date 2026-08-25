#!/usr/bin/env bash
set -euo pipefail

# full-health-check.sh — Comprehensive infrastructure health check with triage
#
# Usage: bash full-health-check.sh
#
# Runs copilot health, drills into unhealthy services, checks resources,
# and produces a triage report ordered by dependency priority.
#
# Requires: copilot CLI installed and configured
# Output: JSON triage report to stdout, progress logs to stderr

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env if available
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Infrastructure Health Check ===" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "" >&2

# Step 1: Master health check
echo "[1/4] Running master health check..." >&2
HEALTH_OUTPUT=$(copilot health --json 2>/dev/null || echo '{"error": "health command failed"}')

# Step 2: Check system resources
echo "[2/4] Checking system resources..." >&2
RESOURCES=$(copilot monitoring status --json 2>/dev/null || echo '{"error": "monitoring unavailable"}')

# Step 3: Check alerts
echo "[3/4] Checking active alerts..." >&2
ALERTS=$(copilot monitoring alerts --json 2>/dev/null || echo '{"alerts": [], "error": "alerts unavailable"}')

# Step 4: Check Coolify server (if configured)
echo "[4/4] Checking Coolify server..." >&2
COOLIFY=$(copilot coolify server healthcheck --json 2>/dev/null || echo '{"error": "coolify unavailable"}')

# Parse resource thresholds
CPU=$(echo "$RESOURCES" | grep -o '"cpu_percent":[^,}]*' | grep -o '[0-9.]*' || echo "unknown")
MEM=$(echo "$RESOURCES" | grep -o '"memory_percent":[^,}]*' | grep -o '[0-9.]*' || echo "unknown")
DISK=$(echo "$RESOURCES" | grep -o '"disk_percent":[^,}]*' | grep -o '[0-9.]*' || echo "unknown")

# Determine resource warnings
RESOURCE_WARNINGS=""
if [[ "$CPU" != "unknown" ]] && (( $(echo "$CPU > 80" | bc -l 2>/dev/null || echo 0) )); then
    RESOURCE_WARNINGS="${RESOURCE_WARNINGS}CPU above 80% ($CPU%). "
fi
if [[ "$MEM" != "unknown" ]] && (( $(echo "$MEM > 85" | bc -l 2>/dev/null || echo 0) )); then
    RESOURCE_WARNINGS="${RESOURCE_WARNINGS}Memory above 85% ($MEM%). "
fi
if [[ "$DISK" != "unknown" ]] && (( $(echo "$DISK > 90" | bc -l 2>/dev/null || echo 0) )); then
    RESOURCE_WARNINGS="${RESOURCE_WARNINGS}Disk above 90% ($DISK%). "
fi

echo "" >&2
echo "=== Triage Report ===" >&2
echo "" >&2
echo "Resources: CPU=${CPU}% | Memory=${MEM}% | Disk=${DISK}%" >&2
if [[ -n "$RESOURCE_WARNINGS" ]]; then
    echo "WARNINGS: $RESOURCE_WARNINGS" >&2
else
    echo "Resources: All within thresholds" >&2
fi
echo "" >&2

# Output structured JSON report to stdout
cat <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "health": $HEALTH_OUTPUT,
  "resources": $RESOURCES,
  "alerts": $ALERTS,
  "coolify": $COOLIFY,
  "resource_warnings": "${RESOURCE_WARNINGS:-none}",
  "triage_order": [
    "1. Infrastructure (Coolify/Docker)",
    "2. Databases (PostgreSQL)",
    "3. Core services (n8n, NocoDB)",
    "4. Product APIs (Insights, Project, Conversations)",
    "5. External APIs (Brevo)"
  ]
}
EOF

echo "" >&2
echo "Done. Review JSON output for full details." >&2
