"""USPTO API client covering ODP and TSDR access."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from copilot_cli.config.settings import get_settings
from copilot_cli.services.uspto.instructions import ARTIFACTS, CAPTURE_GUIDE
from copilot_cli.services.uspto.storage import list_records, load_json, record_path, save_json
from copilot_cli.shared.errors import ConfigError, CopilotError, NotFoundError, ValidationError
from copilot_cli.shared.http_client import api_request, create_client

SERVICE = "uspto"

PATENT_PUBLIC_SEARCH_URL = "https://www.uspto.gov/patents/search/patent-public-search"
PATENT_CENTER_URL = "https://patentcenter.uspto.gov/"
PATENT_OFFICE_ACTIONS_URL = "https://data.uspto.gov/swagger/index.html?urls.primaryName=USPTO%20Office%20Action%20Text%20Retrieval%20API"
PATENT_PTAB_URL = "https://developer.uspto.gov/ptab-web/assets/documents/ptab-api-help-guide.pdf"
TRADEMARK_SEARCH_URL = "https://www.uspto.gov/trademarks/search"
TSDR_PORTAL_URL = "https://tsdr.uspto.gov/"
TRADEMARK_TMOG_URL = "https://tmog.uspto.gov/"
TRADEMARK_ID_MANUAL_URL = "https://idm-tmng.uspto.gov/id-master-list-public.html"
TRADEMARK_DESIGN_CODES_URL = "https://www.uspto.gov/trademarks/search/design-search-codes"
TRADEMARK_TTAB_URL = "https://ttabcenter.uspto.gov/"
ASSIGNMENT_CENTER_URL = "https://assignmentcenter.uspto.gov/"
COPYRIGHT_RECORDS_URL = "https://www.copyright.gov/public-records/"

_TSDR_STATUS_FORMATS = {
    "json": "info.xml",
    "xml": "info.xml",
    "html": "content",
    "pdf": "download.pdf",
    "zip": "content.zip",
}

_TSDR_DOC_FORMATS = {
    "json": "xml",
    "xml": "xml",
    "pdf": "pdf",
    "zip": "zip",
}


class USPTOClient:
    """Thin wrapper around USPTO ODP and TSDR APIs."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.uspto_cli_api_key.strip()
        self._odp_base_url = settings.uspto_cli_base_url.rstrip("/")
        self._tsdr_base_url = settings.uspto_tsdr_base_url.rstrip("/")

        self._odp = create_client(
            base_url=self._odp_base_url or "https://api.uspto.gov/api/v1",
            headers={
                "Accept": "application/json",
                "X-Api-Key": self._api_key,
            },
            timeout=60.0,
        )
        self._tsdr = create_client(
            base_url=self._tsdr_base_url,
            headers={
                "USPTO-API-KEY": self._api_key,
            },
            timeout=60.0,
        )

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise ConfigError(
                "Missing USPTO_CLI_API_KEY.",
                service=SERVICE,
                hint="Set USPTO_CLI_API_KEY in your .env file.",
            )

    def _require_odp_config(self) -> None:
        if not self._odp_base_url:
            raise ConfigError(
                "Missing USPTO_CLI_BASE_URL.",
                service=SERVICE,
                hint="Set USPTO_CLI_BASE_URL in your .env file.",
            )
        self._require_api_key()

    def _xml_text_to_json(self, xml_text: str) -> dict[str, Any]:
        """Convert XML text into a JSON-serializable nested dict."""

        def convert(element: ET.Element) -> Any:
            children = list(element)
            data: dict[str, Any] = {}

            if element.attrib:
                data["@attrs"] = dict(element.attrib)

            if children:
                grouped: dict[str, list[Any]] = {}
                for child in children:
                    grouped.setdefault(child.tag, []).append(convert(child))
                for key, values in grouped.items():
                    data[key] = values[0] if len(values) == 1 else values

            text = (element.text or "").strip()
            if text:
                if data:
                    data["#text"] = text
                else:
                    return text

            return data

        root = ET.fromstring(xml_text)
        return {root.tag: convert(root)}

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _citation(self, label: str, url: str, notes: str | None = None) -> dict[str, str]:
        citation = {"label": label, "url": url}
        if notes:
            citation["notes"] = notes
        return citation

    def _envelope(
        self,
        source: str,
        source_product: str,
        query: dict[str, Any],
        record_type: str,
        normalized: Any,
        raw: Any | None = None,
        citations: list[dict[str, str]] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "source": source,
            "source_product": source_product,
            "query": query,
            "retrieved_at": self._now(),
            "record_type": record_type,
            "raw": raw,
            "normalized": normalized,
            "citations": citations or [],
            "warnings": warnings or [],
        }

    def _normalize_session_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict) and "cookies" in payload:
            payload.setdefault("origins", [])
            return payload
        if isinstance(payload, list):
            return {"cookies": payload, "origins": []}
        raise ValidationError(
            "Session file must be Playwright storage state JSON or a cookie array.",
            service=SERVICE,
        )

    def request(
        self,
        path: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        """Make a generic authenticated request to the ODP API."""
        self._require_odp_config()
        normalized = path if path.startswith("/") else f"/{path}"
        return api_request(
            self._odp,
            method.upper(),
            normalized,
            service=SERVICE,
            params=params,
            json=json_body,
        )

    def tsdr_status(
        self,
        identifier: str,
        identifier_type: str = "sn",
        fmt: str = "json",
    ) -> Any:
        """Fetch trademark case status from TSDR."""
        self._require_api_key()
        suffix = _TSDR_STATUS_FORMATS.get(fmt.lower())
        if not suffix:
            raise ConfigError(
                f"Unsupported TSDR status format: {fmt}",
                service=SERVICE,
                hint="Use one of: json, xml, html, pdf, zip.",
            )
        path = f"/ts/cd/casestatus/{identifier_type}{identifier}/{suffix}"
        result = api_request(self._tsdr, "GET", path, service=SERVICE)
        if suffix.endswith(".xml") and isinstance(result, str):
            return self._xml_text_to_json(result)
        return result

    def tsdr_documents(
        self,
        query_type: str,
        query_value: str,
        fmt: str = "pdf",
        **params: Any,
    ) -> Any:
        """Fetch TSDR case documents and metadata bundles."""
        self._require_api_key()
        normalized_fmt = _TSDR_DOC_FORMATS.get(fmt.lower())
        if not normalized_fmt:
            raise ConfigError(
                f"Unsupported TSDR documents format: {fmt}",
                service=SERVICE,
                hint="Use one of: json, xml, pdf, zip.",
            )
        all_params = {query_type: query_value}
        all_params.update({k: v for k, v in params.items() if v not in (None, "")})
        result = api_request(
            self._tsdr,
            "GET",
            f"/ts/cd/casedocs/bundle.{normalized_fmt}",
            service=SERVICE,
            params=all_params,
        )
        if normalized_fmt == "xml" and isinstance(result, str):
            return self._xml_text_to_json(result)
        return result

    def tsdr_image(self, serial_number: str) -> Any:
        """Fetch a trademark image from TSDR."""
        self._require_api_key()
        return api_request(
            self._tsdr,
            "GET",
            f"/ts/cd/rawImage/{serial_number}",
            service=SERVICE,
        )

    def patent_search(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="patent_public_search",
            query={"text": query},
            record_type="patent_search",
            normalized={
                "query": query,
                "search_url": PATENT_PUBLIC_SEARCH_URL,
                "recommended_tools": ["Patent Public Search", "Patent Center"],
            },
            citations=[
                self._citation("Patent Public Search", PATENT_PUBLIC_SEARCH_URL),
                self._citation("Patent Center", PATENT_CENTER_URL),
            ],
            warnings=[
                "Patent Public Search does not expose a stable public JSON API in this CLI yet; use the cited portal for interactive review."
            ],
        )

    def patent_application(
        self, identifier: str, identifier_type: str = "application"
    ) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="patent_center",
            query={"identifier": identifier, "identifier_type": identifier_type},
            record_type="patent_application",
            normalized={
                "identifier": identifier,
                "identifier_type": identifier_type,
                "portal_url": PATENT_CENTER_URL,
            },
            citations=[self._citation("Patent Center", PATENT_CENTER_URL)],
            warnings=[
                "Patent Center retrieval is portal-backed; use `copilot uspto portal fetch` with an imported session for protected records."
            ],
        )

    def patent_office_actions(self, query: str) -> dict[str, Any]:
        return self.patent_office_action_records(criteria=query)

    def patent_office_action_fields(self) -> dict[str, Any]:
        """Fetch the published Office Action field schema."""
        raw = self.request("/patent/oa/oa_actions/v1/fields")
        return self._envelope(
            source="uspto",
            source_product="office_actions",
            query={"operation": "fields"},
            record_type="patent_office_action_fields",
            normalized=raw,
            raw=raw,
            citations=[
                self._citation("Office Action Text Retrieval API", PATENT_OFFICE_ACTIONS_URL),
                self._citation(
                    "Office Action Fields Endpoint",
                    "https://api.uspto.gov/api/v1/patent/oa/oa_actions/v1/fields",
                ),
            ],
        )

    def patent_office_action_records(
        self,
        criteria: str = "*:*",
        start: int = 0,
        rows: int = 25,
    ) -> dict[str, Any]:
        """Search Office Action records using the published form-encoded API."""
        self._require_odp_config()
        raw = api_request(
            self._odp,
            "POST",
            "/patent/oa/oa_actions/v1/records",
            service=SERVICE,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=f"criteria={quote_plus(criteria)}&start={start}&rows={rows}",
        )
        response = raw.get("response", {}) if isinstance(raw, dict) else {}
        docs = response.get("docs", [])
        normalized = {
            "criteria": criteria,
            "start": response.get("start", start),
            "rows": rows,
            "num_found": response.get("numFound", 0),
            "documents": docs,
        }
        return self._envelope(
            source="uspto",
            source_product="office_actions",
            query={"criteria": criteria, "start": start, "rows": rows},
            record_type="patent_office_action",
            normalized=normalized,
            raw=raw,
            citations=[
                self._citation("Office Action Text Retrieval API", PATENT_OFFICE_ACTIONS_URL),
                self._citation(
                    "Office Action Records Endpoint",
                    "https://api.uspto.gov/api/v1/patent/oa/oa_actions/v1/records",
                ),
            ],
        )

    def patent_ptab(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="ptab",
            query={"text": query},
            record_type="patent_proceeding",
            normalized={"query": query, "product_url": PATENT_PTAB_URL},
            citations=[self._citation("PTAB API Help Guide", PATENT_PTAB_URL)],
            warnings=[
                "PTAB support is currently a product handoff with normalized citations; dedicated adapter work requires endpoint-specific mapping."
            ],
        )

    def trademark_search(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="trademark_search",
            query={"text": query},
            record_type="trademark_search",
            normalized={
                "query": query,
                "search_url": TRADEMARK_SEARCH_URL,
                "related_tools": ["TSDR", "Trademark Search", "TTAB Center"],
            },
            citations=[
                self._citation("Trademark Search", TRADEMARK_SEARCH_URL),
                self._citation("TSDR", TSDR_PORTAL_URL),
            ],
            warnings=[
                "Trademark Search is currently linked as an official portal resource; exact portal query automation is not implemented in this CLI yet."
            ],
        )

    def trademark_status(self, identifier: str, identifier_type: str = "sn") -> dict[str, Any]:
        raw = self.tsdr_status(identifier=identifier, identifier_type=identifier_type, fmt="json")
        warnings: list[str] = []
        if isinstance(raw, dict):
            text_blob = json.dumps(raw).lower()
            if "live" in text_blob or "pending" in text_blob:
                warnings.append(
                    "Active or pending trademark record detected; manual legal review is recommended."
                )
        return self._envelope(
            source="uspto",
            source_product="tsdr",
            query={"identifier": identifier, "identifier_type": identifier_type},
            record_type="trademark_case",
            normalized={
                "identifier": identifier,
                "identifier_type": identifier_type,
                "status_record": raw,
            },
            raw=raw,
            citations=[
                self._citation(
                    "TSDR",
                    TSDR_PORTAL_URL,
                    notes=f"Lookup {identifier_type}:{identifier} in the official TSDR portal if needed.",
                )
            ],
            warnings=warnings,
        )

    def trademark_documents(
        self, query_type: str, query_value: str, fmt: str = "json", **params: Any
    ) -> dict[str, Any]:
        raw = self.tsdr_documents(query_type=query_type, query_value=query_value, fmt=fmt, **params)
        return self._envelope(
            source="uspto",
            source_product="tsdr_documents",
            query={"query_type": query_type, "query_value": query_value, "format": fmt, **params},
            record_type="trademark_document",
            normalized={
                "identifier": query_value,
                "identifier_type": query_type,
                "documents": raw,
            },
            raw=raw,
            citations=[self._citation("TSDR", TSDR_PORTAL_URL)],
        )

    def trademark_tmog(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="tmog",
            query={"text": query},
            record_type="trademark_proceeding",
            normalized={"query": query, "product_url": TRADEMARK_TMOG_URL},
            citations=[self._citation("Trademark Official Gazette", TRADEMARK_TMOG_URL)],
            warnings=[
                "TMOG monitoring is currently a portal handoff and citation layer, not a dedicated parser."
            ],
        )

    def trademark_id_manual(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="id_manual",
            query={"text": query},
            record_type="trademark_goods_services",
            normalized={"query": query, "product_url": TRADEMARK_ID_MANUAL_URL},
            citations=[self._citation("Trademark ID Manual", TRADEMARK_ID_MANUAL_URL)],
            warnings=["ID Manual lookup is currently an official handoff only."],
        )

    def trademark_design_codes(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="design_codes",
            query={"text": query},
            record_type="trademark_mark",
            normalized={"query": query, "product_url": TRADEMARK_DESIGN_CODES_URL},
            citations=[self._citation("Design Search Code Manual", TRADEMARK_DESIGN_CODES_URL)],
            warnings=["Design-code lookup is currently an official handoff only."],
        )

    def trademark_proceedings(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="ttab",
            query={"text": query},
            record_type="trademark_proceeding",
            normalized={"query": query, "product_url": TRADEMARK_TTAB_URL},
            citations=[self._citation("TTAB Center", TRADEMARK_TTAB_URL)],
            warnings=[
                "Trademark proceedings support is currently a portal handoff with citations."
            ],
        )

    def assignment_search(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="uspto",
            source_product="assignment_center",
            query={"text": query},
            record_type="assignment_record",
            normalized={
                "query": query,
                "portal_url": ASSIGNMENT_CENTER_URL,
            },
            citations=[self._citation("Assignment Center", ASSIGNMENT_CENTER_URL)],
            warnings=[
                "Assignment search is currently provided as an official portal handoff; authenticated retrieval can use `copilot uspto portal fetch`."
            ],
        )

    def copyright_search(self, query: str) -> dict[str, Any]:
        return self._envelope(
            source="copyright_office",
            source_product="copyright_public_records",
            query={"text": query},
            record_type="copyright_record",
            normalized={
                "query": query,
                "search_url": COPYRIGHT_RECORDS_URL,
                "system": "Copyright Public Records Portal",
            },
            citations=[self._citation("Copyright Public Records Portal", COPYRIGHT_RECORDS_URL)],
            warnings=[
                "This is an adjacent non-USPTO registry. Exact API-backed querying is not implemented in this CLI yet."
            ],
        )

    def build_dossier(self, seeds: list[str]) -> dict[str, Any]:
        if not seeds:
            raise ValidationError(
                "At least one seed is required to build a dossier.", service=SERVICE
            )

        records: list[dict[str, Any]] = []
        flags: list[str] = []
        citations: list[dict[str, str]] = []
        warnings: list[str] = []

        for seed in seeds:
            records.append(self.patent_search(seed))
            records.append(self.trademark_search(seed))
            records.append(self.assignment_search(seed))
            records.append(self.copyright_search(seed))

            if seed.isdigit() and len(seed) in (7, 8):
                try:
                    tm = self.trademark_status(seed, identifier_type="sn")
                    records.append(tm)
                    flags.extend(tm.get("warnings", []))
                except CopilotError as exc:
                    warnings.append(f"TSDR lookup failed for {seed}: {exc}")

        for record in records:
            citations.extend(record.get("citations", []))
            warnings.extend(record.get("warnings", []))

        deduped_citations: list[dict[str, str]] = []
        seen_citations: set[tuple[str, str]] = set()
        for citation in citations:
            key = (citation.get("label", ""), citation.get("url", ""))
            if key not in seen_citations:
                seen_citations.add(key)
                deduped_citations.append(citation)

        summary = {
            "seed_count": len(seeds),
            "record_count": len(records),
            "record_types": sorted({record["record_type"] for record in records}),
            "active_flags": sorted(set(flags)),
        }
        return {
            "name": None,
            "created_at": self._now(),
            "seeds": seeds,
            "summary": summary,
            "records": records,
            "citations": deduped_citations,
            "warnings": sorted(set(warnings)),
        }

    def save_dossier(self, name: str, dossier: dict[str, Any]) -> dict[str, Any]:
        dossier["name"] = name
        path = record_path("dossiers", name)
        save_json(path, dossier)
        return {"name": name, "path": str(path), "saved_at": self._now()}

    def get_dossier(self, name: str) -> dict[str, Any]:
        path = record_path("dossiers", name)
        dossier = load_json(path)
        if not dossier:
            raise NotFoundError(f"Dossier not found: {name}", service=SERVICE)
        return dossier

    def list_dossiers(self) -> list[dict[str, Any]]:
        return list_records("dossiers")

    def export_dossier(self, name: str, output_path: str, fmt: str = "json") -> dict[str, Any]:
        dossier = self.get_dossier(name)
        destination = Path(output_path).expanduser().resolve()
        if fmt == "json":
            destination.write_text(json.dumps(dossier, indent=2, default=str), encoding="utf-8")
        elif fmt == "md":
            flag_lines = [
                f"- {flag}" for flag in dossier.get("summary", {}).get("active_flags", [])
            ]
            if not flag_lines:
                flag_lines = ["- None"]
            lines = [
                f"# Clearance Dossier: {name}",
                "",
                f"Created: {dossier.get('created_at', '')}",
                "",
                "## Seeds",
                *[f"- {seed}" for seed in dossier.get("seeds", [])],
                "",
                "## Summary",
                f"- Records: {dossier.get('summary', {}).get('record_count', 0)}",
                f"- Record types: {', '.join(dossier.get('summary', {}).get('record_types', []))}",
                "",
                "## Flags",
                *flag_lines,
                "",
                "## Citations",
                *[
                    f"- [{citation.get('label', citation.get('url', 'source'))}]({citation.get('url', '')})"
                    for citation in dossier.get("citations", [])
                ],
            ]
            destination.write_text("\n".join(lines), encoding="utf-8")
        else:
            raise ValidationError(
                "Unsupported dossier export format. Use json or md.", service=SERVICE
            )
        return {"name": name, "format": fmt, "output_path": str(destination)}

    def import_session(self, name: str, session_file: str) -> dict[str, Any]:
        source = Path(session_file).expanduser().resolve()
        if not source.is_file():
            raise NotFoundError(f"Session file not found: {source}", service=SERVICE)

        payload = json.loads(source.read_text(encoding="utf-8"))
        normalized = self._normalize_session_payload(payload)

        storage_state_path = record_path("session_states", name)
        metadata_path = record_path("sessions", name)
        save_json(storage_state_path, normalized)
        metadata = {
            "name": name,
            "source_path": str(source),
            "storage_state_path": str(storage_state_path),
            "imported_at": self._now(),
            "cookie_count": len(normalized.get("cookies", [])),
            "origin_count": len(normalized.get("origins", [])),
        }
        save_json(metadata_path, metadata)
        return metadata

    def list_sessions(self) -> list[dict[str, Any]]:
        return list_records("sessions")

    def get_session(self, name: str) -> dict[str, Any]:
        session = load_json(record_path("sessions", name))
        if not session:
            raise NotFoundError(f"Session not found: {name}", service=SERVICE)
        return session

    def portal_fetch(
        self,
        session_name: str,
        url: str,
        include_html: bool = False,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        session = self.get_session(session_name)
        storage_state_path = session.get("storage_state_path")
        if not storage_state_path:
            raise ValidationError(
                "Imported session is missing storage_state_path.", service=SERVICE
            )

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ConfigError(
                f"Playwright is unavailable: {exc}",
                service=SERVICE,
                hint="Install Playwright and its browser binaries before using portal fetch.",
            )

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(storage_state=storage_state_path)
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                result = {
                    "session": session_name,
                    "requested_url": url,
                    "final_url": page.url,
                    "status": response.status if response else None,
                    "title": page.title(),
                    "body_text": page.locator("body").inner_text(timeout=timeout_ms)[:4000],
                }
                if include_html:
                    result["html"] = page.content()
                context.close()
                browser.close()
                return result
        except PlaywrightError as exc:
            raise CopilotError(
                f"Portal fetch failed: {exc}",
                service=SERVICE,
                hint="Confirm the imported session is valid and the target portal is reachable.",
            )

    def capture_session(self, name: str, url: str) -> dict[str, Any]:
        """Open a headed browser, let the user log in manually, then save storage state."""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ConfigError(
                f"Playwright is unavailable: {exc}",
                service=SERVICE,
                hint="Install Playwright and its browser binaries before using session capture.",
            )

        storage_state_path = record_path("session_states", name)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                input(
                    "Complete login in the opened browser window, then press Enter here to save the session..."
                )
                context.storage_state(path=str(storage_state_path))
                context.close()
                browser.close()
        except PlaywrightError as exc:
            raise CopilotError(
                f"Session capture failed: {exc}",
                service=SERVICE,
                hint="Confirm the target URL is reachable and try again.",
            )

        return self.import_session(name, str(storage_state_path))

    def auth_requirements(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, artifact in ARTIFACTS.items():
            rows.append(
                {
                    "id": key,
                    "name": artifact["name"],
                    "kind": artifact["kind"],
                    "env_var": artifact.get("env_var") or "",
                    "required_for": ", ".join(artifact.get("required_for", [])),
                }
            )
        return rows

    def auth_instructions(self, artifact_id: str) -> dict[str, Any]:
        artifact = ARTIFACTS.get(artifact_id)
        if not artifact:
            raise NotFoundError(f"Unknown auth artifact: {artifact_id}", service=SERVICE)
        result = dict(artifact)
        if artifact["kind"] == "storage_state":
            result["capture_guide"] = CAPTURE_GUIDE
        return result

    def auth_status(self) -> dict[str, Any]:
        sessions = {row.get("name"): row for row in self.list_sessions()}
        checks: list[dict[str, Any]] = []

        settings_map = {
            "odp_base_url": self._odp_base_url,
            "odp_api_key": self._api_key,
        }

        for artifact_id, artifact in ARTIFACTS.items():
            kind = artifact["kind"]
            value_present = False
            detail = ""

            if kind in {"api_key", "config"}:
                raw_value = settings_map.get(artifact_id, "")
                value_present = bool(raw_value)
                detail = artifact.get("env_var") or ""
            elif kind == "storage_state":
                if artifact_id == "patent_center_session":
                    candidates = ["patent-center", "patent_center", "patentcenter"]
                elif artifact_id == "trademark_center_session":
                    candidates = ["trademark-center", "trademark_center", "trademarkcenter"]
                elif artifact_id == "assignment_center_session":
                    candidates = ["assignment-center", "assignment_center", "assignmentcenter"]
                else:
                    candidates = []
                matched = next((sessions[name] for name in candidates if name in sessions), None)
                value_present = matched is not None
                detail = (
                    matched.get("name", "") if matched else "No matching imported session found"
                )
            elif kind == "public_portal":
                value_present = True
                detail = "No token required"

            checks.append(
                {
                    "id": artifact_id,
                    "name": artifact["name"],
                    "kind": kind,
                    "status": "ready" if value_present else "missing",
                    "detail": detail,
                }
            )

        implemented = [
            "health/auth/products/request",
            "patent search/application handoffs",
            "trademark search/status/TSDR/TMOG/ID Manual/design code/proceedings handoffs",
            "assignment and copyright handoffs",
            "dossier build/show/list/export",
            "watch create/list/run",
            "session import/capture/list",
            "portal fetch with imported session",
        ]
        pending = [
            "Dedicated ODP endpoint adapters for office actions, PTAB, and other products once exact official paths are confirmed",
            "Authenticated filing/submission automation beyond retrieval and session capture",
            "Native API-backed adapters for public trademark search, TMOG, ID Manual, design codes, and assignment search if official stable endpoints become available",
        ]
        return {
            "implemented": implemented,
            "checks": checks,
            "pending": pending,
            "next_steps": [
                "Set USPTO_CLI_API_KEY and USPTO_CLI_BASE_URL in .env.",
                "Run `copilot uspto auth show <artifact_id>` for any missing item.",
                "Capture portal sessions with `copilot uspto sessions capture <name> <url>` as needed.",
            ],
        }

    def create_watch(self, name: str, seeds: list[str]) -> dict[str, Any]:
        if not seeds:
            raise ValidationError(
                "At least one seed is required to create a watch.", service=SERVICE
            )
        watch = {
            "name": name,
            "seeds": seeds,
            "created_at": self._now(),
            "last_run_at": None,
            "last_hash": None,
        }
        save_json(record_path("watches", name), watch)
        return watch

    def list_watches(self) -> list[dict[str, Any]]:
        return list_records("watches")

    def run_watch(self, name: str) -> dict[str, Any]:
        watch = load_json(record_path("watches", name))
        if not watch:
            raise NotFoundError(f"Watch not found: {name}", service=SERVICE)

        dossier = self.build_dossier(watch.get("seeds", []))
        digest = hashlib.sha256(json.dumps(dossier["summary"], sort_keys=True).encode()).hexdigest()
        previous = watch.get("last_hash")
        changed = previous is not None and previous != digest
        events: list[dict[str, Any]] = []
        if previous is None:
            events.append({"type": "initialized", "message": "Initial watch snapshot created."})
        elif changed:
            events.append({"type": "changed", "message": "Watch summary changed since last run."})
        else:
            events.append({"type": "unchanged", "message": "No summary change since last run."})

        watch["last_hash"] = digest
        watch["last_run_at"] = self._now()
        save_json(record_path("watches", name), watch)
        snapshot_path = record_path("watch_runs", f"{name}-{digest[:12]}")
        save_json(snapshot_path, {"watch": name, "dossier": dossier, "events": events})
        return {"watch": watch, "events": events, "dossier_summary": dossier["summary"]}

    def health(self) -> dict[str, Any]:
        """Check USPTO configuration and verify the TSDR key path."""
        if not self._api_key:
            return {
                "healthy": False,
                "status": "unhealthy",
                "error": "Missing USPTO_CLI_API_KEY",
            }
        if not self._odp_base_url:
            return {
                "healthy": False,
                "status": "unhealthy",
                "error": "Missing USPTO_CLI_BASE_URL",
            }

        details = {
            "odp_base_url": self._odp_base_url,
            "tsdr_base_url": self._tsdr_base_url,
            "auth_headers": {
                "odp": "X-Api-Key",
                "tsdr": "USPTO-API-KEY",
            },
        }
        try:
            self.tsdr_status("78787878")
            details["tsdr_check"] = "ok"
            return {"healthy": True, "status": "healthy", **details}
        except NotFoundError:
            details["tsdr_check"] = "ok (authenticated, sample case not found)"
            return {"healthy": True, "status": "healthy", **details}
        except CopilotError as exc:
            return {
                "healthy": False,
                "status": "unhealthy",
                "error": str(exc),
                **details,
            }
        except Exception as exc:
            return {
                "healthy": False,
                "status": "unhealthy",
                "error": str(exc),
                **details,
            }
