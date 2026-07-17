#!/usr/bin/env python3
"""Human-readable live connectivity smoke check for Copilot CLI services."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from typer.testing import CliRunner

from copilot_cli.main import app


@dataclass
class Check:
    name: str
    args: list[str]


CHECKS: list[Check] = [
    Check("core", ["health"]),
    Check("git", ["git", "status", "--path", "."]),
    Check("docker", ["docker", "health"]),
    Check("shell", ["shell", "ps"]),
    Check("filesystem", ["fs", "health"]),
    Check("services", ["services", "health"]),
    Check("postgresql", ["db", "health"]),
    Check("nocodb", ["crm", "health"]),
    Check("brevo", ["brevo", "health"]),
    Check("n8n", ["n8n", "health"]),
    Check("docs", ["docs", "health"]),
    Check("bi", ["bi", "health"]),
    Check("monitoring", ["monitoring", "health"]),
]


def _reason_text(result) -> str:
    text = (result.output or "").strip()
    if result.exception is not None:
        text = f"{text}\n{result.exception}".strip()
    return " ".join(text.split())


def _classify_env_failure(reason: str) -> str | None:
    lower = reason.lower()
    if "bad revision" in lower or "no upstream configured" in lower:
        return "No upstream branch configured"
    if "does not have any commits yet" in lower:
        return "Repository has no commits yet"
    if "docker" in lower and ("operation not permitted" in lower or "permission denied" in lower):
        return "Docker socket permission denied"
    if "operation not permitted" in lower or "permission denied" in lower:
        return "Local command blocked by OS/sandbox permissions"
    if "missing required configuration" in lower or "not configured" in lower:
        return "Missing service configuration"
    if "api key" in lower or "access token" in lower:
        return "Missing/invalid credentials"
    if (
        "cannot connect to" in lower
        or "connection refused" in lower
        or "name or service not known" in lower
        or "temporary failure in name resolution" in lower
        or "timed out" in lower
        or "network is unreachable" in lower
    ):
        return "Service unreachable (network/DNS/firewall)"
    return None


def _run_check(runner: CliRunner, check: Check) -> tuple[str, str]:
    result = runner.invoke(app, check.args)
    if result.exit_code == 0:
        return "PASS", ""

    reason_full = _reason_text(result)
    env_reason = _classify_env_failure(reason_full)
    if env_reason is not None:
        return "SKIP", env_reason
    display = reason_full[:180] + ("..." if len(reason_full) > 180 else "")
    return "FAIL", display or f"exit code {result.exit_code}"


def main() -> int:
    os.environ["COPILOT_E2E_LIVE"] = "1"
    start = time.time()
    runner = CliRunner()

    print("============================================================")
    print("CLI Copilot E2E Connectivity (Human Summary)")
    print("============================================================")

    rows: list[tuple[str, str, str]] = []
    for check in CHECKS:
        status, reason = _run_check(runner, check)
        rows.append((check.name, status, reason))

    # Coolify check (reads from .env via CLI config loader as well as process env)
    status, reason = _run_check(runner, Check("coolify", ["coolify", "version"]))
    rows.append(("coolify", status, reason))

    print("")
    print("Service      Status  Notes")
    print("-----------  ------  --------------------------------------------------------------")
    for name, status, reason in rows:
        note = reason if reason else "-"
        print(f"{name:<11}  {status:<6}  {note}")

    passed = sum(1 for _, s, _ in rows if s == "PASS")
    skipped = sum(1 for _, s, _ in rows if s == "SKIP")
    failed = sum(1 for _, s, _ in rows if s == "FAIL")
    duration = int(time.time() - start)

    print("")
    print("Summary")
    print("-------")
    print(f"PASS: {passed}")
    print(f"SKIP: {skipped} (environment/config dependent)")
    print(f"FAIL: {failed} (action needed)")
    print(f"Duration: {duration}s")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
