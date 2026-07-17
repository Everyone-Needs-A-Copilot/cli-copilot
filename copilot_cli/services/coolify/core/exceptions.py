"""Custom exceptions for the Coolify CLI."""

from __future__ import annotations

from copilot_cli.shared.errors import CopilotError


class CoolifyError(CopilotError):
    """Base exception for all Coolify CLI errors.

    Subclasses `CopilotError` (SOUL.md §6 Quality Bar / Principle 4: Honest
    Failure) so every Coolify error carries a `service` and can be handled
    uniformly alongside every other service's errors. Coolify's SOUL-documented
    exception (SOUL.md §5 Gate 2 / case law) covers only its three-layer
    *config* loading, not its error hierarchy.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message, service="coolify", hint=hint)


class APIError(CoolifyError):
    """Error from the Coolify API."""

    def __init__(self, message: str, status_code: int | None = None, errors: dict | None = None):
        self.status_code = status_code
        self.errors = errors or {}
        detail = message
        if errors:
            validation = "; ".join(
                f"{field}: {', '.join(msgs) if isinstance(msgs, list) else str(msgs)}"
                for field, msgs in errors.items()
            )
            detail = f"{message} — {validation}"
        super().__init__(detail)


class ConnectionError(CoolifyError):
    """Cannot connect to Coolify server."""


class AuthenticationError(CoolifyError):
    """Invalid or missing API token."""


class ResourceNotFoundError(CoolifyError):
    """No resource matches the given query."""

    def __init__(self, resource_type: str, query: str, suggestions: list[str] | None = None):
        self.resource_type = resource_type
        self.query = query
        self.suggestions = suggestions or []
        msg = f'No {resource_type} found matching "{query}"'
        if suggestions:
            msg += f". Did you mean: {', '.join(suggestions)}"
        super().__init__(msg)


class AmbiguousMatchError(CoolifyError):
    """Multiple resources match the given query."""

    def __init__(self, resource_type: str, query: str, matches: list[str]):
        self.resource_type = resource_type
        self.query = query
        self.matches = matches
        msg = f'Multiple {resource_type}s match "{query}": {", ".join(matches)}. Please be more specific or use a UUID.'
        super().__init__(msg)


class ConfigError(CoolifyError):
    """Configuration error (missing config, invalid values)."""


class SSHError(CoolifyError):
    """SSH connection or command execution error."""
