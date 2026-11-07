"""Launcher installer: temp HOME only, never the real launcher or base-cli."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from copilot_cli import launcher_install as li

_REAL_CC_ROLLBACK = li._cc_rollback

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


@pytest.fixture(autouse=True)
def _no_cc(monkeypatch):
    """Exercise the in-package fallback; the real cc is never consulted."""
    monkeypatch.setattr(li, "_cc_rollback", lambda home, steps, to: None)


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
    (home / ".copilot" / "release-history.jsonl").write_text(
        "".join(json.dumps({"action": "flip", "release": r.name}) + "\n" for r in (r1, r2))
    )
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


def test_rollback_matches_cc_semantics(env):
    home, r1, r2 = env
    hist = home / ".copilot" / "release-history.jsonl"
    hist.write_text(
        json.dumps({"action": "flip", "release": r1.name})
        + "\n"
        + json.dumps({"action": "flip", "release": r2.name})
        + "\n"
    )
    _point(home, r2)
    li.install(home)
    li.rollback(home)
    link = home / ".copilot" / "current"
    assert os.readlink(link) == f"releases/{r1.name}"
    last = json.loads(hist.read_text().splitlines()[-1])
    assert last["action"] == "rollback" and last["release"] == r1.name
    assert last["previous"] == r2.name


def test_check_accepts_live_link_component(env):
    home, _, r2 = env
    live = home / "live" / "cli-copilot"
    shutil.copytree(r2 / "cli-copilot", live)
    manifest = json.loads((r2 / "release.json").read_text())
    for row in manifest["components"]:
        if row["name"] == "cli-copilot":
            row.update(kind="live-link", path="cli-copilot", signer="")
    shutil.rmtree(r2 / "cli-copilot")
    (r2 / "cli-copilot").symlink_to(live)
    (r2 / "release.json").write_text(json.dumps(manifest))
    _point(home, r2)
    li.install(home)
    assert li.check(home)["ok"], li.check(home)["problems"]


def test_malformed_dev_marker_is_clear_error(env):
    home, _, _ = env
    li.install(home)
    (home / ".copilot" / "cli-dev.json").write_text("{not json")
    proc = _run(home, "--launcher-info")
    assert proc.returncode != 0 and "malformed dev marker" in proc.stderr
    assert "Traceback" not in proc.stderr
    with pytest.raises(li.InstallerError, match="malformed dev marker"):
        li.check(home)


# Verbatim reference of cc.core.release.engine.pointer._lineage/earlier_releases
# (claude-copilot d1f632b), operating on plain rows, to cross-check the fallback.
def _cc_earlier(rows, current, available):
    stack = []
    for row in rows:
        release = row.get("release")
        if not release:
            continue
        if row.get("action") == "rollback" and release in stack:
            del stack[len(stack) - stack[::-1].index(release) :]
        else:
            stack.append(release)
    if current in stack:
        stack = stack[: len(stack) - stack[::-1].index(current) - 1]
    out = []
    for candidate in reversed(stack):
        if candidate != current and candidate in available and candidate not in out:
            out.append(candidate)
    return out


def _three(tmp_path):
    ids = ["20260101T000000Z-aaa", "20260102T000000Z-bbb", "20260103T000000Z-ccc"]
    dirs = [_make_release(tmp_path, rid, rid[-3:] * 2 + "x") for rid in ids]
    hist = tmp_path / ".copilot" / "release-history.jsonl"
    hist.write_text("".join(json.dumps({"action": "flip", "release": rid}) + "\n" for rid in ids))
    _point(tmp_path, dirs[2])
    return ids, hist


def _current(home):
    return os.readlink(home / ".copilot" / "current").split("/")[-1]


def test_repeated_rollback_pops_stack_like_cc(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    (a, b, c), hist = _three(tmp_path)
    seen = []
    for _ in range(2):
        rows = [json.loads(x) for x in hist.read_text().splitlines()]
        expected = _cc_earlier(rows, _current(tmp_path), {a, b, c})[0]
        li.rollback(tmp_path)
        seen.append(_current(tmp_path))
        assert seen[-1] == expected
    assert seen == [b, a]  # not B, C, B
    with pytest.raises(li.InstallerError, match="no earlier release"):
        li.rollback(tmp_path)


def test_rollback_steps_matches_cc(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    (a, b, c), hist = _three(tmp_path)
    rows = [json.loads(x) for x in hist.read_text().splitlines()]
    assert _cc_earlier(rows, c, {a, b, c})[1] == a
    li.rollback(tmp_path, steps=2)
    assert _current(tmp_path) == a
    with pytest.raises(li.InstallerError, match="no earlier release"):
        li.rollback(tmp_path, steps=1)


def test_rollback_to_named_release(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    (a, *_), _ = _three(tmp_path)
    li.rollback(tmp_path, to=a)
    assert _current(tmp_path) == a
    with pytest.raises(li.InstallerError, match="already current"):
        li.rollback(tmp_path, to=a)
    with pytest.raises(li.InstallerError):
        li.rollback(tmp_path, to="20260109T000000Z-zzz")


def test_rollback_delegates_to_cc_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / ".copilot"))
    (_, b, _c), _ = _three(tmp_path)
    calls = []

    def fake(home, steps, to):
        calls.append((steps, to))
        _point(tmp_path, tmp_path / ".copilot" / "releases" / b)
        return True

    monkeypatch.setattr(li, "_cc_rollback", fake)
    out = li.rollback(tmp_path, steps=3)
    assert calls == [(3, None)] and out["release"] == b and out["via"] == "cc"


def _stub(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


_CLANG_LIKE = 'echo "OVERVIEW: clang LLVM compiler"; echo "USAGE: cc [options] file..."; exit 0\n'
_REAL_CC = (
    'if [ "$1 $2 $3" = "release rollback --help" ]; then '
    'echo "Usage: cc release rollback [OPTIONS]"; echo "  --steps INTEGER"; echo "  --to TEXT"; exit 0; fi\n'
    'echo "$@" > "$HOME/cc-called"; exit 0\n'
)


def test_compiler_cc_on_path_is_not_delegated_to(tmp_path, monkeypatch):
    fake_bin = tmp_path / "pathbin"
    _stub(fake_bin / "cc", _CLANG_LIKE)
    monkeypatch.setenv("PATH", f"{fake_bin}:/usr/bin:/bin")
    assert _REAL_CC_ROLLBACK(tmp_path, 1, None) is None


def test_framework_cc_in_home_is_preferred_over_path(tmp_path, monkeypatch):
    fake_bin = tmp_path / "pathbin"
    _stub(fake_bin / "cc", _CLANG_LIKE)
    _stub(tmp_path / ".local" / "bin" / "cc", _REAL_CC)
    monkeypatch.setenv("PATH", f"{fake_bin}:/usr/bin:/bin")
    assert _REAL_CC_ROLLBACK(tmp_path, 2, None) is True
    assert (tmp_path / "cc-called").read_text().split() == ["release", "rollback", "--steps", "2"]


def test_rollback_uses_fallback_when_only_compiler_cc(env, monkeypatch):
    home, r1, r2 = env
    (home / ".copilot" / "release-history.jsonl").write_text(
        "".join(json.dumps({"action": "flip", "release": r.name}) + "\n" for r in (r1, r2))
    )
    _point(home, r2)
    _stub(home / "pathbin" / "cc", _CLANG_LIKE)
    monkeypatch.setenv("PATH", f"{home / 'pathbin'}:/usr/bin:/bin")
    monkeypatch.setattr(li, "_cc_rollback", _REAL_CC_ROLLBACK)
    assert li.rollback(home)["release"] == r1.name
