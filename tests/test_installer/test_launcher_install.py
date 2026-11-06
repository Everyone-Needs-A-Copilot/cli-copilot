"""Launcher installer: temp HOME only, never the real launcher or base-cli."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from copilot_cli import launcher_install as li

REPO = Path(__file__).resolve().parents[2]


def _make_release(home: Path, rid: str, commit: str, previous: str | None = None) -> Path:
    rdir = home / ".copilot" / "releases" / rid
    pkg = rdir / "cli-copilot" / "copilot_cli"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(f'__version__ = "9.9.9"\nCOMMIT = "{commit}"\n')
    (pkg / "main.py").write_text(
        "def app():\n    print('app-' + __import__('copilot_cli').COMMIT)\n"
    )
    overlay = rdir / "cli" / "organization"
    overlay.mkdir(parents=True)
    rows = [
        {
            "name": "cli-copilot",
            "tier": "foundation",
            "kind": "signed-tag",
            "version": "9",
            "ref": "v9",
            "commit": commit,
            "source": "x",
            "path": "cli-copilot",
            "signer": "s",
        },
        {
            "name": "cli/organization",
            "tier": "organization",
            "kind": "signed-tag",
            "version": "1",
            "ref": "v1",
            "commit": "o" * 7,
            "source": "x",
            "path": "cli/organization",
            "signer": "s",
        },
    ]
    (rdir / "release.json").write_text(
        json.dumps(
            {"schema": 1, "release": rid, "created": "t", "previous": previous, "components": rows}
        )
    )
    return rdir


def _point(home: Path, rdir: Path) -> None:
    cur = home / ".copilot" / "current"
    cur.unlink(missing_ok=True)
    cur.symlink_to(rdir)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    r1 = _make_release(tmp_path, "20260101T000000Z-aaa", "aaaaaaa")
    r2 = _make_release(tmp_path, "20260102T000000Z-bbb", "bbbbbbb", "20260101T000000Z-aaa")
    _point(tmp_path, r1)
    return tmp_path, r1, r2


def _run(home, *args):
    return subprocess.run(
        [str(home / ".local" / "bin" / "copilot"), *args],
        capture_output=True,
        text=True,
        env={"COPILOT_HOME": str(home / ".copilot"), "PATH": "/usr/bin:/bin"},
    )


def test_install_is_idempotent(env):
    home, _, _ = env
    first = li.install(home)
    assert first["changed"] and set(first["steps"]) == {"launcher", "receipt"}
    second = li.install(home)
    assert second["changed"] is False
    assert (home / ".local" / "bin" / "copilot").stat().st_mode & 0o111
    assert json.loads((home / ".copilot" / "cli-install.json").read_text())["release"].endswith(
        "aaa"
    )


def test_install_requires_pointer(tmp_path):
    with pytest.raises(li.InstallerError):
        li.install(tmp_path)


def test_launcher_resolves_through_pointer_and_flip(env):
    home, _, r2 = env
    li.install(home)
    info = li.launcher_info(home)
    assert info["commit"] == "aaaaaaa" and info["module"].startswith(str(env[1].resolve()))
    assert any(p.endswith("cli/organization") for p in info["paths"])
    assert _run(home, "x").stdout.strip() == "app-aaaaaaa"
    before = (home / ".local" / "bin" / "copilot").read_text()
    _point(home, r2)  # a flip must not require rewriting the launcher
    assert (home / ".local" / "bin" / "copilot").read_text() == before
    assert li.launcher_info(home)["commit"] == "bbbbbbb"
    assert _run(home, "x").stdout.strip() == "app-bbbbbbb"
    assert li.check(home)["ok"]


def test_check_detects_edited_launcher(env):
    home, _, _ = env
    li.install(home)
    launcher = home / ".local" / "bin" / "copilot"
    launcher.write_text(launcher.read_text() + "\n# hand edit\n")
    result = li.check(home)
    assert not result["ok"] and "receipt" in result["problems"][0]


def test_rollback_repoints_to_previous(env):
    home, r1, r2 = env
    _point(home, r2)
    li.install(home)
    out = li.rollback(home)
    assert out["action"] == "repointed" and out["release"] == r1.name
    assert (home / ".copilot" / "current").resolve() == r1.resolve()
    with pytest.raises(li.InstallerError):
        li.rollback(home)  # r1 has no previous


def test_dev_mode_and_rollback_leaves_dev(env):
    home, _, _ = env
    li.install(home, dev_path=REPO)
    info = li.launcher_info(home)
    assert info["mode"] == "dev" and info["module"].startswith(str(REPO))
    assert li.rollback(home)["action"] == "dev-mode-disabled"
    assert li.launcher_info(home)["mode"] == "release"
    with pytest.raises(li.InstallerError):
        li.install(home, dev_path=home)


def test_version_prints_release_commit():
    out = subprocess.run(
        [sys.executable, "-m", "copilot_cli", "--version"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={
            "PATH": "/usr/bin:/bin",
            "COPILOT_RELEASE_ID": "20260101T000000Z-aaa",
            "COPILOT_RELEASE_COMMIT": "abc1234",
        },
    )
    assert "release 20260101T000000Z-aaa commit abc1234" in out.stdout
