"""Manifest-driven service-discovery loader for the CLI component.

Implements the tier-inheritance design's §2 "Connector placement & the
adopt-vs-override mechanism" (Option C: a manifest-driven loader, not PEP
420 namespace packages, not setuptools entry-points -- see D1/D2).

`resolve_cli_services()` is the single source of truth for "what services
does this invocation of `copilot` register": `main.py` iterates it to build
the Typer app, and `copilot layers --json` reports it verbatim for
provenance. With no `copilot.layers.yml` resolving a `cli`-component chain
(`config.layers.resolve_cli_layer_chain()` returns `None`), it returns
exactly `_BASE_SERVICES` -- the same 12 services, same names, same order,
same help text `main.py` used to hardcode. This is the fast-path contract
the Phase-1 parity fitness test asserts.

`load_service(name)` is the cross-service adapter lookup (design §2.5): a
base service that wants an *optional* companion adapter (e.g. `db` wanting
a Coolify-shaped remote adapter) asks the loader by name instead of
hardcoding an import path to a package the public foundation may not ship.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

from copilot_cli.config.layers import (
    CliLayer,
    LayersManifestError,
    load_tier_overlay,
    resolve_cli_layer_chain,
)


@dataclass(frozen=True)
class ServiceEntry:
    """One registered `copilot <name>` service group.

    `package` is the dotted path to the service's top-level package (e.g.
    `"copilot_cli.services.uspto"`); `commands_module`/`commands_attr` name
    the module and attribute inside it that expose the Typer `app` instance
    registered under `name`. Kept separate from `package` (rather than one
    flat dotted path) so `submodule()` can reach *other* modules inside the
    same package -- the seam `postgresql/commands.py` uses to look up
    Coolify's `core.api_client`, `core.config`, etc. without hardcoding
    those import paths (design §2.5).
    """

    name: str
    help: str
    package: str
    commands_module: str = "commands"
    commands_attr: str = "app"
    tier: str = "foundation"
    mode: str = "base"  # base | adopt | override | provides

    @property
    def app(self):
        """The registered Typer app for this service (lazy import)."""
        module = importlib.import_module(f"{self.package}.{self.commands_module}")
        return getattr(module, self.commands_attr)

    def submodule(self, dotted: str):
        """Import and return `<package>.<dotted>` -- lets a base service
        reach into a specific adapter module inside another resolved
        service's package (e.g. `"core.api_client"`) without hardcoding the
        full import path."""
        return importlib.import_module(f"{self.package}.{dotted}")


# ---------------------------------------------------------------------------
# The base 12 -- foundation-owned, byte-identical set/order/help to the
# pre-Phase-1 hardcoded `add_typer(...)` calls in main.py. This tuple IS the
# fast-path contract.
# ---------------------------------------------------------------------------

_BASE_SERVICES: tuple[ServiceEntry, ...] = (
    ServiceEntry("git", "Git repository operations", package="copilot_cli.services.git"),
    ServiceEntry("docker", "Docker container management", package="copilot_cli.services.docker"),
    ServiceEntry("shell", "Shell command execution", package="copilot_cli.services.shell"),
    ServiceEntry("fs", "File system operations", package="copilot_cli.services.filesystem"),
    ServiceEntry(
        "services",
        "System service management (launchctl)",
        package="copilot_cli.services.system_services",
    ),
    ServiceEntry("db", "PostgreSQL database operations", package="copilot_cli.services.postgresql"),
    ServiceEntry("docs", "Document management", package="copilot_cli.services.document"),
    ServiceEntry("bi", "Business intelligence", package="copilot_cli.services.bi"),
    ServiceEntry("monitoring", "System monitoring", package="copilot_cli.services.monitoring"),
    ServiceEntry(
        "infisical",
        "Infisical secrets management",
        package="copilot_cli.services.infisical",
        commands_module="main",
    ),
    ServiceEntry(
        "skill",
        "Skill runtime — discover, execute, verify skills",
        package="copilot_cli.services.skill",
    ),
    ServiceEntry("uspto", "USPTO patent and trademark data access", package="copilot_cli.services.uspto"),
)


def _ensure_on_syspath(root: Path) -> None:
    """Add a tier's mirror root to `sys.path` so its overlay package(s) can
    be imported -- the git-synced, path-imported distribution model (D2):
    tiers are clone dirs `copilot update` pulls, never a pip-installed
    second `copilot-cli`."""
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _compose(chain: list[CliLayer]) -> tuple[ServiceEntry, ...]:
    """Fold `chain` (highest precedence first) onto the base 12,
    nearest-tier-wins.

    Walks foundation -> ... -> personal (ascending precedence) so each
    later, higher-precedence tier's `adopt`/`provides`/`override` naturally
    replaces an earlier tier's via dict assignment -- the same nearest-wins
    semantics the content resolver already uses.

    An undeclared shadowing module is impossible by construction here: only
    names explicitly listed under `adopt`/`provides`/`override` are ever
    touched; `provides` refuses to silently replace an existing name
    (raises `LayersManifestError` -- use `override` for that, deliberately).
    """
    services: dict[str, ServiceEntry] = {svc.name: svc for svc in _BASE_SERVICES}

    for layer in reversed(chain):
        overlay = load_tier_overlay(layer.overlay_path)
        if overlay.adopt or overlay.provides or overlay.override:
            _ensure_on_syspath(layer.root)

        for adopted in overlay.adopt:
            base = services.get(adopted.service)
            if base is None:
                raise LayersManifestError(
                    f"{layer.id}: adopt references unknown base service {adopted.service!r}"
                )
            services[adopted.service] = dataclasses.replace(base, tier=layer.id, mode="adopt")

        override_names = {o.service for o in overlay.override}
        for added in overlay.provides:
            if added.service in services and added.service not in override_names:
                raise LayersManifestError(
                    f"{layer.id}: provides {added.service!r} collides with an existing "
                    "service name -- use 'override' to replace an existing command "
                    "(undeclared shadowing is refused)"
                )
            package, _, module = added.module.rpartition(".")
            services[added.service] = ServiceEntry(
                name=added.service,
                help=added.help or f"{added.service} (added by {layer.id})",
                package=package,
                commands_module=module,
                tier=layer.id,
                mode="provides",
            )

        for overridden in overlay.override:
            if overridden.service not in services:
                raise LayersManifestError(
                    f"{layer.id}: override references unknown service {overridden.service!r}"
                )
            package, _, module = overridden.module.rpartition(".")
            services[overridden.service] = ServiceEntry(
                name=overridden.service,
                help=services[overridden.service].help,
                package=package,
                commands_module=module,
                tier=layer.id,
                mode="override",
            )

    # Preserve base registration order; append any newly-provided services
    # (not among the base 12) in first-added order.
    ordered_names = [svc.name for svc in _BASE_SERVICES]
    ordered_names += [name for name in services if name not in ordered_names]
    return tuple(services[name] for name in ordered_names)


def resolve_cli_services() -> tuple[ServiceEntry, ...]:
    """Resolve the full set of registered services: base + tier overlays.

    No manifest resolves -> returns exactly `_BASE_SERVICES`: same 12
    services, same names, same order, same help text as the pre-Phase-1
    hardcoded registration in `main.py`. This is the fast-path contract the
    parity fitness test asserts.
    """
    chain = resolve_cli_layer_chain()
    if chain is None:
        return _BASE_SERVICES
    return _compose(chain)


def load_service(name: str) -> ServiceEntry | None:
    """Look up one resolved service by name (cross-service adapter lookup).

    Returns `None` if no tier (base or overlay) provides *name* -- callers
    (e.g. `postgresql`'s optional remote-adapter lookup, design §2.5) must
    handle the `None` case themselves, typically by raising their own
    domain-specific error. This function never raises just because a
    service is absent -- absence is an ordinary, expected outcome.
    """
    for svc in resolve_cli_services():
        if svc.name == name:
            return svc
    return None
