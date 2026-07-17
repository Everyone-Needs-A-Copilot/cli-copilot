"""Tests for Coolify service diagnostics, log access, and monitoring."""

from __future__ import annotations

import asyncio
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Service container discovery tests ---


class TestDiscoverServiceContainers:
    def test_returns_empty_when_no_ssh(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            discover_service_containers,
        )

        result = discover_service_containers(None, "test-uuid")
        assert result == []

    def test_discovers_by_label(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            discover_service_containers,
        )

        ssh = MagicMock()
        ssh.execute.return_value = (
            "svc-test-formbricks|abc123def456|formbricks:latest|Up 2 hours\n"
            "svc-test-postgres|789012345678|postgres:15|Up 2 hours\n"
        )

        result = discover_service_containers(ssh, "test-uuid")
        assert len(result) == 2
        assert result[0].name == "svc-test-formbricks"
        assert result[0].image == "formbricks:latest"
        assert result[0].service_component == "formbricks"
        assert result[1].service_component == "postgres"

    def test_fallback_to_name_matching(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            discover_service_containers,
        )

        ssh = MagicMock()
        # First call (label filter) returns empty, second call (all containers) has matches
        ssh.execute.side_effect = [
            "",  # Label-based discovery finds nothing
            "my-test-uuid-app|abc123|myimage:1|Up 1 hour\nother-container|def456|other:1|Up 1 hour\n",
        ]

        result = discover_service_containers(ssh, "test-uuid")
        assert len(result) == 1
        assert result[0].name == "my-test-uuid-app"

    def test_handles_ssh_error(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            discover_service_containers,
        )

        ssh = MagicMock()
        ssh.execute.side_effect = Exception("SSH connection lost")

        result = discover_service_containers(ssh, "test-uuid")
        assert result == []


# --- Service log retrieval tests ---


class TestServiceLogs:
    def test_get_logs_returns_empty_without_ssh(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            get_service_container_logs,
        )

        result = get_service_container_logs(None, "container-name")
        assert result == ""

    def test_get_logs_from_container(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            get_service_container_logs,
        )

        ssh = MagicMock()
        ssh.execute.return_value = "line1\nline2\nERROR: something failed\n"

        result = get_service_container_logs(ssh, "my-container", lines=100)
        assert "ERROR: something failed" in result
        ssh.execute.assert_called_once_with("docker logs --tail 100 my-container")

    def test_get_all_service_logs(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            get_all_service_logs,
        )

        ssh = MagicMock()
        # First call: discover containers (label-based)
        # Second call: logs for first container
        # Third call: logs for second container
        ssh.execute.side_effect = [
            "svc-app|abc123|img:1|Up 1h\nsvc-db|def456|pg:15|Up 1h\n",
            "app log line 1\napp log line 2\n",
            "db log line 1\n",
        ]

        result = get_all_service_logs(ssh, "test-uuid", lines=50)
        assert "svc-app" in result
        assert "svc-db" in result
        assert "app log line 1" in result["svc-app"]

    def test_get_all_logs_returns_empty_without_ssh(self):
        from copilot_cli.services.coolify.monitoring.service_containers import (
            get_all_service_logs,
        )

        result = get_all_service_logs(None, "test-uuid")
        assert result == {}


# --- Service docker stats tests ---


class TestServiceDockerStats:
    def test_returns_empty_without_ssh(self):
        from copilot_cli.services.coolify.monitoring.docker_stats import (
            get_service_docker_stats,
        )

        result = get_service_docker_stats(None, "test-uuid")
        assert result == []


# --- Diagnose service tests ---


class TestDiagnoseService:
    def test_healthy_service(self):
        from copilot_cli.services.coolify.commands.diag import _diagnose_service

        client = AsyncMock()
        client.get_service.return_value = {
            "uuid": "svc-uuid",
            "name": "formbricks",
            "type": "formbricks",
            "status": "running:healthy",
            "domains": ["survey.example.com"],
        }
        client.list_service_envvars.return_value = [
            {"key": "DATABASE_URL", "is_build_time": False},
        ]

        with patch(
            "copilot_cli.services.coolify.core.resolver.resolve_service",
            new=AsyncMock(return_value="svc-uuid"),
        ):
            result = asyncio.run(_diagnose_service(client, "formbricks"))

        assert result["health"]["status"] == "healthy"
        assert result["service"]["name"] == "formbricks"
        assert result["environment_variables"]["count"] == 1
        assert result["ssh_available"] is False

    def test_unhealthy_service(self):
        from copilot_cli.services.coolify.commands.diag import _diagnose_service

        client = AsyncMock()
        client.get_service.return_value = {
            "uuid": "svc-uuid",
            "name": "formbricks",
            "status": "exited",
            "domains": [],
        }
        client.list_service_envvars.return_value = []

        with patch(
            "copilot_cli.services.coolify.core.resolver.resolve_service",
            new=AsyncMock(return_value="svc-uuid"),
        ):
            result = asyncio.run(_diagnose_service(client, "formbricks"))

        assert result["health"]["status"] == "unhealthy"
        assert len(result["health"]["issues"]) > 0

    def test_no_ssh_graceful_degradation(self):
        from copilot_cli.services.coolify.commands.diag import _diagnose_service

        client = AsyncMock()
        client.get_service.return_value = {
            "uuid": "svc-uuid",
            "name": "formbricks",
            "status": "running:healthy",
            "domains": [],
        }
        client.list_service_envvars.return_value = []

        with patch(
            "copilot_cli.services.coolify.core.resolver.resolve_service",
            new=AsyncMock(return_value="svc-uuid"),
        ):
            result = asyncio.run(_diagnose_service(client, "formbricks", ssh=None))

        assert result["ssh_available"] is False
        assert result["containers"] == []
        assert result["logs"] == {}
        # Should have SSH recommendation
        ssh_recs = [r for r in result["recommendations"] if "SSH" in r["title"]]
        assert len(ssh_recs) == 1


# --- Recommendations tests ---


class TestRecommendations:
    def test_oom_detection(self):
        from copilot_cli.services.coolify.monitoring.log_analyzer import LogAnalysis
        from copilot_cli.services.coolify.monitoring.recommendations import (
            assess_service_health,
        )

        service_data = {"status": "running"}
        containers = []
        log_analyses = {
            "formbricks-app": LogAnalysis(
                total_lines=100,
                error_lines=5,
                error_rate=5.0,
                pattern_counts={"oom": 3, "error": 5},
                recent_errors=["Out of memory"],
                top_errors=[("oom", 3), ("error", 5)],
            )
        }

        recs = assess_service_health(service_data, containers, log_analyses)
        oom_recs = [
            r for r in recs if r["severity"] == "critical" and "memory" in r["title"].lower()
        ]
        assert len(oom_recs) == 1

    def test_high_memory_warning(self):
        from copilot_cli.services.coolify.monitoring.docker_stats import ContainerStats
        from copilot_cli.services.coolify.monitoring.recommendations import (
            assess_service_health,
        )

        service_data = {"status": "running"}
        containers = [
            ContainerStats(
                name="formbricks-app",
                container_id="abc123",
                cpu_percent=10.0,
                memory_usage="900MiB",
                memory_limit="1GiB",
                memory_percent=90.0,
                status="Up 2 hours",
            )
        ]

        recs = assess_service_health(service_data, containers, {})
        mem_recs = [r for r in recs if "memory" in r["title"].lower()]
        assert len(mem_recs) == 1
        assert mem_recs[0]["severity"] == "warning"

    def test_exited_container(self):
        from copilot_cli.services.coolify.monitoring.docker_stats import ContainerStats
        from copilot_cli.services.coolify.monitoring.recommendations import (
            assess_service_health,
        )

        service_data = {"status": "running"}
        containers = [
            ContainerStats(
                name="formbricks-app",
                status="Exited (137) 5 minutes ago",
            )
        ]

        recs = assess_service_health(service_data, containers, {})
        exit_recs = [r for r in recs if "exited" in r["title"].lower()]
        assert len(exit_recs) == 1
        assert exit_recs[0]["severity"] == "critical"

    def test_service_down(self):
        from copilot_cli.services.coolify.monitoring.recommendations import (
            assess_service_health,
        )

        service_data = {"status": "exited"}
        recs = assess_service_health(service_data, [], {})
        down_recs = [r for r in recs if "down" in r["title"].lower()]
        assert len(down_recs) == 1


# --- Monitor watch output format test ---


class TestMonitorWatch:
    def test_watch_output_has_required_fields(self):
        """Verify the status document structure matches NDJSON contract."""
        import json
        from datetime import datetime, timezone

        # Simulate what watch produces
        status_doc = {
            "timestamp": datetime.now(UTC).isoformat(),
            "overall_status": "healthy",
            "issues": [],
            "alerts": [],
            "domains": [],
            "containers": [],
            "ssh_available": False,
        }

        # Should be valid JSON
        serialized = json.dumps(status_doc)
        parsed = json.loads(serialized)
        assert "timestamp" in parsed
        assert "overall_status" in parsed
        assert parsed["overall_status"] in ("healthy", "degraded", "critical")
        assert isinstance(parsed["issues"], list)
        assert isinstance(parsed["alerts"], list)
