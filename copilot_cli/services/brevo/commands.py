"""Typer subcommand group for Brevo email marketing operations."""

from __future__ import annotations

import json

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success, print_table

app = typer.Typer(no_args_is_help=True)

# -- Nested sub-apps for resource groups --
contacts_app = typer.Typer(no_args_is_help=True, help="Brevo contact management.")
lists_app = typer.Typer(no_args_is_help=True, help="Contact list management.")
campaigns_app = typer.Typer(no_args_is_help=True, help="Email campaign management.")
templates_app = typer.Typer(no_args_is_help=True, help="SMTP template management.")

app.add_typer(contacts_app, name="contacts")
app.add_typer(lists_app, name="lists")
app.add_typer(campaigns_app, name="campaigns")
app.add_typer(templates_app, name="templates")


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.brevo.client import BrevoClient

    return BrevoClient()


# ======================================================================
# Contacts
# ======================================================================


@contacts_app.command("list")
def contacts_list(
    limit: int = typer.Option(50, "--limit", help="Max contacts to return."),
    offset: int = typer.Option(0, "--offset", help="Number of contacts to skip."),
) -> None:
    """List Brevo contacts."""
    try:
        result = _client().get_contacts(limit=limit, offset=offset)
        rows = result.get("contacts", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Contacts")
        else:
            print_json(result, title="Contacts")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@contacts_app.command("get")
def contacts_get(
    identifier: str = typer.Argument(..., help="Contact email or numeric ID."),
) -> None:
    """Get a single contact."""
    try:
        result = _client().get_contact(identifier)
        print_json(result, title=f"Contact {identifier}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@contacts_app.command("create")
def contacts_create(
    email: str = typer.Option(..., "--email", help="Contact email address."),
    first_name: str | None = typer.Option(None, "--first-name", help="First name."),
    last_name: str | None = typer.Option(None, "--last-name", help="Last name."),
) -> None:
    """Create a new contact."""
    try:
        data: dict = {"email": email}
        attributes: dict = {}
        if first_name:
            attributes["FIRSTNAME"] = first_name
        if last_name:
            attributes["LASTNAME"] = last_name
        if attributes:
            data["attributes"] = attributes
        result = _client().create_contact(data)
        print_success(f"Contact created: {result.get('id', email)}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@contacts_app.command("update")
def contacts_update(
    identifier: str = typer.Argument(..., help="Contact email or numeric ID."),
    data: str = typer.Option(..., "--data", help="JSON string with fields to update."),
) -> None:
    """Update a contact with a JSON payload."""
    try:
        payload = json.loads(data)
        result = _client().update_contact(identifier, payload)
        print_success(f"Contact {identifier} updated.")
        if result:
            print_json(result)
    except json.JSONDecodeError as exc:
        print_error(f"Invalid JSON: {exc}")
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@contacts_app.command("delete")
def contacts_delete(
    identifier: str = typer.Argument(..., help="Contact email or numeric ID."),
) -> None:
    """Delete a contact."""
    try:
        _client().delete_contact(identifier)
        print_success(f"Contact {identifier} deleted.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Lists
# ======================================================================


@lists_app.command("list")
def lists_list(
    limit: int = typer.Option(50, "--limit", help="Max lists to return."),
    offset: int = typer.Option(0, "--offset", help="Number of lists to skip."),
) -> None:
    """List contact lists."""
    try:
        result = _client().get_lists(limit=limit, offset=offset)
        rows = result.get("lists", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Contact Lists")
        else:
            print_json(result, title="Contact Lists")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@lists_app.command("create")
def lists_create(
    name: str = typer.Option(..., "--name", help="List name."),
    folder_id: int = typer.Option(..., "--folder-id", help="Folder ID for the list."),
) -> None:
    """Create a new contact list."""
    try:
        result = _client().create_list({"name": name, "folderId": folder_id})
        print_success(f"List created: {result.get('id', '')}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Campaigns
# ======================================================================


@campaigns_app.command("list")
def campaigns_list(
    type: str | None = typer.Option(None, "--type", help="Campaign type (e.g. classic)."),
    status: str | None = typer.Option(None, "--status", help="Campaign status filter."),
    limit: int = typer.Option(50, "--limit", help="Max campaigns to return."),
) -> None:
    """List email campaigns."""
    try:
        result = _client().get_campaigns(type=type, status=status, limit=limit)
        rows = result.get("campaigns", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Campaigns")
        else:
            print_json(result, title="Campaigns")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@campaigns_app.command("create")
def campaigns_create(
    name: str = typer.Option(..., "--name", help="Campaign name."),
    subject: str = typer.Option(..., "--subject", help="Email subject line."),
    sender_name: str = typer.Option(..., "--sender-name", help="Sender display name."),
    sender_email: str = typer.Option(..., "--sender-email", help="Sender email address."),
    list_ids: str = typer.Option(..., "--list-ids", help="Comma-separated list IDs."),
    html: str = typer.Option(..., "--html", help="HTML content or path to HTML file."),
) -> None:
    """Create a new email campaign."""
    try:
        parsed_list_ids = [int(lid.strip()) for lid in list_ids.split(",")]
        data: dict = {
            "name": name,
            "subject": subject,
            "sender": {"name": sender_name, "email": sender_email},
            "recipients": {"listIds": parsed_list_ids},
            "htmlContent": html,
        }
        result = _client().create_campaign(data)
        print_success(f"Campaign created: {result.get('id', '')}")
        print_json(result)
    except ValueError:
        print_error("Invalid list IDs. Provide comma-separated integers.")
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@campaigns_app.command("send")
def campaigns_send(
    campaign_id: int = typer.Argument(..., help="Campaign ID to send."),
) -> None:
    """Send an email campaign immediately."""
    try:
        _client().send_campaign(campaign_id)
        print_success(f"Campaign {campaign_id} sent.")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@campaigns_app.command("stats")
def campaigns_stats(
    campaign_id: int = typer.Argument(..., help="Campaign ID."),
) -> None:
    """Get statistics for a campaign."""
    try:
        result = _client().get_campaign_stats(campaign_id)
        print_json(result, title=f"Campaign {campaign_id} Statistics")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Templates
# ======================================================================


@templates_app.command("list")
def templates_list(
    limit: int = typer.Option(50, "--limit", help="Max templates to return."),
) -> None:
    """List SMTP templates."""
    try:
        result = _client().get_templates(limit=limit)
        rows = result.get("templates", result) if isinstance(result, dict) else result
        if isinstance(rows, list):
            print_table(rows, title="Templates")
        else:
            print_json(result, title="Templates")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@templates_app.command("create")
def templates_create(
    name: str = typer.Option(..., "--name", help="Template name."),
    subject: str = typer.Option(..., "--subject", help="Email subject."),
    html: str = typer.Option(..., "--html", help="HTML content."),
) -> None:
    """Create a new SMTP template."""
    try:
        data: dict = {
            "templateName": name,
            "subject": subject,
            "htmlContent": html,
        }
        result = _client().create_template(data)
        print_success(f"Template created: {result.get('id', '')}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Transactional send (top-level command)
# ======================================================================


@app.command("send")
def send(
    to: str = typer.Option(..., "--to", help="Recipient email address."),
    subject: str = typer.Option(..., "--subject", help="Email subject."),
    html: str = typer.Option(..., "--html", help="HTML content."),
    sender_name: str | None = typer.Option(None, "--sender-name", help="Sender display name."),
    sender_email: str | None = typer.Option(None, "--sender-email", help="Sender email address."),
) -> None:
    """Send a transactional email."""
    try:
        data: dict = {
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        if sender_name or sender_email:
            data["sender"] = {}
            if sender_name:
                data["sender"]["name"] = sender_name
            if sender_email:
                data["sender"]["email"] = sender_email
        result = _client().send_transactional(data)
        print_success(f"Email sent: {result.get('messageId', '')}")
        print_json(result)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ======================================================================
# Health
# ======================================================================


@app.command()
def health() -> None:
    """Check Brevo API connectivity."""
    from copilot_cli.shared.output import print_health

    result = _client().health()
    healthy = result.get("healthy", False)
    print_health("brevo", healthy, result if not healthy else None)
    if not healthy:
        raise typer.Exit(1)
