#!/usr/bin/env bash
set -euo pipefail

# maintenance.sh — Database health check, vacuum, and stats for one or all databases
#
# Usage: bash maintenance.sh [database]
# Examples:
#   bash maintenance.sh           # All configured databases
#   bash maintenance.sh nocodb    # Just nocodb
#
# Valid databases: main, nocodb, n8n, formbricks
#
# Requires: copilot CLI installed and configured with DATABASE_URL(s)

DATABASE="${1:-all}"
ALL_DBS=("main" "nocodb" "n8n" "formbricks")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Database Maintenance ===" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "Target: ${DATABASE}" >&2
echo "" >&2

# Determine which databases to process
if [[ "$DATABASE" == "all" ]]; then
    TARGETS=("${ALL_DBS[@]}")
else
    TARGETS=("$DATABASE")
fi

# Step 1: Health check
echo "[1/3] Running health checks..." >&2
HEALTH=$(copilot db health --json 2>/dev/null || echo '{"error": "health check failed"}')
echo "  Health check complete" >&2

# Step 2: Vacuum each database
echo "[2/3] Running vacuum on target databases..." >&2
VACUUM_RESULTS="["
FIRST=true

for DB in "${TARGETS[@]}"; do
    echo "  Vacuuming ${DB}..." >&2
    RESULT=$(copilot db vacuum --database "$DB" --json 2>/dev/null || echo "{\"database\": \"$DB\", \"error\": \"vacuum failed or not configured\"}")

    if [[ "$FIRST" == "true" ]]; then
        FIRST=false
    else
        VACUUM_RESULTS="${VACUUM_RESULTS},"
    fi
    VACUUM_RESULTS="${VACUUM_RESULTS}${RESULT}"
done

VACUUM_RESULTS="${VACUUM_RESULTS}]"
echo "  Vacuum complete" >&2

# Step 3: Post-maintenance stats
echo "[3/3] Collecting post-maintenance stats..." >&2
STATS=$(copilot db stats --json 2>/dev/null || echo '{"error": "stats unavailable"}')
echo "  Stats collected" >&2

echo "" >&2
echo "=== Maintenance Complete ===" >&2

cat <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "target": "$DATABASE",
  "health": $HEALTH,
  "vacuum_results": $VACUUM_RESULTS,
  "post_stats": $STATS
}
EOF
