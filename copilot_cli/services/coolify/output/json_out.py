"""JSON and YAML output formatters."""

from __future__ import annotations

import json
from typing import Any

import yaml

from copilot_cli.services.coolify.output.console import console

_SENSITIVE_FIELD_PARTS = {"password", "secret", "token"}
_SENSITIVE_FIELD_SUFFIXES = ("_api_key", "_license_key", "_private_key")


def _is_sensitive_field(key: object) -> bool:
    """Recognize credential-bearing API fields without hiding key IDs or booleans."""
    normalized = str(key).lower()
    parts = set(normalized.split("_"))
    return bool(
        parts & _SENSITIVE_FIELD_PARTS
        or normalized in {"api_key", "private_key"}
        or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)
    )


def redact_sensitive_data(data: Any) -> Any:
    """Return a recursively redacted copy of structured API output."""
    if isinstance(data, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_field(key) and value else redact_sensitive_data(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_sensitive_data(value) for value in data]
    if isinstance(data, tuple):
        return tuple(redact_sensitive_data(value) for value in data)
    return data


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    console.print_json(json.dumps(redact_sensitive_data(data), indent=2, default=str))


def print_yaml(data: Any) -> None:
    """Print data as formatted YAML."""
    output = yaml.dump(redact_sensitive_data(data), default_flow_style=False, sort_keys=False)
    console.print(output, highlight=False)


def output_data(data: Any, fmt: str = "json") -> None:
    """Output data in the specified format."""
    if fmt == "yaml":
        print_yaml(data)
    else:
        print_json(data)
