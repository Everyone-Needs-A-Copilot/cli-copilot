"""Tests for `report_health`, the shared health-command wrapper.

The defect this covers: a `health` command that builds its client inline crashes
with a raw traceback when the credential is unresolvable, because
`SecretResolutionError` is raised during CONSTRUCTION -- upstream of the
client's own `health()` guard. Four services (brevo, insights, nocodb,
research) each shipped the same missing `except CopilotError`; `report_health`
is the single place that guard now lives.

Nothing here touches a real service: every check is a local callable.
"""

from __future__ import annotations

import json

import pytest
import typer

from copilot_cli.config.secrets_ladder import SecretResolutionError
from copilot_cli.shared.errors import ConnectionError as CopilotConnectionError
from copilot_cli.shared.output import report_health, set_json_mode


@pytest.fixture
def json_mode():
    """Run one test in the CLI's global JSON mode, then reset it.

    JSON mode is process-wide (see main.py's eager `--json` callback), so it
    must be torn down or later tests inherit it.
    """
    set_json_mode(True)
    try:
        yield
    finally:
        set_json_mode(False)


def _health_lines(capsys):
    """The JSON health records printed so far, in order."""
    out = capsys.readouterr().out
    return [json.loads(ln) for ln in out.strip().splitlines() if ln.strip().startswith("{")]


class TestUnresolvableCredential:
    """A credential that will not resolve is a VERDICT, not a crash."""

    def test_reports_unhealthy_instead_of_raising(self, json_mode, capsys):
        def signed_out():
            raise SecretResolutionError("RESEARCH_COPILOT_API_KEY")

        with pytest.raises(typer.Exit) as exit_info:
            report_health("research", signed_out)

        # typer.Exit is the CLI's normal exit path -- the SecretResolutionError
        # itself must not escape, which is what produced the traceback.
        assert exit_info.value.exit_code == 1

        record = _health_lines(capsys)[0]
        assert record["service"] == "research"
        assert record["status"] == "unhealthy"

    def test_names_the_missing_credential_and_how_to_provision_it(self, json_mode, capsys):
        """Fail-closed stays visible AND diagnosable -- never a bare 'unhealthy'."""

        def signed_out():
            raise SecretResolutionError("CLOUDFLARE_API_TOKEN")

        with pytest.raises(typer.Exit):
            report_health("cloudflare", signed_out)

        details = _health_lines(capsys)[0]["details"]
        assert "CLOUDFLARE_API_TOKEN" in details["error"]
        assert "CLOUDFLARE_API_TOKEN" in details["hint"]

    def test_reports_a_copilot_error_raised_by_the_probe_itself(self, json_mode, capsys):
        """Not just construction -- a failing probe is reported the same way."""

        def unreachable():
            raise CopilotConnectionError(
                "Cannot reach https://api.example.com",
                service="insights",
                hint="Check the service is running.",
            )

        with pytest.raises(typer.Exit):
            report_health("insights", unreachable)

        details = _health_lines(capsys)[0]["details"]
        assert details["error"] == "Cannot reach https://api.example.com"
        assert details["hint"] == "Check the service is running."


class TestVerdictFromTheProbeResult:
    """The client's own health dict decides the verdict and carries the detail."""

    def test_healthy_result_exits_zero(self, json_mode, capsys):
        report_health("brevo", lambda: {"healthy": True, "account": "acme"})

        record = _health_lines(capsys)[0]
        assert record == {"service": "brevo", "status": "healthy"}

    def test_unhealthy_result_exits_one_and_passes_the_dict_through_verbatim(
        self, json_mode, capsys
    ):
        """Service-specific findings must survive, not be flattened."""
        probe = {
            "healthy": False,
            "token_active": True,
            "zones_visible": 0,
            "dns_ready": False,
            "error": "The token is active, but no zones are visible.",
            "hint": "Grant Zone Read and DNS Write for the intended zones.",
        }

        with pytest.raises(typer.Exit) as exit_info:
            report_health("cloudflare", lambda: probe)

        assert exit_info.value.exit_code == 1
        assert _health_lines(capsys)[0]["details"] == probe

    def test_a_result_missing_the_healthy_key_is_treated_as_unhealthy(self, json_mode, capsys):
        """Fail closed: an ambiguous probe is not a passing one."""
        with pytest.raises(typer.Exit) as exit_info:
            report_health("nocodb", lambda: {})

        assert exit_info.value.exit_code == 1
        assert _health_lines(capsys)[0]["status"] == "unhealthy"


class TestSuccessMessage:
    """Services that surface an extra healthy-path detail keep doing so."""

    def test_success_message_is_printed_only_when_healthy(self, json_mode, capsys):
        report_health(
            "cloudflare",
            lambda: {"healthy": True, "zones_visible": 7},
            success_message=lambda result: (
                f"Cloudflare DNS is ready ({result['zones_visible']} zones visible)"
            ),
        )

        records = _health_lines(capsys)
        assert records[0]["status"] == "healthy"
        assert records[1] == {
            "status": "ok",
            "message": "Cloudflare DNS is ready (7 zones visible)",
        }

    def test_success_message_is_skipped_on_an_unhealthy_verdict(self, json_mode, capsys):
        with pytest.raises(typer.Exit):
            report_health(
                "cloudflare",
                lambda: {"healthy": False},
                success_message=lambda result: "should not be printed",
            )

        assert all(r.get("status") != "ok" for r in _health_lines(capsys))


class TestOnlyCopilotErrorsAreCaught:
    def test_a_genuine_bug_still_surfaces(self, json_mode):
        """A non-CopilotError must NOT be laundered into a misleading 'unhealthy'."""

        def broken():
            raise TypeError("health() takes 1 positional argument but 2 were given")

        with pytest.raises(TypeError):
            report_health("brevo", broken)
