"""Comprehensive tests for the Brevo email marketing API service.

Covers:
- BrevoClient method calls with correct endpoints and parameters
- Contact CRUD operations
- Campaign listing with filters
- Transactional email sending
- Health check success and failure paths
- CLI commands (contacts list, health)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.shared.errors import AuthError, ConnectionError, CopilotError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api_request():
    with patch("copilot_cli.services.brevo.client.api_request") as mock:
        yield mock


@pytest.fixture
def mock_create_client():
    with patch("copilot_cli.services.brevo.client.create_client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def brevo(mock_api_request, mock_create_client):
    """Instantiate a BrevoClient with mocked HTTP plumbing."""
    from copilot_cli.services.brevo.client import BrevoClient

    return BrevoClient()


# ======================================================================
# Contacts
# ======================================================================


class TestGetContacts:
    """BrevoClient.get_contacts method."""

    def test_default_pagination(self, brevo, mock_api_request):
        """get_contacts uses default limit=50 and offset=0."""
        mock_api_request.return_value = {"contacts": [], "count": 0}
        result = brevo.get_contacts()

        mock_api_request.assert_called_once_with(
            brevo._http,
            "GET",
            "/contacts",
            service="brevo",
            params={"limit": 50, "offset": 0},
        )
        assert result["count"] == 0

    def test_custom_pagination(self, brevo, mock_api_request):
        """get_contacts respects custom limit and offset."""
        mock_api_request.return_value = {"contacts": [{"email": "a@b.com"}], "count": 1}
        brevo.get_contacts(limit=10, offset=20)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["limit"] == 10
        assert params["offset"] == 20


class TestGetContact:
    """BrevoClient.get_contact method."""

    def test_by_email(self, brevo, mock_api_request):
        """get_contact fetches by email identifier."""
        mock_api_request.return_value = {"email": "test@example.com", "id": 1}
        result = brevo.get_contact("test@example.com")

        mock_api_request.assert_called_once_with(
            brevo._http, "GET", "/contacts/test@example.com", service="brevo"
        )
        assert result["id"] == 1

    def test_by_numeric_id(self, brevo, mock_api_request):
        """get_contact fetches by numeric ID string."""
        mock_api_request.return_value = {"email": "x@y.com", "id": 42}
        brevo.get_contact("42")

        path = mock_api_request.call_args[0][2]
        assert path == "/contacts/42"


class TestCreateContact:
    """BrevoClient.create_contact method."""

    def test_posts_data(self, brevo, mock_api_request):
        """create_contact POSTs the contact payload."""
        payload = {"email": "new@example.com", "listIds": [1, 2]}
        mock_api_request.return_value = {"id": 99}
        result = brevo.create_contact(payload)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/contacts", service="brevo", json=payload
        )
        assert result["id"] == 99

    def test_with_attributes(self, brevo, mock_api_request):
        """create_contact passes attributes through."""
        payload = {
            "email": "new@example.com",
            "attributes": {"FIRSTNAME": "Jane", "LASTNAME": "Doe"},
        }
        mock_api_request.return_value = {"id": 100}
        brevo.create_contact(payload)

        json_data = mock_api_request.call_args.kwargs.get("json")
        assert json_data["attributes"]["FIRSTNAME"] == "Jane"


class TestUpdateContact:
    """BrevoClient.update_contact method."""

    def test_puts_data(self, brevo, mock_api_request):
        """update_contact PUTs to /contacts/{identifier}."""
        mock_api_request.return_value = ""
        brevo.update_contact("test@example.com", {"attributes": {"FIRSTNAME": "Updated"}})

        mock_api_request.assert_called_once_with(
            brevo._http,
            "PUT",
            "/contacts/test@example.com",
            service="brevo",
            json={"attributes": {"FIRSTNAME": "Updated"}},
        )


class TestDeleteContact:
    """BrevoClient.delete_contact method."""

    def test_deletes_by_identifier(self, brevo, mock_api_request):
        """delete_contact DELETEs the correct endpoint."""
        mock_api_request.return_value = ""
        brevo.delete_contact("test@example.com")

        mock_api_request.assert_called_once_with(
            brevo._http, "DELETE", "/contacts/test@example.com", service="brevo"
        )


# ======================================================================
# Lists
# ======================================================================


class TestGetLists:
    """BrevoClient.get_lists method."""

    def test_default_params(self, brevo, mock_api_request):
        """get_lists uses default pagination."""
        mock_api_request.return_value = {"lists": [], "count": 0}
        brevo.get_lists()

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"limit": 50, "offset": 0}


class TestCreateList:
    """BrevoClient.create_list method."""

    def test_posts_list_data(self, brevo, mock_api_request):
        """create_list POSTs to /contacts/lists."""
        payload = {"name": "Newsletter", "folderId": 1}
        mock_api_request.return_value = {"id": 5}
        brevo.create_list(payload)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/contacts/lists", service="brevo", json=payload
        )


# ======================================================================
# Campaigns
# ======================================================================


class TestGetCampaigns:
    """BrevoClient.get_campaigns method."""

    def test_default_params(self, brevo, mock_api_request):
        """get_campaigns uses defaults with no filters."""
        mock_api_request.return_value = {"campaigns": []}
        brevo.get_campaigns()

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"limit": 50, "offset": 0}

    def test_with_type_filter(self, brevo, mock_api_request):
        """get_campaigns passes type filter."""
        mock_api_request.return_value = {"campaigns": []}
        brevo.get_campaigns(type="classic")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["type"] == "classic"

    def test_with_status_filter(self, brevo, mock_api_request):
        """get_campaigns passes status filter."""
        mock_api_request.return_value = {"campaigns": []}
        brevo.get_campaigns(status="sent")

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["status"] == "sent"

    def test_with_all_filters(self, brevo, mock_api_request):
        """get_campaigns passes both type and status."""
        mock_api_request.return_value = {"campaigns": []}
        brevo.get_campaigns(type="classic", status="draft", limit=10, offset=5)

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"type": "classic", "status": "draft", "limit": 10, "offset": 5}


class TestCreateCampaign:
    """BrevoClient.create_campaign method."""

    def test_posts_campaign_data(self, brevo, mock_api_request):
        """create_campaign POSTs to /emailCampaigns."""
        payload = {
            "name": "Welcome Campaign",
            "subject": "Hello!",
            "sender": {"name": "Test", "email": "test@example.com"},
            "recipients": {"listIds": [1]},
            "htmlContent": "<h1>Hi</h1>",
        }
        mock_api_request.return_value = {"id": 42}
        result = brevo.create_campaign(payload)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/emailCampaigns", service="brevo", json=payload
        )
        assert result["id"] == 42


class TestSendCampaign:
    """BrevoClient.send_campaign method."""

    def test_sends_immediately(self, brevo, mock_api_request):
        """send_campaign POSTs to /emailCampaigns/{id}/sendNow."""
        mock_api_request.return_value = ""
        brevo.send_campaign(42)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/emailCampaigns/42/sendNow", service="brevo"
        )


class TestGetCampaignStats:
    """BrevoClient.get_campaign_stats method."""

    def test_fetches_stats(self, brevo, mock_api_request):
        """get_campaign_stats GETs /emailCampaigns/{id}/statistics."""
        mock_api_request.return_value = {"delivered": 100, "opens": 50}
        result = brevo.get_campaign_stats(42)

        mock_api_request.assert_called_once_with(
            brevo._http, "GET", "/emailCampaigns/42/statistics", service="brevo"
        )
        assert result["delivered"] == 100


# ======================================================================
# Templates
# ======================================================================


class TestGetTemplates:
    """BrevoClient.get_templates method."""

    def test_default_params(self, brevo, mock_api_request):
        """get_templates uses default pagination."""
        mock_api_request.return_value = {"templates": [], "count": 0}
        brevo.get_templates()

        call_kwargs = mock_api_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params == {"limit": 50, "offset": 0}


class TestCreateTemplate:
    """BrevoClient.create_template method."""

    def test_posts_template_data(self, brevo, mock_api_request):
        """create_template POSTs to /smtp/templates."""
        payload = {
            "templateName": "Welcome",
            "subject": "Hi!",
            "htmlContent": "<p>Welcome</p>",
        }
        mock_api_request.return_value = {"id": 10}
        brevo.create_template(payload)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/smtp/templates", service="brevo", json=payload
        )


# ======================================================================
# Transactional email
# ======================================================================


class TestSendTransactional:
    """BrevoClient.send_transactional method."""

    def test_posts_email_data(self, brevo, mock_api_request):
        """send_transactional POSTs to /smtp/email."""
        payload = {
            "to": [{"email": "user@example.com"}],
            "subject": "Order Confirmation",
            "htmlContent": "<h1>Thank you</h1>",
            "sender": {"name": "Shop", "email": "shop@example.com"},
        }
        mock_api_request.return_value = {"messageId": "msg-123"}
        result = brevo.send_transactional(payload)

        mock_api_request.assert_called_once_with(
            brevo._http, "POST", "/smtp/email", service="brevo", json=payload
        )
        assert result["messageId"] == "msg-123"

    def test_minimal_email(self, brevo, mock_api_request):
        """send_transactional works with a minimal payload."""
        payload = {
            "to": [{"email": "a@b.com"}],
            "subject": "Test",
            "htmlContent": "<p>Test</p>",
        }
        mock_api_request.return_value = {"messageId": "msg-456"}
        result = brevo.send_transactional(payload)
        assert "messageId" in result


# ======================================================================
# Health
# ======================================================================


class TestHealth:
    """BrevoClient.health method."""

    def test_healthy_on_success(self, brevo, mock_api_request):
        """health returns healthy=True when /account call succeeds."""
        mock_api_request.return_value = {
            "companyName": "Acme Corp",
            "plan": [{"type": "premium"}],
        }
        result = brevo.health()

        assert result["healthy"] is True
        assert result["status"] == "healthy"
        assert result["company"] == "Acme Corp"
        assert result["plan"] == "premium"

    def test_healthy_with_empty_plan(self, brevo, mock_api_request):
        """health handles account with no plan list."""
        mock_api_request.return_value = {
            "companyName": "Solo",
            "plan": [],
        }
        result = brevo.health()

        assert result["healthy"] is True
        assert result["plan"] == ""

    def test_unhealthy_on_auth_error(self, brevo, mock_api_request):
        """health returns healthy=False on AuthError."""
        mock_api_request.side_effect = AuthError("Invalid key", service="brevo")
        result = brevo.health()

        assert result["healthy"] is False
        assert result["status"] == "unhealthy"
        assert "Invalid key" in result["error"]

    def test_unhealthy_on_connection_error(self, brevo, mock_api_request):
        """health returns healthy=False on ConnectionError."""
        mock_api_request.side_effect = ConnectionError("DNS failure", service="brevo")
        result = brevo.health()

        assert result["healthy"] is False
        assert "DNS failure" in result["error"]

    def test_unhealthy_on_generic_exception(self, brevo, mock_api_request):
        """health returns healthy=False on unexpected exceptions."""
        mock_api_request.side_effect = RuntimeError("kaboom")
        result = brevo.health()

        assert result["healthy"] is False
        assert "kaboom" in result["error"]


# ======================================================================
# CLI commands
# ======================================================================


class TestCLIContactsListCommand:
    """CLI: copilot brevo contacts list."""

    def test_contacts_list_success(self, cli):
        """brevo contacts list renders contacts table."""
        mock_client = MagicMock()
        mock_client.get_contacts.return_value = {
            "contacts": [
                {"email": "alice@example.com", "id": 1},
                {"email": "bob@example.com", "id": 2},
            ],
            "count": 2,
        }
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "contacts", "list")

        assert result.exit_code == 0
        assert "alice@example.com" in result.output

    def test_contacts_list_empty(self, cli):
        """brevo contacts list handles no contacts gracefully."""
        mock_client = MagicMock()
        mock_client.get_contacts.return_value = {"contacts": [], "count": 0}
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "contacts", "list")

        assert result.exit_code == 0

    def test_contacts_list_error(self, cli):
        """brevo contacts list exits 1 on API error."""
        mock_client = MagicMock()
        mock_client.get_contacts.side_effect = CopilotError("Service unavailable")
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "contacts", "list")

        assert result.exit_code == 1


class TestCLIContactsCreateCommand:
    """CLI: copilot brevo contacts create."""

    def test_contacts_create_success(self, cli):
        """brevo contacts create --email X creates a contact."""
        mock_client = MagicMock()
        mock_client.create_contact.return_value = {"id": 50}
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "contacts", "create", "--email", "new@test.com")

        assert result.exit_code == 0
        mock_client.create_contact.assert_called_once()


class TestCLICampaignsListCommand:
    """CLI: copilot brevo campaigns list."""

    def test_campaigns_list_success(self, cli):
        """brevo campaigns list renders campaigns."""
        mock_client = MagicMock()
        mock_client.get_campaigns.return_value = {"campaigns": [{"id": 1, "name": "Welcome"}]}
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "campaigns", "list")

        assert result.exit_code == 0
        assert "Welcome" in result.output


class TestCLIHealthCommand:
    """CLI: copilot brevo health."""

    def test_health_success(self, cli):
        """brevo health exits 0 when healthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": True,
            "status": "healthy",
            "company": "Test Co",
            "plan": "free",
        }
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "health")

        assert result.exit_code == 0

    def test_health_failure(self, cli):
        """brevo health exits 1 when unhealthy."""
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": False,
            "status": "unhealthy",
            "error": "auth failed",
        }
        with patch("copilot_cli.services.brevo.commands._client", return_value=mock_client):
            result = cli("brevo", "health")

        assert result.exit_code == 1
