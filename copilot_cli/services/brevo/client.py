"""Brevo email marketing API client."""

from __future__ import annotations

from typing import Any

import httpx

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.http_client import api_request, create_client

SERVICE = "brevo"
BASE_URL = "https://api.brevo.com/v3"


class BrevoClient:
    """Thin wrapper around the Brevo (formerly Sendinblue) REST API v3."""

    def __init__(self) -> None:
        settings = get_settings()
        decoded_key = settings.get_brevo_api_key()
        self._http: httpx.Client = create_client(
            base_url=BASE_URL,
            headers={"api-key": decoded_key},
        )

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def get_contacts(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List contacts with pagination.

        Args:
            limit: Maximum contacts to return (max 50 per Brevo).
            offset: Number of contacts to skip.

        Returns:
            Paginated response containing ``contacts`` list.
        """
        return api_request(
            self._http,
            "GET",
            "/contacts",
            service=SERVICE,
            params={"limit": limit, "offset": offset},
        )

    def get_contact(self, identifier: str) -> dict[str, Any]:
        """Get a single contact by email or ID.

        Args:
            identifier: Contact email address or numeric ID.

        Returns:
            The contact object.
        """
        return api_request(self._http, "GET", f"/contacts/{identifier}", service=SERVICE)

    def create_contact(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new contact.

        Args:
            data: Contact payload (email, attributes, listIds, etc.).

        Returns:
            Created contact response with ``id``.
        """
        return api_request(self._http, "POST", "/contacts", service=SERVICE, json=data)

    def update_contact(self, identifier: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing contact.

        Args:
            identifier: Contact email or numeric ID.
            data: Fields to update.

        Returns:
            API confirmation (typically empty on success).
        """
        return api_request(self._http, "PUT", f"/contacts/{identifier}", service=SERVICE, json=data)

    def delete_contact(self, identifier: str) -> dict[str, Any]:
        """Delete a contact.

        Args:
            identifier: Contact email or numeric ID.

        Returns:
            API confirmation payload.
        """
        return api_request(self._http, "DELETE", f"/contacts/{identifier}", service=SERVICE)

    # ------------------------------------------------------------------
    # Contact Lists
    # ------------------------------------------------------------------

    def get_lists(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List contact lists with pagination.

        Args:
            limit: Maximum lists to return.
            offset: Number of lists to skip.

        Returns:
            Paginated response containing ``lists``.
        """
        return api_request(
            self._http,
            "GET",
            "/contacts/lists",
            service=SERVICE,
            params={"limit": limit, "offset": offset},
        )

    def create_list(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new contact list.

        Args:
            data: List definition (name, folderId).

        Returns:
            Created list response with ``id``.
        """
        return api_request(self._http, "POST", "/contacts/lists", service=SERVICE, json=data)

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def get_campaigns(
        self,
        type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List email campaigns with optional filters.

        Args:
            type: Campaign type filter (e.g. ``classic``).
            status: Campaign status filter (e.g. ``sent``, ``draft``).
            limit: Maximum campaigns to return.
            offset: Number of campaigns to skip.

        Returns:
            Paginated response containing ``campaigns`` list.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if type:
            params["type"] = type
        if status:
            params["status"] = status
        return api_request(self._http, "GET", "/emailCampaigns", service=SERVICE, params=params)

    def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new email campaign.

        Args:
            data: Campaign definition payload.

        Returns:
            Created campaign response with ``id``.
        """
        return api_request(self._http, "POST", "/emailCampaigns", service=SERVICE, json=data)

    def send_campaign(self, campaign_id: int) -> dict[str, Any]:
        """Send an email campaign immediately.

        Args:
            campaign_id: Numeric campaign ID.

        Returns:
            API confirmation payload.
        """
        return api_request(
            self._http, "POST", f"/emailCampaigns/{campaign_id}/sendNow", service=SERVICE
        )

    def get_campaign_stats(self, campaign_id: int) -> dict[str, Any]:
        """Get statistics for a sent campaign.

        Args:
            campaign_id: Numeric campaign ID.

        Returns:
            Campaign statistics object.
        """
        return api_request(
            self._http, "GET", f"/emailCampaigns/{campaign_id}/statistics", service=SERVICE
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def get_templates(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List SMTP templates.

        Args:
            limit: Maximum templates to return.
            offset: Number of templates to skip.

        Returns:
            Paginated response containing ``templates`` list.
        """
        return api_request(
            self._http,
            "GET",
            "/smtp/templates",
            service=SERVICE,
            params={"limit": limit, "offset": offset},
        )

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new SMTP template.

        Args:
            data: Template definition (templateName, htmlContent, subject, etc.).

        Returns:
            Created template response with ``id``.
        """
        return api_request(self._http, "POST", "/smtp/templates", service=SERVICE, json=data)

    # ------------------------------------------------------------------
    # Transactional email
    # ------------------------------------------------------------------

    def send_transactional(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send a transactional email.

        Args:
            data: Email payload (sender, to, subject, htmlContent, etc.).

        Returns:
            Send response with ``messageId``.
        """
        return api_request(self._http, "POST", "/smtp/email", service=SERVICE, json=data)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Test connectivity by fetching the account info.

        Returns:
            Dict with ``healthy`` boolean and account details.
        """
        try:
            account = api_request(self._http, "GET", "/account", service=SERVICE)
            return {
                "healthy": True,
                "status": "healthy",
                "company": account.get("companyName", ""),
                "plan": account.get("plan", [{}])[0].get("type", "") if account.get("plan") else "",
            }
        except CopilotError as exc:
            return {"healthy": False, "status": "unhealthy", "error": str(exc)}
        except Exception as exc:
            return {"healthy": False, "status": "unhealthy", "error": str(exc)}
