"""Tests for the Shell service -- client layer and CLI commands."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.shell.client import _DANGEROUS_PATTERNS, ShellClient, health
from copilot_cli.shared.errors import (
    CopilotError,
    ValidationError,
)
from copilot_cli.shared.errors import TimeoutError as CopilotTimeoutError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def shell_client():
    """Return a ShellClient whose settings come from the autouse mock_settings."""
    return ShellClient()


# ------------------------------------------------------------------ #
# Client -- execute
# ------------------------------------------------------------------ #


class TestShellExecute:
    """Tests for ShellClient.execute()."""

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_success(self, mock_run, shell_client):
        """execute() returns exit_code, stdout, stderr from subprocess."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="echo hello",
            returncode=0,
            stdout="hello\n",
            stderr="",
        )

        result = shell_client.execute(command="echo hello")

        mock_run.assert_called_once_with(
            "echo hello",
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=None,
            env=None,
        )
        assert result["exit_code"] == 0
        assert result["stdout"] == "hello\n"
        assert result["stderr"] == ""

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_with_args(self, mock_run, shell_client):
        """execute() appends args to the command string."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ls -la /tmp",
            returncode=0,
            stdout="total 0\n",
            stderr="",
        )

        result = shell_client.execute(command="ls", args=["-la", "/tmp"])

        call_args = mock_run.call_args
        assert call_args[0][0] == "ls -la /tmp"
        assert result["exit_code"] == 0

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_with_working_dir(self, mock_run, shell_client):
        """execute() passes working_dir to subprocess.run."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="pwd", returncode=0, stdout="/tmp\n", stderr=""
        )

        shell_client.execute(command="pwd", working_dir="/tmp")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_with_env(self, mock_run, shell_client):
        """execute() merges custom env with os.environ."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="env", returncode=0, stdout="FOO=bar\n", stderr=""
        )

        shell_client.execute(command="env", env={"FOO": "bar"})

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["env"]["FOO"] == "bar"
        # os.environ keys should also be present
        assert "PATH" in call_kwargs["env"]

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_nonzero_exit(self, mock_run, shell_client):
        """execute() captures nonzero exit codes without raising."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="false", returncode=1, stdout="", stderr="error\n"
        )

        result = shell_client.execute(command="false")

        assert result["exit_code"] == 1
        assert result["stderr"] == "error\n"

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_timeout_raises_copilot_timeout_error(self, mock_run, shell_client):
        """execute() raises CopilotTimeoutError when subprocess times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 999", timeout=5)

        with pytest.raises(CopilotTimeoutError, match="timed out after 5s"):
            shell_client.execute(command="sleep 999", timeout=5)

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_execute_generic_exception_raises_copilot_error(self, mock_run, shell_client):
        """execute() wraps unexpected exceptions in CopilotError."""
        mock_run.side_effect = OSError("permission denied")

        with pytest.raises(CopilotError, match="Command execution failed"):
            shell_client.execute(command="bad_cmd")


# ------------------------------------------------------------------ #
# Client -- _validate_command (security)
# ------------------------------------------------------------------ #


class TestValidateCommand:
    """Tests for ShellClient._validate_command security checks."""

    @pytest.mark.parametrize(
        "dangerous_cmd",
        [
            "rm -rf /",
            "sudo rm -rf /var",
            "format c:",
            "fdisk /dev/sda",
            "mkfs.ext4 /dev/sda1",
            "echo | FDISK",
            "MKFS.ext4 /dev/nvme0",
        ],
    )
    def test_dangerous_commands_are_blocked(self, dangerous_cmd):
        """_validate_command raises ValidationError for dangerous patterns."""
        with pytest.raises(ValidationError, match="Blocked dangerous command"):
            ShellClient._validate_command(dangerous_cmd)

    @pytest.mark.parametrize(
        "safe_cmd",
        [
            "echo hello",
            "ls -la",
            "cat /etc/hosts",
            "rm -rf ./temp_dir",
            "python3 script.py",
            "git status",
        ],
    )
    def test_safe_commands_pass(self, safe_cmd):
        """_validate_command does not raise for safe commands."""
        # Should not raise
        ShellClient._validate_command(safe_cmd)

    def test_dangerous_patterns_list_is_not_empty(self):
        """Sanity check that _DANGEROUS_PATTERNS is populated."""
        assert len(_DANGEROUS_PATTERNS) >= 4
        assert "rm -rf /" in _DANGEROUS_PATTERNS

    def test_validation_is_case_insensitive(self):
        """Dangerous patterns are matched case-insensitively."""
        with pytest.raises(ValidationError):
            ShellClient._validate_command("FORMAT C:")

        with pytest.raises(ValidationError):
            ShellClient._validate_command("Mkfs.ext4 /dev/sda")


# ------------------------------------------------------------------ #
# Client -- find_scripts
# ------------------------------------------------------------------ #


class TestFindScripts:
    """Tests for ShellClient.find_scripts()."""

    def test_find_scripts_in_tmp_directory(self, shell_client, tmp_path):
        """find_scripts locates shell scripts in a given directory."""
        script = tmp_path / "deploy.sh"
        script.write_text("#!/bin/bash\necho deploy")
        script.chmod(0o755)

        other = tmp_path / "readme.md"
        other.write_text("# readme")

        result = shell_client.find_scripts(pattern="*.sh", path=str(tmp_path))

        assert len(result) == 1
        assert result[0]["name"] == "deploy.sh"
        assert result[0]["executable"] is True
        assert result[0]["size"] > 0

    def test_find_scripts_nested(self, shell_client, tmp_path):
        """find_scripts searches recursively with rglob."""
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        script = nested / "backup.sh"
        script.write_text("#!/bin/bash\ntar czf backup.tgz .")

        result = shell_client.find_scripts(pattern="*.sh", path=str(tmp_path))

        assert len(result) == 1
        assert result[0]["name"] == "backup.sh"

    def test_find_scripts_empty_directory(self, shell_client, tmp_path):
        """find_scripts returns an empty list when no matches exist."""
        result = shell_client.find_scripts(pattern="*.sh", path=str(tmp_path))

        assert result == []

    def test_find_scripts_nonexistent_directory(self, shell_client):
        """find_scripts skips directories that do not exist."""
        result = shell_client.find_scripts(pattern="*.sh", path="/no/such/directory")

        assert result == []

    def test_find_scripts_custom_pattern(self, shell_client, tmp_path):
        """find_scripts respects custom glob patterns."""
        py_script = tmp_path / "run.py"
        py_script.write_text("print('hi')")
        sh_script = tmp_path / "run.sh"
        sh_script.write_text("echo hi")

        result = shell_client.find_scripts(pattern="*.py", path=str(tmp_path))

        assert len(result) == 1
        assert result[0]["name"] == "run.py"


# ------------------------------------------------------------------ #
# Client -- list_processes
# ------------------------------------------------------------------ #


class TestListProcesses:
    """Tests for ShellClient.list_processes()."""

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_list_processes_no_filter(self, mock_run, shell_client):
        """list_processes returns raw ps output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ps aux",
            returncode=0,
            stdout="USER  PID  CMD\nroot  1  /sbin/init\nuser  42  node server.js\n",
            stderr="",
        )

        result = shell_client.list_processes()

        assert "node server.js" in result

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_list_processes_with_pattern_filter(self, mock_run, shell_client):
        """list_processes filters output lines by pattern."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ps aux",
            returncode=0,
            stdout="USER  PID  CMD\nroot  1  /sbin/init\nuser  42  node server.js\n",
            stderr="",
        )

        result = shell_client.list_processes(pattern="node")

        assert "node server.js" in result
        assert "/sbin/init" not in result

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_list_processes_with_user(self, mock_run, shell_client):
        """list_processes builds user-specific ps command."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ps -u testuser -o pid,user,%cpu,%mem,command",
            returncode=0,
            stdout="PID USER %CPU %MEM COMMAND\n42 testuser 1.0 2.0 node\n",
            stderr="",
        )

        result = shell_client.list_processes(user="testuser")

        call_args = mock_run.call_args[0][0]
        assert "testuser" in call_args
        assert "node" in result

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_list_processes_pattern_no_matches(self, mock_run, shell_client):
        """list_processes returns just the header when pattern has no matches."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ps aux",
            returncode=0,
            stdout="USER  PID  CMD\nroot  1  /sbin/init\n",
            stderr="",
        )

        result = shell_client.list_processes(pattern="nonexistent_process")

        # Only the header should remain
        assert "USER" in result
        assert "/sbin/init" not in result

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_list_processes_pattern_case_insensitive(self, mock_run, shell_client):
        """list_processes pattern matching is case-insensitive."""
        mock_run.return_value = subprocess.CompletedProcess(
            args="ps aux",
            returncode=0,
            stdout="USER  PID  CMD\nuser  42  Node server.js\n",
            stderr="",
        )

        result = shell_client.list_processes(pattern="node")

        assert "Node server.js" in result


# ------------------------------------------------------------------ #
# CLI -- shell exec
# ------------------------------------------------------------------ #


class TestShellCLIExec:
    """CLI tests for `copilot shell exec`."""

    def test_exec_success(self, runner):
        """shell exec prints stdout of a successful command."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "exit_code": 0,
            "stdout": "hello world\n",
            "stderr": "",
        }

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", "echo hello world"])

        assert result.exit_code == 0
        assert "hello world" in result.output

    def test_exec_nonzero_exit_propagates(self, runner):
        """shell exec exits with the command's exit code on failure."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "exit_code": 2,
            "stdout": "",
            "stderr": "not found\n",
        }

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", "bad_command"])

        assert result.exit_code == 2

    def test_exec_copilot_error_returns_exit_1(self, runner):
        """shell exec exits 1 when CopilotError is raised."""
        mock_client = MagicMock()
        mock_client.execute.side_effect = CopilotError(
            "Command execution failed: permission denied",
            service="shell",
        )

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", "restricted_cmd"])

        assert result.exit_code == 1

    def test_exec_dangerous_command_rejected(self, runner):
        """shell exec exits 1 when a dangerous command is blocked."""
        mock_client = MagicMock()
        mock_client.execute.side_effect = ValidationError(
            "Blocked dangerous command pattern: 'rm -rf /'",
            service="shell",
            hint="This command has been rejected for safety reasons.",
        )

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", "rm -rf /"])

        assert result.exit_code == 1

    def test_exec_with_timeout(self, runner):
        """shell exec passes --timeout to the client."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "exit_code": 0,
            "stdout": "done\n",
            "stderr": "",
        }

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "exec", "long_cmd", "--timeout", "60"])

        assert result.exit_code == 0
        mock_client.execute.assert_called_once_with(
            command="long_cmd",
            timeout=60,
            working_dir=None,
        )


# ------------------------------------------------------------------ #
# CLI -- shell ps
# ------------------------------------------------------------------ #


class TestShellCLIPs:
    """CLI tests for `copilot shell ps`."""

    def test_ps_no_filter(self, runner):
        """shell ps prints process listing."""
        mock_client = MagicMock()
        mock_client.list_processes.return_value = "USER  PID  CMD\nroot  1  /sbin/init\n"

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "ps"])

        assert result.exit_code == 0
        assert "/sbin/init" in result.output

    def test_ps_with_pattern(self, runner):
        """shell ps passes --pattern to the client."""
        mock_client = MagicMock()
        mock_client.list_processes.return_value = "USER  PID  CMD\nuser  42  node server.js\n"

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "ps", "--pattern", "node"])

        assert result.exit_code == 0
        mock_client.list_processes.assert_called_once_with(pattern="node", user=None)

    def test_ps_with_user(self, runner):
        """shell ps passes --user to the client."""
        mock_client = MagicMock()
        mock_client.list_processes.return_value = "PID USER CMD\n42 bob node\n"

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "ps", "--user", "bob"])

        assert result.exit_code == 0
        mock_client.list_processes.assert_called_once_with(pattern=None, user="bob")

    def test_ps_error_returns_exit_1(self, runner):
        """shell ps exits 1 on CopilotError."""
        mock_client = MagicMock()
        mock_client.list_processes.side_effect = CopilotError(
            "Command execution failed", service="shell"
        )

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "ps"])

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# CLI -- shell find
# ------------------------------------------------------------------ #


class TestShellCLIFind:
    """CLI tests for `copilot shell find`."""

    def test_find_success(self, runner):
        """shell find prints a table of matching scripts."""
        mock_client = MagicMock()
        mock_client.find_scripts.return_value = [
            {
                "name": "deploy.sh",
                "path": "/tmp/scripts/deploy.sh",
                "size": 128,
                "modified": "2025-06-01T00:00:00+00:00",
                "executable": True,
            }
        ]

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "find", "--pattern", "*.sh"])

        assert result.exit_code == 0
        assert "deploy.sh" in result.output

    def test_find_no_results(self, runner):
        """shell find prints no-results message for empty list."""
        mock_client = MagicMock()
        mock_client.find_scripts.return_value = []

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "find"])

        assert result.exit_code == 0
        assert "No results" in result.output


# ------------------------------------------------------------------ #
# CLI -- shell run
# ------------------------------------------------------------------ #


class TestShellCLIRun:
    """CLI tests for `copilot shell run`."""

    def test_run_success(self, runner):
        """shell run prints script output and success message."""
        mock_client = MagicMock()
        mock_client.run_script.return_value = {
            "exit_code": 0,
            "stdout": "deploying...\n",
            "stderr": "",
            "script_path": "/tmp/scripts/deploy.sh",
        }

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "run", "deploy.sh"])

        assert result.exit_code == 0
        assert "deploying" in result.output

    def test_run_script_not_found(self, runner):
        """shell run exits 1 when the script is not found."""
        mock_client = MagicMock()
        mock_client.run_script.side_effect = CopilotError(
            "Script not found: ghost.sh",
            service="shell",
            hint="Searched in: /tmp/test-scripts, ./scripts/",
        )

        with patch(
            "copilot_cli.services.shell.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["shell", "run", "ghost.sh"])

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# Module -- health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for shell.client.health() -- a local capability check."""

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_healthy_when_subprocess_works(self, mock_run):
        """health() reports healthy when a trivial subprocess succeeds."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["/bin/sh", "-c", "true"], returncode=0
        )

        result = health()

        assert result["healthy"] is True
        assert result["shell"] == "/bin/sh"

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_unhealthy_when_subprocess_fails(self, mock_run):
        """health() reports unhealthy when the trivial subprocess fails."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["/bin/sh", "-c", "true"], returncode=1
        )

        result = health()

        assert result["healthy"] is False

    @patch("copilot_cli.services.shell.client.subprocess.run")
    def test_unhealthy_on_exception(self, mock_run):
        """health() reports unhealthy and an error when subprocess raises."""
        mock_run.side_effect = OSError("no shell available")

        result = health()

        assert result["healthy"] is False
        assert "no shell available" in result["error"]
