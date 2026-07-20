"""Basic CLI integration tests."""

import json
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.shared.output import set_json_mode

runner = CliRunner()


def _run_git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_remote(tmp_path: Path, name: str = "remote") -> Path:
    """A local, non-bare git repo usable as a `file://` clone/pull source."""
    remote = tmp_path / name
    remote.mkdir()
    _run_git("init", "-q", "-b", "main", cwd=remote)
    _run_git("config", "user.email", "test@example.com", cwd=remote)
    _run_git("config", "user.name", "Test", cwd=remote)
    (remote / "README.md").write_text("hello\n")
    _run_git("add", "README.md", cwd=remote)
    _run_git("commit", "-q", "-m", "init", cwd=remote)
    return remote


def _write_cli_manifest(path: Path, repo_url: str, ref: str = "main") -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "layers": [
                    {
                        "id": "foundation",
                        "role": "foundation",
                        "component": "cli",
                        "rank": 40,
                        "source": {"repo": repo_url, "ref": ref},
                        "auth": "anon",
                    }
                ],
            }
        )
    )


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Unified CLI" in result.output


def test_version():
    from copilot_cli import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_subcommands_registered():
    result = runner.invoke(app, ["--help"])
    assert "git" in result.output
    assert "docker" in result.output
    assert "shell" in result.output
    assert "fs" in result.output
    assert "services" in result.output
    assert "db" in result.output
    assert "docs" in result.output
    assert "bi" in result.output
    assert "monitoring" in result.output
    assert "skill" in result.output
    assert "uspto" in result.output
    assert "health" in result.output


def test_docker_help():
    result = runner.invoke(app, ["docker", "--help"])
    assert result.exit_code == 0
    assert "ps" in result.output
    assert "start" in result.output


def test_db_help():
    result = runner.invoke(app, ["db", "--help"])
    assert result.exit_code == 0
    assert "query" in result.output
    assert "tables" in result.output


def test_git_help():
    result = runner.invoke(app, ["git", "--help"])
    assert result.exit_code == 0
    assert "clone" in result.output
    assert "status" in result.output


def test_uspto_help():
    result = runner.invoke(app, ["uspto", "--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "patents" in result.output
    assert "trademarks" in result.output
    assert "dossier" in result.output


def test_layers_registered():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "layers" in result.output


def test_layers_json_reports_base_services_with_no_manifest(tmp_path, monkeypatch):
    """`copilot --json layers` with no `copilot.layers.yml` anywhere reports
    an empty chain and the base 12 services, each `tier: foundation, mode:
    base` -- the Phase-1 inert state."""
    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    monkeypatch.chdir(project_dir)

    try:
        result = runner.invoke(app, ["--json", "layers"])
    finally:
        set_json_mode(False)

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["schema_version"] == 1
    assert payload["component"] == "cli"
    assert payload["manifest"]["cli_layers_resolved"] is False
    assert payload["chain"] == []
    assert len(payload["services"]) == 12
    assert all(svc["tier"] == "foundation" and svc["mode"] == "base" for svc in payload["services"])
    names = {svc["name"] for svc in payload["services"]}
    assert names == {
        "git",
        "docker",
        "shell",
        "fs",
        "services",
        "db",
        "docs",
        "bi",
        "monitoring",
        "infisical",
        "skill",
        "uspto",
    }


def test_layers_human_output_with_no_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    monkeypatch.chdir(project_dir)

    result = runner.invoke(app, ["layers"])
    assert result.exit_code == 0
    assert "No copilot.layers.yml resolved" in result.output
    assert "uspto" in result.output


# ------------------------------------------------------------------ #
# `copilot update` -- mirror sync (V-3/V-4 onboarding blocker, item #2a)
# ------------------------------------------------------------------ #
#
# All mirrors sync against local `file://` remotes under `tmp_path`, and
# `COPILOT_MIRRORS_ROOT` always points at a scratch tmp dir -- the real
# `~/.copilot/mirrors` and `~/.config/copilot/copilot.layers.yml` are never
# read or written by these tests.


def test_update_registered():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "update" in result.output


def test_update_no_manifest_reports_nothing_to_sync(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    monkeypatch.chdir(project_dir)

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "nothing to sync" in result.output


def test_update_clones_absent_mirror(tmp_path, monkeypatch):
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}")
    copilot_home = tmp_path / "copilot-home"  # scratch, never the real ~/.copilot

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "cloned" in result.output
    mirror = copilot_home / "mirrors" / "cli" / "foundation"
    assert (mirror / "README.md").exists()


def test_update_holds_dirty_mirror_and_makes_zero_writes(tmp_path, monkeypatch):
    """V-3 acceptance criterion, exercised end-to-end through the real
    `copilot update` command: an uncommitted local change means the mirror
    is HELD -- zero writes, reported as held."""
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}")
    copilot_home = tmp_path / "copilot-home"  # scratch, never the real ~/.copilot

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    first = runner.invoke(app, ["update"])
    assert first.exit_code == 0
    assert "cloned" in first.output

    mirror = copilot_home / "mirrors" / "cli" / "foundation"
    (mirror / "README.md").write_text("locally edited, uncommitted\n")

    before = (mirror / "README.md").read_bytes()
    second = runner.invoke(app, ["update"])
    after = (mirror / "README.md").read_bytes()

    assert second.exit_code == 0
    assert "held" in second.output
    assert before == after, "held mirror must make zero writes"


def test_update_range_ref_with_no_matching_tag_is_skipped(tmp_path, monkeypatch):
    """The scratch remote here carries zero tags, so the declared `^1.4.5`
    range can never resolve -- reported `skipped`, never a crash, never a
    write (#2b: resolution itself is covered in test_config/test_sync.py
    and test_config/test_semver.py)."""
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}", ref="^1.4.5")
    copilot_home = tmp_path / "copilot-home"  # scratch, never the real ~/.copilot

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "skipped" in result.output
    assert "no tag matches" in result.output
    assert not (copilot_home / "mirrors" / "cli" / "foundation").exists()


def test_update_json_reports_versioned_payload(tmp_path, monkeypatch):
    """`copilot --json update` emits the versioned per-layer + store-
    readiness payload -- Control Tower renders this, never recomputes it
    (invariant #1)."""
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}")
    copilot_home = tmp_path / "copilot-home"

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    try:
        result = runner.invoke(app, ["--json", "update"])
    finally:
        set_json_mode(False)

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["schema_version"] == 1
    assert payload["component"] == "cli"
    assert payload["overall"] == "ok"
    assert len(payload["layers"]) == 1
    layer = payload["layers"][0]
    assert layer["id"] == "foundation"
    assert layer["role"] == "foundation"
    assert layer["ref"] == "main"
    assert layer["resolved_ref"] == "main"
    assert layer["action"] == "cloned"
    assert payload["store"] == {"status": "none", "detail": "store: none declared", "layer_id": None}


def test_update_json_no_manifest_reports_empty_layers(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    monkeypatch.chdir(project_dir)

    try:
        result = runner.invoke(app, ["--json", "update"])
    finally:
        set_json_mode(False)

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["layers"] == []
    assert payload["overall"] == "ok"
    assert payload["store"]["status"] == "none"


def test_update_human_output_reports_store_readiness_line(tmp_path, monkeypatch):
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}")
    copilot_home = tmp_path / "copilot-home"

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "store: none declared" in result.output


# ------------------------------------------------------------------ #
# `copilot update` -- V-4 fan-out acceptance: one shared mirror serves
# every project that enrolls the same layer id, so a single `copilot
# update` propagates to all of them.
# ------------------------------------------------------------------ #


def test_update_fan_out_propagates_to_every_enrolled_project(tmp_path, monkeypatch):
    """Two independent projects (separate CWDs, separate manifests) both
    enroll the SAME layer id against the SAME source repo -- so they share
    one physical mirror (`_mirror_root` keys purely off layer id under
    `COPILOT_MIRRORS_ROOT`). Pushing a new tag to the shared remote and
    running `copilot update` once (from project A) must be visible from
    BOTH projects' resolution -- one update, every enrolled project."""
    remote = _init_remote(tmp_path)
    _run_git("tag", "v1.0.0", cwd=remote)

    copilot_home = tmp_path / "copilot-home"  # ONE shared mirror root
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    project_a = tmp_path / "project-a"
    project_a.mkdir()
    (project_a / ".git").mkdir()
    manifest_a = project_a / "copilot.layers.yml"
    _write_cli_manifest(manifest_a, f"file://{remote}", ref="^1.0.0")

    project_b = tmp_path / "project-b"
    project_b.mkdir()
    (project_b / ".git").mkdir()
    manifest_b = project_b / "copilot.layers.yml"
    _write_cli_manifest(manifest_b, f"file://{remote}", ref="^1.0.0")

    monkeypatch.delenv("COPILOT_LAYERS_FILE", raising=False)

    # Initial `copilot update` from project A resolves and clones v1.0.0.
    monkeypatch.chdir(project_a)
    first = runner.invoke(app, ["update"])
    assert first.exit_code == 0
    assert "cloned" in first.output

    mirror = copilot_home / "mirrors" / "cli" / "foundation"
    assert not (mirror / "SECOND.md").exists()

    # A new patch tag lands on the shared remote.
    (remote / "SECOND.md").write_text("second commit\n")
    _run_git("add", "SECOND.md", cwd=remote)
    _run_git("commit", "-q", "-m", "second", cwd=remote)
    _run_git("tag", "v1.0.1", cwd=remote)

    # ONE `copilot update`, run from project A.
    second = runner.invoke(app, ["update"])
    assert second.exit_code == 0
    assert "pulled" in second.output

    # Project A's own resolution reflects it directly.
    resolved_a = runner.invoke(app, ["--json", "layers"])
    set_json_mode(False)
    assert resolved_a.exit_code == 0
    assert (mirror / "SECOND.md").exists()

    # Project B never ran `update` itself -- but it enrolls the SAME layer
    # id against the SAME mirror root, so its OWN resolution already
    # reflects the update too.
    from copilot_cli.config.layers import resolve_cli_layer_chain

    monkeypatch.chdir(project_b)
    resolved_b = runner.invoke(app, ["--json", "layers"])
    set_json_mode(False)
    assert resolved_b.exit_code == 0
    payload_b = json.loads(resolved_b.output.strip())
    assert payload_b["chain"][0]["id"] == "foundation"

    b_chain = resolve_cli_layer_chain()
    assert b_chain[0].root == mirror, "project B's resolved mirror root IS project A's"
    assert (b_chain[0].root / "SECOND.md").exists(), (
        "one `copilot update` (run only from project A) propagated to project B's "
        "own resolved mirror -- proving one shared mirror serves every enrolled project"
    )
