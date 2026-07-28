"""Mirror-sync logic for `copilot update` (V-3/V-4 onboarding blocker).

Per resolved `component: cli` layer (`config.layers.resolve_cli_layer_chain`),
clone-or-pull that layer's local read-only mirror (`layer.root`, conventionally
``~/.copilot/mirrors/cli/<id>``) from its declared `source.repo`/`source.ref`.

Concrete refs (branch / exact tag / SHA) sync directly. A semver-RANGE ref
(e.g. the live foundation layer's ``^1.4.5``) is resolved to the HIGHEST
matching tag first (`config.semver.resolve_range_to_tag`, item #2b), then
synced via that same concrete-ref path -- if no tag satisfies the range (or
the repo's tags can't even be listed), the layer is reported ``skipped``/
``error`` and, per the never-destroy gate below, nothing is written.

Hard invariants (control-tower invariants #2/#3, "never-destroy" + "pull-only
downward"):

- A mirror whose git working tree is DIRTY (staged, modified, untracked, or
  conflicted changes -- see `_is_dirty`) is HELD: zero writes, reported, and
  skipped. Only a clean OR absent mirror may be touched.
- A mirror that is working-tree CLEAN but carries unpushed local commits
  (`status["ahead"] > 0`) is likewise HELD. A read-only consumer mirror
  should never have local commits; if one does, it must be treated as a
  personal tree and never pulled, even though `_is_dirty` alone would not
  catch it -- pulling could start a merge/rebase against a diverged remote
  and leave the tree mid-conflict (F5). `behind` alone never holds: that is
  the ordinary "remote has new commits" case pull exists to fast-forward.
- This gate is fail-SAFE: if a mirror's git status can't be determined at all
  (e.g. `GitClient.status()` raises because the path exists but is not a git
  repository), it is treated as dirty and HELD -- never written to on the
  strength of an assumption.
- Only ever clones or pulls (`GitClient.clone` / `GitClient.pull`) -- never
  pushes, never touches anything outside a layer's own mirror root.
"""

from __future__ import annotations

from dataclasses import dataclass

from copilot_cli.config.layers import CliLayer, resolve_cli_layer_chain
from copilot_cli.config.semver import resolve_range_to_tag
from copilot_cli.services.git.client import GitClient

# Per the ratified detection rule: a `source.ref` is a semver RANGE (not a
# concrete branch/tag/SHA) if it starts with `^`/`~`, or contains a range
# operator. Deliberately narrow -- concrete refs like `main`, `v1.x`, or a
# 40-char SHA must never be misdetected as a range.
_RANGE_PREFIXES = ("^", "~")
_RANGE_OPERATORS = ("<", ">", "||")

# `GitClient.status()` fields that indicate the working tree is dirty.
# `tracking`/`current` are purely descriptive. `behind` alone is never grounds
# to withhold a pull -- that's the ordinary case pull is meant to handle.
# `ahead` is handled separately (see `_has_unpushed_commits`): a clean tree
# with unpushed local commits still holds, per the never-destroy gate.
_DIRTY_STATUS_FIELDS = ("staged", "modified", "not_added", "deleted", "conflicted")


def is_semver_range(ref: str) -> bool:
    """True if `ref` looks like a semver RANGE rather than a concrete
    branch/tag/SHA -- e.g. ``^1.4.5``, ``~1.2.0``, ``>=1.0.0 <2.0.0``.

    Detection only -- `resolve_range_to_tag` does the actual range ->
    concrete-tag resolution `sync_layer` wires in below.
    """
    stripped = ref.strip()
    if stripped.startswith(_RANGE_PREFIXES):
        return True
    return any(op in stripped for op in _RANGE_OPERATORS)


def _is_dirty(status: dict) -> bool:
    """True if a `GitClient.status()` result reports any local change."""
    return any(status.get(field) for field in _DIRTY_STATUS_FIELDS)


def _has_unpushed_commits(status: dict) -> bool:
    """True if a `GitClient.status()` result reports the branch is ahead of
    its tracking branch (`ahead` is an int count -- see `GitClient.status`).

    A working-tree-clean mirror can still carry unpushed local commits (e.g.
    a stray manual commit on a supposedly read-only mirror). A read-only
    consumer mirror should never have these; if it does, treat it as a
    personal tree and hold rather than pull (F5)."""
    return status.get("ahead", 0) > 0


@dataclass(frozen=True)
class LayerSyncResult:
    """The outcome of syncing one layer's mirror."""

    layer_id: str
    action: str  # "cloned" | "pulled" | "held" | "skipped" | "error"
    detail: str = ""
    role: str = ""
    ref: str = ""  # the layer's declared `source.ref` (may be a range)
    resolved_ref: str = ""  # concrete ref actually used/considered; equals
    # `ref` for a concrete ref, the picked tag for a resolved range, or ""
    # when no ref was resolved at all (bad range syntax, or no tag matched).

    def describe(self) -> str:
        """Human-readable one-line summary, e.g. ``held (local changes)``."""
        return f"{self.action} ({self.detail})" if self.detail else self.action


def _ref_detail(layer: CliLayer, resolved_ref: str) -> str:
    """Detail text for a `cloned`/`pulled` result: unchanged `ref=<ref>` for
    a concrete ref (preserving #2a's exact wording), or `@ <tag> (<range>)`
    when the ref was resolved from a semver range."""
    if resolved_ref != layer.ref:
        return f"@ {resolved_ref} ({layer.ref})"
    return f"ref={layer.ref}"


def sync_layer(layer: CliLayer, git: GitClient | None = None) -> LayerSyncResult:
    """Clone-or-pull a single layer's mirror, honoring the never-destroy gate.

    Args:
        layer: the resolved layer to sync (see `CliLayer`).
        git: injected `GitClient` for testability; a fresh one is constructed
            if omitted.
    """
    git = git or GitClient()
    root = layer.root

    if is_semver_range(layer.ref):
        try:
            tags = git.list_tags(layer.repo)
        except Exception as exc:  # report, never crash
            return LayerSyncResult(
                layer.id,
                "error",
                f"could not list tags for range '{layer.ref}': {exc}",
                role=layer.role,
                ref=layer.ref,
            )
        resolved_ref = resolve_range_to_tag(layer.ref, tags)
        if resolved_ref is None:
            return LayerSyncResult(
                layer.id,
                "skipped",
                f"no tag matches '{layer.ref}'",
                role=layer.role,
                ref=layer.ref,
            )
    else:
        resolved_ref = layer.ref

    if root.exists():
        if not (root / ".git").exists():
            # Something occupies the mirror path but it isn't a git repo we
            # can reason about -- fail-safe: hold rather than clone into it.
            return LayerSyncResult(
                layer.id,
                "held",
                "path exists, not a git repo",
                role=layer.role,
                ref=layer.ref,
                resolved_ref=resolved_ref,
            )

        try:
            status = git.status(str(root))
        except Exception as exc:
            # Fail-safe: any status failure is treated as "can't confirm
            # clean", never as license to write.
            return LayerSyncResult(
                layer.id,
                "held",
                f"status unknown ({exc})",
                role=layer.role,
                ref=layer.ref,
                resolved_ref=resolved_ref,
            )

        if _is_dirty(status):
            return LayerSyncResult(
                layer.id,
                "held",
                "local changes",
                role=layer.role,
                ref=layer.ref,
                resolved_ref=resolved_ref,
            )

        if _has_unpushed_commits(status):
            return LayerSyncResult(
                layer.id,
                "held",
                "local commits present",
                role=layer.role,
                ref=layer.ref,
                resolved_ref=resolved_ref,
            )

        try:
            git.pull(str(root), branch=resolved_ref)
        except Exception as exc:  # report, never crash
            return LayerSyncResult(
                layer.id,
                "error",
                str(exc),
                role=layer.role,
                ref=layer.ref,
                resolved_ref=resolved_ref,
            )
        return LayerSyncResult(
            layer.id,
            "pulled",
            _ref_detail(layer, resolved_ref),
            role=layer.role,
            ref=layer.ref,
            resolved_ref=resolved_ref,
        )

    # Mirror absent -- safe to clone (never-destroy has nothing to protect).
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        git.clone(layer.repo, str(root), branch=resolved_ref)
    except Exception as exc:  # report, never crash
        return LayerSyncResult(
            layer.id,
            "error",
            str(exc),
            role=layer.role,
            ref=layer.ref,
            resolved_ref=resolved_ref,
        )
    return LayerSyncResult(
        layer.id,
        "cloned",
        _ref_detail(layer, resolved_ref),
        role=layer.role,
        ref=layer.ref,
        resolved_ref=resolved_ref,
    )


def sync_all(
    chain: list[CliLayer] | None = None, git: GitClient | None = None
) -> list[LayerSyncResult]:
    """Sync every layer in the resolved `cli` chain.

    Args:
        chain: explicit layer list, bypassing `resolve_cli_layer_chain()`.
            Primarily for tests; normal callers should omit this.
        git: injected `GitClient`, shared across all layers in this run.
    """
    chain = chain if chain is not None else resolve_cli_layer_chain()
    git = git or GitClient()
    return [sync_layer(layer, git=git) for layer in (chain or [])]
