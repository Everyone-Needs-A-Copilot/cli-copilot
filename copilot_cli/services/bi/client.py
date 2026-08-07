"""Business intelligence service - local data analysis helpers for JSON/CSV files."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

from copilot_cli.shared.errors import NotFoundError, ValidationError

SERVICE = "bi"


def _load_data(file_path: str) -> list[dict[str, Any]]:
    """Load data from a JSON or CSV file.

    Args:
        file_path: Path to a ``.json`` or ``.csv`` file.

    Returns:
        List of dicts representing rows.

    Raises:
        NotFoundError: If the file does not exist.
        ValidationError: If the format is unsupported or the data cannot be parsed.
    """
    p = Path(file_path)
    if not p.exists():
        raise NotFoundError(f"File not found: {file_path}", service=SERVICE)
    if not p.is_file():
        raise ValidationError(f"Not a file: {file_path}", service=SERVICE)

    suffix = p.suffix.lower()

    if suffix == ".json":
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON in {file_path}: {exc}", service=SERVICE) from exc
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and "data" in raw:
            return raw["data"]
        raise ValidationError(
            "JSON must be a list of objects or a dict with a 'data' key.",
            service=SERVICE,
        )

    if suffix == ".csv":
        try:
            with open(p, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as exc:
            raise ValidationError(
                f"Failed to parse CSV {file_path}: {exc}", service=SERVICE
            ) from exc

    raise ValidationError(
        f"Unsupported file format: {suffix}. Use .json or .csv.",
        service=SERVICE,
    )


def _numeric_values(data: list[dict[str, Any]], column: str) -> list[float]:
    """Extract numeric values from a column, skipping non-numeric entries."""
    values: list[float] = []
    for row in data:
        val = row.get(column)
        if val is None:
            continue
        try:
            values.append(float(val))
        except (ValueError, TypeError):
            continue
    return values


def _detect_numeric_columns(data: list[dict[str, Any]]) -> list[str]:
    """Identify columns that contain predominantly numeric data."""
    if not data:
        return []
    columns: list[str] = []
    for key in data[0].keys():
        nums = _numeric_values(data, key)
        if len(nums) >= len(data) * 0.5:
            columns.append(key)
    return columns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_data(
    data: list[dict[str, Any]],
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Perform basic statistical analysis on tabular data.

    Args:
        data: List of row dicts.
        metrics: Optional list of specific numeric columns to analyze.
            Defaults to all detected numeric columns.

    Returns:
        Dict keyed by column name, each containing count, sum, avg, min, max.
    """
    if not data:
        return {"rows": 0, "columns": {}}

    target_columns = metrics or _detect_numeric_columns(data)
    result: dict[str, Any] = {}

    for col in target_columns:
        values = _numeric_values(data, col)
        if not values:
            result[col] = {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
            continue
        result[col] = {
            "count": len(values),
            "sum": round(sum(values), 4),
            "avg": round(statistics.mean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    return {"rows": len(data), "columns": result}


def detect_patterns(
    data: list[dict[str, Any]],
    column: str,
) -> list[dict[str, Any]]:
    """Perform frequency analysis on values in a column.

    Args:
        data: List of row dicts.
        column: Column name to analyze.

    Returns:
        Sorted list of dicts with keys: value, count, percentage.
    """
    if not data:
        return []

    freq: dict[str, int] = {}
    total = 0
    for row in data:
        val = str(row.get(column, "(empty)"))
        freq[val] = freq.get(val, 0) + 1
        total += 1

    results = [
        {
            "value": value,
            "count": count,
            "percentage": round((count / total) * 100, 2) if total else 0,
        }
        for value, count in freq.items()
    ]
    results.sort(key=lambda r: -r["count"])
    return results


def calculate_kpis(
    data: list[dict[str, Any]],
    kpi_definitions: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Calculate KPIs from data based on definitions.

    Each KPI definition should have:
        - ``column``: the numeric column to operate on
        - ``operation``: one of ``sum``, ``avg``, ``min``, ``max``, ``count``

    Args:
        data: List of row dicts.
        kpi_definitions: Dict mapping KPI name to its definition.

    Returns:
        Dict mapping KPI name to its calculated value.
    """
    results: dict[str, Any] = {}

    for kpi_name, definition in kpi_definitions.items():
        col = definition.get("column", "")
        operation = definition.get("operation", "count").lower()
        values = _numeric_values(data, col)

        if not values and operation != "count":
            results[kpi_name] = None
            continue

        if operation == "sum":
            results[kpi_name] = round(sum(values), 4)
        elif operation == "avg":
            results[kpi_name] = round(statistics.mean(values), 4) if values else None
        elif operation == "min":
            results[kpi_name] = round(min(values), 4) if values else None
        elif operation == "max":
            results[kpi_name] = round(max(values), 4) if values else None
        elif operation == "count":
            results[kpi_name] = len(data)
        else:
            results[kpi_name] = None

    return results


def generate_summary(data: list[dict[str, Any]]) -> str:
    """Generate a text summary of the dataset.

    Args:
        data: List of row dicts.

    Returns:
        Multi-line text summary string.
    """
    if not data:
        return "Empty dataset - no rows to summarize."

    all_columns = list(data[0].keys()) if data else []
    numeric_cols = _detect_numeric_columns(data)
    text_cols = [c for c in all_columns if c not in numeric_cols]

    lines: list[str] = [
        "Dataset Summary",
        f"  Rows: {len(data)}",
        f"  Columns: {len(all_columns)} ({len(numeric_cols)} numeric, {len(text_cols)} text)",
        "",
    ]

    if numeric_cols:
        lines.append("Numeric Columns:")
        for col in numeric_cols:
            values = _numeric_values(data, col)
            if values:
                lines.append(
                    f"  {col}: avg={statistics.mean(values):.2f}, "
                    f"min={min(values):.2f}, max={max(values):.2f}"
                )

    if text_cols:
        lines.append("")
        lines.append("Text Columns:")
        for col in text_cols:
            unique_vals = {str(row.get(col, "")) for row in data}
            lines.append(f"  {col}: {len(unique_vals)} unique values")

    return "\n".join(lines)


def health() -> dict[str, Any]:
    """Return health status for the BI analysis service.

    Returns:
        Dict with ``healthy`` boolean.
    """
    return {
        "healthy": True,
        "service": "bi",
        "description": "Local data analysis - always available",
    }
