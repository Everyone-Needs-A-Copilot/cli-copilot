"""Installer for the stable `copilot` launcher (central resolution).

The launcher is a tiny stdlib-only script that resolves the CLI code and its
tier overlays through the release pointer `~/.copilot/current` (release.json
schema 1, components `cli-copilot` and `cli/<tier>`). It is written once and
never rewritten per release: a release flip changes what `current` points at,
not the launcher. A dev marker (`~/.copilot/cli-dev.json`) redirects the
launcher to a working checkout instead.

Every function takes an injectable `home` so tests never touch the real one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Mirrors cc.core.release.engine.layout (contract: schema 1, commit 609c77b).
COPILOT_DIRNAME = ".copilot"
CURRENT_NAME = "current"
MANIFEST_NAME = "release.json"
COMPONENT_CLI = "cli-copilot"
# Overlay tiers in ascending precedence; the launcher puts the highest first.
OVERLAY_TIERS = ("organization", "department-accounting", "personal")
RELEASE_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-z]{1,40}")
DEV_MARKER_NAME = "cli-dev.json"
RECEIPT_NAME = "cli-install.json"
LAUNCHER_NAME = "copilot"
INFO_FLAG = "--launcher-info"

LAUNCHER_TEMPLATE = """#!{python}
# Managed by cli-copilot `copilot_cli.launcher_install`; do not edit.
# Stable by design: resolves through ~/.copilot/current, never rewritten per release.
import json
import os
import sys
from pathlib import Path

home = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
current = home / "current"
tiers = ("personal", "department-accounting", "organization")
info = {{"mode": "release", "release": None, "commit": None}}
paths = []

dev = home / "cli-dev.json"
if dev.is_file():
    root = json.loads(dev.read_text(encoding="utf-8"))["path"]
    paths.append(root)
    info.update(mode="dev", commit="dev")
else:
    manifest = current / "release.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        rows = {{row["name"]: row for row in data["components"]}}
        cli = rows["cli-copilot"]
    except (OSError, ValueError, KeyError) as exc:
        sys.exit("copilot: no usable release at %s (%s). Run the cli installer." % (current, exc))
    info.update(release=data["release"], commit=cli.get("commit") or None)
    for tier in tiers:
        row = rows.get("cli/" + tier)
        if row and row.get("path"):
            overlay = current / row["path"]
            if overlay.is_dir():
                paths.append(str(overlay))
    paths.append(str(current / cli["path"]))
    os.environ["COPILOT_RELEASE_ID"] = data["release"]
    os.environ["COPILOT_RELEASE_COMMIT"] = cli.get("commit") or ""

# Remove any ambient copy (e.g. a stale base-cli) from the import path.
sys.path[:] = [p for p in sys.path if "base-cli" not in p]
sys.path[0:0] = paths

if sys.argv[1:] == ["{info_flag}"]:
    import copilot_cli

    info["module"] = str(Path(copilot_cli.__file__).resolve())
    info["paths"] = paths
    print(json.dumps(info))
    sys.exit(0)

from copilot_cli.main import app

app()
"""


class InstallerError(RuntimeError):
    """An install, check or rollback step cannot proceed."""


def copilot_home(home: Path | str | None = None) -> Path:
    return (Path(home) if home is not None else Path.home()) / COPILOT_DIRNAME


def default_bin_dir(home: Path | str | None = None) -> Path:
    return (Path(home) if home is not None else Path.home()) / ".local" / "bin"


def render_launcher(python: str | None = None) -> str:
    return LAUNCHER_TEMPLATE.format(python=python or sys.executable, info_flag=INFO_FLAG)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_manifest(release_dir: Path) -> dict[str, Any]:
    path = release_dir / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["schema"] != 1 or not RELEASE_ID.fullmatch(data["release"]):
            raise ValueError("unsupported schema or release id")
        rows = {row["name"]: row for row in data["components"]}
        rows[COMPONENT_CLI]["path"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InstallerError(f"no usable release.json in {release_dir}: {exc}") from exc
    return data


def install(
    home: Path | str | None = None,
    bin_dir: Path | str | None = None,
    python: str | None = None,
    dev_path: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write the launcher (only if changed), the dev marker and the receipt.

    Idempotent: a second identical call changes nothing and reports
    `changed: false`. Without `dev_path` any dev marker is removed so the
    launcher resolves through the pointer; the pointer must already exist.
    """
    chome = copilot_home(home)
    target_dir = Path(bin_dir) if bin_dir is not None else default_bin_dir(home)
    launcher = target_dir / LAUNCHER_NAME
    changed: list[str] = []

    text = render_launcher(python)
    if not launcher.is_file() or launcher.read_text(encoding="utf-8") != text:
        _atomic_write(launcher, text, 0o755)
        changed.append("launcher")

    marker = chome / DEV_MARKER_NAME
    if dev_path is not None:
        root = Path(dev_path).resolve()
        if not (root / "copilot_cli" / "__init__.py").is_file():
            raise InstallerError(f"{root} is not a cli-copilot checkout")
        body = json.dumps({"path": str(root)}, indent=2) + "\n"
        if not marker.is_file() or marker.read_text(encoding="utf-8") != body:
            _atomic_write(marker, body)
            changed.append("dev-marker")
        mode, release = "dev", None
    else:
        if marker.is_file():
            marker.unlink()
            changed.append("dev-marker-removed")
        current = chome / CURRENT_NAME
        if not (current / MANIFEST_NAME).is_file():
            raise InstallerError(
                f"{current} has no {MANIFEST_NAME}; build a release or use --dev <checkout>"
            )
        mode, release = "release", read_manifest(current)["release"]

    receipt = {
        "schema": 1,
        "mode": mode,
        "launcher": str(launcher),
        "launcher_sha256": _sha(text),
        "python": python or sys.executable,
        "dev_path": str(Path(dev_path).resolve()) if dev_path is not None else None,
        "release": release,
    }
    receipt_path = chome / RECEIPT_NAME
    previous = None
    if receipt_path.is_file():
        try:
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        except ValueError:
            previous = None
    stable = {k: v for k, v in (previous or {}).items() if k != "installed"}
    if stable != receipt:
        stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _atomic_write(receipt_path, json.dumps({**receipt, "installed": stamp}, indent=2) + "\n")
        changed.append("receipt")
    return {"changed": bool(changed), "steps": changed, **receipt}


def launcher_info(
    home: Path | str | None = None, bin_dir: Path | str | None = None
) -> dict[str, Any]:
    """Run the installed launcher's identity probe (what `copilot` would import)."""
    launcher = (Path(bin_dir) if bin_dir is not None else default_bin_dir(home)) / LAUNCHER_NAME
    if not launcher.is_file():
        raise InstallerError(f"launcher not installed at {launcher}")
    env = {**os.environ, "COPILOT_HOME": str(copilot_home(home))}
    proc = subprocess.run(
        [str(launcher), INFO_FLAG], capture_output=True, text=True, env=env, check=False
    )
    if proc.returncode != 0:
        raise InstallerError(f"launcher probe failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return json.loads(proc.stdout)


def check(home: Path | str | None = None, bin_dir: Path | str | None = None) -> dict[str, Any]:
    """Verify launcher content, the receipt and the module path against the release."""
    chome = copilot_home(home)
    launcher = (Path(bin_dir) if bin_dir is not None else default_bin_dir(home)) / LAUNCHER_NAME
    problems: list[str] = []
    info = launcher_info(home, bin_dir)
    receipt_path = chome / RECEIPT_NAME
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        actual = _sha(launcher.read_text(encoding="utf-8"))
        if actual != receipt.get("launcher_sha256"):
            problems.append("launcher differs from the install receipt (edited or reinstalled)")
    else:
        problems.append("no install receipt")
    if "base-cli" in info["module"]:
        problems.append(f"module resolves from a base-cli copy: {info['module']}")
    if info["mode"] == "release":
        current = chome / CURRENT_NAME
        data = read_manifest(current)
        if info["release"] != data["release"]:
            problems.append("launcher release differs from current/release.json")
        real = current.resolve()
        if real not in Path(info["module"]).parents:
            problems.append(f"module {info['module']} is outside {real}")
    return {"ok": not problems, "problems": problems, "info": info, "receipt": receipt}


def rollback(home: Path | str | None = None) -> dict[str, Any]:
    """Leave dev mode, or repoint `current` at the release's `previous`."""
    chome = copilot_home(home)
    marker = chome / DEV_MARKER_NAME
    if marker.is_file():
        marker.unlink()
        return {
            "action": "dev-mode-disabled",
            "release": read_manifest(chome / CURRENT_NAME)["release"],
        }
    current = chome / CURRENT_NAME
    data = read_manifest(current)
    previous = data.get("previous")
    if not previous:
        raise InstallerError(f"release {data['release']} has no previous release")
    target = chome / "releases" / previous
    read_manifest(target)
    tmp = chome / f".{CURRENT_NAME}.rollback"
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target)
    os.replace(tmp, current)
    return {"action": "repointed", "from": data["release"], "release": previous}
