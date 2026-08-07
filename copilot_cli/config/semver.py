"""Semver RANGE ref -> concrete tag resolution for `copilot update` (#2b).

`copilot.layers.yml` lets a tier pin a layer's `source.ref` to a semver
RANGE instead of a concrete branch/tag/SHA -- e.g. the live foundation
layer's ``^1.4.5`` (see `config/layers.py`'s module docstring). This module
maps a range to a `packaging.specifiers.SpecifierSet`-compatible specifier
string, then picks the HIGHEST tag (from a repo's real tag list) that
satisfies it.

Uses `packaging` (already transitively available via this project's own
`pytest` dev dependency, and now declared directly in `pyproject.toml`)
rather than hand-rolling version parsing/comparison -- `packaging.version.
Version` and `packaging.specifiers.SpecifierSet` are the same battle-tested
PEP 440 machinery pip itself uses, and PEP 440 versions are a superset-
compatible model for the plain dotted `MAJOR.MINOR.PATCH` tags this
ecosystem's repos actually use (optionally `v`-prefixed, e.g. ``v1.5.0`` --
`Version()` parses the `v` prefix natively).

Range -> specifier rules (ratified, matching real-world caret/tilde
semantics from npm/cargo's semver, translated to a PEP 440 specifier):

    ^1.4.5   -> >=1.4.5,<2.0.0        (caret, major > 0: pin major)
    ^0.2.3   -> >=0.2.3,<0.3.0        (caret, major == 0: pin minor)
    ^0.0.3   -> >=0.0.3,<0.0.4        (caret, major == minor == 0: pin patch)
    ^1.x     -> >=1.0.0,<2.0.0        (caret, partial version)
    ~1.2.3   -> >=1.2.3,<1.3.0        (tilde: pin major.minor)
    ~1.2     -> >=1.2.0,<1.3.0        (tilde, partial version)
    >=1.4.5  -> >=1.4.5               (already a plain comparator -- passes
                                        through unchanged; `packaging`
                                        parses it directly)

Never raises past this module's own boundary: an unresolvable range (bad
syntax, no matching tag) resolves to `None` from `resolve_range_to_tag`,
which `config/sync.py` reports as a clean `skipped` result -- consistent
with the never-destroy gate's "never crash, never guess" contract.
"""

from __future__ import annotations

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

# A version component that means "not specified" in a partial version like
# `1.x`, `1.X`, `1.*`, or a bare `1` (component simply absent).
_WILDCARDS = {"x", "X", "*", ""}


class RangeResolutionError(Exception):
    """A semver RANGE ref could not be mapped to a valid specifier (e.g.
    malformed version components). Caught internally by
    `resolve_range_to_tag`, which reports `None` rather than raise -- this
    type exists to make the two failure modes (bad range syntax vs. no
    matching tag) distinguishable to any caller that wants to introspect,
    without ever escaping to crash `copilot update`."""


def _parse_partial(version_str: str) -> tuple[int, int | None, int | None]:
    """Parse a possibly-partial dotted version (``1``, ``1.2``, ``1.2.3``,
    ``1.2.x``) into ``(major, minor, patch)``, where an absent or wildcard
    component is `None` -- caret/tilde math treats "not specified"
    differently from "explicitly zero" (see module docstring)."""
    parts = version_str.split(".")

    def _component(i: int) -> int | None:
        if i >= len(parts) or parts[i] in _WILDCARDS:
            return None
        try:
            return int(parts[i])
        except ValueError as exc:
            raise RangeResolutionError(f"invalid version '{version_str}': {exc}") from exc

    major = _component(0)
    if major is None:
        raise RangeResolutionError(f"invalid version '{version_str}': missing major component")
    return major, _component(1), _component(2)


def _caret_to_specifier(version_str: str) -> str:
    major, minor, patch = _parse_partial(version_str)
    lower = f"{major}.{minor if minor is not None else 0}.{patch if patch is not None else 0}"

    if major > 0:
        upper = f"{major + 1}.0.0"
    elif minor is None:
        upper = "1.0.0"
    elif minor > 0:
        upper = f"0.{minor + 1}.0"
    elif patch is None:
        upper = "0.1.0"
    else:
        upper = f"0.0.{patch + 1}"

    return f">={lower},<{upper}"


def _tilde_to_specifier(version_str: str) -> str:
    major, minor, patch = _parse_partial(version_str)
    lower = f"{major}.{minor if minor is not None else 0}.{patch if patch is not None else 0}"
    upper = f"{major + 1}.0.0" if minor is None else f"{major}.{minor + 1}.0"
    return f">={lower},<{upper}"


def range_to_specifier(range_ref: str) -> str:
    """Map a semver RANGE ref to a `packaging.specifiers.SpecifierSet`
    string. See module docstring for the exact rules.

    Raises:
        RangeResolutionError: if a caret/tilde range's version component
            can't be parsed (e.g. non-numeric).
    """
    stripped = range_ref.strip()
    if stripped.startswith("^"):
        return _caret_to_specifier(stripped[1:])
    if stripped.startswith("~"):
        return _tilde_to_specifier(stripped[1:])
    # Already a plain comparator/specifier (e.g. `>=1.4.5`) -- pass through
    # unchanged; `packaging.specifiers.SpecifierSet` parses it directly.
    return stripped


def resolve_range_to_tag(range_ref: str, tags: list[str]) -> str | None:
    """Given a semver RANGE ref and a repo's tag names (e.g. from
    `GitClient.list_tags`), return the HIGHEST tag that satisfies the
    range, or `None` if the range can't be resolved at all -- either because
    it's malformed, or because no tag in *tags* matches. Never raises: a
    caller (`config/sync.py`) treats `None` as "nothing to sync", never a
    crash.

    Non-semver-looking tag names in *tags* (an arbitrary git tag, not every
    tag in a real repo need be a version) are silently skipped rather than
    treated as an error -- a tag list is a real repo's tags, not a curated
    version list.
    """
    try:
        specifier = SpecifierSet(range_to_specifier(range_ref))
    except (RangeResolutionError, InvalidSpecifier):
        return None

    best_tag: str | None = None
    best_version: Version | None = None
    for tag in tags:
        try:
            version = Version(tag)
        except InvalidVersion:
            continue
        # `prereleases=False`: a plain range must resolve to the highest
        # STABLE tag. A prerelease is only ever obtained by pinning an
        # exact ref (the concrete-ref path, not this resolver) -- so a
        # range never selects one, even if it's otherwise in-range.
        if not specifier.contains(version, prereleases=False):
            continue
        if best_version is None or version > best_version:
            best_version = version
            best_tag = tag
    return best_tag
