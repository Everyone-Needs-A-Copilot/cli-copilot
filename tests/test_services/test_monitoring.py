"""Tests for the system monitoring service -- client layer and CLI commands."""

from __future__ import annotations

import subprocess
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.monitoring.client import (
    _parse_cpu_usage,
    _parse_disk_usage,
    _parse_memory_usage,
    _run_command,
    check_service_health,
    get_alerts,
    get_system_metrics,
    health,
)
from copilot_cli.shared.errors import CopilotError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


# Sample macOS command outputs used across multiple test classes.

SAMPLE_TOP_OUTPUT = (
    "Processes: 350 total, 2 running\n"
    "CPU usage: 5.0% user, 3.0% sys, 92.0% idle\n"
    "SharedLibs: 300M resident\n"
)

SAMPLE_VM_STAT_OUTPUT = (
    "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
    "Pages free:                              100000.\n"
    "Pages active:                            200000.\n"
    "Pages inactive:                           50000.\n"
    "Pages speculative:                         5000.\n"
    "Pages wired down:                        150000.\n"
)

SAMPLE_DF_OUTPUT = (
    "Filesystem      Size   Used  Avail Capacity  Mounted on\n"
    "/dev/disk1s1   500G   250G   250G    50%    /\n"
    "/dev/disk2s1   1.0T   400G   600G    40%    /Volumes/Dev\n"
)


# ------------------------------------------------------------------ #
# _run_command
# ------------------------------------------------------------------ #


class TestRunCommand:
    """Tests for the _run_command() internal helper."""

    @patch("copilot_cli.services.monitoring.client.subprocess.run")
    def test_returns_stripped_stdout(self, mock_run):
        """_run_command returns the stripped stdout from the subprocess."""
        mock_run.return_value = MagicMock(stdout="  hello world  \n")
        result = _run_command(["echo", "hello"])
        assert result == "hello world"

    @patch("copilot_cli.services.monitoring.client.subprocess.run")
    def test_timeout_raises_copilot_error(self, mock_run):
        """_run_command raises CopilotError when the subprocess times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["slow"], timeout=10)
        with pytest.raises(CopilotError, match="timed out"):
            _run_command(["slow"], timeout=10)

    @patch("copilot_cli.services.monitoring.client.subprocess.run")
    def test_command_not_found_raises_copilot_error(self, mock_run):
        """_run_command raises CopilotError when the command binary is missing."""
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(CopilotError, match="Command not found"):
            _run_command(["nosuchcmd"])

    @patch("copilot_cli.services.monitoring.client.subprocess.run")
    def test_generic_exception_raises_copilot_error(self, mock_run):
        """_run_command wraps unexpected exceptions in CopilotError."""
        mock_run.side_effect = OSError("permission denied")
        with pytest.raises(CopilotError, match="Command failed"):
            _run_command(["forbidden"])

    @patch("copilot_cli.services.monitoring.client.subprocess.run")
    def test_passes_timeout_to_subprocess(self, mock_run):
        """_run_command forwards the timeout parameter to subprocess.run."""
        mock_run.return_value = MagicMock(stdout="ok")
        _run_command(["cmd"], timeout=42)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 42


# ------------------------------------------------------------------ #
# _parse_cpu_usage
# ------------------------------------------------------------------ #


class TestParseCpuUsage:
    """Tests for _parse_cpu_usage() with mocked subprocess output."""

    @patch("copilot_cli.services.monitoring.client.platform.system", return_value="Darwin")
    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_parses_macos_top_output(self, mock_cmd, mock_platform):
        """Extracts CPU usage from macOS top output (100 - idle)."""
        mock_cmd.return_value = SAMPLE_TOP_OUTPUT
        result = _parse_cpu_usage()
        # 100 - 92.0 = 8.0
        assert result == 8.0

    @patch("copilot_cli.services.monitoring.client.platform.system", return_value="Darwin")
    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_returns_zero_when_no_cpu_line(self, mock_cmd, mock_platform):
        """Returns 0.0 when the top output has no CPU usage line."""
        mock_cmd.return_value = "Processes: 100 total\nNothing useful here"
        result = _parse_cpu_usage()
        assert result == 0.0

    @patch("copilot_cli.services.monitoring.client.platform.system", return_value="Darwin")
    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_high_cpu_usage(self, mock_cmd, mock_platform):
        """Correctly reports high CPU usage."""
        mock_cmd.return_value = (
            "Processes: 350 total\nCPU usage: 60.0% user, 35.0% sys, 5.0% idle\n"
        )
        result = _parse_cpu_usage()
        assert result == 95.0


# ------------------------------------------------------------------ #
# _parse_memory_usage
# ------------------------------------------------------------------ #


class TestParseMemoryUsage:
    """Tests for _parse_memory_usage() with mocked subprocess output."""

    @patch("copilot_cli.services.monitoring.client.platform.system", return_value="Darwin")
    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_parses_macos_vm_stat_output(self, mock_cmd, mock_platform):
        """Correctly computes memory percentages from vm_stat output."""
        mock_cmd.return_value = SAMPLE_VM_STAT_OUTPUT
        result = _parse_memory_usage()

        assert "used_percent" in result
        assert "used_gb" in result
        assert "total_gb" in result
        assert result["total_gb"] > 0
        assert result["used_gb"] > 0
        assert 0 <= result["used_percent"] <= 100

    @patch("copilot_cli.services.monitoring.client.platform.system", return_value="Darwin")
    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_memory_calculation_values(self, mock_cmd, mock_platform):
        """Verify the specific calculation with known page counts.

        Pages: free=100000, active=200000, inactive=50000,
               speculative=5000, wired=150000
        Total = 505000 pages, used (active+wired) = 350000 pages
        Page size = 16384 bytes
        used_percent = (350000 / 505000) * 100 ~ 69.3%
        """
        mock_cmd.return_value = SAMPLE_VM_STAT_OUTPUT
        result = _parse_memory_usage()

        expected_pct = round((350000 / 505000) * 100, 1)
        assert result["used_percent"] == expected_pct

        expected_total_gb = round((505000 * 16384) / (1024**3), 2)
        assert result["total_gb"] == expected_total_gb

        expected_used_gb = round((350000 * 16384) / (1024**3), 2)
        assert result["used_gb"] == expected_used_gb


# ------------------------------------------------------------------ #
# _parse_disk_usage
# ------------------------------------------------------------------ #


class TestParseDiskUsage:
    """Tests for _parse_disk_usage() with mocked subprocess output."""

    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_parses_df_output(self, mock_cmd):
        """Extracts disk information from df -h output."""
        mock_cmd.return_value = SAMPLE_DF_OUTPUT
        result = _parse_disk_usage()

        assert len(result) == 2

        root_disk = result[0]
        assert root_disk["filesystem"] == "/dev/disk1s1"
        assert root_disk["mount"] == "/"
        assert root_disk["use_percent"] == 50.0
        assert root_disk["size"] == "500G"
        assert root_disk["used"] == "250G"
        assert root_disk["available"] == "250G"

        dev_disk = result[1]
        assert dev_disk["mount"] == "/Volumes/Dev"
        assert dev_disk["use_percent"] == 40.0

    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_skips_virtual_filesystems(self, mock_cmd):
        """Virtual mounts like /dev and /proc are excluded."""
        mock_cmd.return_value = (
            "Filesystem      Size   Used  Avail Capacity  Mounted on\n"
            "/dev/disk1s1   500G   250G   250G    50%    /\n"
            "devfs          200K   200K     0B   100%    /dev\n"
        )
        result = _parse_disk_usage()
        mounts = [d["mount"] for d in result]
        assert "/" in mounts
        assert "/dev" not in mounts

    @patch("copilot_cli.services.monitoring.client._run_command")
    def test_empty_df_output(self, mock_cmd):
        """Returns an empty list when df has only a header line."""
        mock_cmd.return_value = "Filesystem      Size   Used  Avail Capacity  Mounted on\n"
        result = _parse_disk_usage()
        assert result == []


# ------------------------------------------------------------------ #
# get_system_metrics
# ------------------------------------------------------------------ #


class TestGetSystemMetrics:
    """Tests for get_system_metrics()."""

    @patch("copilot_cli.services.monitoring.client._parse_disk_usage")
    @patch("copilot_cli.services.monitoring.client._parse_memory_usage")
    @patch("copilot_cli.services.monitoring.client._parse_cpu_usage")
    def test_combines_all_parsers(self, mock_cpu, mock_mem, mock_disk):
        """get_system_metrics assembles cpu, memory, and disk sections."""
        mock_cpu.return_value = 8.0
        mock_mem.return_value = {
            "used_percent": 69.3,
            "used_gb": 5.34,
            "total_gb": 7.7,
        }
        mock_disk.return_value = [
            {
                "filesystem": "/dev/disk1s1",
                "size": "500G",
                "used": "250G",
                "available": "250G",
                "use_percent": 50.0,
                "mount": "/",
            }
        ]

        result = get_system_metrics()

        assert result["cpu"]["usage_percent"] == 8.0
        assert result["memory"]["used_percent"] == 69.3
        assert len(result["disk"]) == 1
        assert result["disk"][0]["mount"] == "/"


# ------------------------------------------------------------------ #
# check_service_health
# ------------------------------------------------------------------ #


class TestCheckServiceHealth:
    """Tests for check_service_health()."""

    @patch("copilot_cli.services.monitoring.client.httpx.get")
    def test_healthy_service(self, mock_get):
        """Reports a service as healthy when it returns a 2xx status."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 200
        mock_response.elapsed = timedelta(milliseconds=42)
        mock_get.return_value = mock_response

        services = [{"name": "n8n", "url": "http://localhost:5678/healthz"}]
        results = check_service_health(services)

        assert len(results) == 1
        assert results[0]["healthy"] is True
        assert results[0]["status_code"] == 200
        assert results[0]["name"] == "n8n"
        assert results[0]["response_ms"] == 42.0

    @patch("copilot_cli.services.monitoring.client.httpx.get")
    def test_unhealthy_service_status_code(self, mock_get):
        """Reports a service as unhealthy when it returns a non-2xx status."""
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 503
        mock_response.elapsed = timedelta(milliseconds=100)
        mock_get.return_value = mock_response

        services = [{"name": "down", "url": "http://localhost:9999/health"}]
        results = check_service_health(services)

        assert results[0]["healthy"] is False
        assert results[0]["status_code"] == 503

    @patch("copilot_cli.services.monitoring.client.httpx.get")
    def test_connection_error(self, mock_get):
        """Reports a service as unhealthy when the connection fails."""
        mock_get.side_effect = ConnectionError("Connection refused")

        services = [{"name": "offline", "url": "http://localhost:1234"}]
        results = check_service_health(services)

        assert len(results) == 1
        assert results[0]["healthy"] is False
        assert results[0]["status_code"] is None
        assert "error" in results[0]

    @patch("copilot_cli.services.monitoring.client.httpx.get")
    def test_multiple_services(self, mock_get):
        """Checks multiple services and returns a result for each."""
        ok_resp = MagicMock()
        ok_resp.is_success = True
        ok_resp.status_code = 200
        ok_resp.elapsed = timedelta(milliseconds=10)

        fail_resp = MagicMock()
        fail_resp.is_success = False
        fail_resp.status_code = 500
        fail_resp.elapsed = timedelta(milliseconds=200)

        mock_get.side_effect = [ok_resp, fail_resp]

        services = [
            {"name": "svc1", "url": "http://host1"},
            {"name": "svc2", "url": "http://host2"},
        ]
        results = check_service_health(services)

        assert len(results) == 2
        assert results[0]["healthy"] is True
        assert results[1]["healthy"] is False

    def test_empty_services_list(self):
        """Returns an empty list when no services are provided."""
        results = check_service_health([])
        assert results == []


# ------------------------------------------------------------------ #
# get_alerts
# ------------------------------------------------------------------ #


class TestGetAlerts:
    """Tests for get_alerts()."""

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_cpu_exceeds_threshold(self, mock_metrics):
        """Generates a CPU alert when usage exceeds the threshold."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 90.0},
            "memory": {"used_percent": 50.0},
            "disk": [],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 90.0})

        assert len(alerts) == 1
        assert alerts[0]["metric"] == "cpu"
        assert alerts[0]["current"] == 90.0
        assert alerts[0]["threshold"] == 80.0
        assert alerts[0]["level"] == "warning"

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_critical_cpu_alert(self, mock_metrics):
        """CPU usage >= 95% produces a critical-level alert."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 97.0},
            "memory": {"used_percent": 50.0},
            "disk": [],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 90.0})

        assert len(alerts) == 1
        assert alerts[0]["level"] == "critical"

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_memory_exceeds_threshold(self, mock_metrics):
        """Generates a memory alert when usage exceeds the threshold."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 92.0},
            "disk": [],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 85.0})

        assert len(alerts) == 1
        assert alerts[0]["metric"] == "memory"
        assert alerts[0]["current"] == 92.0

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_disk_exceeds_threshold(self, mock_metrics):
        """Generates a disk alert when usage exceeds the threshold."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 50.0},
            "disk": [
                {"use_percent": 95.5, "mount": "/"},
            ],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 85.0, "disk": 90.0})

        assert len(alerts) == 1
        assert alerts[0]["metric"] == "disk"
        assert alerts[0]["level"] == "critical"
        assert "/" in alerts[0]["message"]

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_all_ok_returns_empty_list(self, mock_metrics):
        """Returns an empty alert list when all metrics are below thresholds."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 30.0},
            "disk": [
                {"use_percent": 25.0, "mount": "/"},
            ],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 85.0, "disk": 90.0})
        assert alerts == []

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_multiple_alerts(self, mock_metrics):
        """Generates alerts for multiple metrics exceeding thresholds."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 90.0},
            "memory": {"used_percent": 92.0},
            "disk": [
                {"use_percent": 96.0, "mount": "/"},
            ],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 85.0, "disk": 90.0})

        metrics = [a["metric"] for a in alerts]
        assert "cpu" in metrics
        assert "memory" in metrics
        assert "disk" in metrics
        assert len(alerts) == 3

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_uses_settings_defaults_when_no_thresholds(self, mock_metrics, mock_settings):
        """Falls back to settings thresholds when none are passed explicitly."""
        # mock_settings has cpu_alert_threshold=80, memory_alert_threshold=85,
        # disk_alert_threshold=90
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 85.0},
            "memory": {"used_percent": 50.0},
            "disk": [],
        }

        alerts = get_alerts()  # No explicit thresholds

        assert len(alerts) == 1
        assert alerts[0]["metric"] == "cpu"
        assert alerts[0]["threshold"] == 80.0

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_multiple_disks_only_alerts_on_over_threshold(self, mock_metrics):
        """Only disks exceeding the threshold generate alerts."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 30.0},
            "disk": [
                {"use_percent": 50.0, "mount": "/"},
                {"use_percent": 92.0, "mount": "/data"},
                {"use_percent": 45.0, "mount": "/backup"},
            ],
        }

        alerts = get_alerts(thresholds={"cpu": 80.0, "memory": 85.0, "disk": 90.0})

        assert len(alerts) == 1
        assert alerts[0]["metric"] == "disk"
        assert "/data" in alerts[0]["message"]


# ------------------------------------------------------------------ #
# health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for health()."""

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_returns_healthy(self, mock_metrics):
        """health() returns healthy=True with basic metric data."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 12.5},
            "memory": {"used_percent": 60.0},
        }

        result = health()
        assert result["healthy"] is True
        assert result["cpu_percent"] == 12.5
        assert result["memory_percent"] == 60.0

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_returns_unhealthy_on_error(self, mock_metrics):
        """health() returns healthy=False when metric collection fails."""
        mock_metrics.side_effect = RuntimeError("subprocess broke")

        result = health()
        assert result["healthy"] is False
        assert "error" in result
        assert "subprocess broke" in result["error"]


# ------------------------------------------------------------------ #
# CLI commands
# ------------------------------------------------------------------ #


class TestMonitoringCLI:
    """CLI integration tests for the 'monitoring' subcommand group."""

    def test_monitoring_help(self, runner):
        """'copilot monitoring --help' lists available subcommands."""
        result = runner.invoke(app, ["monitoring", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "alerts" in result.output
        assert "health" in result.output

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_monitoring_status(self, mock_metrics, runner):
        """'copilot monitoring status' displays system metrics."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 15.0},
            "memory": {"used_percent": 60.0, "used_gb": 4.8, "total_gb": 8.0},
            "disk": [
                {
                    "filesystem": "/dev/disk1s1",
                    "size": "500G",
                    "used": "250G",
                    "available": "250G",
                    "use_percent": 50.0,
                    "mount": "/",
                }
            ],
        }

        result = runner.invoke(app, ["monitoring", "status"])
        assert result.exit_code == 0
        assert "CPU" in result.output
        assert "Memory" in result.output

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    @patch("copilot_cli.services.monitoring.client.get_settings")
    def test_monitoring_alerts_none(self, mock_settings_fn, mock_metrics, runner, mock_settings):
        """'copilot monitoring alerts' reports no active alerts."""
        mock_settings_fn.return_value = mock_settings
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 30.0},
            "disk": [],
        }

        result = runner.invoke(app, ["monitoring", "alerts"])
        assert result.exit_code == 0
        assert "No active alerts" in result.output

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_monitoring_health_ok(self, mock_metrics, runner):
        """'copilot monitoring health' reports healthy when metrics succeed."""
        mock_metrics.return_value = {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_percent": 40.0},
        }

        result = runner.invoke(app, ["monitoring", "health"])
        assert result.exit_code == 0

    @patch("copilot_cli.services.monitoring.client.get_system_metrics")
    def test_monitoring_health_fail(self, mock_metrics, runner):
        """'copilot monitoring health' exits 1 when metrics fail."""
        mock_metrics.side_effect = RuntimeError("broken")

        result = runner.invoke(app, ["monitoring", "health"])
        assert result.exit_code == 1
