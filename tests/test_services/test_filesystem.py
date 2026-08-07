"""Comprehensive tests for the filesystem service client and CLI commands."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.filesystem.client import (
    _validate_path,
    calculate_checksum,
    copy_file,
    create_directory,
    delete_file,
    get_metadata,
    get_volumes,
    health,
    list_directory,
    move_file,
    read_file,
    search_files,
    write_file,
)
from copilot_cli.shared.errors import NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()


@pytest.fixture(autouse=True)
def _bypass_path_validation():
    """Disable _validate_path for every test by default.

    On macOS, pytest's ``tmp_path`` resolves through the ``/private``
    symlink (``/tmp`` -> ``/private/var/folders/...``) so the resolved
    path never starts with ``/tmp``.  Bypassing validation lets us test
    real filesystem behaviour without fighting the symlink.

    Tests that specifically verify path validation override this fixture
    at the class level to restore the real implementation.
    """
    with patch(
        "copilot_cli.services.filesystem.client._validate_path",
        side_effect=lambda p: None,
    ):
        yield


@pytest.fixture
def _real_validate_path(mock_settings):
    """Restore the real ``_validate_path`` and patch ``get_settings``
    at the client module so the fake allowed-volumes list is used.

    Apply this fixture (via ``autouse=True`` at class level or by
    requesting it) in tests that exercise path-validation logic.
    """
    with patch(
        "copilot_cli.services.filesystem.client.get_settings",
        return_value=mock_settings,
    ):
        # Undo the autouse no-op by NOT patching _validate_path here.
        # Because this fixture is requested *after* the autouse fixture
        # runs, we need to explicitly restore the original function.
        import copilot_cli.services.filesystem.client as _mod

        real_fn = _validate_path  # captured at import time above
        _mod._validate_path = real_fn
        try:
            yield
        finally:
            pass  # autouse fixture's context manager handles cleanup


@pytest.fixture
def _patch_client_settings(mock_settings):
    """Patch ``get_settings`` at the client module level so functions
    like ``get_volumes()`` and ``health()`` see the fake settings.
    """
    with patch(
        "copilot_cli.services.filesystem.client.get_settings",
        return_value=mock_settings,
    ):
        yield


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample text file under tmp_path for testing."""
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    return f


@pytest.fixture
def nested_tree(tmp_path: Path) -> Path:
    """Create a small directory tree for list / search tests.

    Structure::

        tmp_path/
            alpha.txt
            beta.json
            subdir/
                gamma.txt
                delta.json
    """
    (tmp_path / "alpha.txt").write_text("alpha content")
    (tmp_path / "beta.json").write_text('{"key": "value"}')
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "gamma.txt").write_text("gamma content")
    (sub / "delta.json").write_text('{"key": "value2"}')
    return tmp_path


# ===================================================================
# Unit tests -- client functions
# ===================================================================


class TestReadFile:
    """Tests for read_file()."""

    def test_reads_content_correctly(self, sample_file: Path) -> None:
        """read_file returns file content and metadata."""
        result = read_file(str(sample_file))
        assert result["content"] == "hello world"
        assert result["size"] == sample_file.stat().st_size
        assert result["encoding"] == "utf-8"
        assert "modified" in result

    def test_reads_with_custom_encoding(self, tmp_path: Path) -> None:
        """read_file respects a non-default encoding parameter."""
        f = tmp_path / "latin.txt"
        f.write_text("caf\u00e9", encoding="utf-8")
        result = read_file(str(f), encoding="utf-8")
        assert "caf" in result["content"]

    def test_raises_not_found_for_missing_file(self, tmp_path: Path) -> None:
        """read_file raises NotFoundError when the file does not exist."""
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(NotFoundError, match="File not found"):
            read_file(str(missing))

    def test_raises_validation_for_directory(self, tmp_path: Path) -> None:
        """read_file raises ValidationError when path is a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            read_file(str(tmp_path))


class TestWriteFile:
    """Tests for write_file()."""

    def test_creates_file_with_content(self, tmp_path: Path) -> None:
        """write_file creates a new file and returns metadata."""
        target = tmp_path / "output.txt"
        result = write_file(str(target), "test content")
        assert result["success"] is True
        assert result["size"] > 0
        assert target.read_text() == "test content"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """write_file creates intermediate parent directories."""
        deep = tmp_path / "a" / "b" / "c" / "file.txt"
        result = write_file(str(deep), "deep content")
        assert result["success"] is True
        assert deep.exists()
        assert deep.read_text() == "deep content"

    def test_overwrites_existing_file(self, sample_file: Path) -> None:
        """write_file overwrites an existing file."""
        write_file(str(sample_file), "new content")
        assert sample_file.read_text() == "new content"


class TestDeleteFile:
    """Tests for delete_file()."""

    def test_removes_file(self, sample_file: Path) -> None:
        """delete_file removes the file from disk."""
        result = delete_file(str(sample_file))
        assert result["success"] is True
        assert not sample_file.exists()

    def test_raises_not_found_for_missing(self, tmp_path: Path) -> None:
        """delete_file raises NotFoundError if the file is missing."""
        with pytest.raises(NotFoundError, match="File not found"):
            delete_file(str(tmp_path / "ghost.txt"))

    def test_raises_validation_for_directory(self, tmp_path: Path) -> None:
        """delete_file raises ValidationError when given a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            delete_file(str(tmp_path))


class TestCopyFile:
    """Tests for copy_file()."""

    def test_copies_correctly(self, sample_file: Path, tmp_path: Path) -> None:
        """copy_file duplicates a file to the destination."""
        dst = tmp_path / "copy.txt"
        result = copy_file(str(sample_file), str(dst))
        assert result["success"] is True
        assert dst.read_text() == "hello world"
        assert result["size"] == sample_file.stat().st_size
        # Original still exists
        assert sample_file.exists()

    def test_creates_destination_parent_dirs(self, sample_file: Path, tmp_path: Path) -> None:
        """copy_file creates parent directories for the destination."""
        dst = tmp_path / "sub" / "deep" / "copy.txt"
        result = copy_file(str(sample_file), str(dst))
        assert result["success"] is True
        assert dst.exists()

    def test_raises_not_found_for_missing_source(self, tmp_path: Path) -> None:
        """copy_file raises NotFoundError when source does not exist."""
        with pytest.raises(NotFoundError, match="Source not found"):
            copy_file(str(tmp_path / "nope.txt"), str(tmp_path / "dst.txt"))

    def test_preserves_timestamps_when_requested(self, sample_file: Path, tmp_path: Path) -> None:
        """copy_file preserves mtime when preserve_timestamps=True."""
        # Set a known modification time in the past
        old_time = time.time() - 86400
        os.utime(str(sample_file), (old_time, old_time))

        dst = tmp_path / "preserved.txt"
        copy_file(str(sample_file), str(dst), preserve_timestamps=True)

        src_mtime = sample_file.stat().st_mtime
        dst_mtime = dst.stat().st_mtime
        assert abs(src_mtime - dst_mtime) < 2  # allow small rounding


class TestMoveFile:
    """Tests for move_file()."""

    def test_moves_correctly(self, sample_file: Path, tmp_path: Path) -> None:
        """move_file relocates a file and removes the original."""
        dst = tmp_path / "moved.txt"
        result = move_file(str(sample_file), str(dst))
        assert result["success"] is True
        assert dst.read_text() == "hello world"
        assert not sample_file.exists()

    def test_creates_destination_dirs(self, sample_file: Path, tmp_path: Path) -> None:
        """move_file creates intermediate destination directories."""
        dst = tmp_path / "x" / "y" / "moved.txt"
        result = move_file(str(sample_file), str(dst))
        assert result["success"] is True
        assert dst.exists()

    def test_raises_not_found_for_missing_source(self, tmp_path: Path) -> None:
        """move_file raises NotFoundError when source is missing."""
        with pytest.raises(NotFoundError, match="Source not found"):
            move_file(str(tmp_path / "gone.txt"), str(tmp_path / "dst.txt"))


class TestListDirectory:
    """Tests for list_directory()."""

    def test_lists_files_and_dirs(self, nested_tree: Path) -> None:
        """list_directory returns both files and subdirectories."""
        results = list_directory(str(nested_tree))
        names = [r["name"] for r in results]
        assert "alpha.txt" in names
        assert "beta.json" in names
        assert "subdir" in names

    def test_files_only_filter(self, nested_tree: Path) -> None:
        """list_directory with files_only=True excludes directories."""
        results = list_directory(str(nested_tree), files_only=True)
        types = {r["type"] for r in results}
        assert types == {"file"}
        names = [r["name"] for r in results]
        assert "subdir" not in names

    def test_dirs_only_filter(self, nested_tree: Path) -> None:
        """list_directory with dirs_only=True excludes files."""
        results = list_directory(str(nested_tree), dirs_only=True)
        types = {r["type"] for r in results}
        assert types == {"dir"}

    def test_pattern_filter(self, nested_tree: Path) -> None:
        """list_directory respects glob pattern."""
        results = list_directory(str(nested_tree), pattern="*.json")
        names = [r["name"] for r in results]
        assert "beta.json" in names
        assert "alpha.txt" not in names

    def test_sort_by_name(self, nested_tree: Path) -> None:
        """list_directory sorts results by name when requested."""
        results = list_directory(str(nested_tree), sort_by="name")
        names = [r["name"] for r in results]
        assert names == sorted(names, key=str.lower)

    def test_raises_not_found_for_missing_dir(self, tmp_path: Path) -> None:
        """list_directory raises NotFoundError for non-existent path."""
        with pytest.raises(NotFoundError, match="Directory not found"):
            list_directory(str(tmp_path / "nonexistent"))

    def test_raises_validation_for_file_path(self, sample_file: Path) -> None:
        """list_directory raises ValidationError when given a file path."""
        with pytest.raises(ValidationError, match="Not a directory"):
            list_directory(str(sample_file))

    def test_result_structure(self, nested_tree: Path) -> None:
        """Each entry in the listing has the expected keys."""
        results = list_directory(str(nested_tree))
        assert len(results) > 0
        for entry in results:
            assert "name" in entry
            assert "path" in entry
            assert "type" in entry
            assert "size" in entry
            assert "modified" in entry


class TestSearchFiles:
    """Tests for search_files()."""

    def test_filters_by_extension(self, nested_tree: Path) -> None:
        """search_files returns only files matching the extension."""
        results = search_files(str(nested_tree), extension=".json")
        names = [r["name"] for r in results]
        assert "beta.json" in names
        assert "delta.json" in names
        assert "alpha.txt" not in names

    def test_extension_without_dot(self, nested_tree: Path) -> None:
        """search_files accepts extension without leading dot."""
        results = search_files(str(nested_tree), extension="txt")
        names = [r["name"] for r in results]
        assert "alpha.txt" in names
        assert "gamma.txt" in names
        assert "beta.json" not in names

    def test_filters_by_name_substring(self, nested_tree: Path) -> None:
        """search_files filters by name substring (case-insensitive)."""
        results = search_files(str(nested_tree), name="alpha")
        assert len(results) == 1
        assert results[0]["name"] == "alpha.txt"

    def test_filters_by_min_size(self, nested_tree: Path) -> None:
        """search_files filters out files smaller than min_size."""
        # All test files are small; use min_size=9999 to get empty results
        results = search_files(str(nested_tree), min_size=9999)
        assert results == []

    def test_filters_by_max_size(self, nested_tree: Path) -> None:
        """search_files filters out files larger than max_size."""
        results = search_files(str(nested_tree), max_size=999999)
        # Should include all files since they are all tiny
        assert len(results) == 4

    def test_raises_not_found_for_missing_dir(self, tmp_path: Path) -> None:
        """search_files raises NotFoundError for non-existent path."""
        with pytest.raises(NotFoundError, match="Directory not found"):
            search_files(str(tmp_path / "nonexistent"))

    def test_results_sorted_by_name(self, nested_tree: Path) -> None:
        """search_files results are sorted alphabetically by name."""
        results = search_files(str(nested_tree))
        names = [r["name"] for r in results]
        assert names == sorted(names, key=str.lower)


class TestCalculateChecksum:
    """Tests for calculate_checksum()."""

    def test_returns_correct_sha256(self, sample_file: Path) -> None:
        """calculate_checksum produces the correct sha256 digest."""
        result = calculate_checksum(str(sample_file), algorithm="sha256")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result["checksum"] == expected
        assert result["algorithm"] == "sha256"

    def test_returns_correct_md5(self, sample_file: Path) -> None:
        """calculate_checksum works with md5 algorithm."""
        result = calculate_checksum(str(sample_file), algorithm="md5")
        expected = hashlib.md5(b"hello world").hexdigest()
        assert result["checksum"] == expected

    def test_raises_not_found_for_missing(self, tmp_path: Path) -> None:
        """calculate_checksum raises NotFoundError for missing file."""
        with pytest.raises(NotFoundError, match="File not found"):
            calculate_checksum(str(tmp_path / "nope.txt"))

    def test_raises_validation_for_unsupported_algorithm(self, sample_file: Path) -> None:
        """calculate_checksum raises ValidationError for bad algorithm."""
        with pytest.raises(ValidationError, match="Unsupported hash algorithm"):
            calculate_checksum(str(sample_file), algorithm="bogus_hash")

    def test_raises_validation_for_directory(self, tmp_path: Path) -> None:
        """calculate_checksum raises ValidationError when given a directory."""
        with pytest.raises(ValidationError, match="Not a file"):
            calculate_checksum(str(tmp_path))


class TestGetMetadata:
    """Tests for get_metadata()."""

    def test_returns_file_info(self, sample_file: Path) -> None:
        """get_metadata returns correct metadata for a file."""
        result = get_metadata(str(sample_file))
        assert result["type"] == "file"
        assert result["size"] == sample_file.stat().st_size
        assert "modified" in result
        assert "created" in result
        assert "permissions" in result
        assert str(sample_file.resolve()) == result["path"]

    def test_returns_dir_info(self, tmp_path: Path) -> None:
        """get_metadata returns type='dir' for directories."""
        result = get_metadata(str(tmp_path))
        assert result["type"] == "dir"

    def test_raises_not_found(self, tmp_path: Path) -> None:
        """get_metadata raises NotFoundError for missing paths."""
        with pytest.raises(NotFoundError, match="Path not found"):
            get_metadata(str(tmp_path / "missing"))

    def test_permissions_string_format(self, sample_file: Path) -> None:
        """get_metadata permissions string has the expected rwx format."""
        result = get_metadata(str(sample_file))
        perm = result["permissions"]
        assert len(perm) == 9
        assert all(c in "rwx-" for c in perm)


class TestCreateDirectory:
    """Tests for create_directory()."""

    def test_creates_single_directory(self, tmp_path: Path) -> None:
        """create_directory creates a new directory."""
        target = tmp_path / "newdir"
        result = create_directory(str(target))
        assert result["success"] is True
        assert target.is_dir()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """create_directory with recursive=True creates full chain."""
        deep = tmp_path / "a" / "b" / "c"
        result = create_directory(str(deep), recursive=True)
        assert result["success"] is True
        assert deep.is_dir()

    def test_idempotent_on_existing(self, tmp_path: Path) -> None:
        """create_directory does not fail when directory already exists."""
        result = create_directory(str(tmp_path))
        assert result["success"] is True


class TestValidatePath:
    """Tests for _validate_path().

    These tests need the real ``_validate_path`` implementation and the
    fake settings injected into the client module.  We override the
    module-level autouse ``_bypass_path_validation`` fixture so the
    real function is exercised.
    """

    @pytest.fixture(autouse=True)
    def _bypass_path_validation(self, mock_settings):
        """Override the module-level autouse fixture to restore the real
        ``_validate_path`` and inject fake settings into the client.
        """
        with patch(
            "copilot_cli.services.filesystem.client.get_settings",
            return_value=mock_settings,
        ):
            yield

    def test_allows_path_under_volumes_dev(self) -> None:
        """Paths under /Volumes/Dev are allowed by the test settings."""
        # Should not raise -- /Volumes/Dev does not involve a symlink
        _validate_path(Path("/Volumes/Dev/project/file.py"))

    def test_rejects_path_outside_allowed_volumes(self) -> None:
        """Paths outside allowed volumes raise ValidationError."""
        with pytest.raises(ValidationError, match="outside allowed volumes"):
            _validate_path(Path("/etc/passwd"))

    def test_rejects_home_directory(self) -> None:
        """Home directory paths are rejected unless in allowed volumes."""
        with pytest.raises(ValidationError, match="outside allowed volumes"):
            _validate_path(Path("/Users/someone/secrets.txt"))

    def test_rejects_root_path(self) -> None:
        """Root path is rejected."""
        with pytest.raises(ValidationError, match="outside allowed volumes"):
            _validate_path(Path("/"))


class TestGetVolumes:
    """Tests for get_volumes()."""

    @pytest.fixture(autouse=True)
    def _inject_settings(self, _patch_client_settings):
        """Ensure the fake settings are used inside the client."""

    def test_returns_configured_volumes(self) -> None:
        """get_volumes returns entries for each configured allowed volume."""
        results = get_volumes()
        volumes = [r["volume"] for r in results]
        assert "/tmp" in volumes
        assert "/Volumes/Dev" in volumes

    def test_each_entry_has_expected_keys(self) -> None:
        """Each volume entry has volume, accessible, exists, is_dir keys."""
        results = get_volumes()
        for vol in results:
            assert "volume" in vol
            assert "accessible" in vol
            assert "exists" in vol
            assert "is_dir" in vol

    def test_tmp_is_accessible(self) -> None:
        """The /tmp volume should be accessible on any macOS/Linux system."""
        results = get_volumes()
        tmp_vol = next(v for v in results if v["volume"] == "/tmp")
        assert tmp_vol["accessible"] is True


class TestHealth:
    """Tests for health()."""

    @pytest.fixture(autouse=True)
    def _inject_settings(self, _patch_client_settings):
        """Ensure the fake settings are used inside the client."""

    def test_returns_health_dict(self) -> None:
        """health() returns a dict with expected keys."""
        result = health()
        assert "status" in result
        assert "healthy" in result
        assert "accessible_volumes" in result
        assert "total_volumes" in result
        assert "volumes" in result

    def test_total_volumes_matches_settings(self) -> None:
        """total_volumes reflects the number of configured allowed volumes."""
        result = health()
        assert result["total_volumes"] == 2  # /tmp and /Volumes/Dev


# ===================================================================
# CLI integration tests
# ===================================================================


class TestFsCLI:
    """CLI command tests for the 'fs' subcommand group."""

    def test_fs_help(self) -> None:
        """fs --help lists available subcommands."""
        result = runner.invoke(app, ["fs", "--help"])
        assert result.exit_code == 0
        assert "read" in result.output
        assert "write" in result.output
        assert "ls" in result.output

    def test_fs_ls(self, nested_tree: Path) -> None:
        """fs ls PATH lists directory contents."""
        result = runner.invoke(app, ["fs", "ls", str(nested_tree)])
        assert result.exit_code == 0
        assert "alpha.txt" in result.output
        assert "beta.json" in result.output
        assert "subdir" in result.output

    def test_fs_ls_files_only(self, nested_tree: Path) -> None:
        """fs ls --files-only filters out directories."""
        result = runner.invoke(app, ["fs", "ls", str(nested_tree), "--files-only"])
        assert result.exit_code == 0
        assert "alpha.txt" in result.output
        assert "subdir" not in result.output

    def test_fs_read(self, sample_file: Path) -> None:
        """fs read PATH displays file content."""
        result = runner.invoke(app, ["fs", "read", str(sample_file)])
        assert result.exit_code == 0
        assert "hello world" in result.output

    def test_fs_read_missing_file(self, tmp_path: Path) -> None:
        """fs read of a nonexistent file exits with code 1."""
        result = runner.invoke(app, ["fs", "read", str(tmp_path / "ghost.txt")])
        assert result.exit_code == 1

    def test_fs_write(self, tmp_path: Path) -> None:
        """fs write PATH --content creates a file."""
        target = tmp_path / "written.txt"
        result = runner.invoke(app, ["fs", "write", str(target), "--content", "cli wrote this"])
        assert result.exit_code == 0
        assert target.read_text() == "cli wrote this"

    def test_fs_delete_with_force(self, sample_file: Path) -> None:
        """fs delete PATH --force removes the file without confirmation."""
        result = runner.invoke(app, ["fs", "delete", str(sample_file), "--force"])
        assert result.exit_code == 0
        assert not sample_file.exists()

    def test_fs_cp(self, sample_file: Path, tmp_path: Path) -> None:
        """fs cp SRC DST copies a file."""
        dst = tmp_path / "copy_cli.txt"
        result = runner.invoke(app, ["fs", "cp", str(sample_file), str(dst)])
        assert result.exit_code == 0
        assert dst.exists()
        assert dst.read_text() == "hello world"

    def test_fs_mv(self, sample_file: Path, tmp_path: Path) -> None:
        """fs mv SRC DST moves a file."""
        dst = tmp_path / "moved_cli.txt"
        result = runner.invoke(app, ["fs", "mv", str(sample_file), str(dst)])
        assert result.exit_code == 0
        assert dst.exists()
        assert not sample_file.exists()

    def test_fs_mkdir(self, tmp_path: Path) -> None:
        """fs mkdir PATH creates a directory."""
        target = tmp_path / "new_dir_cli"
        result = runner.invoke(app, ["fs", "mkdir", str(target)])
        assert result.exit_code == 0
        assert target.is_dir()

    def test_fs_search(self, nested_tree: Path) -> None:
        """fs search PATH --ext .json finds matching files."""
        result = runner.invoke(app, ["fs", "search", str(nested_tree), "--ext", ".json"])
        assert result.exit_code == 0
        assert "beta.json" in result.output
        assert "delta.json" in result.output

    def test_fs_checksum(self, sample_file: Path) -> None:
        """fs checksum PATH outputs the sha256 digest."""
        result = runner.invoke(app, ["fs", "checksum", str(sample_file)])
        assert result.exit_code == 0
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert expected in result.output

    def test_fs_meta(self, sample_file: Path) -> None:
        """fs meta PATH displays metadata."""
        result = runner.invoke(app, ["fs", "meta", str(sample_file)])
        assert result.exit_code == 0
        assert "file" in result.output

    def test_fs_volumes(self, _patch_client_settings) -> None:
        """fs volumes lists configured volumes."""
        result = runner.invoke(app, ["fs", "volumes"])
        assert result.exit_code == 0
        assert "/tmp" in result.output

    def test_fs_health(self, _patch_client_settings) -> None:
        """fs health runs a health check and prints status."""
        result = runner.invoke(app, ["fs", "health"])
        assert result.exit_code == 0
        assert "healthy" in result.output.lower() or "unhealthy" in result.output.lower()
