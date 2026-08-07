"""Adapter stub generator for captured USPTO API contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from copilot_cli.services.uspto.models import CapturedContract


def _slugify(name: str) -> str:
    """Convert a product name to a valid Python identifier."""
    slug = re.sub(r"[^a-z0-9_]", "_", name.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "product"


def _method_name(product: str) -> str:
    return f"search_{_slugify(product)}"


def _class_name(product: str) -> str:
    parts = _slugify(product).split("_")
    return "".join(p.title() for p in parts) + "Client"


def _extract_body_params(contract: CapturedContract) -> list[str]:
    """Derive CLI argument names from request body keys."""
    body = contract.request_body
    if isinstance(body, dict):
        return list(body.keys())
    if isinstance(body, str):
        # Try JSON
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return list(parsed.keys())
        except json.JSONDecodeError:
            pass
        # Try form-encoded: key=value&key2=value2
        if "=" in body:
            pairs = body.split("&")
            keys = []
            for pair in pairs:
                if "=" in pair:
                    keys.append(pair.split("=", 1)[0])
            return keys
    return ["query"]


def _indent(text: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


class AdapterGenerator:
    """Generates Python stubs from a CapturedContract."""

    def __init__(self, contract: CapturedContract) -> None:
        self.contract = contract

    def generate_client_method(self) -> str:
        c = self.contract
        method_name = _method_name(c.product)
        params = _extract_body_params(c)
        http_method = c.method.upper()

        param_sig = ", ".join(f'{p}: str = ""' for p in params)
        if param_sig:
            param_sig = f"self, {param_sig}"
        else:
            param_sig = "self"

        # Build headers repr (already masked)
        headers_repr = repr(dict(c.request_headers.items()))

        # Build body repr
        if params and http_method in ("POST", "PUT", "PATCH"):
            body_dict = "{" + ", ".join(f'"{p}": {p}' for p in params) + "}"
            body_line = f"        body = {body_dict}"
        else:
            body_line = "        body = None"

        if http_method in ("POST", "PUT", "PATCH"):
            call_line = f'        return self._session.{http_method.lower()}("{c.url}", json=body, headers=headers)'
        else:
            qs = "{" + ", ".join(f'"{p}": {p}' for p in params) + "}"
            call_line = f'        return self._session.{http_method.lower()}("{c.url}", params={qs}, headers=headers)'

        lines = [
            f"def {method_name}({param_sig}) -> Any:",
            f'    """Auto-generated stub from captured contract for {c.product}.',
            "",
            f"    Captured: {c.captured_at}",
            f"    URL: {c.url}",
            f"    Method: {http_method}",
            f"    Sample query: {c.sample_query}",
            '    """',
            f"    headers = {headers_repr}",
            f"    {body_line.strip()}",
            f"    {call_line.strip()}",
        ]
        return "\n".join(lines)

    def generate_command(self) -> str:
        c = self.contract
        params = _extract_body_params(c)
        product_slug = _slugify(c.product)
        method_name = _method_name(c.product)

        arg_lines = []
        for p in params:
            arg_lines.append(
                f'    {p}: str = typer.Argument(..., help="{p.replace("_", " ").title()} to search for."),'
            )

        arg_sig = "\n".join(arg_lines)
        call_args = ", ".join(f"{p}={p}" for p in params)

        lines = [
            f'@app.command("{product_slug.replace("_", "-")}")',
            f"def {product_slug}_search(",
            arg_sig if arg_sig else "    # No arguments detected from contract.",
            ") -> None:",
            f'    """Search {c.product.replace("_", " ").title()} using the captured API contract."""',
            "    try:",
            f"        result = _client().{method_name}({call_args})",
            f'        print_json(result, title="{c.product.replace("_", " ").title()} Search")',
            "    except CopilotError as exc:",
            "        print_error(str(exc), hint=exc.hint)",
            "        raise typer.Exit(1)",
        ]
        return "\n".join(lines)

    def generate_test(self) -> str:
        c = self.contract
        params = _extract_body_params(c)
        method_name = _method_name(c.product)
        _slugify(c.product)
        class_name = _class_name(c.product)

        call_args = ", ".join(f'"{p}_value"' for p in params)

        lines = [
            f'"""Tests for {c.product} adapter stub (auto-generated)."""',
            "from __future__ import annotations",
            "",
            "from unittest.mock import MagicMock, patch",
            "",
            "import pytest",
            "",
            "",
            "@pytest.fixture",
            "def mock_session():",
            "    return MagicMock()",
            "",
            "",
            f"def test_{method_name}_returns_response(mock_session):",
            f"    mock_session.{c.method.lower()}.return_value = MagicMock(status_code=200)",
            "    # Instantiate the stub client with the mock session",
            f"    # client = {class_name}(session=mock_session)",
            f"    # result = client.{method_name}({call_args})",
            "    # assert result is not None",
            "    pass  # TODO: wire up once stub class is promoted to a real client",
        ]
        return "\n".join(lines)

    def generate_all(self, output_dir: Path) -> dict[str, Path]:
        """Write client, command, and test stubs. Returns paths of generated files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        product_slug = _slugify(self.contract.product)

        client_path = output_dir / f"client_{product_slug}.py"
        command_path = output_dir / f"command_{product_slug}.py"
        test_path = output_dir / f"test_{product_slug}.py"

        client_content = "\n".join(
            [
                '"""Auto-generated client stub."""',
                "from __future__ import annotations",
                "from typing import Any",
                "",
                "",
                self.generate_client_method(),
            ]
        )

        command_content = "\n".join(
            [
                '"""Auto-generated command stub."""',
                "from __future__ import annotations",
                "",
                "import typer",
                "",
                "from copilot_cli.shared.errors import CopilotError",
                "from copilot_cli.shared.output import print_error, print_json",
                "",
                "app = typer.Typer(no_args_is_help=True)",
                "",
                "",
                "def _client():",
                '    raise NotImplementedError("Wire up your client here.")',
                "",
                "",
                self.generate_command(),
            ]
        )

        test_content = self.generate_test()

        client_path.write_text(client_content, encoding="utf-8")
        command_path.write_text(command_content, encoding="utf-8")
        test_path.write_text(test_content, encoding="utf-8")

        return {
            "client": client_path,
            "command": command_path,
            "test": test_path,
        }
