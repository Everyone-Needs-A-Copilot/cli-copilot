#!/usr/bin/env bash
# sync-skills.sh — Symlink skills from cli-copilot to other CLI tool directories
#
# Usage: bash .claude/skills/skill-authoring/scripts/sync-skills.sh [target_dir ...]
#
# If no target directories are provided, it reads from SYNC_TARGETS below.
# Each target should be a path to another CLI tool's .claude/skills/ directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Add paths to other CLI tool .claude/skills/ directories here
SYNC_TARGETS=(
    # Example: "/path/to/other-tool/.claude/skills"
    # Example: "/path/to/another-tool/.claude/skills"
)

# Override with command-line args if provided
if [[ $# -gt 0 ]]; then
    SYNC_TARGETS=("$@")
fi

if [[ ${#SYNC_TARGETS[@]} -eq 0 ]]; then
    echo "No sync targets configured."
    echo ""
    echo "Usage: $0 [target_dir ...]"
    echo ""
    echo "Or edit SYNC_TARGETS in this script to add permanent targets."
    exit 0
fi

synced=0
skipped=0

for target in "${SYNC_TARGETS[@]}"; do
    # Create target directory if it doesn't exist
    mkdir -p "$target"

    for skill_dir in "$SOURCE_DIR"/*/; do
        skill_name="$(basename "$skill_dir")"

        # Skip the meta-skill (it's specific to this repo)
        [[ "$skill_name" == "skill-authoring" ]] && continue

        target_link="$target/$skill_name"

        if [[ -L "$target_link" ]]; then
            # Already symlinked — check if pointing to same source
            current_target="$(readlink "$target_link")"
            if [[ "$current_target" == "$skill_dir" ]]; then
                ((skipped++))
                continue
            fi
            # Different source — update
            rm "$target_link"
        elif [[ -d "$target_link" ]]; then
            echo "  SKIP $skill_name → $target (directory exists, not a symlink)"
            ((skipped++))
            continue
        fi

        ln -s "$skill_dir" "$target_link"
        echo "  LINK $skill_name → $target"
        ((synced++))
    done
done

echo ""
echo "Done: $synced linked, $skipped unchanged"
