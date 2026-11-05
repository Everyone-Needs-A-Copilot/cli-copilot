#!/usr/bin/env python3
"""Check CLI guides for required sections and broken local links; never run commands."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

SECTIONS = (
    "Purpose",
    "Setup and identity",
    "Command discovery",
    "Intent and examples",
    "Inputs and outputs",
    "Effects and verification",
    "Errors and recovery",
    "Maintenance",
)


def check(path: Path) -> list[str]:
    if not path.is_file():
        return [f"{path}: missing guide"]
    text = path.read_text(encoding="utf-8")
    errors = []
    for section in SECTIONS:
        match = re.search(
            r"^## " + re.escape(section) + r"[^\S\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S
        )
        if not match or not match.group(1).strip():
            errors.append(f"{path}: missing or empty section: {section}")
    if "--help" not in text:
        errors.append(f"{path}: no help invocation")
    if not re.search(r"^\|.*Intent.*\|.*Command.*\|", text, re.M | re.I):
        errors.append(f"{path}: missing intent-to-command table")
    if re.search(r"\b(?:REPLACE|TODO|TBD)\b", text):
        errors.append(f"{path}: unfinished placeholder")
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
        link = urlsplit(target.strip("<>"))
        if link.scheme or not link.path:
            continue
        resolved = path.parent / unquote(link.path)
        if not resolved.exists():
            errors.append(f"{path}: broken local link: {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Standard and usage: docs/04-cli-standard.md. Read-only; exit 0 passes structural checks, 1 reports defects, 2 is invalid usage. No credentials or network required.",
    )
    parser.add_argument(
        "guides",
        type=Path,
        nargs="+",
        help="Markdown guide paths; resolves links relative to each guide",
    )
    args = parser.parse_args()
    errors = [error for path in args.guides for error in check(path)]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"CLI guide structure: PASS ({len(args.guides)} guides; semantic verification separate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
