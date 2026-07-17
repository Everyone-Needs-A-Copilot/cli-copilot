"""Basic CLI integration tests."""

from typer.testing import CliRunner

from copilot_cli.main import app

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
    assert "crm" in result.output
    assert "brevo" in result.output
    assert "n8n" in result.output
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


def test_crm_help():
    result = runner.invoke(app, ["crm", "--help"])
    assert result.exit_code == 0
    assert "clients" in result.output
    assert "projects" in result.output


def test_git_help():
    result = runner.invoke(app, ["git", "--help"])
    assert result.exit_code == 0
    assert "clone" in result.output
    assert "status" in result.output


def test_n8n_help():
    result = runner.invoke(app, ["n8n", "--help"])
    assert result.exit_code == 0
    assert "workflows" in result.output
    assert "executions" in result.output


def test_uspto_help():
    result = runner.invoke(app, ["uspto", "--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "patents" in result.output
    assert "trademarks" in result.output
    assert "dossier" in result.output
