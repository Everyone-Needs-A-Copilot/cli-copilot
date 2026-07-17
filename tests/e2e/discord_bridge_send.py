#!/usr/bin/env python3
"""Playwright harness: send a message into a Discord thread as a real user.

Drives the real Discord web UI (not the API) so it exercises the exact path a
human takes: type in the thread's message box and press Enter. Used to test the
Discord -> bridge -> local-session loop end to end.

Auth uses a dedicated persistent browser profile, so you log into Discord once
in the launched window and the session sticks for future runs.

Usage:
  # One-time (or whenever the session expires): open Discord and log in.
  python tests/e2e/discord_bridge_send.py --login

  # Send a message to a thread as the logged-in user.
  python tests/e2e/discord_bridge_send.py \
      --url https://discord.com/channels/<guild>/<thread> \
      --message "hello from the real Discord UI"

  # Verify a CLI-sent message is visible in the real Discord UI.
  python tests/e2e/discord_bridge_send.py \
      --url https://discord.com/channels/<guild>/<thread> \
      --expect-text "message posted by copilot discord notify"

Exit codes: 0 = success, 2 = not logged in, 3 = message box / send failure,
4 = expected text not visible.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path.home() / ".copilot-cli" / "discord" / "pw-profile"

# Discord's composer is a Slate editor exposed as an ARIA textbox.
COMPOSER_SELECTORS = (
    'div[role="textbox"][data-slate-editor="true"]',
    'div[role="textbox"]',
    'div[data-slate-editor="true"]',
)


def _find_composer(page, timeout_ms: int):
    deadline = time.time() + timeout_ms / 1000
    last_err: Exception | None = None
    while time.time() < deadline:
        for sel in COMPOSER_SELECTORS:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    return loc
            except Exception as exc:
                last_err = exc
        page.wait_for_timeout(500)
    if last_err:
        raise last_err
    raise PWTimeout(f"composer not found within {timeout_ms}ms")


def _wait_for_text(page, text: str, timeout_ms: int) -> None:
    """Wait until Discord renders ``text`` somewhere in the loaded thread."""
    page.get_by_text(text, exact=True).first.wait_for(timeout=timeout_ms)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://discord.com/channels/@me")
    ap.add_argument("--message", default="")
    ap.add_argument(
        "--expect-text",
        default="",
        help="Wait until this exact text is visible in the loaded Discord thread.",
    )
    ap.add_argument(
        "--login", action="store_true", help="Open and wait for manual login, then exit."
    )
    ap.add_argument(
        "--timeout", type=int, default=180, help="Seconds to wait for login / composer."
    )
    ap.add_argument(
        "--keep-open", type=int, default=0, help="Seconds to keep the browser open after sending."
    )
    args = ap.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url, wait_until="domcontentloaded")

        if args.login:
            print(
                f"Log into Discord in the opened window. Waiting up to {args.timeout}s...",
                flush=True,
            )
            try:
                _find_composer(page, args.timeout * 1000)
                print("LOGIN_OK: composer detected — you're logged in and on a channel.")
                rc = 0
            except Exception:
                print(
                    "LOGIN_TIMEOUT: could not detect the composer (not logged in or no channel open)."
                )
                rc = 2
            if args.keep_open:
                page.wait_for_timeout(args.keep_open * 1000)
            ctx.close()
            return rc

        if not args.message and not args.expect_text:
            print("ERROR: --message or --expect-text is required when not using --login")
            ctx.close()
            return 3

        if args.message:
            try:
                composer = _find_composer(page, args.timeout * 1000)
            except Exception:
                print("NOT_LOGGED_IN: composer not found. Run with --login first.")
                ctx.close()
                return 2

            composer.click()
            page.keyboard.type(args.message, delay=15)
            page.keyboard.press("Enter")
            # Give Discord a moment to POST the message and echo it back.
            page.wait_for_timeout(2500)
            print(f"SENT: {args.message}")
        if args.expect_text:
            try:
                _wait_for_text(page, args.expect_text, args.timeout * 1000)
            except Exception:
                print(f"TEXT_NOT_FOUND: {args.expect_text}")
                ctx.close()
                return 4
            print(f"VISIBLE: {args.expect_text}")
        if args.keep_open:
            page.wait_for_timeout(args.keep_open * 1000)
        ctx.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
