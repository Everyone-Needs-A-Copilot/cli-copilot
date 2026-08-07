"""Tests for the document management service -- client layer and CLI commands."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.document.client import (
    create_document,
    delete_document,
    get_document,
    health,
    list_collections,
    search_documents,
    update_document,
)
from copilot_cli.shared.errors import NotFoundError, ValidationError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def docs_tree(tmp_path):
    """Create a small directory tree with text files for testing.

    Structure::

        tmp_path/
            notes/
                meeting.md   -> "Meeting notes for Monday\nAction items pending"
                draft.txt    -> "Draft proposal v2\nBudget review required"
            reports/
                q1.md        -> "Q1 revenue report\nTotal revenue: 50000"
                q2.md        -> "Q2 revenue report\nTotal revenue: 72000"
            readme.md        -> "Project readme\nSetup instructions"
    """
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "meeting.md").write_text(
        "Meeting notes for Monday\nAction items pending", encoding="utf-8"
    )
    (notes / "draft.txt").write_text("Draft proposal v2\nBudget review required", encoding="utf-8")

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "q1.md").write_text("Q1 revenue report\nTotal revenue: 50000", encoding="utf-8")
    (reports / "q2.md").write_text("Q2 revenue report\nTotal revenue: 72000", encoding="utf-8")

    (tmp_path / "readme.md").write_text("Project readme\nSetup instructions", encoding="utf-8")

    return tmp_path


# ------------------------------------------------------------------ #
# search_documents
# ------------------------------------------------------------------ #


class TestSearchDocuments:
    """Tests for search_documents()."""

    def test_finds_matching_lines(self, docs_tree):
        """search_documents returns all lines containing the query string."""
        results = search_documents(str(docs_tree), "revenue")

        assert len(results) >= 3
        for hit in results:
            assert "revenue" in hit["line"].lower()
            assert "path" in hit
            assert "filename" in hit
            assert "line_number" in hit

    def test_case_insensitive_search(self, docs_tree):
        """Searches are case-insensitive."""
        results_lower = search_documents(str(docs_tree), "meeting")
        results_upper = search_documents(str(docs_tree), "MEETING")
        assert len(results_lower) == len(results_upper)
        assert len(results_lower) > 0

    def test_filters_by_extension(self, docs_tree):
        """Extension filter restricts results to matching file types."""
        md_results = search_documents(str(docs_tree), "revenue", extension="md")
        txt_results = search_documents(str(docs_tree), "revenue", extension="txt")

        assert len(md_results) >= 2
        for hit in md_results:
            assert hit["filename"].endswith(".md")
        # "revenue" does not appear in the .txt file
        assert len(txt_results) == 0

    def test_extension_with_leading_dot(self, docs_tree):
        """Extension parameter works both with and without a leading dot."""
        results_dot = search_documents(str(docs_tree), "revenue", extension=".md")
        results_no_dot = search_documents(str(docs_tree), "revenue", extension="md")
        assert len(results_dot) == len(results_no_dot)

    def test_no_matches_returns_empty_list(self, docs_tree):
        """Returns an empty list when no lines match the query."""
        results = search_documents(str(docs_tree), "xyznonexistent")
        assert results == []

    def test_nonexistent_directory_raises_not_found(self, tmp_path):
        """Raises NotFoundError for a directory that does not exist."""
        bad_path = str(tmp_path / "does_not_exist")
        with pytest.raises(NotFoundError, match="Directory not found"):
            search_documents(bad_path, "anything")


# ------------------------------------------------------------------ #
# get_document
# ------------------------------------------------------------------ #


class TestGetDocument:
    """Tests for get_document()."""

    def test_reads_file_content(self, docs_tree):
        """get_document returns the full text content and metadata."""
        result = get_document(str(docs_tree / "readme.md"))

        assert result["content"] == "Project readme\nSetup instructions"
        assert result["size"] > 0
        assert "modified" in result
        assert "path" in result

    def test_returns_correct_size(self, docs_tree):
        """The size field matches the actual file size on disk."""
        target = docs_tree / "readme.md"
        result = get_document(str(target))
        assert result["size"] == target.stat().st_size

    def test_missing_file_raises_not_found(self, tmp_path):
        """Raises NotFoundError when the file does not exist."""
        missing = str(tmp_path / "ghost.md")
        with pytest.raises(NotFoundError, match="Document not found"):
            get_document(missing)

    def test_directory_path_raises_validation_error(self, docs_tree):
        """Raises ValidationError when the path is a directory, not a file."""
        with pytest.raises(ValidationError, match="Not a file"):
            get_document(str(docs_tree / "notes"))


# ------------------------------------------------------------------ #
# create_document
# ------------------------------------------------------------------ #


class TestCreateDocument:
    """Tests for create_document()."""

    def test_creates_new_file(self, tmp_path):
        """create_document writes content and returns success metadata."""
        new_file = str(tmp_path / "new_doc.md")
        result = create_document(new_file, "Hello, world!")

        assert result["success"] is True
        assert result["size"] > 0
        assert (tmp_path / "new_doc.md").read_text(encoding="utf-8") == "Hello, world!"

    def test_creates_parent_directories(self, tmp_path):
        """create_document creates intermediate directories when needed."""
        nested = str(tmp_path / "a" / "b" / "c" / "doc.txt")
        result = create_document(nested, "nested content")

        assert result["success"] is True
        assert (tmp_path / "a" / "b" / "c" / "doc.txt").exists()

    def test_existing_file_raises_validation_error(self, docs_tree):
        """Raises ValidationError if the file already exists."""
        existing = str(docs_tree / "readme.md")
        with pytest.raises(ValidationError, match="already exists"):
            create_document(existing, "overwrite attempt")

    def test_empty_content_is_allowed(self, tmp_path):
        """Creating a document with empty string content succeeds."""
        empty_file = str(tmp_path / "empty.md")
        result = create_document(empty_file, "")

        assert result["success"] is True
        assert result["size"] == 0


# ------------------------------------------------------------------ #
# update_document
# ------------------------------------------------------------------ #


class TestUpdateDocument:
    """Tests for update_document()."""

    def test_updates_existing_file(self, docs_tree):
        """update_document replaces the content of an existing file."""
        target = str(docs_tree / "readme.md")
        result = update_document(target, "Updated content here")

        assert result["success"] is True
        assert (docs_tree / "readme.md").read_text(encoding="utf-8") == "Updated content here"

    def test_missing_file_raises_not_found(self, tmp_path):
        """Raises NotFoundError for a file that does not exist."""
        missing = str(tmp_path / "no_such_file.md")
        with pytest.raises(NotFoundError, match="Document not found"):
            update_document(missing, "content")

    def test_directory_path_raises_validation_error(self, docs_tree):
        """Raises ValidationError when the path is a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            update_document(str(docs_tree / "notes"), "content")

    def test_size_reflects_new_content(self, docs_tree):
        """The returned size matches the length of the new content."""
        target = str(docs_tree / "readme.md")
        new_content = "short"
        result = update_document(target, new_content)

        assert result["size"] == len(new_content.encode("utf-8"))


# ------------------------------------------------------------------ #
# delete_document
# ------------------------------------------------------------------ #


class TestDeleteDocument:
    """Tests for delete_document()."""

    def test_removes_file(self, docs_tree):
        """delete_document removes the file from the filesystem."""
        target = docs_tree / "readme.md"
        assert target.exists()

        result = delete_document(str(target))

        assert result["success"] is True
        assert not target.exists()

    def test_missing_file_raises_not_found(self, tmp_path):
        """Raises NotFoundError for a file that does not exist."""
        missing = str(tmp_path / "phantom.md")
        with pytest.raises(NotFoundError, match="Document not found"):
            delete_document(missing)

    def test_directory_path_raises_validation_error(self, docs_tree):
        """Raises ValidationError when the path is a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            delete_document(str(docs_tree / "notes"))


# ------------------------------------------------------------------ #
# list_collections
# ------------------------------------------------------------------ #


class TestListCollections:
    """Tests for list_collections()."""

    def test_lists_subdirectories(self, docs_tree):
        """list_collections returns one entry per non-hidden subdirectory."""
        results = list_collections(str(docs_tree))

        names = [c["name"] for c in results]
        assert "notes" in names
        assert "reports" in names
        # Top-level files (readme.md) are not included as collections
        assert "readme.md" not in names

    def test_document_count_and_size(self, docs_tree):
        """Each collection reports correct document_count and total_size."""
        results = list_collections(str(docs_tree))
        by_name = {c["name"]: c for c in results}

        # notes/ has meeting.md and draft.txt
        assert by_name["notes"]["document_count"] == 2
        assert by_name["notes"]["total_size"] > 0

        # reports/ has q1.md and q2.md
        assert by_name["reports"]["document_count"] == 2
        assert by_name["reports"]["total_size"] > 0

    def test_hidden_directories_excluded(self, docs_tree):
        """Directories starting with '.' are excluded."""
        (docs_tree / ".hidden").mkdir()
        (docs_tree / ".hidden" / "secret.txt").write_text("secret", encoding="utf-8")

        results = list_collections(str(docs_tree))
        names = [c["name"] for c in results]
        assert ".hidden" not in names

    def test_nonexistent_base_raises_not_found(self, tmp_path):
        """Raises NotFoundError if the base_path does not exist."""
        bad = str(tmp_path / "nonexistent")
        with pytest.raises(NotFoundError, match="Directory not found"):
            list_collections(bad)

    def test_empty_directory_returns_empty_list(self, tmp_path):
        """An empty directory returns an empty collection list."""
        results = list_collections(str(tmp_path))
        assert results == []


# ------------------------------------------------------------------ #
# health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for health()."""

    def test_returns_healthy(self):
        """health() returns healthy=True when the cwd is readable."""
        result = health()
        assert result["healthy"] is True
        assert "cwd" in result
        assert result["readable"] is True


# ------------------------------------------------------------------ #
# CLI commands
# ------------------------------------------------------------------ #


class TestDocsCLI:
    """CLI integration tests for the 'docs' subcommand group."""

    def test_docs_help(self, runner):
        """'copilot docs --help' lists available subcommands."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "get" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output
        assert "collections" in result.output
        assert "stats" in result.output
        assert "health" in result.output

    def test_docs_search_success(self, runner, docs_tree):
        """'copilot docs search' returns matching results."""
        result = runner.invoke(app, ["docs", "search", str(docs_tree), "revenue"])
        assert result.exit_code == 0
        assert "revenue" in result.output.lower()

    def test_docs_search_no_matches(self, runner, docs_tree):
        """'copilot docs search' with no matches still exits 0."""
        result = runner.invoke(app, ["docs", "search", str(docs_tree), "zzzznotfound"])
        assert result.exit_code == 0

    def test_docs_get_success(self, runner, docs_tree):
        """'copilot docs get' prints document content."""
        result = runner.invoke(app, ["docs", "get", str(docs_tree / "readme.md")])
        assert result.exit_code == 0
        assert "Project readme" in result.output

    def test_docs_get_missing_file(self, runner, tmp_path):
        """'copilot docs get' exits 1 for a missing file."""
        result = runner.invoke(app, ["docs", "get", str(tmp_path / "nope.md")])
        assert result.exit_code == 1

    def test_docs_health_success(self, runner):
        """'copilot docs health' reports healthy status."""
        result = runner.invoke(app, ["docs", "health"])
        assert result.exit_code == 0
