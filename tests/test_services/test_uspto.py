"""Tests for the USPTO service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.shared.errors import ConfigError, NotFoundError

runner = CliRunner()


@pytest.fixture
def mock_api_request():
    with patch("copilot_cli.services.uspto.client.api_request") as mock:
        yield mock


@pytest.fixture
def mock_create_client():
    with patch("copilot_cli.services.uspto.client.create_client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_settings():
    with patch("copilot_cli.services.uspto.client.get_settings") as mock:
        mock.return_value = type(
            "SettingsStub",
            (),
            {
                "uspto_cli_api_key": "test-key",
                "uspto_cli_base_url": "https://api.uspto.gov/api/v1/",
                "uspto_tsdr_base_url": "https://tsdrapi.uspto.gov",
            },
        )()
        yield mock


@pytest.fixture
def uspto(mock_api_request, mock_create_client, mock_settings):
    from copilot_cli.services.uspto.client import USPTOClient

    return USPTOClient()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path / "uspto-data"))
    return tmp_path / "uspto-data"


def test_request_uses_odp_client(uspto, mock_api_request):
    mock_api_request.return_value = {"ok": True}
    result = uspto.request("patent/applications", params={"q": "battery"})

    mock_api_request.assert_called_once_with(
        uspto._odp,
        "GET",
        "/patent/applications",
        service="uspto",
        params={"q": "battery"},
        json=None,
    )
    assert result["ok"] is True


def test_tsdr_status_builds_expected_path(uspto, mock_api_request):
    mock_api_request.return_value = "<case><status>ok</status></case>"
    result = uspto.tsdr_status("78787878", identifier_type="sn", fmt="json")

    mock_api_request.assert_called_once_with(
        uspto._tsdr,
        "GET",
        "/ts/cd/casestatus/sn78787878/info.xml",
        service="uspto",
    )
    assert result == {"case": {"status": "ok"}}


def test_tsdr_documents_builds_expected_params(uspto, mock_api_request):
    mock_api_request.return_value = (
        "<bundle><document>one</document><document>two</document></bundle>"
    )
    result = uspto.tsdr_documents("sn", "72131351", fmt="json", category="RC", sort="date:A")

    mock_api_request.assert_called_once_with(
        uspto._tsdr,
        "GET",
        "/ts/cd/casedocs/bundle.xml",
        service="uspto",
        params={"sn": "72131351", "category": "RC", "sort": "date:A"},
    )
    assert result == {"bundle": {"document": ["one", "two"]}}


def test_xml_converter_preserves_attributes_and_text(uspto):
    result = uspto._xml_text_to_json(
        '<root id="1"><item code="A">alpha</item><item code="B">beta</item></root>'
    )
    assert result == {
        "root": {
            "@attrs": {"id": "1"},
            "item": [
                {"@attrs": {"code": "A"}, "#text": "alpha"},
                {"@attrs": {"code": "B"}, "#text": "beta"},
            ],
        }
    }


def test_request_requires_base_url(mock_api_request, mock_create_client):
    with patch("copilot_cli.services.uspto.client.get_settings") as mock_settings:
        mock_settings.return_value = type(
            "SettingsStub",
            (),
            {
                "uspto_cli_api_key": "test-key",
                "uspto_cli_base_url": "",
                "uspto_tsdr_base_url": "https://tsdrapi.uspto.gov",
            },
        )()

        from copilot_cli.services.uspto.client import USPTOClient

        client = USPTOClient()
        with pytest.raises(ConfigError):
            client.request("patent/applications")


def test_import_session_stores_normalized_state(uspto, data_dir, tmp_path):
    session_file = tmp_path / "session.json"
    session_file.write_text(
        json.dumps([{"name": "session", "value": "abc", "domain": ".uspto.gov", "path": "/"}])
    )

    result = uspto.import_session("portal", str(session_file))

    assert result["name"] == "portal"
    assert result["cookie_count"] == 1
    stored = json.loads((data_dir / "session_states" / "portal.json").read_text())
    assert stored["cookies"][0]["value"] == "abc"
    assert stored["origins"] == []


def test_build_and_save_dossier(uspto, data_dir, mock_api_request):
    mock_api_request.return_value = "<case><status>LIVE</status></case>"

    dossier = uspto.build_dossier(["72131351"])
    result = uspto.save_dossier("acme", dossier)

    assert result["name"] == "acme"
    saved = uspto.get_dossier("acme")
    assert saved["summary"]["seed_count"] == 1
    assert (
        "Active or pending trademark record detected; manual legal review is recommended."
        in saved["summary"]["active_flags"]
    )


def test_run_watch_creates_initial_snapshot(uspto, data_dir, mock_api_request):
    mock_api_request.return_value = "<case><status>LIVE</status></case>"
    uspto.create_watch("acme-watch", ["72131351"])

    result = uspto.run_watch("acme-watch")

    assert result["events"][0]["type"] == "initialized"
    assert result["watch"]["name"] == "acme-watch"


def test_get_missing_dossier_raises(uspto, data_dir):
    with pytest.raises(NotFoundError):
        uspto.get_dossier("missing")


def test_auth_instructions_include_capture_guide(uspto):
    result = uspto.auth_instructions("patent_center_session")
    assert result["kind"] == "storage_state"
    assert "capture_guide" in result


def test_auth_status_reports_missing_sessions(uspto, data_dir):
    result = uspto.auth_status()
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["odp_api_key"]["status"] == "ready"
    assert checks["patent_center_session"]["status"] == "missing"
    assert checks["copyright_records_access"]["status"] == "ready"


def test_patent_ptab_handoff_contains_citation(uspto):
    result = uspto.patent_ptab("IPR2024")
    assert result["record_type"] == "patent_proceeding"
    assert result["citations"][0]["label"] == "PTAB API Help Guide"


def test_patent_office_action_fields_uses_real_path(uspto, mock_api_request):
    mock_api_request.return_value = {
        "apiKey": "oa_actions",
        "fieldCount": 56,
        "fields": ["bodyText"],
    }

    result = uspto.patent_office_action_fields()

    mock_api_request.assert_called_once_with(
        uspto._odp,
        "GET",
        "/patent/oa/oa_actions/v1/fields",
        service="uspto",
        params=None,
        json=None,
    )
    assert result["record_type"] == "patent_office_action_fields"
    assert result["normalized"]["apiKey"] == "oa_actions"


def test_patent_office_action_records_uses_form_payload(uspto, mock_api_request):
    mock_api_request.return_value = {
        "response": {
            "start": 0,
            "numFound": 2,
            "docs": [{"id": "doc-1"}, {"id": "doc-2"}],
        }
    }

    result = uspto.patent_office_action_records(criteria="*:*", start=0, rows=2)

    mock_api_request.assert_called_once_with(
        uspto._odp,
        "POST",
        "/patent/oa/oa_actions/v1/records",
        service="uspto",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        content="criteria=%2A%3A%2A&start=0&rows=2",
    )
    assert result["record_type"] == "patent_office_action"
    assert result["normalized"]["num_found"] == 2
    assert len(result["normalized"]["documents"]) == 2


def test_uspto_help_registered():
    result = runner.invoke(app, ["uspto", "--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "patents" in result.output
    assert "dossier" in result.output
    assert "sessions" in result.output
    assert "products" in result.output
    assert "tsdr" in result.output


def test_uspto_health_reports_a_verdict_when_the_credential_is_unresolvable():
    """`uspto health` must REPORT a signed-out credential, not crash.

    `USPTOClient.health()` already downgrades a failed probe to an unhealthy
    verdict, but BUILDING the client reads `USPTO_CLI_API_KEY` -- which is where
    a signed-out credential raises, upstream of that guard. This command carried
    the same missing `except CopilotError` as brevo/insights/nocodb/research;
    it now shares their `report_health` wrapper.
    """
    from copilot_cli.config.secrets_ladder import SecretResolutionError

    def signed_out():
        raise SecretResolutionError("USPTO_CLI_API_KEY")

    with patch("copilot_cli.services.uspto.commands._client", signed_out):
        result = runner.invoke(app, ["uspto", "health"])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "unhealthy" in result.output
    assert "USPTO_CLI_API_KEY" in result.output


def test_uspto_health_exits_zero_and_keeps_its_probe_detail():
    class _Healthy:
        def health(self):
            return {"healthy": True, "odp_base_url": "https://api.uspto.gov/api/v1"}

    with patch("copilot_cli.services.uspto.commands._client", _Healthy):
        result = runner.invoke(app, ["uspto", "health"])

    assert result.exit_code == 0
    assert "healthy" in result.output


def test_uspto_health_exits_one_and_shows_the_client_findings_when_unhealthy():
    class _Unhealthy:
        def health(self):
            return {
                "healthy": False,
                "error": "Permission denied",
                "odp_base_url": "https://api.uspto.gov/api/v1",
            }

    with patch("copilot_cli.services.uspto.commands._client", _Unhealthy):
        result = runner.invoke(app, ["uspto", "health"])

    assert result.exit_code == 1
    assert "unhealthy" in result.output
    assert "odp_base_url" in result.output
