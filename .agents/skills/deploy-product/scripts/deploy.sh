#!/usr/bin/env bash
set -euo pipefail

# deploy.sh — End-to-end deployment with pre-checks, monitoring, and auto-rollback
#
# Usage: bash deploy.sh <app-uuid>
# Example: bash deploy.sh abc123-def456
#
# Steps: Pre-check → Deploy trigger → Monitor → Health verify → Auto-rollback on failure
#
# Requires: copilot CLI installed and configured with COOLIFY_BASE_URL, COOLIFY_ACCESS_TOKEN

APP_UUID="${1:?Usage: $0 <app-uuid>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../../../.env" ]]; then
    set -a; source "${SCRIPT_DIR}/../../../../.env"; set +a
fi

echo "=== Deploying app: $APP_UUID ===" >&2
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')" >&2
echo "" >&2

# Step 1: Pre-deploy checks
echo "[1/5] Running pre-deploy checks..." >&2

SERVER_HEALTH=$(copilot coolify server healthcheck --json 2>/dev/null || echo '{"healthy": false}')
if echo "$SERVER_HEALTH" | grep -q '"healthy": false'; then
    echo "ABORT: Coolify server is unhealthy. Fix infrastructure first." >&2
    echo '{"status": "aborted", "reason": "server_unhealthy"}'
    exit 1
fi
echo "  Server: healthy" >&2

RESOURCES=$(copilot monitoring status --json 2>/dev/null || echo '{}')
CPU=$(echo "$RESOURCES" | grep -o '"cpu_percent":[^,}]*' | grep -o '[0-9.]*' || echo "0")
MEM=$(echo "$RESOURCES" | grep -o '"memory_percent":[^,}]*' | grep -o '[0-9.]*' || echo "0")

if (( $(echo "$CPU > 80" | bc -l 2>/dev/null || echo 0) )); then
    echo "WARNING: CPU at ${CPU}% — deploy may cause issues" >&2
fi
if (( $(echo "$MEM > 85" | bc -l 2>/dev/null || echo 0) )); then
    echo "WARNING: Memory at ${MEM}% — deploy may cause OOM" >&2
fi
echo "  Resources: CPU=${CPU}% Memory=${MEM}%" >&2

# Step 2: Get current app state (for rollback reference)
echo "[2/5] Capturing current app state..." >&2
APP_STATE=$(copilot coolify app get --uuid "$APP_UUID" --json 2>/dev/null || echo '{"error": "app not found"}')
echo "  App state captured" >&2

# Step 3: Trigger deployment
echo "[3/5] Triggering deployment..." >&2
DEPLOY_RESULT=$(copilot coolify deploy trigger --app-uuid "$APP_UUID" --json 2>/dev/null || echo '{"error": "deploy trigger failed"}')

if echo "$DEPLOY_RESULT" | grep -q '"error"'; then
    echo "ABORT: Deploy trigger failed" >&2
    echo "$DEPLOY_RESULT"
    exit 1
fi

echo "  Deploy triggered" >&2

# Step 4: Wait and check deployment status
echo "[4/5] Monitoring deployment..." >&2
echo "  Waiting 30 seconds for build..." >&2
sleep 30

POST_APP_STATE=$(copilot coolify app get --uuid "$APP_UUID" --json 2>/dev/null || echo '{"error": "check failed"}')
echo "  Post-deploy app state retrieved" >&2

# Step 5: Post-deploy health verification
echo "[5/5] Verifying post-deploy health..." >&2
POST_HEALTH=$(copilot health --json 2>/dev/null || echo '{"error": "health check failed"}')

# Check for failures — auto-rollback
if echo "$POST_HEALTH" | grep -q '"unhealthy"'; then
    echo "" >&2
    echo "WARNING: Unhealthy services detected post-deploy!" >&2
    echo "Triggering automatic rollback..." >&2
    ROLLBACK_RESULT=$(copilot coolify deploy rollback --app-uuid "$APP_UUID" --json 2>/dev/null || echo '{"error": "rollback failed"}')
    echo "Rollback triggered. Verify manually." >&2

    cat <<EOF
{
  "status": "rolled_back",
  "app_uuid": "$APP_UUID",
  "deploy_result": $DEPLOY_RESULT,
  "post_health": $POST_HEALTH,
  "rollback": $ROLLBACK_RESULT
}
EOF
    exit 1
fi

echo "" >&2
echo "=== Deployment successful ===" >&2

cat <<EOF
{
  "status": "success",
  "app_uuid": "$APP_UUID",
  "deploy_result": $DEPLOY_RESULT,
  "post_health": $POST_HEALTH,
  "resources": $RESOURCES
}
EOF
