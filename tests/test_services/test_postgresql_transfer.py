"""Tests for the pg_dump / pg_restore transfer helpers.

External processes are mocked — these tests verify command construction, error
handling, and dump-format detection. End-to-end runs against a real container
are out of scope here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.services.postgresql.transfer import (
    SSHTarget,
    detect_dump_format,
    local_pg_restore,
    remote_pg_dump,
)
from copilot_cli.shared.errors import CopilotError

SSH = SSHTarget(user="root", host="10.0.0.5", port=22, key_file="/keys/id")


# ---------------------------------------------------------------------------
# SSHTarget.args
# ---------------------------------------------------------------------------


class TestSSHTargetArgs:
    def test_includes_key_file_when_set(self):
        args = SSH.args()
        assert "-i" in args
        assert "/keys/id" in args
        assert "root@10.0.0.5" in args

    def test_omits_key_when_unset(self):
        args = SSHTarget(user="u", host="h", port=2222).args()
        assert "-i" not in args
        assert "u@h" in args
        assert "2222" in args

    def test_has_batch_and_strict_settings(self):
        args = SSH.args()
        assert "BatchMode=yes" in args
        assert "StrictHostKeyChecking=accept-new" in args


# ---------------------------------------------------------------------------
# remote_pg_dump command construction
# ---------------------------------------------------------------------------


def _mock_run_ok(*args, **kwargs):
    """Side-effect for subprocess.run: write a fake dump and exit 0."""
    stdout = kwargs.get("stdout")
    if stdout is not None and hasattr(stdout, "write"):
        stdout.write(b"PGDMP\x00\x00fake-archive-bytes")
    return subprocess.CompletedProcess(args=args[0], returncode=0, stderr=b"")


def _mock_run_fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=args[0], returncode=1, stderr=b"pg_dump: ERROR: nope")


class TestRemotePgDump:
    def test_writes_file_and_returns_metadata(self, tmp_path: Path):
        out = tmp_path / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_ok) as run:
            result = remote_pg_dump(
                ssh=SSH, container="abc", db_user="u", db_name="d", output_path=out
            )
            cmd = run.call_args[0][0]
            assert cmd[0] == "ssh"
            assert "root@10.0.0.5" in cmd
            # Last positional arg is the remote command string.
            assert cmd[-1].startswith("docker exec abc ")
            assert "pg_dump" in cmd[-1]
            assert "-Fc" in cmd[-1]
            assert "-U u" in cmd[-1]
            assert "-d d" in cmd[-1]

        assert out.exists()
        assert out.read_bytes().startswith(b"PGDMP")
        assert result["path"] == str(out)
        assert result["format"] == "custom"
        assert result["size_bytes"] > 0

    def test_plain_format_uses_Fp(self, tmp_path: Path):
        out = tmp_path / "x.sql"
        with patch("subprocess.run", side_effect=_mock_run_ok) as run:
            remote_pg_dump(
                ssh=SSH,
                container="abc",
                db_user="u",
                db_name="d",
                output_path=out,
                fmt="plain",
            )
            assert "-Fp" in run.call_args[0][0][-1]

    def test_schema_only_flag(self, tmp_path: Path):
        out = tmp_path / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_ok) as run:
            remote_pg_dump(
                ssh=SSH,
                container="abc",
                db_user="u",
                db_name="d",
                output_path=out,
                schema_only=True,
            )
            assert "--schema-only" in run.call_args[0][0][-1]

    def test_table_filter(self, tmp_path: Path):
        out = tmp_path / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_ok) as run:
            remote_pg_dump(
                ssh=SSH,
                container="abc",
                db_user="u",
                db_name="d",
                output_path=out,
                table="users",
            )
            assert "-t users" in run.call_args[0][0][-1]

    def test_schema_only_and_data_only_are_mutually_exclusive(self, tmp_path: Path):
        with pytest.raises(CopilotError, match="mutually exclusive"):
            remote_pg_dump(
                ssh=SSH,
                container="abc",
                db_user="u",
                db_name="d",
                output_path=tmp_path / "x.dump",
                schema_only=True,
                data_only=True,
            )

    def test_invalid_format_raises(self, tmp_path: Path):
        with pytest.raises(CopilotError, match="Invalid dump format"):
            remote_pg_dump(
                ssh=SSH,
                container="abc",
                db_user="u",
                db_name="d",
                output_path=tmp_path / "x.dump",
                fmt="parquet",
            )

    def test_nonzero_exit_raises_and_removes_empty_file(self, tmp_path: Path):
        out = tmp_path / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_fail):
            with pytest.raises(CopilotError, match="pg_dump failed"):
                remote_pg_dump(
                    ssh=SSH,
                    container="abc",
                    db_user="u",
                    db_name="d",
                    output_path=out,
                )
        assert not out.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        out = tmp_path / "nested" / "dirs" / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_ok):
            remote_pg_dump(ssh=SSH, container="abc", db_user="u", db_name="d", output_path=out)
        assert out.exists()

    def test_quotes_unsafe_container_and_db_args(self, tmp_path: Path):
        """Ensure shell-quoting prevents injection if a name contains spaces."""
        out = tmp_path / "x.dump"
        with patch("subprocess.run", side_effect=_mock_run_ok) as run:
            remote_pg_dump(
                ssh=SSH,
                container="abc;rm -rf /",
                db_user="u",
                db_name="d",
                output_path=out,
            )
            remote = run.call_args[0][0][-1]
            # The dangerous string survives only inside single quotes.
            assert "'abc;rm -rf /'" in remote


# ---------------------------------------------------------------------------
# detect_dump_format
# ---------------------------------------------------------------------------


class TestDetectDumpFormat:
    def test_custom_format_signature(self, tmp_path: Path):
        p = tmp_path / "x.dump"
        p.write_bytes(b"PGDMP\x01\x14\x00")
        assert detect_dump_format(p) == "custom"

    def test_plain_sql(self, tmp_path: Path):
        p = tmp_path / "x.sql"
        p.write_bytes(b"-- PostgreSQL database dump\n")
        assert detect_dump_format(p) == "plain"


# ---------------------------------------------------------------------------
# local_pg_restore
# ---------------------------------------------------------------------------


class TestLocalPgRestore:
    def test_custom_format_uses_pg_restore(self, tmp_path: Path):
        p = tmp_path / "x.dump"
        p.write_bytes(b"PGDMP\x01\x14")
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stderr=b""),
        ) as run:
            result = local_pg_restore(dump_path=p, target_url="postgres://u@localhost/x")
            cmd = run.call_args[0][0]
            assert cmd[0] == "pg_restore"
            assert "--no-owner" in cmd
            assert "-d" in cmd
            assert "postgres://u@localhost/x" in cmd
            assert str(p) in cmd
        assert result["tool"] == "pg_restore"

    def test_clean_flag_appends_clean_args(self, tmp_path: Path):
        p = tmp_path / "x.dump"
        p.write_bytes(b"PGDMP\x01\x14")
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stderr=b""),
        ) as run:
            local_pg_restore(dump_path=p, target_url="postgres://u@localhost/x", clean=True)
            cmd = run.call_args[0][0]
            assert "--clean" in cmd
            assert "--if-exists" in cmd

    def test_plain_format_uses_psql(self, tmp_path: Path):
        p = tmp_path / "x.sql"
        p.write_bytes(b"-- plain sql\nSELECT 1;\n")
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stderr=b""),
        ) as run:
            result = local_pg_restore(dump_path=p, target_url="postgres://u@localhost/x")
            cmd = run.call_args[0][0]
            assert cmd[0] == "psql"
            assert "ON_ERROR_STOP=1" in cmd
            assert "-f" in cmd
        assert result["tool"] == "psql"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(CopilotError, match="not found"):
            local_pg_restore(
                dump_path=tmp_path / "nope.dump",
                target_url="postgres://u@localhost/x",
            )

    def test_nonzero_exit_raises(self, tmp_path: Path):
        p = tmp_path / "x.dump"
        p.write_bytes(b"PGDMP\x01\x14")
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stderr=b"pg_restore: ERROR: nope"
            ),
        ):
            with pytest.raises(CopilotError, match="restore failed"):
                local_pg_restore(dump_path=p, target_url="postgres://u@localhost/x")
