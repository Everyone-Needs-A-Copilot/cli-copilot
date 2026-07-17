#!/usr/bin/env bash
set -euo pipefail

# audit-skill.sh — Audit a single skill directory against quality standards
#
# Usage: bash audit-skill.sh <skill-directory>
# Example: bash audit-skill.sh .claude/skills/new-service-scaffold
#
# Checks:
#   SKILL.md exists and is non-empty
#   Frontmatter has required fields (name, description)
#   Frontmatter has recommended fields (triggers.keywords)
#   Body has key sections (Instructions/Framework, Examples, Guidelines)
#   Has Define Done section
#   Has Quality Tests section
#   Notes scripts/ and reference/ presence
#
# Output: PASS/WARN/MISSING per check + overall score

SKILL_DIR="${1:?Usage: $0 <skill-directory>}"

# Normalize path (remove trailing slash)
SKILL_DIR="${SKILL_DIR%/}"

# Find SKILL.md (handle both direct path and directory)
if [[ -f "$SKILL_DIR" ]]; then
    SKILL_FILE="$SKILL_DIR"
    SKILL_DIR="$(dirname "$SKILL_DIR")"
elif [[ -f "$SKILL_DIR/SKILL.md" ]]; then
    SKILL_FILE="$SKILL_DIR/SKILL.md"
else
    echo "MISSING  SKILL.md not found in $SKILL_DIR"
    exit 1
fi

SKILL_NAME="$(basename "$SKILL_DIR")"
PASS=0
WARN=0
MISSING=0
TOTAL=0

check() {
    local status="$1"
    local message="$2"
    ((TOTAL++))
    case "$status" in
        PASS)    ((PASS++));    printf "  %-8s %s\n" "PASS" "$message" ;;
        WARN)    ((WARN++));    printf "  %-8s %s\n" "WARN" "$message" ;;
        MISSING) ((MISSING++)); printf "  %-8s %s\n" "MISSING" "$message" ;;
    esac
}

echo "=== Auditing: $SKILL_NAME ==="
echo "    Path: $SKILL_DIR"
echo ""

# --- Check 1: SKILL.md exists and non-empty ---
if [[ -s "$SKILL_FILE" ]]; then
    check PASS "SKILL.md exists and non-empty"
else
    check MISSING "SKILL.md is empty or missing"
fi

# --- Check 2: Frontmatter exists (first line is ---) ---
if head -1 "$SKILL_FILE" | grep -q "^---"; then
    check PASS "Frontmatter block present"
else
    check MISSING "Frontmatter block (---) not found"
fi

# --- Check 3: name field ---
if grep -q "^name:" "$SKILL_FILE"; then
    check PASS "Frontmatter: name field"
else
    check MISSING "Frontmatter: name field"
fi

# --- Check 4: description field ---
if grep -q "^description:" "$SKILL_FILE"; then
    check PASS "Frontmatter: description field"
else
    check MISSING "Frontmatter: description field"
fi

# --- Check 5: triggers.keywords ---
if grep -q "keywords:" "$SKILL_FILE"; then
    check PASS "Frontmatter: triggers.keywords"
else
    check WARN "Frontmatter: triggers.keywords (recommended)"
fi

# --- Check 6: allowed-tools ---
if grep -q "^allowed-tools:" "$SKILL_FILE"; then
    check PASS "Frontmatter: allowed-tools"
else
    check WARN "Frontmatter: allowed-tools (recommended)"
fi

# --- Check 7: Instructions or Framework section ---
# Knowledge skills may use domain-specific H2 sections instead of ## Instructions.
# Count substantive H2 sections (excluding structural ones like Overview, Define Done, etc.)
if grep -qE "^## (Instructions|Framework)" "$SKILL_FILE"; then
    check PASS "Body: Instructions/Framework section"
else
    # Count H2 sections that aren't structural boilerplate
    STRUCTURAL="Overview|Define Done|Quality Tests|Examples|Guidelines|References|Anti-Patterns|Error Handling|Conclusion|Table of Contents"
    SUBSTANTIVE_H2=$(grep -cE "^## " "$SKILL_FILE" 2>/dev/null || true)
    STRUCTURAL_H2=$(grep -cE "^## ($STRUCTURAL)" "$SKILL_FILE" 2>/dev/null || true)
    CONTENT_H2=$(( ${SUBSTANTIVE_H2:-0} - ${STRUCTURAL_H2:-0} ))
    if [[ $CONTENT_H2 -ge 2 ]]; then
        check PASS "Body: content sections (${CONTENT_H2} domain-specific H2s — knowledge skill)"
    else
        check MISSING "Body: Instructions or Framework section"
    fi
fi

# --- Check 8: Examples section ---
if grep -q "^## Examples" "$SKILL_FILE"; then
    check PASS "Body: Examples section"
else
    check WARN "Body: Examples section (recommended)"
fi

# --- Check 9: Guidelines section ---
if grep -q "^## Guidelines" "$SKILL_FILE"; then
    check PASS "Body: Guidelines section"
else
    check WARN "Body: Guidelines section (recommended)"
fi

# --- Check 10: Error Handling section ---
if grep -q "^## Error Handling" "$SKILL_FILE"; then
    check PASS "Body: Error Handling section"
else
    check WARN "Body: Error Handling section (recommended for CLI skills)"
fi

# --- Check 11: Define Done section ---
if grep -q "^## Define Done" "$SKILL_FILE"; then
    check PASS "Body: Define Done section"
else
    check MISSING "Body: Define Done section"
fi

# --- Check 12: Quality Tests section ---
if grep -q "^## Quality Tests" "$SKILL_FILE"; then
    check PASS "Body: Quality Tests section"
else
    check MISSING "Body: Quality Tests section"
fi

# --- Check 13: scripts/ directory ---
if [[ -d "$SKILL_DIR/scripts" ]] && [[ -n "$(ls -A "$SKILL_DIR/scripts/" 2>/dev/null)" ]]; then
    SCRIPT_COUNT=$(find "$SKILL_DIR/scripts" -type f \( -name "*.sh" -o -name "*.sh.md" \) | wc -l | tr -d ' ')
    check PASS "scripts/ directory ($SCRIPT_COUNT script(s))"
else
    check WARN "scripts/ directory (not present — OK for knowledge skills)"
fi

# --- Check 14: reference/ directory ---
if [[ -d "$SKILL_DIR/reference" ]] && [[ -n "$(ls -A "$SKILL_DIR/reference/" 2>/dev/null)" ]]; then
    REF_COUNT=$(find "$SKILL_DIR/reference" -type f -name "*.md" | wc -l | tr -d ' ')
    check PASS "reference/ directory ($REF_COUNT file(s))"
else
    check WARN "reference/ directory (not present — OK for simple skills)"
fi

# --- Check 15: Required/optional step marking ---
if grep -qE "\(REQUIRED\)|\(OPTIONAL\)" "$SKILL_FILE"; then
    check PASS "Steps marked REQUIRED/OPTIONAL"
else
    check WARN "Steps not marked REQUIRED/OPTIONAL"
fi

# --- Summary ---
echo ""
SCORE=$(( (PASS * 100) / TOTAL ))
echo "--- Score: $PASS/$TOTAL passed ($SCORE%) | $WARN warnings | $MISSING missing ---"

# Exit code: 0 if no MISSING, 1 if any MISSING
if [[ $MISSING -gt 0 ]]; then
    exit 1
else
    exit 0
fi
