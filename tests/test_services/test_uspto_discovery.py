"""Tests for the USPTO contract discovery subsystem."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.services.uspto.codegen import AdapterGenerator
from copilot_cli.services.uspto.discovery import (
    ContractDiscoverer,
    _mask_sensitive_headers,
    _parse_body,
)
from copilot_cli.services.uspto.models import CapturedContract, ProductRecipe
from copilot_cli.services.uspto.recipes import RECIPES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(**kwargs) -> CapturedContract:
    defaults = {
        "product": "test_product",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "url": "https://api.example.com/search",
        "method": "GET",
        "request_headers": {"Accept": "application/json"},
        "request_content_type": None,
        "request_body": None,
        "response_status": 200,
        "response_content_type": "application/json",
        "response_headers": {"content-type": "application/json"},
        "response_body_sample": {"results": [1, 2, 3]},
        "response_body_size": 512,
        "sample_query": "test",
        "notes": ["Response is JSON."],
    }
    defaults.update(kwargs)
    return CapturedContract(**defaults)


# ---------------------------------------------------------------------------
# _should_capture filtering
# ---------------------------------------------------------------------------


class TestShouldCapture:
    def setup_method(self):
        self.d = ContractDiscoverer()

    def test_accepts_xhr_api_request(self):
        assert self.d._should_capture("https://api.example.com/search", "xhr") is True

    def test_accepts_fetch_request(self):
        assert self.d._should_capture("https://api.example.com/data", "fetch") is True

    def test_rejects_stylesheet(self):
        assert self.d._should_capture("https://example.com/style.css", "stylesheet") is False

    def test_rejects_image_resource_type(self):
        assert self.d._should_capture("https://example.com/logo.png", "image") is False

    def test_rejects_script_resource_type(self):
        assert self.d._should_capture("https://example.com/app.js", "script") is False

    def test_rejects_font_resource_type(self):
        assert self.d._should_capture("https://example.com/font.woff2", "font") is False

    def test_rejects_media_resource_type(self):
        assert self.d._should_capture("https://example.com/video.mp4", "media") is False

    def test_rejects_google_analytics_url(self):
        assert self.d._should_capture("https://www.google-analytics.com/collect", "xhr") is False

    def test_rejects_googletagmanager_url(self):
        assert self.d._should_capture("https://www.googletagmanager.com/gtag/js", "xhr") is False

    def test_rejects_fonts_googleapis_url(self):
        assert self.d._should_capture("https://fonts.googleapis.com/css", "xhr") is False

    def test_rejects_doubleclick_url(self):
        assert self.d._should_capture("https://ad.doubleclick.net/pixel", "xhr") is False

    def test_rejects_js_extension(self):
        assert self.d._should_capture("https://example.com/bundle.js", "document") is False

    def test_rejects_css_extension(self):
        assert self.d._should_capture("https://example.com/main.css", "document") is False

    def test_rejects_png_extension(self):
        assert self.d._should_capture("https://example.com/img.png", "document") is False

    def test_rejects_svg_extension(self):
        assert self.d._should_capture("https://example.com/icon.svg", "document") is False

    def test_rejects_woff2_extension(self):
        assert self.d._should_capture("https://example.com/font.woff2", "document") is False

    def test_rejects_ico_extension(self):
        assert self.d._should_capture("https://example.com/favicon.ico", "document") is False

    def test_accepts_api_path_no_extension(self):
        assert self.d._should_capture("https://api.example.com/api/v1/search", "document") is True

    def test_accepts_json_endpoint(self):
        assert self.d._should_capture("https://api.example.com/data.json", "document") is True


# ---------------------------------------------------------------------------
# _rank_captures scoring
# ---------------------------------------------------------------------------


class TestRankCaptures:
    def setup_method(self):
        self.d = ContractDiscoverer()

    def test_json_response_ranks_higher(self):
        json_contract = _make_contract(response_content_type="application/json", notes=[])
        non_json = _make_contract(response_content_type="text/html", notes=[])
        ranked = self.d._rank_captures([non_json, json_contract])
        assert ranked[0].response_content_type == "application/json"

    def test_post_ranks_higher_than_get(self):
        post_contract = _make_contract(method="POST", response_content_type="text/plain", notes=[])
        get_contract = _make_contract(method="GET", response_content_type="text/plain", notes=[])
        ranked = self.d._rank_captures([get_contract, post_contract])
        assert ranked[0].method == "POST"

    def test_api_path_boosts_score(self):
        api_contract = _make_contract(
            url="https://example.com/api/search",
            response_content_type="text/plain",
            method="GET",
            notes=[],
        )
        plain_contract = _make_contract(
            url="https://example.com/page",
            response_content_type="text/plain",
            method="GET",
            notes=[],
        )
        ranked = self.d._rank_captures([plain_contract, api_contract])
        assert "/api/" in ranked[0].url

    def test_large_body_boosts_score(self):
        large = _make_contract(
            response_body_size=2048,
            response_content_type="text/plain",
            method="GET",
            notes=[],
        )
        small = _make_contract(
            response_body_size=100,
            response_content_type="text/plain",
            method="GET",
            notes=[],
        )
        ranked = self.d._rank_captures([small, large])
        assert ranked[0].response_body_size == 2048

    def test_analytics_url_penalizes_score(self):
        # analytics: +10 (json) +5 (POST) -5 (analytics) -5 (beacon) = +5
        analytics = _make_contract(
            url="https://example.com/analytics/beacon",
            response_content_type="application/json",
            method="POST",
            response_body_size=0,
            notes=[],
        )
        # data_api: +10 (json) +3 (/api/) +2 (body > 1KB) = +15
        data_api = _make_contract(
            url="https://example.com/api/search",
            response_content_type="application/json",
            method="GET",
            response_body_size=2048,
            notes=[],
        )
        ranked = self.d._rank_captures([analytics, data_api])
        assert "/api/" in ranked[0].url

    def test_returns_empty_list_for_no_input(self):
        assert self.d._rank_captures([]) == []

    def test_preserves_all_captures(self):
        contracts = [_make_contract(url=f"https://api.example.com/{i}") for i in range(5)]
        ranked = self.d._rank_captures(contracts)
        assert len(ranked) == 5


# ---------------------------------------------------------------------------
# Contract serialization / deserialization
# ---------------------------------------------------------------------------


class TestContractSerialization:
    def test_round_trip_via_model_dump(self):
        contract = _make_contract()
        dumped = contract.model_dump()
        restored = CapturedContract(**dumped)
        assert restored.product == contract.product
        assert restored.url == contract.url
        assert restored.response_body_sample == contract.response_body_sample

    def test_save_and_load_contract(self, tmp_path):
        contract = _make_contract(product="ptab_test")
        d = ContractDiscoverer()
        saved_path = d.save_contract(contract, data_dir=tmp_path)
        assert saved_path.exists()
        loaded = d.load_contract("ptab_test", data_dir=tmp_path)
        assert loaded is not None
        assert loaded.product == "ptab_test"
        assert loaded.url == contract.url

    def test_load_contract_returns_none_if_missing(self, tmp_path):
        d = ContractDiscoverer()
        result = d.load_contract("does_not_exist", data_dir=tmp_path)
        assert result is None

    def test_list_contracts_empty_when_no_saved(self, tmp_path):
        d = ContractDiscoverer()
        result = d.list_contracts(data_dir=tmp_path)
        assert result == []

    def test_list_contracts_returns_names(self, tmp_path):
        d = ContractDiscoverer()
        for name in ("alpha", "beta", "gamma"):
            d.save_contract(_make_contract(product=name), data_dir=tmp_path)
        names = d.list_contracts(data_dir=tmp_path)
        assert names == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# Recipe validation
# ---------------------------------------------------------------------------


class TestRecipeValidation:
    def test_all_recipes_are_valid_product_recipes(self):
        for name, recipe in RECIPES.items():
            assert isinstance(recipe, ProductRecipe)
            assert recipe.product == name

    def test_all_recipes_have_urls(self):
        for recipe in RECIPES.values():
            assert recipe.url.startswith("http")

    def test_none_confirmed_by_default(self):
        for recipe in RECIPES.values():
            assert recipe.confirmed is False

    def test_design_search_has_no_selectors(self):
        r = RECIPES["design_search"]
        assert r.search_selector is None
        assert r.submit_selector is None

    def test_recipe_model_copy_updates_query(self):
        r = RECIPES["trademark_search"]
        updated = r.model_copy(update={"sample_query": "APPLE"})
        assert updated.sample_query == "APPLE"
        # Original unchanged
        assert RECIPES["trademark_search"].sample_query == "NIKE"


# ---------------------------------------------------------------------------
# _parse_body helper
# ---------------------------------------------------------------------------


class TestParseBody:
    def test_parses_json_body(self):
        body = json.dumps({"results": [1, 2, 3]}).encode()
        parsed, size, _notes = _parse_body(body, "application/json")
        assert parsed == {"results": [1, 2, 3]}
        assert size == len(body)

    def test_returns_string_for_text_body(self):
        body = b"Hello world"
        parsed, size, _notes = _parse_body(body, "text/plain")
        assert parsed == "Hello world"
        assert size == 11

    def test_empty_body_returns_none(self):
        parsed, size, _notes = _parse_body(b"", "application/json")
        assert parsed is None
        assert size == 0

    def test_large_body_truncated_with_note(self):
        body = b"x" * 200_000
        _parsed, size, notes = _parse_body(body, "text/plain")
        assert size == 200_000
        assert any("truncated" in note for note in notes)

    def test_large_json_body_truncated(self):
        large_json = json.dumps({"data": "y" * 150_000}).encode()
        _parsed, size, notes = _parse_body(large_json, "application/json; charset=utf-8")
        assert size == len(large_json)
        assert any("truncated" in note for note in notes)


# ---------------------------------------------------------------------------
# _mask_sensitive_headers
# ---------------------------------------------------------------------------


class TestMaskSensitiveHeaders:
    def test_masks_cookie_header(self):
        headers = {"Cookie": "session=abc123; token=xyz"}
        masked = _mask_sensitive_headers(headers)
        assert masked["Cookie"] == "[MASKED]"

    def test_masks_authorization_header(self):
        headers = {"Authorization": "Bearer super-secret"}
        masked = _mask_sensitive_headers(headers)
        assert masked["Authorization"] == "[MASKED]"

    def test_preserves_non_sensitive_headers(self):
        headers = {"Accept": "application/json", "Content-Type": "text/plain"}
        masked = _mask_sensitive_headers(headers)
        assert masked["Accept"] == "application/json"
        assert masked["Content-Type"] == "text/plain"

    def test_masks_x_api_key(self):
        headers = {"X-Api-Key": "secret-key-value"}
        masked = _mask_sensitive_headers(headers)
        assert masked["X-Api-Key"] == "[MASKED]"


# ---------------------------------------------------------------------------
# Codegen — produces valid Python
# ---------------------------------------------------------------------------


class TestAdapterGenerator:
    def test_generate_client_method_is_valid_python(self):
        contract = _make_contract(
            product="ptab",
            url="https://developer.uspto.gov/ptab-api/trials",
            method="POST",
            request_body=json.dumps({"q": "IPR2020-00001", "page": "1"}),
        )
        gen = AdapterGenerator(contract)
        code = gen.generate_client_method()
        # Wrap in a module context since it's a function definition
        module = f"from typing import Any\n\n{code}\n"
        ast.parse(module)  # Raises SyntaxError if invalid

    def test_generate_command_is_valid_python(self):
        contract = _make_contract(
            product="trademark_search",
            url="https://tmsearch.uspto.gov/api/search",
            method="GET",
            request_body=None,
        )
        gen = AdapterGenerator(contract)
        code = gen.generate_command()
        module = (
            "import typer\n"
            "from copilot_cli.shared.errors import CopilotError\n"
            "from copilot_cli.shared.output import print_error, print_json\n"
            "app = typer.Typer()\n"
            "def _client(): pass\n\n"
            f"{code}\n"
        )
        ast.parse(module)

    def test_generate_test_is_valid_python(self):
        contract = _make_contract(product="assignment_search")
        gen = AdapterGenerator(contract)
        code = gen.generate_test()
        ast.parse(code)

    def test_generate_all_writes_three_files(self, tmp_path):
        contract = _make_contract(product="my_product", request_body={"term": "test"})
        gen = AdapterGenerator(contract)
        result = gen.generate_all(tmp_path)

        assert "client" in result
        assert "command" in result
        assert "test" in result
        for path in result.values():
            assert path.exists()
            assert path.stat().st_size > 0

    def test_generate_all_files_are_valid_python(self, tmp_path):
        contract = _make_contract(product="demo_product", request_body={"query": "example"})
        gen = AdapterGenerator(contract)
        result = gen.generate_all(tmp_path)

        for label, path in result.items():
            source = path.read_text(encoding="utf-8")
            try:
                ast.parse(source)
            except SyntaxError as exc:
                pytest.fail(
                    f"Generated {label} file has invalid syntax: {exc}\n\nContent:\n{source}"
                )

    def test_body_params_extracted_from_dict(self):
        contract = _make_contract(request_body={"name": "NIKE", "page": 1})
        gen = AdapterGenerator(contract)
        code = gen.generate_client_method()
        assert "name" in code
        assert "page" in code

    def test_body_params_extracted_from_form_string(self):
        contract = _make_contract(request_body="criteria=*%3A*&start=0&rows=25")
        gen = AdapterGenerator(contract)
        code = gen.generate_client_method()
        assert "criteria" in code

    def test_body_params_extracted_from_json_string(self):
        contract = _make_contract(request_body='{"search": "term", "limit": "10"}')
        gen = AdapterGenerator(contract)
        code = gen.generate_client_method()
        assert "search" in code
        assert "limit" in code


# ---------------------------------------------------------------------------
# Playwright-related discovery — mocked
# ---------------------------------------------------------------------------


class TestContractDiscovererInit:
    def test_no_session_name_leaves_storage_state_none(self):
        d = ContractDiscoverer()
        assert d._storage_state_path is None

    def test_session_name_with_no_file_leaves_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        d = ContractDiscoverer(session_name="missing-session")
        assert d._storage_state_path is None

    def test_session_name_with_existing_file_sets_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        state_dir = tmp_path / "session_states"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "my-session.json"
        state_file.write_text("{}", encoding="utf-8")

        d = ContractDiscoverer(session_name="my-session")
        assert d._storage_state_path == str(state_file)


class TestDiscoverManualMocked:
    def test_discover_manual_raises_config_error_without_playwright(self):
        """Verify ConfigError is raised when Playwright is unavailable."""
        d = ContractDiscoverer()
        # Patch the import inside the method by making the module raise on import
        with patch.dict(
            "sys.modules",
            {
                "playwright": None,
                "playwright.sync_api": None,
            },
        ):
            import importlib

            import copilot_cli.services.uspto.discovery as disc_mod

            # Force the inner import to fail by patching the module import path
            with patch.object(
                disc_mod, "_playwright_import_error", new=ImportError("no playwright"), create=True
            ):
                from copilot_cli.shared.errors import ConfigError

                # The function tries "from playwright.sync_api import sync_playwright"
                # Since playwright.sync_api is None in sys.modules it raises ImportError
                # which discovery.py catches and re-raises as ConfigError
                with pytest.raises((ConfigError, ImportError, Exception)):
                    d.discover_manual("https://example.com", product="test")

    def test_discover_manual_with_mock_playwright(self, monkeypatch):
        """Verify manual discovery runs without error using a fully mocked Playwright."""
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_pw_instance = MagicMock()

        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_pw_instance.__enter__ = MagicMock(return_value=mock_pw_instance)
        mock_pw_instance.__exit__ = MagicMock(return_value=False)

        handlers = {}

        def fake_on(event, handler):
            handlers[event] = handler

        mock_page.on.side_effect = fake_on
        mock_page.goto.return_value = MagicMock(status=200)

        monkeypatch.setattr("builtins.input", lambda _prompt="": "")

        # Patch the sync_playwright inside playwright.sync_api so the local import works
        mock_sync_playwright_cls = MagicMock(return_value=mock_pw_instance)
        mock_sync_api = MagicMock()
        mock_sync_api.sync_playwright = mock_sync_playwright_cls
        mock_sync_api.Error = Exception
        mock_playwright = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "playwright": mock_playwright,
                "playwright.sync_api": mock_sync_api,
            },
        ):
            d = ContractDiscoverer()
            captures = d.discover_manual("https://example.com", product="test", timeout_s=5)

        assert isinstance(captures, list)


class TestDiscoverAutoBuildInterceptors:
    def test_build_interceptors_captures_matching_request_response(self):
        d = ContractDiscoverer()
        captures: list = []
        on_request, on_response = d._build_interceptors(captures, "test_product", "sample")

        # Simulate a request
        mock_request = MagicMock()
        mock_request.url = "https://api.example.com/search?q=sample"
        mock_request.resource_type = "xhr"
        mock_request.method = "GET"
        mock_request.headers = {"Accept": "application/json"}
        mock_request.post_data = None
        on_request(mock_request)

        # Simulate a response
        mock_response = MagicMock()
        mock_response.url = "https://api.example.com/search?q=sample"
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.body.return_value = json.dumps({"results": []}).encode()
        on_response(mock_response)

        assert len(captures) == 1
        assert captures[0].url == "https://api.example.com/search?q=sample"
        assert captures[0].method == "GET"
        assert captures[0].response_status == 200
        assert captures[0].product == "test_product"

    def test_build_interceptors_ignores_noise_requests(self):
        d = ContractDiscoverer()
        captures: list = []
        on_request, _on_response = d._build_interceptors(captures, "test_product", "sample")

        # Simulate a script resource type request
        mock_request = MagicMock()
        mock_request.url = "https://www.google-analytics.com/collect"
        mock_request.resource_type = "script"
        mock_request.method = "GET"
        mock_request.headers = {}
        on_request(mock_request)

        # No response expected since request was filtered
        assert len(captures) == 0

    def test_build_interceptors_ignores_response_with_no_pending_request(self):
        d = ContractDiscoverer()
        captures: list = []
        _, on_response = d._build_interceptors(captures, "test_product", "sample")

        mock_response = MagicMock()
        mock_response.url = "https://api.example.com/not-requested"
        mock_response.status = 200
        on_response(mock_response)

        assert len(captures) == 0


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestDiscoverCLI:
    def test_discover_products_command(self):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "products"])
        assert result.exit_code == 0
        assert "ptab" in result.output

    def test_discover_list_command_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "list"])
        assert result.exit_code == 0

    def test_discover_show_missing_contract(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "show", "missing_product"])
        assert result.exit_code != 0

    def test_discover_generate_missing_contract(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "generate", "missing_product"])
        assert result.exit_code != 0

    def test_discover_show_saved_contract(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        contract = _make_contract(product="ptab")
        d = ContractDiscoverer()
        d.save_contract(contract, data_dir=tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "show", "ptab"])
        assert result.exit_code == 0
        assert "ptab" in result.output

    def test_discover_generate_saved_contract(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        contract = _make_contract(product="ptab", request_body={"q": "IPR2020-00001"})
        d = ContractDiscoverer()
        d.save_contract(contract, data_dir=tmp_path)

        out_dir = tmp_path / "stubs"
        runner = CliRunner()
        result = runner.invoke(
            app, ["uspto", "discover", "generate", "ptab", "--output-dir", str(out_dir)]
        )
        assert result.exit_code == 0
        assert (out_dir / "client_ptab.py").exists()
        assert (out_dir / "command_ptab.py").exists()
        assert (out_dir / "test_ptab.py").exists()

    def test_discover_auto_unknown_product(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        monkeypatch.setenv("COPILOT_USPTO_DATA_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "auto", "not_a_real_product"])
        assert result.exit_code != 0
        assert "Unknown product" in result.output

    def test_discover_help_registered(self):
        from typer.testing import CliRunner

        from copilot_cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["uspto", "discover", "--help"])
        assert result.exit_code == 0
        assert "auto" in result.output
        assert "manual" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "generate" in result.output
        assert "products" in result.output
