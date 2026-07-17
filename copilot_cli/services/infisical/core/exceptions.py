"""Custom exceptions for the Infisical CLI."""

from __future__ import annotations

from copilot_cli.shared.errors import CopilotError


class InfisicalError(CopilotError):
    """Base exception for all Infisical CLI errors.

    Subclasses `CopilotError` (SOUL.md §6 Quality Bar / Principle 4: Honest
    Failure) so every Infisical error carries a `service` and can be handled
    uniformly alongside every other service's errors. No SOUL exception
    covers Infisical's error hierarchy.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message, service="infisical", hint=hint)


class APIError(InfisicalError):
    """Error returned by the Infisical API."""

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


class ConnectionError(InfisicalError):
    """Cannot connect to the Infisical server."""


class AuthenticationError(InfisicalError):
    """Authentication failed — bad client ID / secret, or expired token."""


class ConfigError(InfisicalError):
    """Configuration error (missing env vars, invalid values)."""
