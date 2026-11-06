#!/usr/bin/env python3
"""Install, check or roll back the stable `copilot` launcher.

install-cli.py install [--dev [PATH]] [--bin-dir DIR] [--home DIR]
install-cli.py check | rollback
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from copilot_cli import launcher_install as li  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check", "rollback"))
    parser.add_argument("--dev", nargs="?", const=str(REPO), default=None, metavar="PATH")
    parser.add_argument("--bin-dir")
    parser.add_argument("--home")
    parser.add_argument("--python")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--to")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = li.install(args.home, args.bin_dir, args.python, args.dev)
        elif args.command == "check":
            result = li.check(args.home, args.bin_dir)
        else:
            result = li.rollback(args.home, steps=args.steps, to=args.to)
    except li.InstallerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
