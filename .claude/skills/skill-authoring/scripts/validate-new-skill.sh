#!/usr/bin/env bash
set -euo pipefail

# validate-new-skill.sh — Pre-commit validation for a new skill
#
# Usage: bash validate-new-skill.sh <skill-directory>
# Example: bash validate-new-skill.sh .claude/skills/my-new-skill
#
# Fails with specific messages if required elements are missing.
# Intended for use before committing a new skill.

SKILL_DIR="${1:?Usage: $0 <skill-directory>}"
SKILL_DIR="${SKILL_DIR%/}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# First run the standard audit
echo "=== Validating New Skill ===" >&2
echo "" >&2

if [[ ! -f "$SKILL_DIR/SKILL.md" ]]; then
    echo "FAIL: $SKILL_DIR/SKILL.md does not exist" >&2
    echo "" >&2
    echo "Every skill must have a SKILL.md file. Use a template:" >&2
    echo "  cp templates/SKILL-TEMPLATE.md $SKILL_DIR/SKILL.md" >&2
    echo "  cp templates/CLI-WORKFLOW-TEMPLATE.md $SKILL_DIR/SKILL.md" >&2
    echo "  cp templates/KNOWLEDGE-SKILL-TEMPLATE.md $SKILL_DIR/SKILL.md" >&2
    exit 1
fi

CONTENT="$(cat "$SKILL_DIR/SKILL.md")"
ERRORS=0

# Required frontmatter
check_required() {
    local field="$1"
    local message="$2"
    if ! echo "$CONTENT" | grep -q "$field"; then
        echo "FAIL: $message" >&2
        ((ERRORS++))
    fi
}

check_required "^name:" "Frontmatter missing 'name:' field"
check_required "^description:" "Frontmatter missing 'description:' field"
check_required "keywords:" "Frontmatter missing 'triggers.keywords:' — skill won't be discoverable"
check_required "^allowed-tools:" "Frontmatter missing 'allowed-tools:' field"

# Required body sections
check_required "^## Define Done" "Missing '## Define Done' section — add success criteria"
check_required "^## Quality Tests" "Missing '## Quality Tests' section — add domain-specific tests"

# Check for Instructions or Framework (at least one)
if ! echo "$CONTENT" | grep -qE "^## (Instructions|Framework)"; then
    echo "FAIL: Missing '## Instructions' or '## Framework' section" >&2
    ((ERRORS++))
fi

# Warnings (non-blocking)
if ! echo "$CONTENT" | grep -q "^## Examples"; then
    echo "WARN: No '## Examples' section — consider adding worked examples" >&2
fi

if ! echo "$CONTENT" | grep -q "^## Error Handling"; then
    echo "WARN: No '## Error Handling' section — recommended for CLI skills" >&2
fi

if ! echo "$CONTENT" | grep -qE "\(REQUIRED\)|\(OPTIONAL\)"; then
    echo "WARN: Steps not marked (REQUIRED)/(OPTIONAL) — consider adding" >&2
fi

# Check for REPLACE placeholders left in
if echo "$CONTENT" | grep -q "REPLACE"; then
    echo "WARN: Template REPLACE placeholders still present — fill them in" >&2
fi

echo "" >&2
if [[ $ERRORS -gt 0 ]]; then
    echo "=== VALIDATION FAILED: $ERRORS required element(s) missing ===" >&2
    exit 1
else
    echo "=== VALIDATION PASSED ===" >&2

    # Run full audit for informational score
    echo "" >&2
    "$SCRIPT_DIR/audit-skill.sh" "$SKILL_DIR" 2>&1 || true
fi
