"""Tests for the Git service -- client layer and CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from typer.testing import CliRunner

from copilot_cli.main import app
from copilot_cli.services.git.client import GitClient, health
from copilot_cli.shared.errors import CopilotError, NotFoundError

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_client(mock_settings):
    """Return a GitClient with deterministic commit-author settings.

    The autouse ``mock_settings`` fixture patches the module-level
    ``get_settings`` on ``copilot_cli.config.settings``, but GitClient
    imports it by name so we must also patch the local reference for the
    lifetime of each test. Construction itself deliberately does not read
    settings; only an implicit-author commit does.
    """
    with patch("copilot_cli.services.git.client.get_settings", return_value=mock_settings):
        yield GitClient()


def test_constructor_does_not_load_global_settings():
    """Read-only Git callers may construct a client without resolving any
    unrelated service credentials from the layered Settings object."""
    with patch(
        "copilot_cli.services.git.client.get_settings",
        side_effect=AssertionError("settings must stay lazy"),
    ):
        GitClient()


@pytest.fixture
def mock_repo():
    """A MagicMock that behaves like a git.Repo instance."""
    repo = MagicMock()
    repo.active_branch = MagicMock()
    repo.active_branch.__str__ = lambda self: "main"
    repo.active_branch.tracking_branch.return_value = None
    repo.index = MagicMock()
    repo.untracked_files = []
    return repo


# ------------------------------------------------------------------ #
# Client -- clone
# ------------------------------------------------------------------ #


class TestGitClientClone:
    """Tests for GitClient.clone()."""

    @patch("copilot_cli.services.git.client.Repo")
    def test_clone_success(self, mock_repo_cls, git_client, tmp_path):
        """clone() should call Repo.clone_from and return path + branch."""
        fake_repo = MagicMock()
        fake_repo.active_branch.__str__ = lambda self: "main"
        mock_repo_cls.clone_from.return_value = fake_repo

        dest = str(tmp_path / "my-repo")
        result = git_client.clone(url="https://github.com/x/y.git", path=dest)

        mock_repo_cls.clone_from.assert_called_once_with("https://github.com/x/y.git", dest)
        assert result["branch"] == "main"
        assert dest in result["path"] or "my-repo" in result["path"]

    @patch("copilot_cli.services.git.client.Repo")
    def test_clone_with_branch(self, mock_repo_cls, git_client, tmp_path):
        """clone() passes the branch kwarg when provided."""
        fake_repo = MagicMock()
        fake_repo.active_branch.__str__ = lambda self: "develop"
        mock_repo_cls.clone_from.return_value = fake_repo

        dest = str(tmp_path / "repo")
        result = git_client.clone(url="https://github.com/x/y.git", path=dest, branch="develop")

        mock_repo_cls.clone_from.assert_called_once_with(
            "https://github.com/x/y.git", dest, branch="develop"
        )
        assert result["branch"] == "develop"

    @patch("copilot_cli.services.git.client.Repo")
    def test_clone_failure_raises_copilot_error(self, mock_repo_cls, git_client):
        """clone() wraps exceptions in CopilotError."""
        mock_repo_cls.clone_from.side_effect = Exception("auth failed")

        with pytest.raises(CopilotError, match="Clone failed"):
            git_client.clone(url="https://bad.url", path="/tmp/nope")

    @patch("copilot_cli.services.git.client.Repo")
    def test_clone_of_exact_tag_reports_requested_ref_not_crash(
        self, mock_repo_cls, git_client, tmp_path
    ):
        """Cloning an exact tag/SHA (e.g. a semver-range ref resolved by
        `config/semver.py`, #2b) leaves HEAD detached -- a successful clone
        must never be turned into a `CopilotError` by that, and must report
        the ref that was actually requested."""
        fake_repo = MagicMock()
        type(fake_repo).active_branch = PropertyMock(
            side_effect=TypeError("HEAD is a detached symbolic reference")
        )
        fake_repo.head.commit.hexsha = "deadbeef"
        mock_repo_cls.clone_from.return_value = fake_repo

        dest = str(tmp_path / "repo")
        result = git_client.clone(url="https://github.com/x/y.git", path=dest, branch="v1.5.0")

        assert result["branch"] == "v1.5.0"


# ------------------------------------------------------------------ #
# Client -- pull
# ------------------------------------------------------------------ #


class TestGitClientPull:
    """Tests for GitClient.pull()."""

    @patch.object(GitClient, "_open_repo")
    def test_pull_success(self, mock_open, git_client):
        """pull() fetches from the remote and returns status."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"
        remote_obj = MagicMock()
        pull_info = MagicMock()
        pull_info.note = "fast-forward"
        remote_obj.pull.return_value = [pull_info]
        repo.remote.return_value = remote_obj
        mock_open.return_value = repo

        result = git_client.pull(path="/repo")

        assert result["remote"] == "origin"
        assert result["branch"] == "main"
        assert "fast-forward" in result["status"]

    @patch.object(GitClient, "_open_repo")
    def test_pull_custom_remote_and_branch(self, mock_open, git_client):
        """pull() respects explicit remote and branch arguments."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"
        remote_obj = MagicMock()
        remote_obj.pull.return_value = []
        repo.remote.return_value = remote_obj
        mock_open.return_value = repo

        result = git_client.pull(path="/repo", remote="upstream", branch="develop")

        repo.remote.assert_called_once_with("upstream")
        remote_obj.pull.assert_called_once_with("develop")
        assert result["remote"] == "upstream"
        assert result["branch"] == "develop"
        assert result["status"] == "up-to-date"

    @patch.object(GitClient, "_open_repo")
    def test_pull_failure_raises_copilot_error(self, mock_open, git_client):
        """pull() wraps exceptions in CopilotError."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"
        remote_obj = MagicMock()
        remote_obj.pull.side_effect = Exception("network error")
        repo.remote.return_value = remote_obj
        mock_open.return_value = repo

        with pytest.raises(CopilotError, match="Pull failed"):
            git_client.pull(path="/repo")


# ------------------------------------------------------------------ #
# Client -- status
# ------------------------------------------------------------------ #


class TestGitClientStatus:
    """Tests for GitClient.status()."""

    @patch.object(GitClient, "_open_repo")
    def test_status_clean_repo(self, mock_open, git_client):
        """status() returns empty lists for a clean repository."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"
        repo.active_branch.tracking_branch.return_value = None
        repo.index.diff.return_value = []
        repo.untracked_files = []
        mock_open.return_value = repo

        result = git_client.status(path="/repo")

        assert result["current"] == "main"
        assert result["tracking"] == ""
        assert result["ahead"] == 0
        assert result["behind"] == 0
        assert result["staged"] == []
        assert result["modified"] == []
        assert result["not_added"] == []
        assert result["deleted"] == []
        assert result["conflicted"] == []

    @patch.object(GitClient, "_open_repo")
    def test_status_with_changes(self, mock_open, git_client):
        """status() correctly classifies staged, modified, and untracked files."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"
        repo.active_branch.tracking_branch.return_value = None

        staged_item = MagicMock()
        staged_item.a_path = "staged.py"
        repo.index.diff.side_effect = lambda arg: [staged_item] if arg == "HEAD" else []
        repo.untracked_files = ["new_file.txt"]
        mock_open.return_value = repo

        result = git_client.status(path="/repo")

        assert result["staged"] == ["staged.py"]
        assert result["not_added"] == ["new_file.txt"]

    @patch.object(GitClient, "_open_repo")
    def test_status_with_tracking_branch(self, mock_open, git_client):
        """status() computes ahead/behind counts when tracking branch exists."""
        repo = MagicMock()
        repo.active_branch.__str__ = lambda self: "main"

        tracking = MagicMock()
        tracking.__str__ = lambda self: "origin/main"
        repo.active_branch.tracking_branch.return_value = tracking

        # 2 commits ahead, 1 behind
        repo.iter_commits.side_effect = lambda spec: (
            [MagicMock(), MagicMock()] if spec == "origin/main..main" else [MagicMock()]
        )
        repo.index.diff.return_value = []
        repo.untracked_files = []
        mock_open.return_value = repo

        result = git_client.status(path="/repo")

        assert result["tracking"] == "origin/main"
        assert result["ahead"] == 2
        assert result["behind"] == 1

    @patch.object(GitClient, "_open_repo")
    def test_status_detached_head_reports_commit_not_crash(self, mock_open, git_client):
        """A mirror pinned to an exact tag/SHA is a detached HEAD -- status()
        must report it (commit sha, no tracking/ahead/behind), never raise,
        so `config/sync.py`'s never-destroy gate doesn't permanently HOLD a
        legitimate resolved-range mirror as 'status unknown' (#2b)."""
        repo = MagicMock()
        type(repo).active_branch = PropertyMock(
            side_effect=TypeError("HEAD is a detached symbolic reference")
        )
        repo.head.commit.hexsha = "abc123def456"
        repo.index.diff.return_value = []
        repo.untracked_files = []
        mock_open.return_value = repo

        result = git_client.status(path="/repo")

        assert result["current"] == "abc123def456"
        assert result["tracking"] == ""
        assert result["ahead"] == 0
        assert result["behind"] == 0


# ------------------------------------------------------------------ #
# Client -- list_tags
# ------------------------------------------------------------------ #


class TestGitClientListTags:
    """Tests for GitClient.list_tags()."""

    @patch("copilot_cli.services.git.client.Git")
    def test_list_tags_parses_ls_remote_output(self, mock_git_cls, git_client):
        mock_git_cls.return_value.ls_remote.return_value = (
            "abc111\trefs/tags/v1.4.5\n"
            "abc222\trefs/tags/v1.5.0\n"
            "abc222deref\trefs/tags/v1.5.0^{}\n"  # annotated-tag pointer
            "abc333\trefs/heads/main\n"  # a branch -- must be ignored
        )

        tags = git_client.list_tags("https://github.com/x/y.git")

        assert tags == ["v1.4.5", "v1.5.0"]
        mock_git_cls.return_value.ls_remote.assert_called_once_with(
            "--tags", "https://github.com/x/y.git"
        )

    @patch("copilot_cli.services.git.client.Git")
    def test_list_tags_empty_output_returns_empty_list(self, mock_git_cls, git_client):
        mock_git_cls.return_value.ls_remote.return_value = ""

        assert git_client.list_tags("https://github.com/x/y.git") == []

    @patch("copilot_cli.services.git.client.Git")
    def test_list_tags_failure_raises_copilot_error(self, mock_git_cls, git_client):
        mock_git_cls.return_value.ls_remote.side_effect = Exception("network error")

        with pytest.raises(CopilotError, match="Listing tags failed"):
            git_client.list_tags("https://bad.url")

    def test_list_tags_against_a_real_file_remote(self, git_client, tmp_path):
        """Integration coverage against a real `file://` scratch remote --
        no network, no mocking of git itself."""
        import subprocess

        remote = tmp_path / "remote"
        remote.mkdir()

        def _git(*args):
            subprocess.run(["git", *args], cwd=remote, check=True, capture_output=True, text=True)

        _git("init", "-q", "-b", "main")
        _git("config", "user.email", "test@example.com")
        _git("config", "user.name", "Test")
        (remote / "f.txt").write_text("1\n")
        _git("add", "f.txt")
        _git("commit", "-q", "-m", "one")
        _git("tag", "v1.0.0")
        (remote / "f.txt").write_text("2\n")
        _git("add", "f.txt")
        _git("commit", "-q", "-m", "two")
        _git("tag", "v1.1.0")

        tags = git_client.list_tags(f"file://{remote}")

        assert set(tags) == {"v1.0.0", "v1.1.0"}


# ------------------------------------------------------------------ #
# Client -- add
# ------------------------------------------------------------------ #


class TestGitClientAdd:
    """Tests for GitClient.add()."""

    @patch.object(GitClient, "_open_repo")
    def test_add_success(self, mock_open, git_client):
        """add() stages the specified files."""
        repo = MagicMock()
        mock_open.return_value = repo

        result = git_client.add(path="/repo", files=["a.py", "b.py"])

        repo.index.add.assert_called_once_with(["a.py", "b.py"])
        assert result["staged"] == ["a.py", "b.py"]

    @patch.object(GitClient, "_open_repo")
    def test_add_failure_raises_copilot_error(self, mock_open, git_client):
        """add() wraps index errors in CopilotError."""
        repo = MagicMock()
        repo.index.add.side_effect = Exception("bad path")
        mock_open.return_value = repo

        with pytest.raises(CopilotError, match="Add failed"):
            git_client.add(path="/repo", files=["nonexistent.py"])


# ------------------------------------------------------------------ #
# Client -- commit
# ------------------------------------------------------------------ #


class TestGitClientCommit:
    """Tests for GitClient.commit()."""

    @patch.object(GitClient, "_open_repo")
    def test_commit_with_default_author(self, mock_open, git_client):
        """commit() uses settings-based author when none is supplied."""
        repo = MagicMock()
        commit_obj = MagicMock()
        commit_obj.hexsha = "abc123def456"
        repo.index.commit.return_value = commit_obj
        mock_open.return_value = repo

        result = git_client.commit(path="/repo", message="initial commit")

        assert result["sha"] == "abc123def456"
        assert result["message"] == "initial commit"
        # The author Actor is built from test settings
        call_kwargs = repo.index.commit.call_args
        actor = call_kwargs[1]["author"]
        assert actor.name == "test-user"
        assert actor.email == "test@example.com"

    @patch.object(GitClient, "_open_repo")
    def test_commit_with_explicit_author(self, mock_open, git_client):
        """commit() parses an explicit author without loading settings."""
        repo = MagicMock()
        commit_obj = MagicMock()
        commit_obj.hexsha = "deadbeef"
        repo.index.commit.return_value = commit_obj
        mock_open.return_value = repo

        with patch(
            "copilot_cli.services.git.client.get_settings",
            side_effect=AssertionError("explicit author must not load settings"),
        ):
            result = git_client.commit(
                path="/repo",
                message="feat: new thing",
                author="Alice <alice@example.com>",
            )

        call_kwargs = repo.index.commit.call_args
        actor = call_kwargs[1]["author"]
        assert actor.name == "Alice"
        assert actor.email == "alice@example.com"
        assert result["sha"] == "deadbeef"

    @patch.object(GitClient, "_open_repo")
    def test_commit_failure_raises_copilot_error(self, mock_open, git_client):
        """commit() wraps exceptions in CopilotError."""
        repo = MagicMock()
        repo.index.commit.side_effect = Exception("nothing to commit")
        mock_open.return_value = repo

        with pytest.raises(CopilotError, match="Commit failed"):
            git_client.commit(path="/repo", message="empty")


# ------------------------------------------------------------------ #
# Client -- _open_repo error paths
# ------------------------------------------------------------------ #


class TestOpenRepo:
    """Tests for GitClient._open_repo edge cases."""

    @patch("copilot_cli.services.git.client.Repo")
    def test_open_repo_nonexistent_path_raises_not_found(self, mock_repo_cls):
        """_open_repo raises NotFoundError for a missing filesystem path."""
        from git import NoSuchPathError

        mock_repo_cls.side_effect = NoSuchPathError("/no/such/path")

        with pytest.raises(NotFoundError, match="Path does not exist"):
            GitClient._open_repo("/no/such/path")

    @patch("copilot_cli.services.git.client.Repo")
    def test_open_repo_not_a_git_dir_raises_copilot_error(self, mock_repo_cls):
        """_open_repo raises CopilotError for a non-git directory."""
        from git import InvalidGitRepositoryError

        mock_repo_cls.side_effect = InvalidGitRepositoryError("/tmp")

        with pytest.raises(CopilotError, match="Not a git repository"):
            GitClient._open_repo("/tmp")


# ------------------------------------------------------------------ #
# CLI commands
# ------------------------------------------------------------------ #


class TestGitCLIClone:
    """CLI tests for `copilot git clone`."""

    def test_clone_success(self, runner):
        """git clone prints success message on happy path."""
        mock_client = MagicMock()
        mock_client.clone.return_value = {
            "path": "/tmp/repo",
            "branch": "main",
        }

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app,
                ["git", "clone", "--url", "https://github.com/x/y.git", "--path", "/tmp/repo"],
            )

        assert result.exit_code == 0
        assert "Cloned" in result.output

    def test_clone_error_returns_exit_code_1(self, runner):
        """git clone exits 1 when the client raises CopilotError."""
        mock_client = MagicMock()
        mock_client.clone.side_effect = CopilotError(
            "Clone failed: auth", service="git", hint="Check creds"
        )

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app,
                ["git", "clone", "--url", "https://bad.url", "--path", "/tmp/nope"],
            )

        assert result.exit_code == 1


class TestGitCLIStatus:
    """CLI tests for `copilot git status`."""

    def test_status_success(self, runner):
        """git status prints JSON output on happy path."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "current": "main",
            "tracking": "origin/main",
            "ahead": 0,
            "behind": 0,
            "staged": [],
            "modified": [],
            "not_added": [],
            "deleted": [],
            "conflicted": [],
        }

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["git", "status", "--path", "/tmp/repo"])

        assert result.exit_code == 0
        assert "main" in result.output

    def test_status_error_returns_exit_code_1(self, runner):
        """git status exits 1 on CopilotError."""
        mock_client = MagicMock()
        mock_client.status.side_effect = NotFoundError(
            "Path does not exist: /nope",
            service="git",
            hint="Check path.",
        )

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(app, ["git", "status", "--path", "/nope"])

        assert result.exit_code == 1


class TestGitCLICommit:
    """CLI tests for `copilot git commit`."""

    def test_commit_success(self, runner):
        """git commit prints abbreviated SHA on success."""
        mock_client = MagicMock()
        mock_client.commit.return_value = {
            "sha": "abc123def456",
            "message": "fix: typo",
            "author": "test-user <test@example.com>",
        }

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app,
                ["git", "commit", "--path", "/tmp/repo", "-m", "fix: typo"],
            )

        assert result.exit_code == 0
        assert "abc123de" in result.output

    def test_commit_error_returns_exit_code_1(self, runner):
        """git commit exits 1 when nothing staged."""
        mock_client = MagicMock()
        mock_client.commit.side_effect = CopilotError(
            "Commit failed: nothing staged", service="git"
        )

        with patch(
            "copilot_cli.services.git.commands._client",
            return_value=mock_client,
        ):
            result = runner.invoke(
                app,
                ["git", "commit", "--path", "/tmp/repo", "-m", "oops"],
            )

        assert result.exit_code == 1


# ------------------------------------------------------------------ #
# Module -- health
# ------------------------------------------------------------------ #


class TestHealth:
    """Tests for git.client.health() -- a local capability check."""

    @patch("copilot_cli.services.git.client.Git")
    def test_healthy_when_git_binary_available(self, mock_git_cls):
        """health() reports healthy with the git version when available."""
        mock_git_cls.return_value.version.return_value = "git version 2.43.0"

        result = health()

        assert result["healthy"] is True
        assert result["version"] == "git version 2.43.0"

    @patch("copilot_cli.services.git.client.Git")
    def test_unhealthy_when_git_binary_missing(self, mock_git_cls):
        """health() reports unhealthy when the git binary is unavailable."""
        mock_git_cls.return_value.version.side_effect = OSError("git not found")

        result = health()

        assert result["healthy"] is False
        assert "git not found" in result["error"]
