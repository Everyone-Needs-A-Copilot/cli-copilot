"""Mirror-sync logic for `copilot update` (V-3/V-4 onboarding blocker).

Per resolved `component: cli` layer (`config.layers.resolve_cli_layer_chain`),
clone-or-pull that layer's local read-only mirror (`layer.root`, conventionally
``~/.copilot/mirrors/cli/<id>``) from its declared `source.repo`/`source.ref`.

Scope (initiative item #2a -- see `copilot-control-tower`'s onboarding-blocker
tracking): concrete refs only (branch / exact tag / SHA) and the never-destroy
gate. Semver-RANGE refs (e.g. the live foundation layer's ``^1.4.5``) are
detected and reported ``skipped`` -- resolving them is a separate follow-up
(#2b), never attempted here, and never a crash.

Hard invariants (control-tower invariants #2/#3, "never-destroy" + "pull-only
downward"):

- A mirror whose git working tree is DIRTY (staged, modified, untracked, or
  conflicted changes -- see `_is_dirty`) is HELD: zero writes, reported, and
  skipped. Only a clean OR absent mirror may be touched.
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
from copilot_cli.services.git.client import GitClient

# Per the ratified detection rule: a `source.ref` is a semver RANGE (not a
# concrete branch/tag/SHA) if it starts with `^`/`~`, or contains a range
# operator. Deliberately narrow -- concrete refs like `main`, `v1.x`, or a
# 40-char SHA must never be misdetected as a range.
_RANGE_PREFIXES = ("^", "~")
_RANGE_OPERATORS = ("<", ">", "||")

# `GitClient.status()` fields that indicate the working tree is dirty. `ahead`/
# `behind`/`tracking`/`current` describe divergence from the remote, not local
# changes, and are never grounds to withhold a pull.
_DIRTY_STATUS_FIELDS = ("staged", "modified", "not_added", "deleted", "conflicted")


def is_semver_range(ref: str) -> bool:
    """True if `ref` looks like a semver RANGE rather than a concrete
    branch/tag/SHA -- e.g. ``^1.4.5``, ``~1.2.0``, ``>=1.0.0 <2.0.0``.

    Resolving ranges is out of scope here (#2b); this only needs to detect
    them reliably enough to skip without crashing.
    """
    stripped = ref.strip()
    if stripped.startswith(_RANGE_PREFIXES):
        return True
    return any(op in stripped for op in _RANGE_OPERATORS)


def _is_dirty(status: dict) -> bool:
    """True if a `GitClient.status()` result reports any local change."""
    return any(status.get(field) for field in _DIRTY_STATUS_FIELDS)


@dataclass(frozen=True)
class LayerSyncResult:
    """The outcome of syncing one layer's mirror."""

    layer_id: str
    action: str  # "cloned" | "pulled" | "held" | "skipped" | "error"
    detail: str = ""

    def describe(self) -> str:
        """Human-readable one-line summary, e.g. ``held (local changes)``."""
        return f"{self.action} ({self.detail})" if self.detail else self.action


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
        return LayerSyncResult(
            layer.id, "skipped", f"range ref '{layer.ref}' pending #2b"
        )

    if root.exists():
        if not (root / ".git").exists():
            # Something occupies the mirror path but it isn't a git repo we
            # can reason about -- fail-safe: hold rather than clone into it.
            return LayerSyncResult(layer.id, "held", "path exists, not a git repo")

        try:
            status = git.status(str(root))
        except Exception as exc:
            # Fail-safe: any status failure is treated as "can't confirm
            # clean", never as license to write.
            return LayerSyncResult(layer.id, "held", f"status unknown ({exc})")

        if _is_dirty(status):
            return LayerSyncResult(layer.id, "held", "local changes")

        try:
            git.pull(str(root), branch=layer.ref)
        except Exception as exc:  # report, never crash
            return LayerSyncResult(layer.id, "error", str(exc))
        return LayerSyncResult(layer.id, "pulled", f"ref={layer.ref}")

    # Mirror absent -- safe to clone (never-destroy has nothing to protect).
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        git.clone(layer.repo, str(root), branch=layer.ref)
    except Exception as exc:  # report, never crash
        return LayerSyncResult(layer.id, "error", str(exc))
    return LayerSyncResult(layer.id, "cloned", f"ref={layer.ref}")


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
