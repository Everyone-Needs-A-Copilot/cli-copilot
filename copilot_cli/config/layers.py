"""Tier-inheritance manifest resolution for the CLI component.

Phase 1 of the ratified CLI tier-inheritance model (see the design doc's §1
"Layered config + secret resolution" and §2 "Connector placement & the
adopt-vs-override mechanism"). This module is the **contract freeze**: the
`copilot.layers.yml` manifest shape and the per-tier `cli.overlay.yml`
overlay shape are defined here, once, and reused by both
`config/settings.py` (layered config/secret sources) and
`services/_loader.py` (service-discovery loader).

`copilot.layers.yml` is the **same manifest** the content-component resolver
(claude/knowledge/codex) already uses -- one spine for all four CSE
components, filtered here to entries whose `component` is ``"cli"``. See
`four-tier-topology.md` §4 in the `copilot-control-tower` docs for the full
cross-component schema this is one slice of.

    # copilot.layers.yml -- highest precedence FIRST; rank is the tiebreak of record
    version: 1
    layers:
      - id: personal-pablo
        role: personal              # open vocabulary, not a closed enum
        component: cli               # the CSE component this layer belongs to -- required
        rank: 10                    # lower = higher precedence; gaps leave room to insert
        source:
          repo: git@github-personal:pablitoalejo/cli-copilot-private.git
          ref: main
        auth: ssh-personal

      - id: org-acme
        role: org
        component: cli
        rank: 30
        source:
          repo: git@github-work:acme-corp/cli-copilot-internal.git
          ref: v1.x
        auth: ssh-work

      - id: foundation
        role: foundation
        component: cli
        rank: 40
        source:
          repo: https://github.com/Everyone-Needs-A-Copilot/cli-copilot.git
          ref: ^1.4.5
        auth: anon

Each resolved layer is expected to contribute, at its local mirror root
(``~/.copilot/mirrors/cli/<id>`` by convention -- see `_mirror_root`):

- ``.env`` -- non-secret config only (base URLs, IDs, flags). Secret
  *values* never live here; see `cli.overlay.yml`'s ``requires_secret``.
- ``cli.overlay.yml`` -- this tier's adopt/provides/override declaration
  (see `load_tier_overlay` / `TierOverlay` below). Optional: a config-only
  tier (D3 -- dept/personal by default) may have no overlay file at all and
  contribute only a `.env`.

    # cli.overlay.yml -- one tier's service declarations
    version: 1

    adopt:                    # turn ON a BASE service with tier config/secrets only -- zero code
      - service: uspto
        config:                          # non-secret, merged into this tier's .env
          uspto_cli_base_url: https://internal-uspto-proxy.acme.example
        requires_secret:                 # names resolved via the credential ladder -- never a value here
          - USPTO_CLI_API_KEY

    provides:                 # ADD a service this tier's own package implements (not in base at all)
      - service: coolify
        module: copilot_overlay_internal.services.coolify.commands
        help: "Coolify infrastructure operations"
        requires_secret:
          - COOLIFY_API_TOKEN

    override:                 # REPLACE a base service's command with this tier's own implementation
      - service: db
        module: copilot_overlay_internal.services.db_coolify.commands

Precedence for both the config fold and the service fold is **nearest-tier
wins**: PERSONAL > DEPARTMENT > ORG > FOUNDATION, identical to the ratified
content-component resolver. `resolve_cli_layer_chain()` returns layers in
that order (highest precedence first); callers that fold config/services
onto a base state should walk the chain **in reverse** (foundation first)
so a later, higher-precedence tier's contribution naturally wins via normal
dict/last-write-wins assignment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

COMPONENT = "cli"
MANIFEST_FILENAME = "copilot.layers.yml"
OVERLAY_FILENAME = "cli.overlay.yml"

# Project-root markers shared with settings.py's `_find_env_file` so the two
# resolvers agree on "where is this project's root" without importing from
# each other.
_ROOT_MARKERS = {".git", "pyproject.toml", ".mcp.json", "package.json"}


class LayersManifestError(Exception):
    """`copilot.layers.yml` (or a tier's `cli.overlay.yml`) exists but is
    structurally invalid -- e.g. a duplicate `rank` among `cli` entries, a
    missing required key, or an `adopt`/`override` referencing an unknown
    service name. Raised eagerly so a malformed manifest fails loudly at
    resolution time, never silently drops a layer.
    """


@dataclass(frozen=True)
class CliLayer:
    """One resolved `component: cli` layer, in precedence order."""

    id: str
    role: str
    rank: int
    repo: str
    ref: str
    auth: str
    root: Path
    path: str | None = None
    unit: str | None = None
    activation: str = "always"

    @property
    def env_path(self) -> Path:
        """This layer's non-secret `.env` (may not exist on disk yet)."""
        return self.root / ".env"

    @property
    def overlay_path(self) -> Path:
        """This layer's `cli.overlay.yml` (may not exist -- config-only tiers
        have no overlay file at all; see `load_tier_overlay`)."""
        return self.root / OVERLAY_FILENAME


def find_layers_manifest() -> Path | None:
    """Locate `copilot.layers.yml`, mirroring `_find_env_file`'s search shape:

    1. `COPILOT_LAYERS_FILE` explicit override
    2. Walk up from CWD, stopping at the first project-root marker
    3. Standard user config locations (machine-agnostic, `$HOME`-relative)

    Returns `None` when nothing resolves -- the ordinary, expected state
    until a tier opts into the manifest. Unlike `_find_env_file`, this never
    synthesizes a fallback path: a `.env` with no manifest is meaningless
    to *create*, whereas a nonexistent-until-configured `copilot.layers.yml`
    is meaningless to *invent*.
    """
    explicit = os.environ.get("COPILOT_LAYERS_FILE")
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None

    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / MANIFEST_FILENAME
        if candidate.is_file():
            return candidate
        if any((parent / marker).exists() for marker in _ROOT_MARKERS):
            break

    xdg = os.environ.get("XDG_CONFIG_HOME")
    standard = [
        Path(xdg) / "copilot" / MANIFEST_FILENAME
        if xdg
        else Path.home() / ".config" / "copilot" / MANIFEST_FILENAME,
        Path.home() / ".copilot-cli" / MANIFEST_FILENAME,
    ]
    for candidate in standard:
        if candidate.is_file():
            return candidate
    return None


def _mirror_root(layer_id: str) -> Path:
    """Conventional local read-only mirror dir for a synced `cli` layer.

    Mirrors are materialized by `copilot update` (out of Phase-1 scope --
    Phase 1 ships the loader inert, not the sync path) at
    ``~/.copilot/mirrors/cli/<id>``, per `inheritance-and-publish.md`'s
    ``~/.copilot/mirrors/<tier>`` convention, namespaced by component so a
    `cli` layer id can never collide with a `claude`/`knowledge`/`codex`
    layer sharing the same id.

    `COPILOT_MIRRORS_ROOT` overrides the `~/.copilot` base -- used by tests
    to point mirrors at an isolated tmp directory without touching the real
    machine, and available to any future harness that needs the same.
    """
    override = os.environ.get("COPILOT_MIRRORS_ROOT")
    if override:
        base = Path(override)
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) / "copilot" if xdg else Path.home() / ".copilot"
    return base / "mirrors" / COMPONENT / layer_id


def _parse_manifest(manifest_path: Path) -> list[dict]:
    try:
        raw = yaml.safe_load(manifest_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise LayersManifestError(f"{manifest_path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict) or "layers" not in raw:
        raise LayersManifestError(f"{manifest_path}: missing top-level 'layers' list")
    layers = raw.get("layers") or []
    if not isinstance(layers, list):
        raise LayersManifestError(f"{manifest_path}: 'layers' must be a list")
    return layers


def resolve_cli_layer_chain(manifest_path: Path | str | None = None) -> list[CliLayer] | None:
    """Resolve the precedence-ordered `component: cli` layer chain.

    Returns `None` when:
    - no `copilot.layers.yml` resolves at all, or
    - one resolves but contains zero `component: cli` entries.

    Both are "no CLI tiering configured" and are the trigger for the
    back-compat fast path in `settings.py` and `services/_loader.py` --
    this is the single source of truth both consult.

    Ordering: ascending by `rank` (lower rank = higher precedence), i.e.
    the returned list is highest-precedence-first (personal -> ... ->
    foundation), matching `four-tier-topology.md` §4. Raises
    `LayersManifestError` on a duplicate rank among `cli` entries -- the
    ratified "hard-error on equal-rank pair" rule -- so ordering ambiguity
    is caught here, not silently resolved by list/dict insertion order.

    Args:
        manifest_path: explicit manifest location, bypassing
            `find_layers_manifest()`'s search. Primarily for tests; normal
            callers should omit this and let discovery run.
    """
    path = Path(manifest_path) if manifest_path is not None else find_layers_manifest()
    if path is None or not path.is_file():
        return None

    entries = _parse_manifest(path)
    cli_entries = [e for e in entries if isinstance(e, dict) and e.get("component") == COMPONENT]
    if not cli_entries:
        return None

    layers: list[CliLayer] = []
    for entry in cli_entries:
        try:
            layer_id = str(entry["id"])
            role = str(entry["role"])
            rank = int(entry["rank"])
            source = entry["source"]
            repo = str(source["repo"])
            ref = str(source.get("ref", "main"))
            auth = str(entry.get("auth", "anon"))
        except (KeyError, TypeError, ValueError) as exc:
            raise LayersManifestError(
                f"{path}: malformed 'cli' layer entry {entry!r}: {exc}"
            ) from exc
        layers.append(
            CliLayer(
                id=layer_id,
                role=role,
                rank=rank,
                repo=repo,
                ref=ref,
                auth=auth,
                root=_mirror_root(layer_id),
                path=source.get("path"),
                unit=entry.get("unit"),
                activation=str(entry.get("activation", "always")),
            )
        )

    layers.sort(key=lambda layer: layer.rank)
    ranks = [layer.rank for layer in layers]
    if len(set(ranks)) != len(ranks):
        raise LayersManifestError(
            f"{path}: duplicate rank among 'cli' layers {ranks} -- rank must be "
            "unique per component"
        )
    return layers


# ---------------------------------------------------------------------------
# Per-tier `cli.overlay.yml` -- adopt / provides / override
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlayAdopt:
    """Turn on a BASE service with this tier's config/secrets only. The base
    module runs unchanged -- zero code, zero drift (design §2.3)."""

    service: str
    config: dict[str, str] = field(default_factory=dict)
    requires_secret: tuple[str, ...] = ()
    requires_secret_hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OverlayProvide:
    """Add a NEW service this tier's own package implements -- not present in
    base at all (e.g. the org's `coolify` adapter, design §2.5)."""

    service: str
    module: str
    help: str = ""
    requires_secret: tuple[str, ...] = ()
    requires_secret_hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OverlayOverride:
    """Replace a base service's command with this tier's own implementation,
    under the same command name (design §2.4). Must be declared explicitly
    -- an undeclared shadowing module is refused by the loader."""

    service: str
    module: str
    requires_secret: tuple[str, ...] = ()
    requires_secret_hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TierOverlay:
    """One tier's parsed `cli.overlay.yml`."""

    adopt: tuple[OverlayAdopt, ...] = ()
    provides: tuple[OverlayProvide, ...] = ()
    override: tuple[OverlayOverride, ...] = ()

    def all_requires_secret(self) -> tuple[str, ...]:
        """Every `requires_secret` name declared anywhere in this overlay,
        de-duplicated, order preserved."""
        names: list[str] = []
        for a in self.adopt:
            names.extend(a.requires_secret)
        for p in self.provides:
            names.extend(p.requires_secret)
        for o in self.override:
            names.extend(o.requires_secret)
        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return tuple(out)

    def all_requires_secret_hints(self) -> dict[str, str]:
        """Ordered ``{name: hint}`` for every `requires_secret` name declared
        with a non-default routing hint (`from: keychain` | `from: store`)
        anywhere in this overlay. A name absent here has the default `"any"`
        hint -- i.e. `resolve_secret` tries every ladder rung, byte-for-byte
        today's behavior. First declaration wins on a duplicate name, matching
        `all_requires_secret()`'s own dedup order.

        This is purely a routing-perf hint (see `secrets_ladder.py`'s
        `_RUNG_SUBSET_FOR_HINT`) -- it never changes *which* names are
        declared secret, only which ladder rungs are consulted to resolve
        one.
        """
        merged: dict[str, str] = {}
        for a in self.adopt:
            for name, hint in a.requires_secret_hints.items():
                merged.setdefault(name, hint)
        for p in self.provides:
            for name, hint in p.requires_secret_hints.items():
                merged.setdefault(name, hint)
        for o in self.override:
            for name, hint in o.requires_secret_hints.items():
                merged.setdefault(name, hint)
        return merged


# Valid `from:` values on a mapping-form `requires_secret` entry. `"any"` is
# the default (equivalent to a bare string name) and is never stored in
# `requires_secret_hints` -- see `_parse_requires_secret`.
_VALID_SECRET_SOURCES = frozenset({"any", "store", "keychain"})


def _parse_requires_secret(raw: object) -> tuple[tuple[str, ...], dict[str, str]]:
    """Parse one `requires_secret:` list into ``(names, hints)``.

    Each entry is either:

    - a bare string name (``FOO``) -- back-compat form, hint defaults to
      `"any"` (try every ladder rung, today's behavior, unchanged).
    - a mapping (``{name: FOO, from: keychain}``) -- gives the credential
      ladder (`secrets_ladder.resolve_secret`'s `prefer` param) a routing
      hint that RESTRICTS which rungs are tried for that one name. The hint
      never adds a source and never changes ladder precedence -- see
      `secrets_ladder._RUNG_SUBSET_FOR_HINT`.

    ``names`` preserves declaration order (mirrors the pre-hint bare-tuple
    shape exactly, so every existing reader of `.requires_secret` keeps
    working unchanged). ``hints`` only contains entries with a non-default
    (non-`"any"`) hint.
    """
    names: list[str] = []
    hints: dict[str, str] = {}
    for entry in raw or []:
        if isinstance(entry, str):
            names.append(entry)
            continue
        if isinstance(entry, dict):
            try:
                name = str(entry["name"])
            except KeyError as exc:
                raise LayersManifestError(
                    f"requires_secret entry {entry!r} is missing required key 'name'"
                ) from exc
            source = str(entry.get("from", "any"))
            if source not in _VALID_SECRET_SOURCES:
                raise LayersManifestError(
                    f"requires_secret entry {entry!r}: 'from' must be one of "
                    f"{sorted(_VALID_SECRET_SOURCES)}, got {source!r}"
                )
            names.append(name)
            if source != "any":
                hints[name] = source
            continue
        raise LayersManifestError(
            f"requires_secret entry must be a string or a {{name, from}} mapping, got {entry!r}"
        )
    return tuple(names), hints


def load_tier_overlay(overlay_path: Path) -> TierOverlay:
    """Parse one tier's `cli.overlay.yml`.

    Returns an empty `TierOverlay` (all three lists empty) if the file does
    not exist -- config-only tiers (D3: dept/personal are config-only by
    default, until they ship code) are not required to have any
    adopt/provides/override at all, only non-secret config in their `.env`.
    """
    if not overlay_path.is_file():
        return TierOverlay()
    try:
        raw = yaml.safe_load(overlay_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise LayersManifestError(f"{overlay_path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LayersManifestError(f"{overlay_path}: top-level must be a mapping")

    try:
        adopt_list = []
        for e in raw.get("adopt") or []:
            names, hints = _parse_requires_secret(e.get("requires_secret"))
            adopt_list.append(
                OverlayAdopt(
                    service=str(e["service"]),
                    config={str(k): str(v) for k, v in (e.get("config") or {}).items()},
                    requires_secret=names,
                    requires_secret_hints=hints,
                )
            )
        adopt = tuple(adopt_list)

        provides_list = []
        for e in raw.get("provides") or []:
            names, hints = _parse_requires_secret(e.get("requires_secret"))
            provides_list.append(
                OverlayProvide(
                    service=str(e["service"]),
                    module=str(e["module"]),
                    help=str(e.get("help", "")),
                    requires_secret=names,
                    requires_secret_hints=hints,
                )
            )
        provides = tuple(provides_list)

        override_list = []
        for e in raw.get("override") or []:
            names, hints = _parse_requires_secret(e.get("requires_secret"))
            override_list.append(
                OverlayOverride(
                    service=str(e["service"]),
                    module=str(e["module"]),
                    requires_secret=names,
                    requires_secret_hints=hints,
                )
            )
        override = tuple(override_list)
    except (KeyError, TypeError) as exc:
        raise LayersManifestError(f"{overlay_path}: malformed entry: {exc}") from exc

    return TierOverlay(adopt=adopt, provides=provides, override=override)
