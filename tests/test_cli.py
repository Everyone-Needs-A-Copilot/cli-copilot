"""Basic CLI integration tests."""

import json

from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.shared.output import set_json_mode

runner = CliRunner()


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
