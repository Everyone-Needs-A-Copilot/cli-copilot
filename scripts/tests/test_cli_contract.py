"""Behavior checks for CLI documentation tooling, with no service operations."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guide_check", SCRIPTS / "check-cli-guide.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class GuideContractTests(unittest.TestCase):
    def setUp(self):
        # Retain fixtures for diagnosis; do not remove other sessions' evidence.
        self.root = Path(tempfile.mkdtemp(prefix="cli-contract-"))
        self.guide = self.root / "CLI.md"
        self.valid = (
            "# CLI\n\ncli --help\n\n| Intent | Command | Result |\n|---|---|---|\n| Discover | cli --help | Usage |\n\n"
            + "\n".join(f"## {section}\n\nConcrete usage.\n" for section in checker.SECTIONS)
        )

    def check(self, text):
        self.guide.write_text(text)
        return checker.check(self.guide)

    def test_complete_guide_passes(self):
        self.assertEqual([], self.check(self.valid))

    def test_missing_and_empty_sections_fail(self):
        for section in checker.SECTIONS:
            for replacement in ("", f"## {section}\n\n"):
                with self.subTest(section=section, replacement=replacement):
                    errors = self.check(
                        self.valid.replace(f"## {section}\n\nConcrete usage.\n", replacement)
                    )
                    self.assertTrue(any(section in error for error in errors), errors)

    def test_broken_link_fails_and_existing_relative_link_passes(self):
        text = self.valid + "\n[Reference](commands.md)\n"
        self.assertTrue(any("broken local link" in error for error in self.check(text)))
        (self.root / "commands.md").write_text("Command reference")
        self.assertEqual([], self.check(text))

    def test_missing_discovery_intent_and_placeholder_fail(self):
        for text, expected in (
            (self.valid.replace("--help", "help"), "help invocation"),
            (self.valid.replace("| Intent |", "| Goal |"), "intent-to-command"),
            (self.valid + "\nTODO", "placeholder"),
        ):
            self.assertTrue(any(expected in e for e in self.check(text)))

    def test_process_status_distinguishes_invalid_document(self):
        self.guide.write_text("# Incomplete\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check-cli-guide.py"), str(self.guide)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("missing or empty", result.stderr)

    def export(self, source, *options):
        (self.root / "fixture_cli.py").write_text(source)
        import os

        env = dict(os.environ, PYTHONPATH=str(self.root), PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "export-cli-reference.py"),
                "fixture_cli:app",
                "--name",
                "fixture",
                *options,
            ],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_click_nested_aliases_options_without_callbacks(self):
        result = self.export('''import click
@click.group()
def app():
    raise AssertionError("group callback executed")
@app.command()
@click.option("--mode", type=click.Choice(["read", "write"]), default="read", show_default=True)
def inspect(mode):
    """Inspect the selected record."""
    raise AssertionError("business callback executed")
app.add_command(inspect, "show")
''')
        self.assertEqual(0, result.returncode, result.stderr)
        for expected in (
            "## `fixture inspect`",
            "## `fixture show`",
            "--mode",
            "read|write",
            "Inspect the selected record",
        ):
            self.assertIn(expected, result.stdout)

    def test_argparse_factory_does_not_run_actions(self):
        result = self.export(
            """import argparse
class Action(argparse.Action):
    def __call__(self, *args, **kwargs):
        raise AssertionError("action executed")
def app():
    parser = argparse.ArgumentParser(prog="fixture")
    child = parser.add_subparsers().add_parser("inspect", aliases=["show"])
    child.add_argument("--value", action=Action)
    return parser
""",
            "--factory",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("## `fixture show`", result.stdout)
        self.assertIn("--value", result.stdout)

    def test_import_network_is_refused(self):
        result = self.export("""import socket
socket.getaddrinfo("localhost", 80)
app = None
""")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("must not access the network", result.stderr)

    def test_missing_command_purpose_is_rejected(self):
        result = self.export(
            """import click
@click.command()
def app():
    raise AssertionError("callback executed")
""",
            "--require-purpose",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Missing command purpose: fixture", result.stderr)


if __name__ == "__main__":
    unittest.main()
