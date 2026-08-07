"""Tests for the business intelligence service -- client layer and CLI commands."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.bi.client import (
    _detect_numeric_columns,
    _load_data,
    _numeric_values,
    analyze_data,
    calculate_kpis,
    detect_patterns,
    generate_summary,
    health,
)
from copilot_cli.shared.errors import NotFoundError, ValidationError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_data():
    """Provide a reusable in-memory dataset for unit tests."""
    return [
        {"name": "Alice", "department": "Engineering", "salary": 95000, "age": 30},
        {"name": "Bob", "department": "Engineering", "salary": 105000, "age": 35},
        {"name": "Carol", "department": "Marketing", "salary": 80000, "age": 28},
        {"name": "Dave", "department": "Marketing", "salary": 85000, "age": 32},
        {"name": "Eve", "department": "Engineering", "salary": 110000, "age": 40},
    ]


@pytest.fixture
def json_file(tmp_path, sample_data):
    """Write sample data as a JSON file and return the path."""
    path = tmp_path / "data.json"
    path.write_text(json.dumps(sample_data), encoding="utf-8")
    return path


@pytest.fixture
def csv_file(tmp_path):
    """Write sample data as a CSV file and return the path."""
    path = tmp_path / "data.csv"
    path.write_text(
        "name,department,salary,age\n"
        "Alice,Engineering,95000,30\n"
        "Bob,Engineering,105000,35\n"
        "Carol,Marketing,80000,28\n"
        "Dave,Marketing,85000,32\n"
        "Eve,Engineering,110000,40\n",
        encoding="utf-8",
    )
    return path


# ------------------------------------------------------------------ #
# analyze_data
# ------------------------------------------------------------------ #


class TestAnalyzeData:
    """Tests for analyze_data()."""

    def test_with_numeric_data(self, sample_data):
        """analyze_data returns correct stats for detected numeric columns."""
        result = analyze_data(sample_data)

        assert result["rows"] == 5
        assert "salary" in result["columns"]
        assert "age" in result["columns"]

        salary = result["columns"]["salary"]
        assert salary["count"] == 5
        assert salary["sum"] == 475000
        assert salary["min"] == 80000
        assert salary["max"] == 110000
        assert salary["avg"] == 95000

    def test_with_specific_metrics(self, sample_data):
        """analyze_data respects an explicit metrics list."""
        result = analyze_data(sample_data, metrics=["salary"])

        assert "salary" in result["columns"]
        assert "age" not in result["columns"]

    def test_with_empty_data(self):
        """analyze_data returns zero rows and empty columns for empty input."""
        result = analyze_data([])
        assert result["rows"] == 0
        assert result["columns"] == {}

    def test_nonexistent_metric_column(self, sample_data):
        """Requesting a column that does not exist returns zeroed stats."""
        result = analyze_data(sample_data, metrics=["nonexistent"])

        col = result["columns"]["nonexistent"]
        assert col["count"] == 0
        assert col["sum"] == 0

    def test_single_row(self):
        """analyze_data handles a single-row dataset correctly."""
        data = [{"value": 42}]
        result = analyze_data(data, metrics=["value"])

        assert result["rows"] == 1
        col = result["columns"]["value"]
        assert col["count"] == 1
        assert col["sum"] == 42
        assert col["avg"] == 42
        assert col["min"] == 42
        assert col["max"] == 42


# ------------------------------------------------------------------ #
# detect_patterns
# ------------------------------------------------------------------ #


class TestDetectPatterns:
    """Tests for detect_patterns()."""

    def test_frequency_analysis(self, sample_data):
        """detect_patterns counts values and calculates percentages."""
        results = detect_patterns(sample_data, "department")

        by_value = {r["value"]: r for r in results}
        assert by_value["Engineering"]["count"] == 3
        assert by_value["Marketing"]["count"] == 2
        assert by_value["Engineering"]["percentage"] == 60.0
        assert by_value["Marketing"]["percentage"] == 40.0

    def test_sorted_by_count_descending(self, sample_data):
        """Results are sorted from most to least frequent."""
        results = detect_patterns(sample_data, "department")
        counts = [r["count"] for r in results]
        assert counts == sorted(counts, reverse=True)

    def test_missing_column_treated_as_empty(self, sample_data):
        """When a column does not exist in rows, the value is '(empty)'."""
        results = detect_patterns(sample_data, "missing_column")
        assert len(results) == 1
        assert results[0]["value"] == "(empty)"
        assert results[0]["count"] == 5

    def test_empty_data_returns_empty_list(self):
        """detect_patterns returns an empty list for empty input."""
        assert detect_patterns([], "any_column") == []


# ------------------------------------------------------------------ #
# calculate_kpis
# ------------------------------------------------------------------ #


class TestCalculateKpis:
    """Tests for calculate_kpis()."""

    def test_sum_operation(self, sample_data):
        """KPI with 'sum' operation returns the column total."""
        kpis = {"total_salary": {"column": "salary", "operation": "sum"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["total_salary"] == 475000

    def test_avg_operation(self, sample_data):
        """KPI with 'avg' operation returns the column mean."""
        kpis = {"avg_salary": {"column": "salary", "operation": "avg"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["avg_salary"] == 95000

    def test_min_operation(self, sample_data):
        """KPI with 'min' operation returns the column minimum."""
        kpis = {"min_age": {"column": "age", "operation": "min"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["min_age"] == 28

    def test_max_operation(self, sample_data):
        """KPI with 'max' operation returns the column maximum."""
        kpis = {"max_age": {"column": "age", "operation": "max"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["max_age"] == 40

    def test_count_operation(self, sample_data):
        """KPI with 'count' operation returns the total row count."""
        kpis = {"headcount": {"column": "name", "operation": "count"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["headcount"] == 5

    def test_multiple_kpis(self, sample_data):
        """calculate_kpis can compute multiple KPIs in a single call."""
        kpis = {
            "total": {"column": "salary", "operation": "sum"},
            "avg": {"column": "salary", "operation": "avg"},
            "count": {"column": "name", "operation": "count"},
        }
        result = calculate_kpis(sample_data, kpis)
        assert result["total"] == 475000
        assert result["avg"] == 95000
        assert result["count"] == 5

    def test_unknown_operation_returns_none(self, sample_data):
        """An unrecognised operation produces None."""
        kpis = {"mystery": {"column": "salary", "operation": "median"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["mystery"] is None

    def test_nonexistent_column_returns_none(self, sample_data):
        """A column that does not exist yields None for non-count operations."""
        kpis = {"ghost": {"column": "nonexistent", "operation": "sum"}}
        result = calculate_kpis(sample_data, kpis)
        assert result["ghost"] is None


# ------------------------------------------------------------------ #
# generate_summary
# ------------------------------------------------------------------ #


class TestGenerateSummary:
    """Tests for generate_summary()."""

    def test_produces_text_output(self, sample_data):
        """generate_summary returns a non-empty string."""
        text = generate_summary(sample_data)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_includes_row_count(self, sample_data):
        """The summary mentions the number of rows."""
        text = generate_summary(sample_data)
        assert "5" in text
        assert "Rows" in text

    def test_includes_numeric_column_stats(self, sample_data):
        """The summary includes stats for numeric columns."""
        text = generate_summary(sample_data)
        assert "salary" in text
        assert "avg=" in text

    def test_includes_text_column_info(self, sample_data):
        """The summary mentions unique values for text columns."""
        text = generate_summary(sample_data)
        assert "unique values" in text

    def test_empty_data(self):
        """generate_summary handles empty data gracefully."""
        text = generate_summary([])
        assert "Empty dataset" in text


# ------------------------------------------------------------------ #
# _load_data (internal helper)
# ------------------------------------------------------------------ #


class TestLoadData:
    """Tests for _load_data() internal helper."""

    def test_reads_json_list(self, json_file):
        """_load_data parses a JSON file containing a list of objects."""
        data = _load_data(str(json_file))
        assert len(data) == 5
        assert data[0]["name"] == "Alice"

    def test_reads_json_with_data_key(self, tmp_path):
        """_load_data parses a JSON file with a top-level 'data' key."""
        path = tmp_path / "wrapped.json"
        payload = {"data": [{"x": 1}, {"x": 2}]}
        path.write_text(json.dumps(payload), encoding="utf-8")

        data = _load_data(str(path))
        assert len(data) == 2
        assert data[0]["x"] == 1

    def test_reads_csv_file(self, csv_file):
        """_load_data parses a CSV file into a list of dicts."""
        data = _load_data(str(csv_file))
        assert len(data) == 5
        assert data[0]["name"] == "Alice"
        # CSV values are strings
        assert data[0]["salary"] == "95000"

    def test_missing_file_raises_not_found(self, tmp_path):
        """Raises NotFoundError for a nonexistent file."""
        missing = str(tmp_path / "missing.json")
        with pytest.raises(NotFoundError, match="File not found"):
            _load_data(missing)

    def test_unsupported_format_raises_validation_error(self, tmp_path):
        """Raises ValidationError for an unsupported file extension."""
        xml_file = tmp_path / "data.xml"
        xml_file.write_text("<data/>", encoding="utf-8")

        with pytest.raises(ValidationError, match="Unsupported file format"):
            _load_data(str(xml_file))

    def test_invalid_json_raises_validation_error(self, tmp_path):
        """Raises ValidationError for a file with malformed JSON."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(ValidationError, match="Invalid JSON"):
            _load_data(str(bad_json))

    def test_json_dict_without_data_key_raises_validation_error(self, tmp_path):
        """Raises ValidationError when JSON is a dict but lacks a 'data' key."""
        path = tmp_path / "wrong_shape.json"
        path.write_text(json.dumps({"items": [1, 2, 3]}), encoding="utf-8")

        with pytest.raises(ValidationError, match="list of objects"):
            _load_data(str(path))

    def test_directory_path_raises_validation_error(self, tmp_path):
        """Raises ValidationError when the path is a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            _load_data(str(tmp_path))


# ------------------------------------------------------------------ #
# _detect_numeric_columns (internal helper)
# ------------------------------------------------------------------ #


class TestDetectNumericColumns:
    """Tests for _detect_numeric_columns() internal helper."""

    def test_identifies_numeric_columns(self, sample_data):
        """Correctly identifies columns with predominantly numeric values."""
        cols = _detect_numeric_columns(sample_data)
        assert "salary" in cols
        assert "age" in cols
        assert "name" not in cols
        assert "department" not in cols

    def test_empty_data_returns_empty_list(self):
        """Returns an empty list for empty input."""
        assert _detect_numeric_columns([]) == []

    def test_mixed_column_below_threshold(self):
        """A column with fewer than 50% numeric values is not detected."""
        data = [
            {"val": "hello"},
            {"val": "world"},
            {"val": 42},
            {"val": "foo"},
        ]
        cols = _detect_numeric_columns(data)
        assert "val" not in cols

    def test_mixed_column_above_threshold(self):
        """A column with >= 50% numeric values is detected."""
        data = [
            {"val": 1},
            {"val": 2},
            {"val": "text"},
            {"val": 4},
        ]
        cols = _detect_numeric_columns(data)
        assert "val" in cols


# ------------------------------------------------------------------ #
# _numeric_values (internal helper)
# ------------------------------------------------------------------ #


class TestNumericValues:
    """Tests for _numeric_values() internal helper."""

    def test_extracts_numeric_values(self, sample_data):
        """Extracts all valid numeric values from a column."""
        values = _numeric_values(sample_data, "salary")
        assert values == [95000.0, 105000.0, 80000.0, 85000.0, 110000.0]

    def test_skips_none_values(self):
        """None values are skipped."""
        data = [{"x": 1}, {"x": None}, {"x": 3}]
        assert _numeric_values(data, "x") == [1.0, 3.0]

    def test_skips_non_numeric_values(self):
        """Non-numeric string values are skipped."""
        data = [{"x": 1}, {"x": "abc"}, {"x": 3}]
        assert _numeric_values(data, "x") == [1.0, 3.0]

    def test_missing_key_skipped(self):
        """Rows without the specified key are skipped."""
        data = [{"x": 1}, {"y": 2}, {"x": 3}]
        assert _numeric_values(data, "x") == [1.0, 3.0]

    def test_string_numeric_values_converted(self):
        """Numeric strings (e.g. from CSV) are converted to float."""
        data = [{"x": "10"}, {"x": "20.5"}]
        assert _numeric_values(data, "x") == [10.0, 20.5]


# ------------------------------------------------------------------ #
# health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for health()."""

    def test_returns_healthy(self):
        """health() always returns healthy=True."""
        result = health()
        assert result["healthy"] is True
        assert result["service"] == "bi"


# ------------------------------------------------------------------ #
# CLI commands
# ------------------------------------------------------------------ #


class TestBiCLI:
    """CLI integration tests for the 'bi' subcommand group."""

    def test_bi_help(self, runner):
        """'copilot bi --help' lists available subcommands."""
        result = runner.invoke(app, ["bi", "--help"])
        assert result.exit_code == 0
        assert "analyze" in result.output
        assert "patterns" in result.output
        assert "kpis" in result.output
        assert "summary" in result.output
        assert "health" in result.output

    def test_bi_analyze_json(self, runner, json_file):
        """'copilot bi analyze' succeeds with a JSON file."""
        result = runner.invoke(app, ["bi", "analyze", str(json_file)])
        assert result.exit_code == 0

    def test_bi_analyze_csv(self, runner, csv_file):
        """'copilot bi analyze' succeeds with a CSV file."""
        result = runner.invoke(app, ["bi", "analyze", str(csv_file)])
        assert result.exit_code == 0

    def test_bi_patterns(self, runner, json_file):
        """'copilot bi patterns' performs frequency analysis."""
        result = runner.invoke(app, ["bi", "patterns", str(json_file), "department"])
        assert result.exit_code == 0
        assert "Engineering" in result.output

    def test_bi_summary(self, runner, json_file):
        """'copilot bi summary' produces a text summary."""
        result = runner.invoke(app, ["bi", "summary", str(json_file)])
        assert result.exit_code == 0
        assert "Rows" in result.output

    def test_bi_health(self, runner):
        """'copilot bi health' reports healthy status."""
        result = runner.invoke(app, ["bi", "health"])
        assert result.exit_code == 0

    def test_bi_analyze_missing_file(self, runner, tmp_path):
        """'copilot bi analyze' exits 1 for a missing file."""
        result = runner.invoke(app, ["bi", "analyze", str(tmp_path / "nope.json")])
        assert result.exit_code == 1

    def test_bi_kpis(self, runner, json_file):
        """'copilot bi kpis' calculates KPIs from definitions JSON."""
        defs = json.dumps({"total": {"column": "salary", "operation": "sum"}})
        result = runner.invoke(app, ["bi", "kpis", str(json_file), "--definitions", defs])
        assert result.exit_code == 0

    def test_bi_kpis_invalid_json(self, runner, json_file):
        """'copilot bi kpis' exits 1 when --definitions is not valid JSON."""
        result = runner.invoke(app, ["bi", "kpis", str(json_file), "--definitions", "{bad json"])
        assert result.exit_code == 1
