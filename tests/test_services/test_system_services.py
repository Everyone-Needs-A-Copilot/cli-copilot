"""Comprehensive tests for the system_services service client and CLI commands."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.system_services.client import (
    _build_domain_target,
    get_process_info,
    get_status,
    health,
    list_processes,
    list_services,
    load_service,
    restart_service,
    start_service,
    stop_service,
    unload_service,
)
from copilot_cli.shared.errors import CopilotError, NotFoundError

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

runner = CliRunner()

LAUNCHCTL_LIST_OUTPUT = (
    "PID\tStatus\tLabel\n"
    "123\t0\tcom.apple.Spotlight\n"
    "-\t0\tcom.apple.Dock\n"
    "456\t-\tcom.example.myapp\n"
    "-\t-\tcom.example.stopped\n"
)

PS_AUX_OUTPUT = (
    "USER       PID  %CPU %MEM    VSZ   RSS  TT  STAT STARTED      TIME COMMAND\n"
    "testuser   100  1.2  0.5  40000  2000  ??  S    Mon09AM   0:02.30 /usr/bin/python3 server.py\n"
    "testuser   200  0.0  0.1  20000  1000  ??  S    Mon09AM   0:00.10 /usr/sbin/syslogd\n"
    "root       300  0.3  0.2  50000  3000  ??  Ss   Mon09AM   0:05.00 /usr/sbin/launchd\n"
)

PS_SINGLE_PROCESS_OUTPUT = (
    "USER       PID  %CPU %MEM    VSZ   RSS STAT STARTED      TIME COMMAND\n"
    "testuser   100  1.2  0.5  40000  2000  S    Mon09AM   0:02.30 /usr/bin/python3 server.py\n"
)


def _make_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a subprocess.CompletedProcess for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ===================================================================
# Unit tests -- client functions
# ===================================================================


class TestListServices:
    """Tests for list_services()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_parses_launchctl_output(self, mock_run: MagicMock) -> None:
        """list_services correctly parses launchctl list output."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        services = list_services()

        assert len(services) == 4
        spotlight = next(s for s in services if s["label"] == "com.apple.Spotlight")
        assert spotlight["pid"] == 123
        assert spotlight["status"] == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_handles_dash_pid(self, mock_run: MagicMock) -> None:
        """Services with PID '-' are returned with pid=None."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        services = list_services()
        dock = next(s for s in services if s["label"] == "com.apple.Dock")
        assert dock["pid"] is None
        assert dock["status"] == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_handles_dash_status(self, mock_run: MagicMock) -> None:
        """Services with status '-' are returned with status=None."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        services = list_services()
        myapp = next(s for s in services if s["label"] == "com.example.myapp")
        assert myapp["pid"] == 456
        assert myapp["status"] is None

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        """list_services raises CopilotError when launchctl fails."""
        mock_run.return_value = _make_completed(returncode=1, stderr="permission denied")
        with pytest.raises(CopilotError, match="launchctl list failed"):
            list_services()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_skips_malformed_lines(self, mock_run: MagicMock) -> None:
        """list_services skips lines with fewer than 3 columns."""
        output = "PID\tStatus\tLabel\n123\t0\tcom.test.ok\nbadline\n"
        mock_run.return_value = _make_completed(stdout=output)

        services = list_services()
        assert len(services) == 1
        assert services[0]["label"] == "com.test.ok"

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_empty_service_list(self, mock_run: MagicMock) -> None:
        """list_services returns empty list when only header is present."""
        mock_run.return_value = _make_completed(stdout="PID\tStatus\tLabel\n")

        services = list_services()
        assert services == []


class TestGetStatus:
    """Tests for get_status()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_finds_service_in_list(self, mock_run: MagicMock) -> None:
        """get_status returns status for an existing service."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        result = get_status("com.apple.Spotlight")
        assert result["label"] == "com.apple.Spotlight"
        assert result["pid"] == 123
        assert result["running"] is True
        assert result["domain"] == "user"

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_reports_not_running(self, mock_run: MagicMock) -> None:
        """get_status sets running=False when PID is None."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        result = get_status("com.apple.Dock")
        assert result["running"] is False

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_raises_not_found_for_unknown_service(self, mock_run: MagicMock) -> None:
        """get_status raises NotFoundError for a service not in the list."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        with pytest.raises(NotFoundError, match="Service not found"):
            get_status("com.nonexistent.service")


class TestStartService:
    """Tests for start_service()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_calls_launchctl_kickstart(self, mock_run: MagicMock) -> None:
        """start_service invokes launchctl kickstart with correct target."""
        mock_run.return_value = _make_completed(stdout="Service started")

        result = start_service("com.example.myapp", domain="system")

        assert result["action"] == "start"
        assert result["success"] is True
        assert result["label"] == "com.example.myapp"

        # Verify the command that was issued
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "launchctl"
        assert call_args[1] == "kickstart"
        assert "system/com.example.myapp" in call_args[3]

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_user_domain_target(self, mock_run: MagicMock) -> None:
        """start_service uses user/{uid} target for user domain."""
        mock_run.return_value = _make_completed()

        start_service("com.test.svc", domain="user")

        call_args = mock_run.call_args[0][0]
        target = call_args[3]
        assert target.startswith("user/")
        assert "com.test.svc" in target

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_reports_failure(self, mock_run: MagicMock) -> None:
        """start_service returns success=False on non-zero exit."""
        mock_run.return_value = _make_completed(returncode=1, stderr="Not found")

        result = start_service("com.example.bad")
        assert result["success"] is False


class TestStopService:
    """Tests for stop_service()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_calls_launchctl_kill(self, mock_run: MagicMock) -> None:
        """stop_service invokes launchctl kill SIGTERM."""
        mock_run.return_value = _make_completed()

        result = stop_service("com.example.myapp", domain="system")

        assert result["action"] == "stop"
        assert result["success"] is True

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "launchctl"
        assert call_args[1] == "kill"
        assert call_args[2] == "SIGTERM"

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_reports_failure(self, mock_run: MagicMock) -> None:
        """stop_service returns success=False on non-zero exit."""
        mock_run.return_value = _make_completed(returncode=1, stderr="Service not running")

        result = stop_service("com.example.bad")
        assert result["success"] is False


class TestRestartService:
    """Tests for restart_service()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_calls_stop_then_start(self, mock_run: MagicMock) -> None:
        """restart_service issues stop (kill) then start (kickstart)."""
        mock_run.return_value = _make_completed()

        result = restart_service("com.example.myapp", domain="user")

        assert result["action"] == "restart"
        assert result["success"] is True
        assert result["label"] == "com.example.myapp"
        assert "stop:" in result["message"]
        assert "start:" in result["message"]

        # Two subprocess calls: kill + kickstart
        assert mock_run.call_count == 2
        first_cmd = mock_run.call_args_list[0][0][0]
        second_cmd = mock_run.call_args_list[1][0][0]
        assert first_cmd[1] == "kill"
        assert second_cmd[1] == "kickstart"


class TestLoadService:
    """Tests for load_service()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_calls_launchctl_load(self, mock_run: MagicMock) -> None:
        """load_service invokes launchctl load with path."""
        mock_run.return_value = _make_completed()

        result = load_service("/Library/LaunchDaemons/com.example.plist")

        assert result["action"] == "load"
        assert result["success"] is True
        assert result["path"] == "/Library/LaunchDaemons/com.example.plist"

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "launchctl"
        assert call_args[1] == "load"
        assert "/Library/LaunchDaemons/com.example.plist" in call_args

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_user_domain_adds_w_flag(self, mock_run: MagicMock) -> None:
        """load_service adds -w flag for user domain."""
        mock_run.return_value = _make_completed()

        load_service("/tmp/test.plist", domain="user")

        call_args = mock_run.call_args[0][0]
        assert "-w" in call_args

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_system_domain_no_w_flag(self, mock_run: MagicMock) -> None:
        """load_service omits -w flag for system domain."""
        mock_run.return_value = _make_completed()

        load_service("/tmp/test.plist", domain="system")

        call_args = mock_run.call_args[0][0]
        assert "-w" not in call_args


class TestUnloadService:
    """Tests for unload_service()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_calls_launchctl_unload(self, mock_run: MagicMock) -> None:
        """unload_service invokes launchctl unload."""
        mock_run.return_value = _make_completed()

        result = unload_service("/tmp/test.plist")

        assert result["action"] == "unload"
        assert result["success"] is True

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "launchctl"
        assert call_args[1] == "unload"

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_user_domain_adds_w_flag(self, mock_run: MagicMock) -> None:
        """unload_service adds -w flag for user domain."""
        mock_run.return_value = _make_completed()

        unload_service("/tmp/test.plist", domain="user")

        call_args = mock_run.call_args[0][0]
        assert "-w" in call_args


class TestListProcesses:
    """Tests for list_processes()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    @patch("pwd.getpwuid")
    @patch("os.getuid", return_value=501)
    def test_parses_ps_output(
        self, mock_getuid: MagicMock, mock_getpwuid: MagicMock, mock_run: MagicMock
    ) -> None:
        """list_processes correctly parses ps aux output."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)
        mock_getpwuid.return_value = MagicMock(pw_name="testuser")

        processes = list_processes(user_only=True)

        assert len(processes) == 2
        pids = [p["pid"] for p in processes]
        assert 100 in pids
        assert 200 in pids
        # root process (300) should be excluded with user_only=True
        assert 300 not in pids

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    @patch("pwd.getpwuid")
    @patch("os.getuid", return_value=501)
    def test_includes_all_users(
        self, mock_getuid: MagicMock, mock_getpwuid: MagicMock, mock_run: MagicMock
    ) -> None:
        """list_processes with user_only=False includes all users."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)
        mock_getpwuid.return_value = MagicMock(pw_name="testuser")

        processes = list_processes(user_only=False)

        assert len(processes) == 3

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    @patch("pwd.getpwuid")
    @patch("os.getuid", return_value=501)
    def test_filters_by_name(
        self, mock_getuid: MagicMock, mock_getpwuid: MagicMock, mock_run: MagicMock
    ) -> None:
        """list_processes filters by command name substring."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)
        mock_getpwuid.return_value = MagicMock(pw_name="testuser")

        processes = list_processes(name_filter="python", user_only=True)

        assert len(processes) == 1
        assert "python" in processes[0]["command"].lower()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    @patch("pwd.getpwuid")
    @patch("os.getuid", return_value=501)
    def test_filter_no_matches(
        self, mock_getuid: MagicMock, mock_getpwuid: MagicMock, mock_run: MagicMock
    ) -> None:
        """list_processes returns empty list when filter matches nothing."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)
        mock_getpwuid.return_value = MagicMock(pw_name="testuser")

        processes = list_processes(name_filter="nonexistent_process_xyz")
        assert processes == []

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    @patch("pwd.getpwuid")
    @patch("os.getuid", return_value=501)
    def test_result_structure(
        self, mock_getuid: MagicMock, mock_getpwuid: MagicMock, mock_run: MagicMock
    ) -> None:
        """Each process entry has pid, user, cpu, mem, command keys."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)
        mock_getpwuid.return_value = MagicMock(pw_name="testuser")

        processes = list_processes(user_only=False)

        for proc in processes:
            assert "pid" in proc
            assert "user" in proc
            assert "cpu" in proc
            assert "mem" in proc
            assert "command" in proc
            assert isinstance(proc["pid"], int)
            assert isinstance(proc["cpu"], float)
            assert isinstance(proc["mem"], float)


class TestGetProcessInfo:
    """Tests for get_process_info()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_returns_process_details(self, mock_run: MagicMock) -> None:
        """get_process_info returns detailed info for a valid PID."""
        mock_run.return_value = _make_completed(stdout=PS_SINGLE_PROCESS_OUTPUT)

        result = get_process_info(100)

        assert result["pid"] == 100
        assert result["user"] == "testuser"
        assert result["cpu"] == 1.2
        assert result["mem"] == 0.5
        assert result["command"] == "/usr/bin/python3 server.py"

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_raises_not_found_for_bad_pid(self, mock_run: MagicMock) -> None:
        """get_process_info raises NotFoundError when PID does not exist."""
        mock_run.return_value = _make_completed(
            returncode=1,
            stdout="USER  PID  %CPU %MEM    VSZ   RSS STAT STARTED      TIME COMMAND\n",
        )

        with pytest.raises(NotFoundError, match="Process not found"):
            get_process_info(99999)

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_raises_not_found_for_empty_output(self, mock_run: MagicMock) -> None:
        """get_process_info raises NotFoundError when ps returns only header."""
        mock_run.return_value = _make_completed(returncode=1, stdout="")

        with pytest.raises(NotFoundError, match="Process not found"):
            get_process_info(12345)

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_result_has_all_keys(self, mock_run: MagicMock) -> None:
        """get_process_info result contains all expected fields."""
        mock_run.return_value = _make_completed(stdout=PS_SINGLE_PROCESS_OUTPUT)

        result = get_process_info(100)

        expected_keys = {
            "pid",
            "user",
            "cpu",
            "mem",
            "vsz",
            "rss",
            "stat",
            "started",
            "time",
            "command",
        }
        assert set(result.keys()) == expected_keys


class TestHealth:
    """Tests for health()."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_healthy_when_both_available(self, mock_run: MagicMock) -> None:
        """health() returns healthy when launchctl and ps both succeed."""

        def side_effect(cmd, **kwargs):
            if cmd[0] == "launchctl":
                return _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)
            elif cmd[0] == "ps":
                return _make_completed(stdout=PS_AUX_OUTPUT)
            return _make_completed(returncode=1)

        mock_run.side_effect = side_effect

        result = health()

        assert result["healthy"] is True
        assert result["status"] == "healthy"
        assert result["launchctl_available"] is True
        assert result["ps_available"] is True
        assert result["process_count"] > 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_unhealthy_when_launchctl_fails(self, mock_run: MagicMock) -> None:
        """health() returns unhealthy when launchctl fails."""

        def side_effect(cmd, **kwargs):
            if cmd[0] == "launchctl":
                return _make_completed(returncode=1, stderr="error")
            elif cmd[0] == "ps":
                return _make_completed(stdout=PS_AUX_OUTPUT)
            return _make_completed(returncode=1)

        mock_run.side_effect = side_effect

        result = health()

        assert result["healthy"] is False
        assert result["launchctl_available"] is False
        assert result["ps_available"] is True

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_unhealthy_when_ps_fails(self, mock_run: MagicMock) -> None:
        """health() returns unhealthy when ps fails."""

        def side_effect(cmd, **kwargs):
            if cmd[0] == "launchctl":
                return _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)
            elif cmd[0] == "ps":
                return _make_completed(returncode=1, stderr="error")
            return _make_completed(returncode=1)

        mock_run.side_effect = side_effect

        result = health()

        assert result["healthy"] is False
        assert result["launchctl_available"] is True
        assert result["ps_available"] is False
        assert result["process_count"] == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_counts_processes(self, mock_run: MagicMock) -> None:
        """health() reports the correct process count."""

        def side_effect(cmd, **kwargs):
            if cmd[0] == "launchctl":
                return _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)
            elif cmd[0] == "ps":
                return _make_completed(stdout=PS_AUX_OUTPUT)
            return _make_completed(returncode=1)

        mock_run.side_effect = side_effect

        result = health()

        # PS_AUX_OUTPUT has 1 header + 3 data lines = 3 processes
        assert result["process_count"] == 3


class TestBuildDomainTarget:
    """Tests for _build_domain_target()."""

    def test_system_domain(self) -> None:
        """System domain produces 'system/{service}' target."""
        target = _build_domain_target("com.example.svc", "system")
        assert target == "system/com.example.svc"

    def test_user_domain(self) -> None:
        """User domain produces 'user/{uid}/{service}' target."""
        import os

        target = _build_domain_target("com.example.svc", "user")
        uid = os.getuid()
        assert target == f"user/{uid}/com.example.svc"


class TestRunErrorHandling:
    """Tests for the _run() helper error paths."""

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_timeout_raises_copilot_error(self, mock_run: MagicMock) -> None:
        """_run raises CopilotError on subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["test"], timeout=30)

        with pytest.raises(CopilotError, match="timed out"):
            list_services()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_file_not_found_raises_copilot_error(self, mock_run: MagicMock) -> None:
        """_run raises CopilotError when command binary is not found."""
        mock_run.side_effect = FileNotFoundError("No such file")

        with pytest.raises(CopilotError, match="Command not found"):
            list_services()


# ===================================================================
# CLI integration tests
# ===================================================================


class TestServicesCLI:
    """CLI command tests for the 'services' subcommand group."""

    def test_services_help(self) -> None:
        """services --help lists available subcommands."""
        result = runner.invoke(app, ["services", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "status" in result.output
        assert "start" in result.output
        assert "stop" in result.output
        assert "restart" in result.output
        assert "load" in result.output
        assert "unload" in result.output
        assert "ps" in result.output
        assert "proc" in result.output
        assert "health" in result.output

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_list(self, mock_run: MagicMock) -> None:
        """services list displays service entries."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        result = runner.invoke(app, ["services", "list"])

        assert result.exit_code == 0
        assert "com.apple.Spotlight" in result.output
        assert "com.apple.Dock" in result.output

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_status(self, mock_run: MagicMock) -> None:
        """services status SERVICE shows service details."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        result = runner.invoke(app, ["services", "status", "com.apple.Spotlight"])

        assert result.exit_code == 0
        assert "com.apple.Spotlight" in result.output

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_status_not_found(self, mock_run: MagicMock) -> None:
        """services status for unknown service exits with code 1."""
        mock_run.return_value = _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)

        result = runner.invoke(app, ["services", "status", "com.nonexistent.xyz"])

        assert result.exit_code == 1

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_start(self, mock_run: MagicMock) -> None:
        """services start SERVICE invokes kickstart."""
        mock_run.return_value = _make_completed()

        result = runner.invoke(app, ["services", "start", "com.example.myapp"])

        assert result.exit_code == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_stop(self, mock_run: MagicMock) -> None:
        """services stop SERVICE invokes kill."""
        mock_run.return_value = _make_completed()

        result = runner.invoke(app, ["services", "stop", "com.example.myapp"])

        assert result.exit_code == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_restart(self, mock_run: MagicMock) -> None:
        """services restart SERVICE invokes stop then start."""
        mock_run.return_value = _make_completed()

        result = runner.invoke(app, ["services", "restart", "com.example.myapp"])

        assert result.exit_code == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_load(self, mock_run: MagicMock) -> None:
        """services load PATH invokes launchctl load."""
        mock_run.return_value = _make_completed()

        result = runner.invoke(app, ["services", "load", "/tmp/test.plist"])

        assert result.exit_code == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_unload(self, mock_run: MagicMock) -> None:
        """services unload PATH invokes launchctl unload."""
        mock_run.return_value = _make_completed()

        result = runner.invoke(app, ["services", "unload", "/tmp/test.plist"])

        assert result.exit_code == 0

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_health(self, mock_run: MagicMock) -> None:
        """services health shows health status."""

        def side_effect(cmd, **kwargs):
            if cmd[0] == "launchctl":
                return _make_completed(stdout=LAUNCHCTL_LIST_OUTPUT)
            elif cmd[0] == "ps":
                return _make_completed(stdout=PS_AUX_OUTPUT)
            return _make_completed(returncode=1)

        mock_run.side_effect = side_effect

        result = runner.invoke(app, ["services", "health"])

        assert result.exit_code == 0
        assert "healthy" in result.output.lower()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_health_unhealthy(self, mock_run: MagicMock) -> None:
        """services health shows unhealthy status when commands fail."""
        mock_run.return_value = _make_completed(returncode=1, stderr="error")

        result = runner.invoke(app, ["services", "health"])

        assert result.exit_code == 0
        assert "unhealthy" in result.output.lower()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_ps(self, mock_run: MagicMock) -> None:
        """services ps lists running processes."""
        mock_run.return_value = _make_completed(stdout=PS_AUX_OUTPUT)

        result = runner.invoke(app, ["services", "ps", "--all-users"])

        assert result.exit_code == 0
        assert "python" in result.output.lower() or "server" in result.output.lower()

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_proc(self, mock_run: MagicMock) -> None:
        """services proc PID shows process details."""
        mock_run.return_value = _make_completed(stdout=PS_SINGLE_PROCESS_OUTPUT)

        result = runner.invoke(app, ["services", "proc", "100"])

        assert result.exit_code == 0
        assert "100" in result.output

    @patch("copilot_cli.services.system_services.client.subprocess.run")
    def test_services_proc_not_found(self, mock_run: MagicMock) -> None:
        """services proc with unknown PID exits with code 1."""
        mock_run.return_value = _make_completed(returncode=1, stdout="")

        result = runner.invoke(app, ["services", "proc", "99999"])

        assert result.exit_code == 1
