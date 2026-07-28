"""Unit tests for `config/sync.py` -- the `copilot update` mirror-sync core
(V-3/V-4 onboarding blocker, initiative item #2a).

Scope under test: concrete refs (branch/tag/SHA) + the never-destroy gate +
human-readable per-layer results. Semver-RANGE ref *resolution* is out of
scope (#2b) -- only detect-and-skip is tested here.

All fixtures use local `file://` git repos under `tmp_path` -- no network,
and the real `~/.copilot/mirrors` / `~/.config/copilot/copilot.layers.yml`
are never touched (mirror roots are always explicit `tmp_path` locations).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from copilot_cli.config.layers import CliLayer
from copilot_cli.config.sync import is_semver_range, sync_all, sync_layer
from copilot_cli.services.git.client import GitClient

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _run_git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_remote(tmp_path: Path, name: str = "remote") -> Path:
    """A local, non-bare git repo usable as a `file://` clone/pull source."""
    remote = tmp_path / name
    remote.mkdir()
    _run_git("init", "-q", "-b", "main", cwd=remote)
    _run_git("config", "user.email", "test@example.com", cwd=remote)
    _run_git("config", "user.name", "Test", cwd=remote)
    (remote / "README.md").write_text("hello\n")
    _run_git("add", "README.md", cwd=remote)
    _run_git("commit", "-q", "-m", "init", cwd=remote)
    return remote


def _remote_url(remote: Path) -> str:
    return f"file://{remote}"


def _make_layer(
    tmp_path: Path,
    repo: str,
    ref: str = "main",
    layer_id: str = "foundation",
) -> CliLayer:
    return CliLayer(
        id=layer_id,
        role="foundation",
        rank=40,
        repo=repo,
        ref=ref,
        auth="anon",
        root=tmp_path / "mirrors" / "cli" / layer_id,
    )


def _snapshot(path: Path) -> dict[str, str]:
    """Content hash of every file under `path` (including `.git`), keyed by
    relative path -- a strong "zero writes" proof: any pull/fetch/merge
    plumbing write (not just working-tree files) would change this."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for f in path.rglob("*"):
        if f.is_file():
            out[str(f.relative_to(path))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


# ------------------------------------------------------------------ #
# is_semver_range
# ------------------------------------------------------------------ #


class TestIsSemverRange:
    def test_caret_prefix_is_a_range(self):
        assert is_semver_range("^1.4.5") is True

    def test_tilde_prefix_is_a_range(self):
        assert is_semver_range("~1.2.0") is True

    def test_comparator_expression_is_a_range(self):
        assert is_semver_range(">=1.0.0 <2.0.0") is True

    def test_or_expression_is_a_range(self):
        assert is_semver_range("1.x || 2.x") is True

    def test_branch_name_is_concrete(self):
        assert is_semver_range("main") is False

    def test_dotted_tag_is_concrete(self):
        assert is_semver_range("v1.x") is False

    def test_sha_is_concrete(self):
        assert is_semver_range("a" * 40) is False


# ------------------------------------------------------------------ #
# sync_layer -- never-destroy gate (V-3, must-have)
# ------------------------------------------------------------------ #


class TestNeverDestroyGate:
    def test_holds_dirty_mirror_and_makes_zero_writes(self, tmp_path):
        """A mirror with an uncommitted change is HELD: zero writes, and the
        result reports it held. Byte-identical before/after (including
        `.git` internals) is the proof no write occurred."""
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote))
        git = GitClient()

        cloned = sync_layer(layer, git=git)
        assert cloned.action == "cloned"

        # Dirty the mirror: one modified tracked file, one untracked file.
        (layer.root / "README.md").write_text("locally edited\n")
        (layer.root / "scratch.txt").write_text("uncommitted\n")

        before = _snapshot(layer.root)
        result = sync_layer(layer, git=git)
        after = _snapshot(layer.root)

        assert result.action == "held"
        assert "local changes" in result.detail
        assert before == after, "held layer must make zero writes"

    def test_holds_when_status_cannot_be_determined(self, tmp_path):
        """A mirror root that exists but isn't a git repo at all is a status
        the gate can't confirm clean -- fail-safe: hold, don't clone into
        it."""
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote))
        layer.root.mkdir(parents=True)
        (layer.root / "not-git.txt").write_text("pre-existing content\n")

        before = _snapshot(layer.root)
        result = sync_layer(layer, git=GitClient())
        after = _snapshot(layer.root)

        assert result.action == "held"
        assert before == after

    def test_holds_clean_mirror_with_unpushed_commits_that_would_conflict(self, tmp_path):
        """F5: a mirror whose working tree is CLEAN but that carries a local
        commit unknown to the remote (`ahead > 0`) must be HELD, even though
        `_is_dirty` alone would say it's clean. A read-only consumer mirror
        should never have local commits; if the gate didn't catch this, the
        subsequent pull would try to merge/rebase the local commit against a
        diverging remote commit, writing conflict markers into the tree and
        potentially leaving it mid-rebase before erroring -- a write into
        what could be a personal commit."""
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote))
        git = GitClient()

        cloned = sync_layer(layer, git=git)
        assert cloned.action == "cloned"

        # A stray local commit lands on the mirror (it should never happen on
        # a read-only mirror, but the gate must not assume that). Modify the
        # same line the remote is about to change, so a pull would conflict.
        (layer.root / "README.md").write_text("locally committed change\n")
        _run_git("config", "user.email", "test@example.com", cwd=layer.root)
        _run_git("config", "user.name", "Test", cwd=layer.root)
        _run_git("add", "README.md", cwd=layer.root)
        _run_git("commit", "-q", "-m", "stray local commit", cwd=layer.root)

        # The remote diverges: a new commit touching the same line.
        (remote / "README.md").write_text("remote diverged change\n")
        _run_git("add", "README.md", cwd=remote)
        _run_git("commit", "-q", "-m", "remote diverges", cwd=remote)

        before = _snapshot(layer.root)
        result = sync_layer(layer, git=git)
        after = _snapshot(layer.root)

        assert result.action == "held"
        assert "local commits present" in result.detail
        assert before == after, "held layer must make zero writes"

        # No conflict markers written into the tracked file.
        assert "<<<<<<<" not in (layer.root / "README.md").read_text(), (
            "must not have started a merge/rebase that wrote conflict markers"
        )

        # No mid-rebase/mid-merge state left behind in .git.
        git_dir = layer.root / ".git"
        assert not list(git_dir.glob("rebase-*")), "must not be left mid-rebase"
        assert not (git_dir / "MERGE_HEAD").exists(), "must not be left mid-merge"


# ------------------------------------------------------------------ #
# sync_layer -- clone
# ------------------------------------------------------------------ #


class TestClone:
    def test_clones_absent_mirror(self, tmp_path):
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote))

        assert not layer.root.exists()
        result = sync_layer(layer, git=GitClient())

        assert result.action == "cloned"
        assert (layer.root / ".git").exists()
        assert (layer.root / "README.md").read_text() == "hello\n"


# ------------------------------------------------------------------ #
# sync_layer -- pull
# ------------------------------------------------------------------ #


class TestPull:
    def test_pulls_clean_mirror_and_advances_it(self, tmp_path):
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote))
        git = GitClient()

        first = sync_layer(layer, git=git)
        assert first.action == "cloned"
        assert not (layer.root / "SECOND.md").exists()

        # New commit lands on the remote after the initial clone.
        (remote / "SECOND.md").write_text("second commit\n")
        _run_git("add", "SECOND.md", cwd=remote)
        _run_git("commit", "-q", "-m", "second", cwd=remote)

        second = sync_layer(layer, git=git)

        assert second.action == "pulled"
        assert (layer.root / "SECOND.md").read_text() == "second commit\n"


# ------------------------------------------------------------------ #
# sync_layer -- semver range: no matching tag
# ------------------------------------------------------------------ #
#
# Range *resolution* (caret/tilde -> specifier -> highest-matching-tag) is
# covered end-to-end in test_semver.py and TestRangeResolution below; this
# class only covers the "no tag satisfies the range" no-write outcome.


class TestRangeRefSkip:
    def test_range_ref_with_no_matching_tag_is_skipped_without_crash_or_write(self, tmp_path):
        """The remote here has zero tags at all, so `^1.4.5` can never
        resolve -- must be a clean `skipped`, never a crash, never a
        write."""
        remote = _init_remote(tmp_path)
        layer = _make_layer(tmp_path, _remote_url(remote), ref="^1.4.5")

        result = sync_layer(layer, git=GitClient())

        assert result.action == "skipped"
        assert "^1.4.5" in result.detail
        assert "no tag matches" in result.detail
        assert result.resolved_ref == ""
        assert not layer.root.exists(), "skipped layer must make zero writes"


# ------------------------------------------------------------------ #
# sync_layer -- semver range: resolves to a concrete tag (#2b)
# ------------------------------------------------------------------ #


def _tag_remote(tmp_path: Path, tags: list[str], name: str = "remote") -> Path:
    """A `file://`-clonable remote carrying one commit per tag, in order --
    each tag's commit is a real descendant of the previous one so a `pull`
    across tags is always a clean fast-forward."""
    remote = _init_remote(tmp_path, name=name)
    for tag in tags:
        (remote / f"{tag}.txt").write_text(f"{tag}\n")
        _run_git("add", f"{tag}.txt", cwd=remote)
        _run_git("commit", "-q", "-m", tag, cwd=remote)
        _run_git("tag", tag, cwd=remote)
    return remote


class TestRangeResolution:
    def test_caret_range_resolves_and_clones_the_highest_matching_tag(self, tmp_path):
        remote = _tag_remote(tmp_path, ["v1.4.5", "v1.5.0", "v1.5.9", "v2.0.0"])
        layer = _make_layer(tmp_path, _remote_url(remote), ref="^1.4.5")

        result = sync_layer(layer, git=GitClient())

        assert result.action == "cloned"
        assert result.resolved_ref == "v1.5.9"
        assert "v1.5.9" in result.detail
        assert "^1.4.5" in result.detail
        assert (layer.root / "v1.5.9.txt").exists()
        assert not (layer.root / "v2.0.0.txt").exists()

    def test_resolved_range_re_sync_pulls_the_new_highest_tag(self, tmp_path):
        """A second `copilot update` after a new tag lands on the remote
        advances the mirror to the new highest match -- the whole point of
        pinning to a range instead of one fixed tag."""
        remote = _tag_remote(tmp_path, ["v1.4.5", "v1.5.0"])
        layer = _make_layer(tmp_path, _remote_url(remote), ref="^1.4.5")
        git = GitClient()

        first = sync_layer(layer, git=git)
        assert first.action == "cloned"
        assert first.resolved_ref == "v1.5.0"

        (remote / "v1.5.9.txt").write_text("v1.5.9\n")
        _run_git("add", "v1.5.9.txt", cwd=remote)
        _run_git("commit", "-q", "-m", "v1.5.9", cwd=remote)
        _run_git("tag", "v1.5.9", cwd=remote)

        second = sync_layer(layer, git=git)

        assert second.action == "pulled"
        assert second.resolved_ref == "v1.5.9"
        assert (layer.root / "v1.5.9.txt").exists()

    def test_held_mirror_still_reports_the_resolved_tag(self, tmp_path):
        """The never-destroy gate holds a dirty resolved-range mirror same
        as a concrete-ref one -- `resolved_ref` is still reported for
        visibility even though nothing was written."""
        remote = _tag_remote(tmp_path, ["v1.4.5", "v1.5.0"])
        layer = _make_layer(tmp_path, _remote_url(remote), ref="^1.4.5")
        git = GitClient()

        cloned = sync_layer(layer, git=git)
        assert cloned.action == "cloned"

        (layer.root / "scratch.txt").write_text("uncommitted\n")

        result = sync_layer(layer, git=git)

        assert result.action == "held"
        assert result.resolved_ref == "v1.5.0"
        assert result.ref == "^1.4.5"


# ------------------------------------------------------------------ #
# sync_all
# ------------------------------------------------------------------ #


class TestSyncAll:
    def test_syncs_every_layer_in_the_chain(self, tmp_path):
        remote_a = _init_remote(tmp_path, name="remote-a")
        remote_b = _init_remote(tmp_path, name="remote-b")
        layer_a = _make_layer(tmp_path, _remote_url(remote_a), layer_id="org-acme")
        layer_b = _make_layer(tmp_path, _remote_url(remote_b), ref="^1.4.5", layer_id="foundation")

        results = sync_all(chain=[layer_a, layer_b], git=GitClient())

        by_id = {r.layer_id: r for r in results}
        assert by_id["org-acme"].action == "cloned"
        assert by_id["foundation"].action == "skipped"

    def test_empty_chain_returns_empty_results(self):
        assert sync_all(chain=[], git=GitClient()) == []
