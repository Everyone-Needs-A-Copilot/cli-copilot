#!/usr/bin/env python3
"""Batch upgrade knowledge-copilot skills with missing sections.

Adds:
- triggers.keywords (derived from name + description) if missing
- allowed-tools if missing
- ## Define Done section if missing
- ## Quality Tests section if missing

Usage:
    python3 batch-upgrade-skills.py <skills-root> [--dry-run]
"""

import re
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

# Category-specific Define Done and Quality Tests templates
CATEGORY_TEMPLATES = {
    "01-analysis": {
        "define_done": [
            "Analysis inputs gathered from relevant data sources",
            "Framework/methodology applied systematically (not ad hoc)",
            "Findings supported by specific evidence, not assumptions",
            "Actionable recommendations produced with clear next steps",
        ],
        "quality_tests": {
            "Evidence Test": {
                "check": "Every finding cites specific data, quotes, or observations",
                "pass": "Each insight traces back to a named source or data point",
                "fail": "Findings use vague language like 'it seems' or 'generally' without evidence",
            },
            "Completeness Test": {
                "check": "All relevant dimensions of the framework have been considered",
                "pass": "Analysis addresses each framework dimension, noting gaps where data is unavailable",
                "fail": "Key dimensions skipped without acknowledgment",
            },
            "Actionability Test": {
                "check": "Recommendations are specific enough to act on immediately",
                "pass": "Each recommendation names who should do what by when",
                "fail": "Recommendations are vague ('improve communication') without concrete actions",
            },
        },
    },
    "01-code-patterns": {
        "define_done": [
            "Pattern applied correctly in context of the codebase",
            "Code follows language-specific idioms and conventions",
            "Anti-patterns identified and avoided",
            "Code is readable, testable, and maintainable",
        ],
        "quality_tests": {
            "Idiomatic Test": {
                "check": "Code follows the language's established conventions",
                "pass": "A senior developer in this language would recognize the patterns as standard",
                "fail": "Code works but uses patterns from a different language or outdated style",
            },
            "Anti-Pattern Test": {
                "check": "Common mistakes for this pattern are explicitly addressed",
                "pass": "Skill warns against known pitfalls with examples of what NOT to do",
                "fail": "Only shows the happy path without mentioning common mistakes",
            },
        },
    },
    "02-testing": {
        "define_done": [
            "Test strategy covers the appropriate levels (unit/integration/e2e)",
            "Test cases are independent, repeatable, and deterministic",
            "Edge cases and error paths are covered",
            "Tests document expected behavior, not implementation details",
        ],
        "quality_tests": {
            "Coverage Test": {
                "check": "All critical paths have test coverage",
                "pass": "Happy path, error paths, and edge cases each have at least one test",
                "fail": "Only happy path tested, error handling untested",
            },
            "Maintainability Test": {
                "check": "Tests are resilient to implementation changes",
                "pass": "Tests verify behavior/outcomes, not internal method calls",
                "fail": "Tests break when refactoring without changing behavior",
            },
        },
    },
    "02-facilitation": {
        "define_done": [
            "Session objectives clearly defined and achievable",
            "Activities designed to surface diverse perspectives",
            "Outputs are documented and actionable",
            "Participants leave with clear next steps",
        ],
        "quality_tests": {
            "Engagement Test": {
                "check": "Activities engage all participants, not just the vocal ones",
                "pass": "Session design includes silent/written activities before group discussion",
                "fail": "Relies solely on open discussion, which favors extroverts",
            },
            "Output Quality Test": {
                "check": "Session produces a tangible, reusable artifact",
                "pass": "Documented output that can be shared with non-participants",
                "fail": "Session ends with verbal agreement but nothing written down",
            },
        },
    },
    "03-design": {
        "define_done": [
            "Design decisions are justified by user needs or established principles",
            "Visual hierarchy guides attention to the most important elements",
            "Design is accessible (WCAG AA minimum)",
            "Design is consistent with existing system patterns",
        ],
        "quality_tests": {
            "Accessibility Test": {
                "check": "Design meets WCAG AA contrast ratios and interaction requirements",
                "pass": "All text passes 4.5:1 contrast ratio, interactive elements have visible focus states",
                "fail": "Low-contrast text or missing keyboard navigation support",
            },
            "Consistency Test": {
                "check": "Design uses established patterns and tokens from the design system",
                "pass": "Colors, spacing, and typography match existing components",
                "fail": "New custom values introduced without justification",
            },
        },
    },
    "04-security": {
        "define_done": [
            "Threat vectors identified for the target system",
            "Vulnerabilities assessed with severity ratings",
            "Mitigation strategies provided with implementation guidance",
            "Security measures don't create unacceptable usability barriers",
        ],
        "quality_tests": {
            "Threat Coverage Test": {
                "check": "Analysis covers relevant OWASP categories for the system type",
                "pass": "Each relevant threat category assessed, even if risk is low",
                "fail": "Only obvious threats checked, subtle attack vectors ignored",
            },
            "Recovery Path Test": {
                "check": "Each vulnerability has a specific remediation path",
                "pass": "Mitigation includes exact code changes or configuration steps",
                "fail": "Advice is generic ('use encryption') without implementation specifics",
            },
        },
    },
    "05-infrastructure": {
        "define_done": [
            "Infrastructure configuration is reproducible (code, not clicks)",
            "Failure scenarios identified with recovery procedures",
            "Resource requirements estimated and within budget",
            "Security boundaries and access controls defined",
        ],
        "quality_tests": {
            "Reproducibility Test": {
                "check": "Infrastructure can be recreated from configuration alone",
                "pass": "All steps are scripted or documented as code",
                "fail": "Setup requires manual console clicks or undocumented steps",
            },
            "Rollback Test": {
                "check": "Changes can be reversed without data loss",
                "pass": "Rollback procedure documented and tested",
                "fail": "No rollback path defined for infrastructure changes",
            },
        },
    },
    "06-architecture": {
        "define_done": [
            "Architecture decisions documented with rationale and trade-offs",
            "Component boundaries and interfaces clearly defined",
            "Scalability and performance characteristics understood",
            "Dependencies identified and coupling minimized",
        ],
        "quality_tests": {
            "Trade-Off Test": {
                "check": "Alternatives were considered before choosing this architecture",
                "pass": "At least 2 alternative approaches evaluated with pros/cons",
                "fail": "Architecture chosen without considering alternatives",
            },
            "Scalability Test": {
                "check": "Architecture handles 10x current load without redesign",
                "pass": "Bottlenecks identified with specific scaling strategies",
                "fail": "No analysis of how the system behaves under increased load",
            },
        },
    },
    "06-strategy": {
        "define_done": [
            "Strategic situation assessed with evidence from multiple sources",
            "Key forces and dynamics identified and prioritized",
            "Recommendations account for constraints and trade-offs",
            "Action plan has clear owners and timelines",
        ],
        "quality_tests": {
            "Evidence Test": {
                "check": "Strategy is grounded in data and observations, not assumptions",
                "pass": "Each strategic recommendation traces to specific evidence",
                "fail": "Strategy based on intuition without supporting data",
            },
            "Completeness Test": {
                "check": "All relevant forces and stakeholders have been considered",
                "pass": "Analysis covers internal, external, and competitive dynamics",
                "fail": "Only internal factors considered, external forces ignored",
            },
        },
    },
    "07-copywriting": {
        "define_done": [
            "Copy serves the user's goal at this specific touchpoint",
            "Tone matches the brand voice and emotional context",
            "Copy is concise — no unnecessary words",
            "Accessible language (no jargon unless audience expects it)",
        ],
        "quality_tests": {
            "Clarity Test": {
                "check": "A first-time user understands the copy without context",
                "pass": "Copy uses plain language and active voice",
                "fail": "Copy requires domain knowledge or re-reading to understand",
            },
            "Action Test": {
                "check": "User knows exactly what to do after reading the copy",
                "pass": "Clear call-to-action or next step is obvious",
                "fail": "Copy describes a situation but doesn't guide the user forward",
            },
        },
    },
    "07-service-design": {
        "define_done": [
            "Service experience mapped from the customer's perspective",
            "Touchpoints across all channels identified and evaluated",
            "Pain points prioritized by impact and frequency",
            "Improvement opportunities linked to business outcomes",
        ],
        "quality_tests": {
            "Customer Perspective Test": {
                "check": "Analysis reflects actual customer experience, not internal assumptions",
                "pass": "Insights are based on customer data, quotes, or observed behavior",
                "fail": "Journey map reflects what we think customers experience, not reality",
            },
            "Systemic Test": {
                "check": "Analysis considers the full service ecosystem, not just one touchpoint",
                "pass": "Cross-channel handoffs and backstage processes are included",
                "fail": "Only the digital touchpoint analyzed, ignoring phone/in-person/email",
            },
        },
    },
    "08-ux-design": {
        "define_done": [
            "Design decisions based on user needs and behavior patterns",
            "Interaction flows tested against common user tasks",
            "Accessibility requirements met (WCAG AA)",
            "Edge cases and error states designed, not just happy path",
        ],
        "quality_tests": {
            "Task Completion Test": {
                "check": "Users can complete primary tasks without confusion",
                "pass": "Task flow has 5 or fewer steps, with clear progress indication",
                "fail": "Users get lost, need to backtrack, or can't find key features",
            },
            "Error Recovery Test": {
                "check": "Users can recover from mistakes without losing progress",
                "pass": "Error messages explain what went wrong and how to fix it",
                "fail": "Generic error messages or data loss on mistakes",
            },
        },
    },
    "09-design-systems": {
        "define_done": [
            "Design tokens/components follow system conventions",
            "Visual consistency maintained across all instances",
            "Documentation updated to reflect any changes",
            "Accessibility requirements preserved in implementation",
        ],
        "quality_tests": {
            "Consistency Test": {
                "check": "New work uses existing tokens and patterns, not custom values",
                "pass": "All colors, spacing, and type sizes reference design tokens",
                "fail": "Hard-coded values or one-off styles introduced",
            },
            "Scalability Test": {
                "check": "Patterns work across all supported contexts and screen sizes",
                "pass": "Component tested in smallest and largest supported viewport",
                "fail": "Pattern only works at one breakpoint or in one context",
            },
        },
    },
    "09-ui-development": {
        "define_done": [
            "UI matches design specifications (spacing, colors, typography)",
            "Component is responsive across supported breakpoints",
            "Keyboard and screen reader accessible",
            "Edge cases handled (empty states, overflow, loading)",
        ],
        "quality_tests": {
            "Visual Fidelity Test": {
                "check": "Implementation matches design within acceptable tolerance",
                "pass": "Spacing, colors, and typography match design tokens exactly",
                "fail": "Visible deviations from design that aren't documented as intentional",
            },
            "Accessibility Test": {
                "check": "Component is usable with keyboard-only and screen reader",
                "pass": "All interactive elements reachable by Tab, operable by Enter/Space",
                "fail": "Mouse-only interactions or missing ARIA labels",
            },
        },
    },
    "10-documentation": {
        "define_done": [
            "Documentation answers the reader's most likely questions",
            "Structure follows a logical flow (concept → usage → reference)",
            "Code examples are tested and runnable",
            "Kept in sync with the code it documents",
        ],
        "quality_tests": {
            "Accuracy Test": {
                "check": "All code examples and commands actually work",
                "pass": "Copy-pasting any code block produces the described result",
                "fail": "Examples are outdated or have syntax errors",
            },
            "Findability Test": {
                "check": "Readers can find what they need within 30 seconds",
                "pass": "Clear headings, table of contents, and search-friendly terms",
                "fail": "Important information buried in paragraphs without clear headings",
            },
        },
    },
    "11-engineering": {
        "define_done": [
            "Solution addresses the root cause, not just symptoms",
            "Code is readable, testable, and follows project conventions",
            "Performance implications understood and acceptable",
            "Error handling covers likely failure modes",
        ],
        "quality_tests": {
            "Correctness Test": {
                "check": "Solution produces correct results for all specified inputs",
                "pass": "Happy path, edge cases, and error cases all handled correctly",
                "fail": "Works for common cases but breaks on edge cases or errors",
            },
            "Maintainability Test": {
                "check": "Another developer can understand and modify the code",
                "pass": "Clear naming, single responsibility, minimal coupling",
                "fail": "Complex logic without explanation, or high coupling to other modules",
            },
        },
    },
    "12-industrial-design": {
        "define_done": [
            "Design decisions tied to functional requirements and user needs",
            "Material choices justified by use context and lifecycle",
            "Form follows function — no purely decorative elements",
            "Evaluation criteria are specific and measurable",
        ],
        "quality_tests": {
            "Functional Necessity Test": {
                "check": "Every design element serves a clear purpose",
                "pass": "Each element can be justified by a user need or functional requirement",
                "fail": "Decorative elements that don't serve function or communication",
            },
            "Longevity Test": {
                "check": "Design ages gracefully in its intended use context",
                "pass": "Materials and form will look appropriate after years of use",
                "fail": "Trend-dependent styling that will look dated within 2 years",
            },
        },
    },
    "13-personal-finance": {
        "define_done": [
            "Financial data gathered and categorized accurately",
            "Analysis based on actual numbers, not estimates",
            "Recommendations account for tax implications and time horizon",
            "Action steps are specific and prioritized",
        ],
        "quality_tests": {
            "Accuracy Test": {
                "check": "All calculations are correct and assumptions are stated",
                "pass": "Numbers are verifiable and assumptions clearly documented",
                "fail": "Rough estimates presented as precise figures",
            },
            "Completeness Test": {
                "check": "Analysis considers tax implications and opportunity costs",
                "pass": "Tax impact calculated for each recommendation",
                "fail": "Pre-tax returns presented without noting tax drag",
            },
        },
    },
    "14-health-fitness": {
        "define_done": [
            "Program designed for the individual's goals and current level",
            "Progressive overload or adaptation principle applied",
            "Recovery and sustainability considered, not just intensity",
            "Measurable markers of progress defined",
        ],
        "quality_tests": {
            "Individualization Test": {
                "check": "Program accounts for the person's specific constraints",
                "pass": "Equipment, time, experience level, and limitations all factored in",
                "fail": "Generic program without adaptation to individual context",
            },
            "Sustainability Test": {
                "check": "Program is maintainable for the intended duration",
                "pass": "Volume and intensity are realistic for the person's lifestyle",
                "fail": "Program requires unsustainable time commitment or intensity",
            },
        },
    },
    "15-life-management": {
        "define_done": [
            "System or plan addresses the specific life area",
            "Steps are concrete and actionable, not aspirational",
            "Time and resource requirements estimated realistically",
            "Progress tracking mechanism defined",
        ],
        "quality_tests": {
            "Practicality Test": {
                "check": "Plan fits within actual available time and resources",
                "pass": "Total time commitment estimated and fits available schedule",
                "fail": "Plan assumes unlimited time or resources",
            },
            "Completeness Test": {
                "check": "Plan covers the full scope of the task or system",
                "pass": "All steps from start to finish are enumerated",
                "fail": "Key steps missing or assumed to be obvious",
            },
        },
    },
    "16-marketing-strategy": {
        "define_done": [
            "Strategy grounded in audience data and market context",
            "Channels and tactics aligned to audience behavior",
            "Success metrics defined with specific targets",
            "Budget and resource requirements estimated",
        ],
        "quality_tests": {
            "Audience Alignment Test": {
                "check": "Strategy targets where the audience actually is, not assumptions",
                "pass": "Channel selection backed by audience research or data",
                "fail": "Channels chosen based on trends rather than audience behavior",
            },
            "Measurability Test": {
                "check": "Every tactic has a specific, measurable success metric",
                "pass": "KPIs defined with target numbers and measurement method",
                "fail": "Goals are vague ('increase awareness') without measurable targets",
            },
        },
    },
}


def generate_keywords(name: str, description: str) -> list[str]:
    """Generate keywords from skill name and description."""
    # Start with name parts
    words = name.replace("-", " ").split()
    keywords = list(words)

    # Add meaningful words from description (skip common words)
    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "use",
        "when",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "where",
        "why",
        "not",
        "no",
        "nor",
        "so",
        "than",
        "too",
        "very",
        "just",
        "about",
        "above",
        "after",
        "again",
        "all",
        "also",
        "am",
        "any",
        "because",
        "before",
        "between",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "over",
        "same",
        "some",
        "such",
        "then",
        "there",
        "through",
        "under",
        "up",
        "down",
        "out",
        "off",
        "into",
        "during",
        "until",
        "while",
    }
    desc_words = re.findall(r"[a-z][a-z-]+", description.lower())
    for w in desc_words:
        if w not in stop_words and w not in keywords and len(w) > 3:
            keywords.append(w)
            if len(keywords) >= 10:
                break

    return keywords


def parse_frontmatter(content: str) -> tuple[dict, str, str]:
    """Parse YAML frontmatter and body. Returns (frontmatter_lines, frontmatter_text, body)."""
    if not content.startswith("---"):
        return {}, "", content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, "", content

    fm_text = content[4:end]
    body = content[end + 4 :]  # skip \n---
    return {}, fm_text, body


def get_category(skill_path: Path) -> str:
    """Get category name from skill path."""
    return skill_path.parent.parent.name


def find_insert_point_after(body: str, section: str) -> int:
    """Find position after a section heading (before next ## heading)."""
    pattern = re.compile(rf"^## {re.escape(section)}", re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return -1

    # Find next ## heading
    next_heading = re.search(r"\n## ", body[match.end() :])
    if next_heading:
        return match.end() + next_heading.start()
    return len(body)


def find_insert_point_before(body: str, section: str) -> int:
    """Find position before a section heading."""
    pattern = re.compile(rf"^## {re.escape(section)}", re.MULTILINE)
    match = pattern.search(body)
    if match:
        return match.start()
    return -1


def build_define_done(category: str, name: str) -> str:
    """Build Define Done section from category template."""
    template = CATEGORY_TEMPLATES.get(category, CATEGORY_TEMPLATES.get("11-engineering"))
    if not template:
        return ""

    items = template["define_done"]
    lines = ["\n## Define Done\n\n"]
    for item in items:
        lines.append(f"- [ ] {item}\n")
    return "".join(lines)


def build_quality_tests(category: str) -> str:
    """Build Quality Tests section from category template."""
    template = CATEGORY_TEMPLATES.get(category, CATEGORY_TEMPLATES.get("11-engineering"))
    if not template:
        return ""

    tests = template["quality_tests"]
    lines = ["\n## Quality Tests\n"]
    for test_name, test_data in tests.items():
        lines.append(f"\n### {test_name}\n")
        lines.append(f"- {test_data['check']}\n")
        lines.append(f"- **PASS:** {test_data['pass']}\n")
        lines.append(f"- **FAIL:** {test_data['fail']}\n")
    return "".join(lines)


def upgrade_skill(skill_file: Path) -> dict:
    """Upgrade a single skill file. Returns dict of changes made."""
    content = skill_file.read_text()
    changes = []
    category = get_category(skill_file)

    # Parse frontmatter
    if not content.startswith("---"):
        return {"path": str(skill_file), "changes": ["SKIP: no frontmatter"]}

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {"path": str(skill_file), "changes": ["SKIP: malformed frontmatter"]}

    fm_text = content[: end_idx + 4]  # includes opening --- and closing ---
    body = content[end_idx + 4 :]

    # --- Fix frontmatter ---

    # Add keywords if missing
    if "keywords:" not in fm_text:
        # Extract name and description
        name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
        desc_match = re.search(
            r"^description:\s*(.+?)(?:\n\S|\n---)", fm_text, re.MULTILINE | re.DOTALL
        )

        if name_match and desc_match:
            name = name_match.group(1).strip()
            desc = desc_match.group(1).strip().replace("\n", " ").replace("  ", " ")
            keywords = generate_keywords(name, desc)
            kw_str = '["' + '", "'.join(keywords) + '"]'

            if "triggers:" in fm_text:
                # Add keywords under existing triggers
                fm_text = fm_text.replace(
                    "triggers:",
                    f"triggers:\n  keywords: {kw_str}",
                )
            else:
                # Add triggers block before allowed-tools or before closing ---
                if "allowed-tools:" in fm_text:
                    fm_text = fm_text.replace(
                        "allowed-tools:",
                        f"triggers:\n  keywords: {kw_str}\nallowed-tools:",
                    )
                else:
                    fm_text = fm_text.replace(
                        "\n---",
                        f"\ntriggers:\n  keywords: {kw_str}\n---",
                        1,
                    )
            changes.append(f"Added keywords: {keywords[:5]}...")

    # Add allowed-tools if missing
    if "allowed-tools:" not in fm_text:
        fm_text = fm_text.replace(
            "\n---",
            "\nallowed-tools: Read, Write, Edit\n---",
            1,
        )
        changes.append("Added allowed-tools: Read, Write, Edit")

    # --- Fix body ---

    # Add Define Done if missing
    if "## Define Done" not in body:
        dd_content = build_define_done(category, "")

        # Try to insert after Overview
        insert_pos = find_insert_point_after(body, "Overview")
        if insert_pos == -1:
            # Try after first ## heading
            first_heading = re.search(r"\n## ", body)
            if first_heading:
                insert_pos = find_insert_point_after(
                    body,
                    body[
                        first_heading.start() + 4 : body.find("\n", first_heading.start() + 4)
                    ].strip(),
                )

        if insert_pos == -1:
            # Insert after first paragraph (find first double newline after content starts)
            first_content = re.search(r"\n\n", body[1:])
            if first_content:
                insert_pos = first_content.start() + 1

        if insert_pos > 0:
            body = body[:insert_pos] + "\n" + dd_content + body[insert_pos:]
            changes.append("Added Define Done section")

    # Add Quality Tests if missing
    if "## Quality Tests" not in body:
        qt_content = build_quality_tests(category)

        # Try to insert before Guidelines
        insert_pos = find_insert_point_before(body, "Guidelines")
        if insert_pos == -1:
            # Try before References
            insert_pos = find_insert_point_before(body, "References")
        if insert_pos == -1:
            # Append to end
            insert_pos = len(body)

        if insert_pos > 0:
            body = body[:insert_pos] + "\n" + qt_content + "\n" + body[insert_pos:]
            changes.append("Added Quality Tests section")

    # Reconstruct file
    if changes:
        new_content = fm_text + body
        if not DRY_RUN:
            skill_file.write_text(new_content)

    return {"path": str(skill_file), "changes": changes}


def main():
    skills_root = (
        Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else Path(".")
    )

    # Find all SKILL.md files (excluding reference directory)
    skill_files = sorted(f for f in skills_root.rglob("SKILL.md") if "00-reference" not in str(f))

    print(f"Found {len(skill_files)} skills in {skills_root}")
    if DRY_RUN:
        print("DRY RUN — no files will be modified\n")

    total = 0
    modified = 0
    by_change = {"keywords": 0, "allowed-tools": 0, "define_done": 0, "quality_tests": 0}

    for sf in skill_files:
        result = upgrade_skill(sf)
        total += 1
        if result["changes"] and "SKIP" not in str(result["changes"]):
            modified += 1
            rel_path = str(sf).replace(str(skills_root) + "/", "")
            changes_str = "; ".join(result["changes"])
            print(f"  {rel_path}: {changes_str}")

            for c in result["changes"]:
                if "keyword" in c.lower():
                    by_change["keywords"] += 1
                if "allowed-tools" in c.lower():
                    by_change["allowed-tools"] += 1
                if "Define Done" in c:
                    by_change["define_done"] += 1
                if "Quality Tests" in c:
                    by_change["quality_tests"] += 1

    print("\n=== Summary ===")
    print(f"Total skills:     {total}")
    print(f"Modified:         {modified}")
    print(f"Keywords added:   {by_change['keywords']}")
    print(f"Allowed-tools:    {by_change['allowed-tools']}")
    print(f"Define Done:      {by_change['define_done']}")
    print(f"Quality Tests:    {by_change['quality_tests']}")


if __name__ == "__main__":
    main()
