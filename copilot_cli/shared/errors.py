"""Exception hierarchy for Copilot CLI."""


class CopilotError(Exception):
    """Base exception for all CLI errors."""

    def __init__(self, message: str, service: str = "", hint: str = ""):
        self.service = service
        self.hint = hint
        super().__init__(message)


class ConfigError(CopilotError):
    """Missing or invalid configuration."""


class ConnectionError(CopilotError):
    """Cannot reach a remote service."""


class AuthError(CopilotError):
    """Authentication or authorization failure."""


class NotFoundError(CopilotError):
    """Requested resource does not exist."""


class ValidationError(CopilotError):
    """Input data failed validation."""


class TimeoutError(CopilotError):
    """Operation exceeded its time limit."""


class RateLimitError(CopilotError):
    """API rate limit exceeded."""
