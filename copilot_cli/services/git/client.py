"""Git repository operations using GitPython."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import Actor, Git, InvalidGitRepositoryError, NoSuchPathError, Repo

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError, NotFoundError


class GitClient:
    """Thin wrapper around GitPython for common repository operations."""

    def __init__(self) -> None:
        settings = get_settings()
        self._user_name: str = settings.git_user_name
        self._user_email: str = settings.git_user_email

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_repo(path: str) -> Repo:
        """Open an existing repository or raise a clear error."""
        try:
            return Repo(path)
        except NoSuchPathError as exc:
            raise NotFoundError(
                f"Path does not exist: {path}",
                service="git",
                hint="Check that the directory exists.",
            ) from exc
        except InvalidGitRepositoryError as exc:
            raise CopilotError(
                f"Not a git repository: {path}",
                service="git",
                hint="Run 'git init' first or provide a valid repo path.",
            ) from exc

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def clone(
        self,
        url: str,
        path: str,
        branch: str | None = None,
    ) -> dict:
        """Clone a remote repository.

        Args:
            url: Remote repository URL (HTTPS or SSH).
            path: Local filesystem path for the clone.
            branch: Optional branch name to check out after cloning.

        Returns:
            Dict with ``path`` and ``branch`` of the cloned repo.

        Raises:
            CopilotError: If the clone operation fails.
        """
        try:
            kwargs: dict = {}
            if branch:
                kwargs["branch"] = branch
            repo = Repo.clone_from(url, path, **kwargs)
            return {
                "path": str(Path(path).resolve()),
                "branch": str(repo.active_branch),
            }
        except Exception as exc:
            raise CopilotError(
                f"Clone failed: {exc}",
                service="git",
                hint="Verify the URL and that you have access.",
            ) from exc

    def pull(
        self,
        path: str,
        remote: str = "origin",
        branch: str | None = None,
    ) -> dict:
        """Pull changes from a remote.

        Args:
            path: Local repository path.
            remote: Remote name (default ``origin``).
            branch: Branch to pull; defaults to the current branch.

        Returns:
            Dict with ``remote``, ``branch``, and ``status``.

        Raises:
            CopilotError: If the pull operation fails.
        """
        repo = self._open_repo(path)
        try:
            remote_obj = repo.remote(remote)
            target_branch = branch or str(repo.active_branch)
            info_list = remote_obj.pull(target_branch)
            summary = ", ".join(str(i.note) for i in info_list if i.note)
            return {
                "remote": remote,
                "branch": target_branch,
                "status": summary or "up-to-date",
            }
        except Exception as exc:
            raise CopilotError(
                f"Pull failed: {exc}",
                service="git",
                hint="Ensure the remote and branch exist.",
            ) from exc

    def status(self, path: str) -> dict:
        """Return the working-tree status of a repository.

        Args:
            path: Local repository path.

        Returns:
            Dict containing ``current``, ``tracking``, ``ahead``,
            ``behind``, ``staged``, ``modified``, ``not_added``,
            ``deleted``, and ``conflicted`` lists/values.
        """
        repo = self._open_repo(path)

        current_branch = str(repo.active_branch)
        tracking = ""
        ahead = 0
        behind = 0

        tracking_branch = repo.active_branch.tracking_branch()
        if tracking_branch:
            tracking = str(tracking_branch)
            commits_ahead = list(repo.iter_commits(f"{tracking_branch}..{current_branch}"))
            commits_behind = list(repo.iter_commits(f"{current_branch}..{tracking_branch}"))
            ahead = len(commits_ahead)
            behind = len(commits_behind)

        diff_staged = repo.index.diff("HEAD")
        diff_unstaged = repo.index.diff(None)
        untracked = repo.untracked_files

        staged = [item.a_path for item in diff_staged]
        modified = [item.a_path for item in diff_unstaged if item.change_type == "M"]
        deleted = [item.a_path for item in diff_unstaged if item.change_type == "D"]
        conflicted = [item.a_path for item in diff_unstaged if item.change_type == "U"]

        return {
            "current": current_branch,
            "tracking": tracking,
            "ahead": ahead,
            "behind": behind,
            "staged": staged,
            "modified": modified,
            "not_added": list(untracked),
            "deleted": deleted,
            "conflicted": conflicted,
        }

    def add(self, path: str, files: list[str]) -> dict:
        """Stage files for commit.

        Args:
            path: Local repository path.
            files: List of file paths (relative to repo root) to stage.

        Returns:
            Dict with the list of ``staged`` files.

        Raises:
            CopilotError: If staging fails.
        """
        repo = self._open_repo(path)
        try:
            repo.index.add(files)
            return {"staged": files}
        except Exception as exc:
            raise CopilotError(
                f"Add failed: {exc}",
                service="git",
                hint="Check that the file paths are correct.",
            ) from exc

    def commit(
        self,
        path: str,
        message: str,
        author: str | None = None,
    ) -> dict:
        """Commit staged changes.

        Args:
            path: Local repository path.
            message: Commit message.
            author: Optional ``Name <email>`` string. Falls back to settings.

        Returns:
            Dict with ``sha``, ``message``, and ``author``.

        Raises:
            CopilotError: If the commit fails.
        """
        repo = self._open_repo(path)
        try:
            if author:
                # Parse "Name <email>" format
                name, _, email = author.partition("<")
                name = name.strip()
                email = email.rstrip(">").strip()
                actor = Actor(name, email)
            else:
                actor = Actor(self._user_name, self._user_email)

            commit_obj = repo.index.commit(message, author=actor)
            return {
                "sha": str(commit_obj.hexsha),
                "message": message,
                "author": str(actor),
            }
        except Exception as exc:
            raise CopilotError(
                f"Commit failed: {exc}",
                service="git",
                hint="Ensure there are staged changes to commit.",
            ) from exc


def health() -> dict[str, Any]:
    """Return health status for the git service.

    A local capability check: confirms a ``git`` executable is present and
    runnable, independent of any specific repository.

    Returns:
        Dict with keys: healthy, version.
    """
    try:
        version = Git().version()
        return {"healthy": True, "version": version}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}
