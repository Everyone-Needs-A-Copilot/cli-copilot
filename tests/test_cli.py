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


def test_update_range_ref_is_skipped(tmp_path, monkeypatch):
    remote = _init_remote(tmp_path)
    manifest = tmp_path / "copilot.layers.yml"
    _write_cli_manifest(manifest, f"file://{remote}", ref="^1.4.5")
    copilot_home = tmp_path / "copilot-home"  # scratch, never the real ~/.copilot

    monkeypatch.setenv("COPILOT_LAYERS_FILE", str(manifest))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(copilot_home))

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "skipped" in result.output
    assert "#2b" in result.output
    assert not (copilot_home / "mirrors" / "cli" / "foundation").exists()
