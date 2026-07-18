"""Unit tests for `config/secrets_ladder.py` -- the fail-closed
credential-resolution ladder `SecretRefSource` calls to resolve a
`requires_secret: <NAME>` reference. Verifies red-team §6.3: a miss at
every rung never silently returns an empty/None value."""

from __future__ import annotations

import subprocess

import pytest

from copilot_cli.config.secrets_ladder import (
    SecretResolutionError,
    _rung_keychain,
    _rung_managed_store,
    _rung_secure_paste,
    _SecretRungUnavailable,
    resolve_secret,
)


class TestManagedStoreRungStub:
    def test_falls_through_cleanly_when_no_client_exists(self):
        with pytest.raises(_SecretRungUnavailable):
            _rung_managed_store("SOME_NAME", chain=[])


class TestKeychainRung:
    def test_non_darwin_platform_is_unavailable(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "linux")
        with pytest.raises(_SecretRungUnavailable, match="macOS-only"):
            _rung_keychain("SOME_NAME", chain=[])

    def test_missing_keychain_entry_is_unavailable(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "darwin")

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=44, stdout="", stderr="not found")

        monkeypatch.setattr("copilot_cli.config.secrets_ladder.subprocess.run", fake_run)
        with pytest.raises(_SecretRungUnavailable, match="no keychain entry"):
            _rung_keychain("SOME_NAME", chain=[])

    def test_found_keychain_entry_returns_value(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "darwin")

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="s3cr3t-value\n", stderr="")

        monkeypatch.setattr("copilot_cli.config.secrets_ladder.subprocess.run", fake_run)
        assert _rung_keychain("SOME_NAME", chain=[]) == "s3cr3t-value"

    def test_subprocess_failure_is_unavailable_not_raised(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "darwin")

        def fake_run(*args, **kwargs):
            raise OSError("security binary not found")

        monkeypatch.setattr("copilot_cli.config.secrets_ladder.subprocess.run", fake_run)
        with pytest.raises(_SecretRungUnavailable):
            _rung_keychain("SOME_NAME", chain=[])


class _NonInteractiveStdin:
    def isatty(self) -> bool:
        return False


class TestSecurePasteRung:
    def test_non_interactive_session_is_unavailable(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.stdin", _NonInteractiveStdin())
        with pytest.raises(_SecretRungUnavailable, match="not an interactive terminal"):
            _rung_secure_paste("SOME_NAME", chain=[])


class TestResolveSecretFailsClosed:
    def test_every_rung_missing_raises_secret_resolution_error_never_empty(self, monkeypatch):
        """The end-to-end fail-closed guarantee: with every rung stubbed
        or unavailable (the realistic CI/no-keychain/non-interactive
        state), resolving a declared secret raises -- it never returns ""
        or None."""
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "linux")
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.stdin", _NonInteractiveStdin())

        with pytest.raises(SecretResolutionError) as exc_info:
            resolve_secret("MISSING_SECRET_NAME", chain=[])
        assert exc_info.value.name == "MISSING_SECRET_NAME"
        assert "Signed-out" in str(exc_info.value)

    def test_keychain_hit_short_circuits_the_ladder(self, monkeypatch):
        monkeypatch.setattr("copilot_cli.config.secrets_ladder.sys.platform", "darwin")

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=0, stdout="from-keychain\n", stderr="")

        monkeypatch.setattr("copilot_cli.config.secrets_ladder.subprocess.run", fake_run)
        assert resolve_secret("SOME_NAME", chain=[]) == "from-keychain"
