#!/usr/bin/env bash
set -euo pipefail

# audit-all-skills.sh — Batch audit all skills in a directory tree
#
# Usage: bash audit-all-skills.sh <skills-root-directory>
# Examples:
#   bash audit-all-skills.sh /Volumes/Dev/Sites/COPILOT/cli-copilot/.claude/skills/
#   bash audit-all-skills.sh /Volumes/Dev/Sites/COPILOT/knowledge-copilot/03-ai-enabling/01-skills/
#
# Finds all SKILL.md files, runs audit-skill.sh on each, produces summary.

SKILLS_ROOT="${1:?Usage: $0 <skills-root-directory>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT_SCRIPT="$SCRIPT_DIR/audit-skill.sh"

if [[ ! -f "$AUDIT_SCRIPT" ]]; then
    echo "ERROR: audit-skill.sh not found at $AUDIT_SCRIPT" >&2
    exit 1
fi

# Find all SKILL.md files (compatible with bash 3.x / macOS)
SKILL_FILES=()
while IFS= read -r line; do
    SKILL_FILES+=("$line")
done < <(find "$SKILLS_ROOT" -name "SKILL.md" -type f | sort)

if [[ ${#SKILL_FILES[@]} -eq 0 ]]; then
    echo "No SKILL.md files found in $SKILLS_ROOT"
    exit 0
fi

echo "=========================================="
echo " Skills Audit Report"
echo " Root: $SKILLS_ROOT"
echo " Found: ${#SKILL_FILES[@]} skill(s)"
echo " Date: $(date '+%Y-%m-%d %H:%M')"
echo "=========================================="
echo ""

TOTAL_SKILLS=0
PASSING_SKILLS=0
FAILING_SKILLS=0

# Track category stats (bash 3.x compatible — use temp files)
CAT_TOTAL_FILE=$(mktemp)
CAT_PASS_FILE=$(mktemp)
trap 'rm -f "$CAT_TOTAL_FILE" "$CAT_PASS_FILE"' EXIT

for SKILL_FILE in "${SKILL_FILES[@]}"; do
    SKILL_DIR="$(dirname "$SKILL_FILE")"

    # Determine category (parent directory of skill directory)
    PARENT_DIR="$(dirname "$SKILL_DIR")"
    CATEGORY="$(basename "$PARENT_DIR")"

    echo "$CATEGORY" >> "$CAT_TOTAL_FILE"

    ((TOTAL_SKILLS++))

    # Run audit (capture output, check exit code)
    if AUDIT_OUTPUT=$("$AUDIT_SCRIPT" "$SKILL_DIR" 2>&1); then
        ((PASSING_SKILLS++))
        echo "$CATEGORY" >> "$CAT_PASS_FILE"
    else
        ((FAILING_SKILLS++))
    fi

    echo "$AUDIT_OUTPUT"
    echo ""
done

# --- Category Summary ---
echo "=========================================="
echo " Category Summary"
echo "=========================================="
echo ""

printf "  %-30s %5s %5s %5s\n" "Category" "Total" "Pass" "Rate"
printf "  %-30s %5s %5s %5s\n" "--------" "-----" "----" "----"

for CATEGORY in $(sort -u "$CAT_TOTAL_FILE"); do
    TOTAL=$(grep -c "^${CATEGORY}$" "$CAT_TOTAL_FILE" 2>/dev/null || true)
    TOTAL=${TOTAL:-0}
    PASS=$(grep -c "^${CATEGORY}$" "$CAT_PASS_FILE" 2>/dev/null || true)
    PASS=${PASS:-0}
    if [[ $TOTAL -gt 0 ]]; then
        RATE=$(( (PASS * 100) / TOTAL ))
    else
        RATE=0
    fi
    printf "  %-30s %5d %5d %4d%%\n" "$CATEGORY" "$TOTAL" "$PASS" "$RATE"
done

echo ""

# --- Overall Summary ---
echo "=========================================="
echo " Overall Summary"
echo "=========================================="
echo ""
if [[ $TOTAL_SKILLS -gt 0 ]]; then
    OVERALL_RATE=$(( (PASSING_SKILLS * 100) / TOTAL_SKILLS ))
else
    OVERALL_RATE=0
fi
echo "  Total skills:   $TOTAL_SKILLS"
echo "  Fully passing:  $PASSING_SKILLS"
echo "  Has missing:    $FAILING_SKILLS"
echo "  Pass rate:      $OVERALL_RATE%"
echo ""

# Exit code: 0 if all pass, 1 if any fail
if [[ $FAILING_SKILLS -gt 0 ]]; then
    exit 1
else
    exit 0
fi
