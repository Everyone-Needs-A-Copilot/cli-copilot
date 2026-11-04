#!/usr/bin/env python3
"""Render the registered Click/Typer command tree without invoking command callbacks.

Run in the target CLI's environment. Imports are trusted project code, not a sandbox.
Network connections are refused during import and rendering. Output goes to stdout;
redirect it to a new reference file, or compare it with the maintained reference.
"""

from __future__ import annotations

import argparse
import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout


def deny_network(event: str, args: tuple) -> None:
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto"}:
        raise RuntimeError("CLI reference export must not access the network")


def render(command, name: str, click, require_purpose: bool = False) -> str:

    sections = [
        f"# {name} command reference",
        "",
        "Generated from the registered parser. Command callbacks were not executed. For intent, effects, configuration and recovery, read the companion CLI guide.",
        "",
    ]

    def walk(cmd, path: str, parent=None):
        if require_purpose and not (cmd.help or "").strip():
            raise ValueError(f"Missing command purpose: {path}")
        context = click.Context(cmd, info_name=path.split()[-1], parent=parent)
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(buffer):
            help_text = cmd.get_help(context)
        sections.extend(
            [f"## `{path}`", "", "```text", (buffer.getvalue() + help_text).rstrip(), "```", ""]
        )
        if callable(getattr(cmd, "list_commands", None)) and callable(
            getattr(cmd, "get_command", None)
        ):
            for child_name in cmd.list_commands(context):
                child = cmd.get_command(context, child_name)
                if child is None:
                    raise ValueError(f"Registered command cannot be resolved: {path} {child_name}")
                walk(child, f"{path} {child_name}", context)

    walk(command, name)
    return "\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Usage and maintenance contract: docs/04-cli-standard.md. Exit 0 produces Markdown; import/render errors exit nonzero. No credentials required. This tool never runs CLI actions.",
    )
    parser.add_argument("target", help="Importable module:attribute, e.g. copilot_cli.main:app")
    parser.add_argument("--name", required=True, help="Installed command name for usage paths")
    parser.add_argument(
        "--factory",
        action="store_true",
        help="Call an explicitly reviewed, side-effect-free argparse parser factory",
    )
    parser.add_argument(
        "--require-purpose",
        action="store_true",
        help="Reject commands or groups without a purpose description",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_network)
    module, separator, attribute = args.target.partition(":")
    if not separator:
        parser.error("target must be module:attribute")
    obj = getattr(importlib.import_module(module), attribute)
    if args.factory:
        obj = obj()
    if isinstance(obj, argparse.ArgumentParser):
        sections = [
            f"# {args.name} command reference",
            "",
            "Generated from the argparse parser. Actions were not executed. Read the companion CLI guide for intent and effects.",
            "",
        ]

        def walk_argparse(cmd, name):
            if args.require_purpose and not (cmd.description or "").strip():
                raise ValueError(f"Missing command purpose: {name}")
            sections.extend([f"## `{name}`", "", "```text", cmd.format_help().rstrip(), "```", ""])
            for action in cmd._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for child_name, child in action.choices.items():
                        walk_argparse(child, name + " " + child_name)

        walk_argparse(obj, args.name)
        print("\n".join(sections))
        return 0
    try:
        from typer import Typer
    except ImportError:
        Typer = ()
    if isinstance(obj, Typer):
        import typer.main

        obj = typer.main.get_command(obj)
        # Typer 0.27+ vendors Click; use the target parser's own types.
        click = getattr(typer.main, "_click", None)
        if click is None:
            import click
    else:
        import click

        if not isinstance(obj, click.Command):
            parser.error("target is not a Click command or Typer app")
    print(render(obj, args.name, click, args.require_purpose))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
