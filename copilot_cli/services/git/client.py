"""Git repository operations using GitPython."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import Actor, Git, InvalidGitRepositoryError, NoSuchPathError, Repo

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import CopilotError, NotFoundError


class GitClient:
    """Thin wrapper around GitPython for common repository operations."""

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
        except Exception as exc:
            raise CopilotError(
                f"Clone failed: {exc}",
                service="git",
                hint="Verify the URL and that you have access.",
            ) from exc

        try:
            active = str(repo.active_branch)
        except TypeError:
            # Checking out an exact tag/SHA (e.g. a resolved semver-range
            # ref -- see config/sync.py) leaves HEAD detached, which has no
            # branch by definition. Report what was actually checked out
            # rather than let a successful clone crash into "Clone failed".
            active = branch or repo.head.commit.hexsha

        return {
            "path": str(Path(path).resolve()),
            "branch": active,
        }

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

        try:
            current_branch = str(repo.active_branch)
            active_branch = repo.active_branch
        except TypeError:
            # Detached HEAD -- e.g. a mirror pinned to an exact tag/SHA (a
            # resolved semver-range ref, see config/sync.py) has no branch
            # by definition. Report the checked-out commit instead of
            # raising: config/sync.py's never-destroy gate treats a status()
            # failure as "can't confirm clean" and HOLDS the mirror forever,
            # which would be wrong here -- detached HEAD is the expected,
            # legitimate state for a tag-pinned mirror, not an error.
            current_branch = repo.head.commit.hexsha
            active_branch = None

        tracking = ""
        ahead = 0
        behind = 0

        tracking_branch = active_branch.tracking_branch() if active_branch is not None else None
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

    def list_tags(self, url_or_path: str) -> list[str]:
        """List tag names published by a repository, via ``git ls-remote
        --tags`` -- works against a remote URL *or* a local path (including
        an already-cloned mirror or a `file://` scratch remote), and never
        requires a local clone to exist first.

        Semver-RANGE resolution (`config/semver.resolve_range_to_tag`) needs
        a source repo's full tag set *before* any local mirror exists -- a
        range like ``^1.4.5`` must resolve to a concrete tag before the
        clone-or-pull decision can even be made -- so this always reads
        straight from the remote rather than requiring a prior clone.

        Args:
            url_or_path: Remote repository URL, or a local filesystem path
                (bare or working) git recognizes as a repo.

        Returns:
            Tag names only (e.g. ``v1.5.0``), de-duplicated, in the order
            ``git ls-remote`` reports them. Callers needing a specific
            ordering (e.g. "highest semver") must sort themselves.

        Raises:
            CopilotError: If listing fails (network error, invalid URL, no
                access, etc).
        """
        try:
            output = Git().ls_remote("--tags", url_or_path)
        except Exception as exc:
            raise CopilotError(
                f"Listing tags failed: {exc}",
                service="git",
                hint="Verify the URL and that you have access.",
            ) from exc

        tags: list[str] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            _, _, ref = line.partition("\t")
            if not ref.startswith("refs/tags/"):
                continue
            name = ref[len("refs/tags/") :]
            if name.endswith("^{}"):
                # Dereferenced pointer for an annotated tag -- same tag name
                # as the entry already seen (or about to be seen) for the
                # tag object itself; de-duplicated below either way.
                name = name[: -len("^{}")]
            if name not in tags:
                tags.append(name)
        return tags

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
                # Clone/pull/status/list-tags are configuration-mirror
                # operations and must not resolve every service credential
                # merely because they share this client. Only a commit needs
                # the configured fallback identity, so load Settings at the
                # point of use rather than in GitClient construction.
                settings = get_settings()
                actor = Actor(settings.git_user_name, settings.git_user_email)

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
