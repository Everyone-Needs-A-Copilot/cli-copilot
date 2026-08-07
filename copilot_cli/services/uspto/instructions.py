"""Static instruction layer for USPTO and adjacent registry access."""

from __future__ import annotations

from typing import Any

ARTIFACTS: dict[str, dict[str, Any]] = {
    "odp_base_url": {
        "name": "USPTO ODP base URL",
        "env_var": "USPTO_CLI_BASE_URL",
        "kind": "config",
        "required_for": [
            "copilot uspto request",
            "future dedicated ODP adapters",
        ],
        "summary": "Base URL for USPTO ODP API requests in this CLI.",
        "how_to_get": [
            "Use the USPTO ODP API base URL documented in the ODP getting-started materials.",
            "Store it in .env as USPTO_CLI_BASE_URL.",
            "For this repo, the configured value is expected to be https://api.uspto.gov/api/v1/ unless USPTO changes it.",
        ],
        "official_sources": [
            "https://data.uspto.gov/apis/getting-started",
        ],
        "notes": [
            "This is configuration, not a secret token.",
        ],
    },
    "odp_api_key": {
        "name": "USPTO ODP API key",
        "env_var": "USPTO_CLI_API_KEY",
        "kind": "api_key",
        "required_for": [
            "copilot uspto health",
            "copilot uspto request",
            "copilot uspto trademarks status",
            "copilot uspto tsdr ...",
        ],
        "summary": "Shared USPTO API key used for ODP and TSDR requests in this CLI.",
        "how_to_get": [
            "Sign in to the USPTO API Manager at https://account.uspto.gov/api-manager/ with your USPTO.gov account.",
            "If you do not already have a USPTO.gov account, create one first.",
            "Request or view your API key in the API Manager.",
            "Store it in .env as USPTO_CLI_API_KEY.",
        ],
        "official_sources": [
            "https://account.uspto.gov/api-manager/",
            "https://developer.uspto.gov/sites/default/files/2020-09/Enterprise-API-User-Guide_1.pdf",
            "https://data.uspto.gov/apis/getting-started",
        ],
        "notes": [
            "TSDR requires the header name USPTO-API-KEY exactly.",
            "ODP requests in this CLI use the X-Api-Key header.",
            "Do not share this key.",
        ],
    },
    "patent_center_session": {
        "name": "Patent Center session",
        "env_var": None,
        "kind": "storage_state",
        "required_for": [
            "copilot uspto portal fetch --session <name> https://patentcenter.uspto.gov/...",
            "future authenticated Patent Center retrieval",
        ],
        "summary": "Imported browser session for authenticated Patent Center pages.",
        "how_to_get": [
            "Create or use a USPTO.gov account associated with Patent Center access and any required customer number.",
            "Sign in at https://patentcenter.uspto.gov/ using USPTO.gov credentials and two-step authentication.",
            "Capture the authenticated browser storage state with `copilot uspto sessions capture <name> https://patentcenter.uspto.gov/`.",
            "Alternatively export a Playwright storage-state JSON yourself and import it with `copilot uspto sessions import <name> <file>`.",
        ],
        "official_sources": [
            "https://patentcenter.uspto.gov/",
            "https://www.uspto.gov/sites/default/files/documents/Patent%20Center%20User%20Guide_Beta508_1.pdf",
        ],
        "notes": [
            "Patent Center uses USPTO.gov two-step authentication.",
            "Full features require appropriate Patent Center registration and customer-number association.",
        ],
    },
    "trademark_center_session": {
        "name": "Trademark Center session",
        "env_var": None,
        "kind": "storage_state",
        "required_for": [
            "future authenticated Trademark Center retrieval or filing helpers",
        ],
        "summary": "Imported browser session for authenticated trademark filing and management pages.",
        "how_to_get": [
            "Create or use a USPTO.gov account.",
            "Complete identity verification if you intend to file through Trademark Center, TEAS, or TEASi.",
            "Sign in through the trademark login flow and complete multifactor authentication.",
            "Capture the authenticated browser storage state with `copilot uspto sessions capture <name> https://www.uspto.gov/trademarks/login`.",
        ],
        "official_sources": [
            "https://www.uspto.gov/trademarks/login",
            "https://www.uspto.gov/trademarks/apply/trademark-center",
        ],
        "notes": [
            "Identity verification is mandatory for filing through Trademark Center and related trademark filing systems.",
            "Do not share USPTO.gov credentials or reuse another person's account.",
        ],
    },
    "assignment_center_session": {
        "name": "Assignment Center session",
        "env_var": None,
        "kind": "storage_state",
        "required_for": [
            "copilot uspto portal fetch --session <name> https://assignmentcenter.uspto.gov/...",
            "future authenticated assignment workflows",
        ],
        "summary": "Imported browser session for Assignment Center pages.",
        "how_to_get": [
            "Sign in to Assignment Center manually in your browser.",
            "Use `copilot uspto sessions capture <name> https://assignmentcenter.uspto.gov/` to save storage state after login.",
            "Reuse that stored session name with portal-backed commands.",
        ],
        "official_sources": [
            "https://assignmentcenter.uspto.gov/",
            "https://www.uspto.gov/learning-and-resources/uspto-videos/signing-assignment-center",
        ],
        "notes": [
            "This CLI does not automate login or MFA. It only captures/imports a session after you authenticate yourself.",
        ],
    },
    "copyright_records_access": {
        "name": "Copyright Public Records access",
        "env_var": None,
        "kind": "public_portal",
        "required_for": [
            "copilot uspto copyright search",
            "future adjacent copyright evidence review",
        ],
        "summary": "No USPTO token. Use the U.S. Copyright Office public records systems.",
        "how_to_get": [
            "Go to the Copyright Public Records Portal.",
            "Choose the relevant records collection based on timeframe.",
            "Use the Copyright Public Records System or other linked historical collections.",
        ],
        "official_sources": [
            "https://www.copyright.gov/public-records/",
        ],
        "notes": [
            "This is an adjacent non-USPTO registry and currently does not require a USPTO token.",
        ],
    },
}


CAPTURE_GUIDE = [
    "Run `copilot uspto sessions capture <name> <url>`.",
    "A Chromium browser window will open.",
    "Log in manually using the official site and complete any MFA or identity-verification prompts yourself.",
    "After the target page is fully authenticated, return to the terminal and press Enter.",
    "The CLI will save a Playwright storage-state JSON under the local USPTO data directory and register the session name for reuse.",
]
