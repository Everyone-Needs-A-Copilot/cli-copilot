#!/usr/bin/env bash
set -euo pipefail

# quality-dashboard.sh — Generate a quality dashboard for all skills
#
# Usage: bash quality-dashboard.sh [cli-copilot-skills-dir] [shared-skills-dir]
# Defaults:
#   CLI: this repo's own .claude/skills/ (resolved relative to this script)
#   Shared: none (pass a path to also audit a shared/knowledge-repo skills dir)
#
# Produces a markdown quality report to stdout.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CLI_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI_DIR="${1:-$DEFAULT_CLI_DIR}"
SHARED_DIR="${2:-}"
AUDIT_ALL="$SCRIPT_DIR/audit-all-skills.sh"

echo "# Skills Quality Dashboard"
echo ""
echo "Generated: $(date '+%Y-%m-%d %H:%M')"
echo ""

# Count skills in each location
CLI_COUNT=$(find "$CLI_DIR" -name "SKILL.md" -type f 2>/dev/null | wc -l | tr -d ' ')
SHARED_COUNT=$(find "$SHARED_DIR" -name "SKILL.md" -type f 2>/dev/null | wc -l | tr -d ' ')

echo "## Overview"
echo ""
echo "| Location | Skills | Status |"
echo "|----------|--------|--------|"

# Audit CLI skills
if [[ -d "$CLI_DIR" ]]; then
    CLI_PASS=0
    CLI_FAIL=0
    while IFS= read -r skill_file; do
        skill_dir="$(dirname "$skill_file")"
        if "$SCRIPT_DIR/audit-skill.sh" "$skill_dir" >/dev/null 2>&1; then
            ((CLI_PASS++))
        else
            ((CLI_FAIL++))
        fi
    done < <(find "$CLI_DIR" -name "SKILL.md" -type f 2>/dev/null | sort)
    CLI_RATE=0
    if [[ $CLI_COUNT -gt 0 ]]; then
        CLI_RATE=$(( (CLI_PASS * 100) / CLI_COUNT ))
    fi
    echo "| cli-copilot | $CLI_COUNT | ${CLI_PASS}/${CLI_COUNT} passing (${CLI_RATE}%) |"
else
    echo "| cli-copilot | - | Directory not found |"
fi

# Audit knowledge-copilot skills
if [[ -d "$SHARED_DIR" ]]; then
    SHARED_PASS=0
    SHARED_FAIL=0
    while IFS= read -r skill_file; do
        skill_dir="$(dirname "$skill_file")"
        if "$SCRIPT_DIR/audit-skill.sh" "$skill_dir" >/dev/null 2>&1; then
            ((SHARED_PASS++))
        else
            ((SHARED_FAIL++))
        fi
    done < <(find "$SHARED_DIR" -name "SKILL.md" -type f 2>/dev/null | sort)
    SHARED_RATE=0
    if [[ $SHARED_COUNT -gt 0 ]]; then
        SHARED_RATE=$(( (SHARED_PASS * 100) / SHARED_COUNT ))
    fi
    echo "| knowledge-copilot | $SHARED_COUNT | ${SHARED_PASS}/${SHARED_COUNT} passing (${SHARED_RATE}%) |"
else
    echo "| knowledge-copilot | - | Directory not found |"
fi

echo ""
echo "## Skills Needing Attention"
echo ""
echo "Skills with MISSING checks (required elements absent):"
echo ""

# List failing CLI skills
if [[ -d "$CLI_DIR" ]]; then
    while IFS= read -r skill_file; do
        skill_dir="$(dirname "$skill_file")"
        skill_name="$(basename "$skill_dir")"
        if ! "$SCRIPT_DIR/audit-skill.sh" "$skill_dir" >/dev/null 2>&1; then
            MISSING=$("$SCRIPT_DIR/audit-skill.sh" "$skill_dir" 2>&1 | grep "MISSING" | sed 's/^  MISSING  /  - /')
            echo "### cli-copilot/$skill_name"
            echo "$MISSING"
            echo ""
        fi
    done < <(find "$CLI_DIR" -name "SKILL.md" -type f 2>/dev/null | sort)
fi

echo "---"
echo ""
echo "Run \`bash scripts/audit-all-skills.sh <dir>\` for detailed per-skill reports."
