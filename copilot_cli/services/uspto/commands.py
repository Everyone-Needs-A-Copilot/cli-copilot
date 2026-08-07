"""Typer commands for USPTO ODP and TSDR access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(
    no_args_is_help=True,
    help="USPTO patent, trademark, assignment, and copyright tools. Requires USPTO_CLI_API_KEY and USPTO_CLI_BASE_URL in .env.",
)
auth_app = typer.Typer(no_args_is_help=True, help="Auth requirements and capture instructions.")
patents_app = typer.Typer(no_args_is_help=True, help="Patent search and retrieval.")
trademarks_app = typer.Typer(no_args_is_help=True, help="Trademark search and TSDR retrieval.")
assignments_app = typer.Typer(no_args_is_help=True, help="Assignment and ownership lookup.")
copyright_app = typer.Typer(no_args_is_help=True, help="Copyright registry handoff and lookup.")
dossier_app = typer.Typer(no_args_is_help=True, help="Cross-source dossier workflows.")
watch_app = typer.Typer(no_args_is_help=True, help="Watchlist management.")
sessions_app = typer.Typer(no_args_is_help=True, help="Imported portal sessions.")
portal_app = typer.Typer(no_args_is_help=True, help="Session-backed portal retrieval.")
tsdr_app = typer.Typer(no_args_is_help=True, help="TSDR trademark retrieval.")
discover_app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Automated API contract discovery via Playwright browser interception. "
        "Opens a real browser, intercepts XHR/fetch requests during a search on USPTO portals, "
        "and saves captured request/response pairs as structured JSON contracts to "
        "~/.copilot-cli/uspto/contracts/. Use these contracts to generate adapter stubs. "
        "Requires: playwright package with Chromium (pip install playwright && playwright install chromium). "
        "Workflow: products -> auto/manual -> show -> generate."
    ),
)

app.add_typer(auth_app, name="auth")
app.add_typer(patents_app, name="patents")
app.add_typer(trademarks_app, name="trademarks")
app.add_typer(assignments_app, name="assignments")
app.add_typer(copyright_app, name="copyright")
app.add_typer(dossier_app, name="dossier")
app.add_typer(watch_app, name="watch")
app.add_typer(sessions_app, name="sessions")
app.add_typer(portal_app, name="portal")
app.add_typer(tsdr_app, name="tsdr")
app.add_typer(discover_app, name="discover")


def _client():
    from copilot_cli.services.uspto.client import USPTOClient

    return USPTOClient()


def _parse_json_option(value: str | None, option_name: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {option_name}: {exc}") from exc


@app.command()
def health() -> None:
    """Check USPTO configuration and API-key connectivity."""
    result = _client().health()
    healthy = result.get("healthy", False)
    print_health("uspto", healthy, result if not healthy else None)
    if not healthy:
        raise typer.Exit(1)


@app.command()
def products() -> None:
    """Show the USPTO product coverage the CLI should support."""
    rows = [
        {
            "area": "Patents",
            "product": "ODP Patent File Wrapper / Application Data",
            "why": "Core application, filing, party, status, and document-level patent search.",
        },
        {
            "area": "Patents",
            "product": "Patent Public Search",
            "why": "Prior-art and issued/publication search coverage for patent clearance workflows.",
        },
        {
            "area": "Patents",
            "product": "Patent Center",
            "why": "Application-level status, documents, and workflow visibility beyond public ODP datasets.",
        },
        {
            "area": "Patents",
            "product": "ODP PTAB APIs",
            "why": "Appeals, trials, and post-grant proceedings that affect freedom-to-operate review.",
        },
        {
            "area": "Patents",
            "product": "ODP Office Action APIs",
            "why": "Examination history, cited art, and prosecution context for risk review.",
        },
        {
            "area": "Trademarks",
            "product": "TSDR APIs",
            "why": "Official trademark case status, documents, bundles, and specimen/image retrieval.",
        },
        {
            "area": "Trademarks",
            "product": "Trademark Search",
            "why": "Primary clearance search for marks, including broader similarity review beyond exact IDs.",
        },
        {
            "area": "Trademarks",
            "product": "Trademark Official Gazette",
            "why": "Monitors marks entering the opposition window before they mature into stronger conflicts.",
        },
        {
            "area": "Trademarks",
            "product": "ID Manual and Design Search Code Manual",
            "why": "Needed to normalize goods/services classes and design-mark searching logic.",
        },
        {
            "area": "Trademarks",
            "product": "Trademark Decisions and Proceedings tool",
            "why": "Shows expungement, reexamination, sanctions, and petitions history relevant to risk.",
        },
        {
            "area": "Assignments",
            "product": "Assignment Center and Assignment Search",
            "why": "Ownership chain, recordation, and historical transfers matter for enforcement and licensing risk.",
        },
        {
            "area": "Copyright",
            "product": "Not covered by USPTO",
            "why": "Use U.S. Copyright Office records separately; USPTO APIs do not solve this domain.",
        },
    ]
    print_table(rows, title="USPTO Capability Map", columns=["area", "product", "why"])


@auth_app.command("list")
def auth_list() -> None:
    """List required auth artifacts, keys, and session types."""
    try:
        rows = _client().auth_requirements()
        print_table(
            rows,
            title="USPTO Auth Requirements",
            columns=["id", "name", "kind", "env_var", "required_for"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@auth_app.command("show")
def auth_show(
    artifact_id: str = typer.Argument(..., help="Auth artifact id from `copilot uspto auth list`."),
) -> None:
    """Show detailed instructions for one auth artifact."""
    try:
        print_json(
            _client().auth_instructions(artifact_id), title=f"Auth Instructions: {artifact_id}"
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@auth_app.command("status")
def auth_status() -> None:
    """Show what is implemented and what you still need to provide."""
    try:
        result = _client().auth_status()
        print_json(result, title="USPTO Readiness")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@patents_app.command("search")
def patents_search(
    query: str = typer.Argument(..., help="Patent search text."),
) -> None:
    """Create a normalized patent search handoff."""
    try:
        print_json(_client().patent_search(query), title="Patent Search")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@patents_app.command("application")
def patents_application(
    identifier: str = typer.Argument(..., help="Application, publication, or patent identifier."),
    type: str = typer.Option("application", "--type", "-t", help="Identifier type."),
) -> None:
    """Create a normalized patent application handoff."""
    try:
        print_json(
            _client().patent_application(identifier, identifier_type=type),
            title="Patent Application",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@patents_app.command("office-actions")
def patents_office_actions(
    query: str = typer.Argument("*:*", help="Office-action criteria query."),
    start: int = typer.Option(0, "--start", help="Result offset."),
    rows: int = typer.Option(25, "--rows", help="Number of records to return."),
) -> None:
    """Search Office Action records using the live API."""
    try:
        print_json(
            _client().patent_office_action_records(criteria=query, start=start, rows=rows),
            title="Patent Office Actions",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@patents_app.command("office-action-fields")
def patents_office_action_fields() -> None:
    """Fetch the Office Action field schema from the live API."""
    try:
        print_json(_client().patent_office_action_fields(), title="Office Action Fields")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@patents_app.command("ptab")
def patents_ptab(
    query: str = typer.Argument(..., help="PTAB query, identifier, or party name."),
) -> None:
    """Create a normalized PTAB handoff."""
    try:
        print_json(_client().patent_ptab(query), title="PTAB")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("search")
def trademarks_search(
    query: str = typer.Argument(..., help="Trademark search text."),
) -> None:
    """Create a normalized trademark search handoff."""
    try:
        print_json(_client().trademark_search(query), title="Trademark Search")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("status")
def trademarks_status(
    identifier: str = typer.Argument(
        ..., help="Trademark serial, registration, ref, or IR number."
    ),
    type: str = typer.Option(
        "sn", "--type", "-t", help="Identifier type such as sn, rn, ref, or ir."
    ),
) -> None:
    """Fetch normalized trademark status."""
    try:
        print_json(
            _client().trademark_status(identifier, identifier_type=type), title="Trademark Status"
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("tmog")
def trademarks_tmog(
    query: str = typer.Argument(..., help="Trademark Official Gazette query."),
) -> None:
    """Create a TMOG handoff."""
    try:
        print_json(_client().trademark_tmog(query), title="Trademark Official Gazette")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("id-manual")
def trademarks_id_manual(
    query: str = typer.Argument(..., help="Goods/services wording query."),
) -> None:
    """Create an ID Manual handoff."""
    try:
        print_json(_client().trademark_id_manual(query), title="Trademark ID Manual")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("design-codes")
def trademarks_design_codes(
    query: str = typer.Argument(..., help="Design-mark search query."),
) -> None:
    """Create a Design Search Code Manual handoff."""
    try:
        print_json(_client().trademark_design_codes(query), title="Design Search Codes")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@trademarks_app.command("proceedings")
def trademarks_proceedings(
    query: str = typer.Argument(..., help="Trademark proceeding query or party name."),
) -> None:
    """Create a TTAB proceedings handoff."""
    try:
        print_json(_client().trademark_proceedings(query), title="Trademark Proceedings")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@assignments_app.command("search")
def assignments_search(
    query: str = typer.Argument(..., help="Assignor, assignee, reel/frame, or entity query."),
) -> None:
    """Create an assignment search handoff."""
    try:
        print_json(_client().assignment_search(query), title="Assignment Search")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@copyright_app.command("search")
def copyright_search(
    query: str = typer.Argument(..., help="Copyright search text."),
) -> None:
    """Create a copyright public-records handoff."""
    try:
        print_json(_client().copyright_search(query), title="Copyright Search")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@dossier_app.command("build")
def dossier_build(
    name: str = typer.Argument(..., help="Saved dossier name."),
    seeds: str = typer.Argument(..., help="Comma-separated seeds to fan out across sources."),
) -> None:
    """Build and save a clearance dossier."""
    try:
        seed_list = [seed.strip() for seed in seeds.split(",") if seed.strip()]
        dossier = _client().build_dossier(seed_list)
        result = _client().save_dossier(name, dossier)
        print_success(f"Saved dossier {name}")
        print_json({"saved": result, "summary": dossier["summary"]}, title="Dossier Build")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@dossier_app.command("show")
def dossier_show(
    name: str = typer.Argument(..., help="Saved dossier name."),
) -> None:
    """Show a saved dossier."""
    try:
        print_json(_client().get_dossier(name), title=f"Dossier {name}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@dossier_app.command("list")
def dossier_list() -> None:
    """List saved dossiers."""
    try:
        rows = _client().list_dossiers()
        print_table(rows, title="Saved Dossiers", columns=["name", "created_at", "_path"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@dossier_app.command("export")
def dossier_export(
    name: str = typer.Argument(..., help="Saved dossier name."),
    output: str = typer.Argument(..., help="Output file path."),
    format: str = typer.Option("json", "--format", "-f", help="json or md."),
) -> None:
    """Export a dossier to disk."""
    try:
        result = _client().export_dossier(name, output_path=output, fmt=format)
        print_success(f"Exported dossier {name}")
        print_json(result, title="Dossier Export")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@watch_app.command("create")
def watch_create(
    name: str = typer.Argument(..., help="Watch name."),
    seeds: str = typer.Argument(..., help="Comma-separated seeds to monitor."),
) -> None:
    """Create a watchlist."""
    try:
        seed_list = [seed.strip() for seed in seeds.split(",") if seed.strip()]
        result = _client().create_watch(name, seed_list)
        print_success(f"Created watch {name}")
        print_json(result, title="Watch Created")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@watch_app.command("list")
def watch_list() -> None:
    """List watchlists."""
    try:
        rows = _client().list_watches()
        print_table(rows, title="Watches", columns=["name", "created_at", "last_run_at"])
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@watch_app.command("run")
def watch_run(
    name: str = typer.Argument(..., help="Watch name."),
) -> None:
    """Run a saved watchlist."""
    try:
        print_json(_client().run_watch(name), title=f"Watch {name}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@sessions_app.command("import")
def sessions_import(
    name: str = typer.Argument(..., help="Session name."),
    file: str = typer.Argument(..., help="Path to storage-state or cookie JSON."),
) -> None:
    """Import a portal session."""
    try:
        result = _client().import_session(name, file)
        print_success(f"Imported session {name}")
        print_json(result, title="Session Imported")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@sessions_app.command("capture")
def sessions_capture(
    name: str = typer.Argument(..., help="Session name."),
    url: str = typer.Argument(..., help="Login or portal URL to open for manual authentication."),
) -> None:
    """Open a browser and capture authenticated storage state."""
    try:
        result = _client().capture_session(name, url)
        print_success(f"Captured session {name}")
        print_json(result, title="Session Captured")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@sessions_app.command("list")
def sessions_list() -> None:
    """List imported sessions."""
    try:
        rows = _client().list_sessions()
        print_table(
            rows,
            title="Imported Sessions",
            columns=["name", "imported_at", "cookie_count", "origin_count"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@portal_app.command("fetch")
def portal_fetch(
    session: str = typer.Option(..., "--session", "-s", help="Imported session name."),
    url: str = typer.Argument(..., help="Target portal URL."),
    include_html: bool = typer.Option(False, "--include-html", help="Include full HTML content."),
    timeout_ms: int = typer.Option(30000, "--timeout-ms", help="Navigation timeout."),
) -> None:
    """Fetch a portal page using an imported session."""
    try:
        result = _client().portal_fetch(
            session_name=session,
            url=url,
            include_html=include_html,
            timeout_ms=timeout_ms,
        )
        print_json(result, title="Portal Fetch")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def request(
    path: str = typer.Argument(..., help="ODP path relative to USPTO_CLI_BASE_URL."),
    method: str = typer.Option("GET", "--method", "-X", help="HTTP method."),
    params: str | None = typer.Option(None, "--params", help="Query params as a JSON object."),
    body: str | None = typer.Option(None, "--body", help="Request body as a JSON object or array."),
) -> None:
    """Make a generic authenticated request to the USPTO ODP API."""
    try:
        result = _client().request(
            path=path,
            method=method,
            params=_parse_json_option(params, "--params"),
            json_body=_parse_json_option(body, "--body"),
        )
        print_json(result, title=f"USPTO {method.upper()} {path}")
    except typer.BadParameter as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@tsdr_app.command("status")
def tsdr_status(
    identifier: str = typer.Argument(
        ..., help="Trademark serial, registration, ref, or IR number."
    ),
    type: str = typer.Option(
        "sn", "--type", "-t", help="Identifier type such as sn, rn, ref, or ir."
    ),
    format: str = typer.Option("json", "--format", "-f", help="json, xml, html, pdf, or zip."),
) -> None:
    """Fetch TSDR trademark case status."""
    try:
        result = _client().trademark_status(identifier=identifier, identifier_type=type)
        if format != "json":
            result = _client().tsdr_status(identifier=identifier, identifier_type=type, fmt=format)
        print_json(result, title="TSDR Status")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@tsdr_app.command("docs")
def tsdr_docs(
    query_value: str = typer.Argument(..., help="Identifier value."),
    query_type: str = typer.Option("sn", "--query-type", "-q", help="sn, rn, ref, or ir."),
    format: str = typer.Option("pdf", "--format", "-f", help="json, xml, pdf, or zip."),
    category: str | None = typer.Option(None, "--category", help="Document category filter."),
    doc_type: str | None = typer.Option(None, "--doc-type", help="Document type filter."),
    date: str | None = typer.Option(None, "--date", help="Exact date YYYY-MM-DD."),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date YYYY-MM-DD."),
    to_date: str | None = typer.Option(None, "--to-date", help="End date YYYY-MM-DD."),
    sort: str | None = typer.Option(None, "--sort", help="Sort expression such as date:A."),
) -> None:
    """Fetch TSDR case document bundles or metadata."""
    try:
        if format == "json":
            result = _client().trademark_documents(
                query_type=query_type,
                query_value=query_value,
                fmt=format,
                category=category,
                type=doc_type,
                date=date,
                fromDate=from_date,
                toDate=to_date,
                sort=sort,
            )
        else:
            result = _client().tsdr_documents(
                query_type=query_type,
                query_value=query_value,
                fmt=format,
                category=category,
                type=doc_type,
                date=date,
                fromDate=from_date,
                toDate=to_date,
                sort=sort,
            )
        print_json(result, title="TSDR Documents")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@tsdr_app.command("image")
def tsdr_image(
    serial_number: str = typer.Argument(..., help="Trademark serial number."),
) -> None:
    """Fetch a trademark image from TSDR."""
    try:
        result = _client().tsdr_image(serial_number)
        print_json(result, title="TSDR Image")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# discover subcommands
# ---------------------------------------------------------------------------


def _discoverer(session: str | None = None):
    from copilot_cli.services.uspto.discovery import ContractDiscoverer

    return ContractDiscoverer(session_name=session)


@discover_app.command("auto")
def discover_auto(
    product: str = typer.Argument(
        ...,
        help=(
            "Product name from the recipe registry. "
            "Valid names: ptab, trademark_search, tmog, id_manual, design_search, assignment_search. "
            "Run 'discover products' to see all."
        ),
    ),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Imported session name to use for auth."
    ),
    query: str | None = typer.Option(
        None, "--query", "-q", help="Override the recipe sample query."
    ),
) -> None:
    """Run automated contract discovery using a saved product recipe.

    Opens a headed Chromium browser, navigates to the recipe URL, fills the search
    field with the sample query, submits, and captures all XHR/fetch API requests.
    The highest-scored contract is saved to ~/.copilot-cli/uspto/contracts/<product>.json.
    Requires: Playwright with Chromium (pip install playwright && playwright install chromium).
    Use 'copilot uspto discover products' to see all valid product names.
    Output: JSON with keys: product, captured (count), top_url, top_method, response_status, saved_to.
    """
    from copilot_cli.services.uspto.recipes import RECIPES

    recipe = RECIPES.get(product)
    if not recipe:
        available = ", ".join(sorted(RECIPES.keys()))
        print_error(f"Unknown product: {product}", hint=f"Available products: {available}")
        raise typer.Exit(1)

    if query:
        recipe = recipe.model_copy(update={"sample_query": query})

    try:
        discoverer = _discoverer(session)
        captures = discoverer.discover_auto(recipe)
        if not captures:
            print_error(
                "No API requests were captured.",
                hint="Try manual discovery or verify selectors in the recipe.",
            )
            raise typer.Exit(1)

        top = captures[0]
        path = discoverer.save_contract(top)
        print_success(f"Saved contract for {product}")
        print_json(
            {
                "product": product,
                "captured": len(captures),
                "top_url": top.url,
                "top_method": top.method,
                "response_status": top.response_status,
                "saved_to": str(path),
            },
            title=f"Discovery: {product}",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@discover_app.command("manual")
def discover_manual(
    url: str = typer.Argument(..., help="Target portal URL to open in the browser."),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Imported session name to use for auth."
    ),
    product: str = typer.Option(
        "unknown", "--product", "-p", help="Product label to save the contract under."
    ),
    query: str = typer.Option(
        "", "--query", "-q", help="Sample query label to embed in the contract."
    ),
    timeout: int = typer.Option(
        120,
        "--timeout",
        "-t",
        help="Navigation timeout in seconds for the initial page load (default: 120).",
    ),
) -> None:
    """Open a headed browser for manual API contract discovery.

    Navigates to the given URL, starts network interception, then waits for you to
    perform a search in the browser. Press Enter in the terminal when done. All
    intercepted XHR/fetch requests are ranked and the top contract is saved to
    ~/.copilot-cli/uspto/contracts/<product>.json.
    Requires: Playwright with Chromium (pip install playwright && playwright install chromium).
    Output: JSON with keys: product, captured (count), top_url, top_method, response_status, saved_to.
    """
    try:
        discoverer = _discoverer(session)
        captures = discoverer.discover_manual(
            url=url, product=product, timeout_s=timeout, sample_query=query
        )
        if not captures:
            print_error(
                "No API requests were captured.",
                hint="Make sure you performed a search before pressing Enter.",
            )
            raise typer.Exit(1)

        top = captures[0]
        path = discoverer.save_contract(top)
        print_success(f"Saved contract for {product}")
        print_json(
            {
                "product": product,
                "captured": len(captures),
                "top_url": top.url,
                "top_method": top.method,
                "response_status": top.response_status,
                "saved_to": str(path),
            },
            title=f"Manual Discovery: {product}",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@discover_app.command("list")
def discover_list() -> None:
    """List all saved API contracts by product name.

    Output: Table with column 'product'. Empty table if no contracts saved yet.
    Contracts are stored in ~/.copilot-cli/uspto/contracts/.
    """
    discoverer = _discoverer()
    names = discoverer.list_contracts()
    if not names:
        print_json({"contracts": []}, title="Saved Contracts")
        return
    rows = [{"product": name} for name in names]
    print_table(rows, title="Saved Contracts", columns=["product"])


@discover_app.command("show")
def discover_show(
    product: str = typer.Argument(..., help="Product name to show the saved contract for."),
) -> None:
    """Show the full saved API contract for a product.

    Output: JSON with fields: product, captured_at, url, method, request_headers,
    request_content_type, request_body, response_status, response_content_type,
    response_headers, response_body_sample, response_body_size, sample_query, notes.
    Prerequisite: Run 'discover auto <product>' or 'discover manual' first.
    """
    discoverer = _discoverer()
    contract = discoverer.load_contract(product)
    if contract is None:
        print_error(
            f"No saved contract found for: {product}",
            hint="Run `copilot uspto discover auto <product>` first.",
        )
        raise typer.Exit(1)
    print_json(contract.model_dump(), title=f"Contract: {product}")


@discover_app.command("generate")
def discover_generate(
    product: str = typer.Argument(..., help="Product name to generate stubs for."),
    output_dir: str = typer.Option(
        ".", "--output-dir", "-o", help="Directory to write generated files into."
    ),
) -> None:
    """Generate Python adapter stubs from a saved API contract.

    Reads the contract saved by 'discover auto' or 'discover manual', then writes
    scaffolded client method, Typer command, and test files to the output directory.
    Generated files are stubs that need review before merging into the service.
    Prerequisite: A saved contract must exist for the given product.
    Output: JSON mapping generated filenames to their absolute paths.
    """
    from copilot_cli.services.uspto.codegen import AdapterGenerator

    discoverer = _discoverer()
    contract = discoverer.load_contract(product)
    if contract is None:
        print_error(
            f"No saved contract found for: {product}",
            hint="Run `copilot uspto discover auto <product>` first.",
        )
        raise typer.Exit(1)

    out = Path(output_dir).expanduser().resolve()
    generator = AdapterGenerator(contract)
    generated = generator.generate_all(out)
    print_success(f"Generated stubs for {product}")
    print_json(
        {product: {k: str(v) for k, v in generated.items()}},
        title=f"Generated Stubs: {product}",
    )


@discover_app.command("products")
def discover_products() -> None:
    """Show all available product recipes and their confirmation status.

    Output: Table with columns: product, url, search_selector, sample_query, confirmed.
    """
    from copilot_cli.services.uspto.recipes import RECIPES

    rows = [
        {
            "product": r.product,
            "url": r.url,
            "search_selector": r.search_selector or "(none)",
            "sample_query": r.sample_query or "(none)",
            "confirmed": "yes" if r.confirmed else "no",
        }
        for r in RECIPES.values()
    ]
    print_table(
        rows,
        title="Discovery Recipes",
        columns=["product", "url", "search_selector", "sample_query", "confirmed"],
    )
