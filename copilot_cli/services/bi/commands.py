"""Typer subcommand group for business intelligence operations."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(no_args_is_help=True)
console = Console()


def _mod():
    """Lazy-import the BI client module."""
    from copilot_cli.services.bi import client

    return client


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def analyze(
    file: str = typer.Argument(..., help="Path to a JSON or CSV file."),
    metrics: str | None = typer.Option(
        None,
        "--metrics",
        "-m",
        help="Comma-separated list of numeric columns to analyze.",
    ),
) -> None:
    """Analyze data in a JSON or CSV file."""
    try:
        mod = _mod()
        data = mod._load_data(file)
        metric_list = [m.strip() for m in metrics.split(",")] if metrics else None
        result = mod.analyze_data(data=data, metrics=metric_list)
        print_json(result, title=f"Analysis: {file}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def patterns(
    file: str = typer.Argument(..., help="Path to a JSON or CSV file."),
    column: str = typer.Argument(..., help="Column name for frequency analysis."),
) -> None:
    """Detect value frequency patterns in a column."""
    try:
        mod = _mod()
        data = mod._load_data(file)
        results = mod.detect_patterns(data=data, column=column)
        print_table(
            results,
            title=f"Patterns: {column}",
            columns=["value", "count", "percentage"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def kpis(
    file: str = typer.Argument(..., help="Path to a JSON or CSV file."),
    definitions: str = typer.Option(
        ...,
        "--definitions",
        "-d",
        help='KPI definitions as JSON string, e.g. \'{"revenue": {"column": "amount", "operation": "sum"}}\'.',
    ),
) -> None:
    """Calculate KPIs from data."""
    try:
        kpi_defs = json.loads(definitions)
    except json.JSONDecodeError as exc:
        print_error(f"Invalid JSON in --definitions: {exc}")
        raise typer.Exit(1)

    try:
        mod = _mod()
        data = mod._load_data(file)
        result = mod.calculate_kpis(data=data, kpi_definitions=kpi_defs)
        print_json(result, title="KPI Results")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def summary(
    file: str = typer.Argument(..., help="Path to a JSON or CSV file."),
) -> None:
    """Generate a text summary of a dataset."""
    try:
        mod = _mod()
        data = mod._load_data(file)
        text = mod.generate_summary(data=data)
        console.print(text)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Check BI service health."""
    try:
        result = _mod().health()
        is_healthy = result.get("healthy", False)
        print_health("bi", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success("BI analysis service is available")
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
