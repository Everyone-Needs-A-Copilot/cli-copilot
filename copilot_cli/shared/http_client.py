"""Shared httpx wrapper with retry, auth, and timeout defaults."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import (
    AuthError,
    ConnectionError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
    ValidationError,
)


def create_client(
    base_url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    verify_ssl: bool = True,
) -> httpx.Client:
    """Create a configured httpx.Client."""
    return httpx.Client(
        base_url=base_url,
        headers=headers or {},
        timeout=timeout,
        verify=verify_ssl,
        follow_redirects=True,
    )


def handle_response(response: httpx.Response, service: str = "") -> Any:
    """Check HTTP response and raise appropriate CopilotError on failure."""
    if response.is_success:
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    status = response.status_code
    try:
        body = response.json()
        msg = body.get("message") or body.get("error") or body.get("msg") or str(body)
    except Exception:
        msg = response.text[:500]

    if status == 401:
        raise AuthError(f"Authentication failed: {msg}", service=service)
    if status == 403:
        raise AuthError(f"Permission denied: {msg}", service=service)
    if status == 404:
        raise NotFoundError(f"Not found: {msg}", service=service)
    if status == 409:
        raise ValidationError(f"Conflict: {msg}", service=service)
    if status == 422:
        raise ValidationError(f"Validation failed: {msg}", service=service)
    if status == 429:
        raise RateLimitError(f"Rate limited: {msg}", service=service)

    raise ConnectionError(f"HTTP {status}: {msg}", service=service)


def api_request(
    client: httpx.Client,
    method: str,
    path: str,
    service: str = "",
    **kwargs: Any,
) -> Any:
    """Make an API request with error handling."""
    try:
        response = client.request(method, path, **kwargs)
    except httpx.TimeoutException:
        raise TimeoutError(f"Request timed out: {method} {path}", service=service)
    except httpx.ConnectError:
        raise ConnectionError(f"Cannot connect to {client.base_url}", service=service)
    return handle_response(response, service=service)
