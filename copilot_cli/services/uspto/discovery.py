"""Core discovery engine for USPTO API contract capture via Playwright network interception."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from copilot_cli.services.uspto.models import CapturedContract, ProductRecipe
from copilot_cli.services.uspto.storage import data_root, load_json, save_json

_NOISE_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "fonts.googleapis.com",
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "analytics.google.com",
}

_NOISE_EXTENSIONS = {
    ".js",
    ".css",
    ".png",
    ".svg",
    ".woff2",
    ".gif",
    ".jpg",
    ".ico",
    ".woff",
    ".ttf",
    ".eot",
}

_NOISE_RESOURCE_TYPES = {"stylesheet", "image", "font", "media", "script"}

_SCORE_URL_KEYWORDS = {"/api/": 3, "/search/": 3, "/records/": 3, "/query/": 3}

_NOISE_URL_KEYWORDS = {"analytics", "tracking", "beacon", "telemetry", "metrics"}

_SENSITIVE_HEADERS = {"cookie", "authorization", "x-api-key", "set-cookie"}

_MAX_BODY_BYTES = 100_000
_SAMPLE_BODY_BYTES = 10_000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _mask_sensitive_headers(headers: dict) -> dict:
    """Keep header names but mask values for known-sensitive headers."""
    result = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            result[key] = "[MASKED]"
        else:
            result[key] = value
    return result


def _parse_body(body_bytes: bytes, content_type: str | None) -> tuple[Any, int, list[str]]:
    """Parse response body. Returns (parsed_body, size, notes)."""
    size = len(body_bytes)
    notes: list[str] = []

    if not body_bytes:
        return None, 0, notes

    ct = (content_type or "").lower()

    if "json" in ct:
        try:
            if size > _MAX_BODY_BYTES:
                sample = body_bytes[:_SAMPLE_BODY_BYTES].decode("utf-8", errors="replace")
                notes.append(
                    f"Response body truncated to {_SAMPLE_BODY_BYTES} bytes (original: {size} bytes)."
                )
                return sample, size, notes
            parsed = json.loads(body_bytes.decode("utf-8", errors="replace"))
            return parsed, size, notes
        except json.JSONDecodeError:
            pass

    if size > _MAX_BODY_BYTES:
        sample = body_bytes[:_SAMPLE_BODY_BYTES].decode("utf-8", errors="replace")
        notes.append(
            f"Response body truncated to {_SAMPLE_BODY_BYTES} bytes (original: {size} bytes)."
        )
        return sample, size, notes

    return body_bytes.decode("utf-8", errors="replace"), size, notes


class ContractDiscoverer:
    """Captures API contracts from USPTO product pages using Playwright network interception."""

    def __init__(self, session_name: str | None = None) -> None:
        self._session_name = session_name
        self._storage_state_path: str | None = None

        if session_name:
            state_path = data_root() / "session_states" / f"{session_name}.json"
            if state_path.exists():
                self._storage_state_path = str(state_path)

    def _should_capture(self, url: str, resource_type: str) -> bool:
        """Return True for XHR/fetch requests that are likely data endpoints."""
        if resource_type.lower() in _NOISE_RESOURCE_TYPES:
            return False

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        for noise_domain in _NOISE_DOMAINS:
            if noise_domain in hostname:
                return False

        path_lower = (parsed.path or "").lower()
        ext = Path(path_lower).suffix.lower()
        if ext in _NOISE_EXTENSIONS:
            return False

        return True

    def _rank_captures(self, captures: list[CapturedContract]) -> list[CapturedContract]:
        """Score and sort captures by likelihood of being a real data endpoint."""

        def score(contract: CapturedContract) -> int:
            s = 0
            ct = (contract.response_content_type or "").lower()
            if "json" in ct:
                s += 10
            if contract.method.upper() == "POST":
                s += 5
            url_lower = contract.url.lower()
            for keyword, points in _SCORE_URL_KEYWORDS.items():
                if keyword in url_lower:
                    s += points
            if contract.response_body_size > 1024:
                s += 2
            for noise_kw in _NOISE_URL_KEYWORDS:
                if noise_kw in url_lower:
                    s -= 5
            return s

        return sorted(captures, key=score, reverse=True)

    def _build_interceptors(
        self, captures: list[CapturedContract], product: str, sample_query: str
    ):
        """Build request/response event handlers that share state via captures list."""
        pending: dict[str, dict] = {}

        def on_request(request) -> None:
            url = request.url
            resource_type = request.resource_type
            if not self._should_capture(url, resource_type):
                return

            headers = dict(request.headers or {})
            body_str: Any = None
            try:
                body_str = request.post_data
            except Exception:
                pass

            pending[url] = {
                "method": request.method,
                "headers": _mask_sensitive_headers(headers),
                "content_type": headers.get("content-type"),
                "body": body_str,
            }

        def on_response(response) -> None:
            url = response.url
            if url not in pending:
                return

            req_info = pending.pop(url)
            resp_headers = dict(response.headers or {})
            resp_ct = resp_headers.get("content-type")

            try:
                body_bytes = response.body()
            except Exception:
                body_bytes = b""

            parsed_body, body_size, body_notes = _parse_body(body_bytes, resp_ct)

            notes: list[str] = list(body_notes)
            if resp_ct and "json" in resp_ct.lower():
                notes.append("Response is JSON.")
            if req_info["method"].upper() == "POST":
                notes.append("Request method is POST.")

            contract = CapturedContract(
                product=product,
                captured_at=_now(),
                url=url,
                method=req_info["method"],
                request_headers=req_info["headers"],
                request_content_type=req_info["content_type"],
                request_body=req_info["body"],
                response_status=response.status,
                response_content_type=resp_ct,
                response_headers=_mask_sensitive_headers(resp_headers),
                response_body_sample=parsed_body,
                response_body_size=body_size,
                sample_query=sample_query,
                notes=notes,
            )
            captures.append(contract)

        return on_request, on_response

    def discover_manual(
        self,
        url: str,
        product: str = "unknown",
        timeout_s: int = 120,
        sample_query: str = "",
    ) -> list[CapturedContract]:
        """Open a headed browser, navigate to URL, start interception, wait for user input."""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            from copilot_cli.shared.errors import ConfigError

            raise ConfigError(
                f"Playwright is unavailable: {exc}",
                service="uspto",
                hint="Install Playwright and its browser binaries before using contract discovery.",
            )

        captures: list[CapturedContract] = []

        try:
            with sync_playwright() as pw:
                launch_kwargs: dict = {"headless": False}
                browser = pw.chromium.launch(**launch_kwargs)
                ctx_kwargs: dict = {}
                if self._storage_state_path:
                    ctx_kwargs["storage_state"] = self._storage_state_path
                context = browser.new_context(**ctx_kwargs)
                page = context.new_page()

                on_request, on_response = self._build_interceptors(captures, product, sample_query)
                page.on("request", on_request)
                page.on("response", on_response)

                page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)

                print(
                    "\nBrowser opened. Perform your search in the browser window.\n"
                    "Press Enter here when done to capture results..."
                )
                input()

                context.close()
                browser.close()
        except PlaywrightError as exc:
            from copilot_cli.shared.errors import CopilotError

            raise CopilotError(
                f"Manual discovery failed: {exc}",
                service="uspto",
                hint="Confirm the target URL is reachable and try again.",
            )

        return self._rank_captures(captures)

    def discover_auto(self, recipe: ProductRecipe) -> list[CapturedContract]:
        """Navigate to recipe URL, fill search, click submit, wait, return captures."""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            from copilot_cli.shared.errors import ConfigError

            raise ConfigError(
                f"Playwright is unavailable: {exc}",
                service="uspto",
                hint="Install Playwright and its browser binaries before using contract discovery.",
            )

        captures: list[CapturedContract] = []

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False)
                ctx_kwargs: dict = {}
                if self._storage_state_path:
                    ctx_kwargs["storage_state"] = self._storage_state_path
                context = browser.new_context(**ctx_kwargs)
                page = context.new_page()

                on_request, on_response = self._build_interceptors(
                    captures, recipe.product, recipe.sample_query
                )
                page.on("request", on_request)
                page.on("response", on_response)

                page.goto(recipe.url, wait_until="domcontentloaded", timeout=60_000)

                if recipe.search_selector and recipe.sample_query:
                    page.fill(recipe.search_selector, recipe.sample_query)

                if recipe.submit_selector:
                    page.click(recipe.submit_selector)

                wait_for = recipe.wait_for
                if wait_for == "networkidle":
                    page.wait_for_load_state("networkidle", timeout=30_000)
                else:
                    page.wait_for_selector(wait_for, timeout=30_000)

                context.close()
                browser.close()
        except PlaywrightError as exc:
            from copilot_cli.shared.errors import CopilotError

            raise CopilotError(
                f"Auto discovery failed for {recipe.product}: {exc}",
                service="uspto",
                hint="Check that the recipe selectors are correct or use manual discovery instead.",
            )

        return self._rank_captures(captures)

    def save_contract(self, contract: CapturedContract, data_dir: Path | None = None) -> Path:
        """Save contract to ~/.copilot-cli/uspto/contracts/<product>.json."""
        base = data_dir if data_dir is not None else data_root()
        contracts_dir = base / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        path = contracts_dir / f"{contract.product}.json"
        save_json(path, contract.model_dump())
        return path

    def load_contract(self, product: str, data_dir: Path | None = None) -> CapturedContract | None:
        """Load a saved contract by product name."""
        base = data_dir if data_dir is not None else data_root()
        path = base / "contracts" / f"{product}.json"
        raw = load_json(path)
        if raw is None:
            return None
        return CapturedContract(**raw)

    def list_contracts(self, data_dir: Path | None = None) -> list[str]:
        """List saved contract product names."""
        base = data_dir if data_dir is not None else data_root()
        contracts_dir = base / "contracts"
        if not contracts_dir.exists():
            return []
        return sorted(p.stem for p in contracts_dir.glob("*.json"))
