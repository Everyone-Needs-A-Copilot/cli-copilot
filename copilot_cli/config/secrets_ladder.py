"""Credential-resolution ladder for `requires_secret: <NAME>` references.

Implements `credentials-and-boundary.md` §1.6.3's fail-closed ladder, in
order:

    1. Managed shared secret store (tier-scoped, e.g. Infisical `/shared`)
    2. Per-user OS keychain
    3. Interactive OAuth/device-code flow
    4. One-time secure paste (manual floor, TTY only)

A miss at every rung raises `SecretResolutionError` -- **never** a silent
empty-string or `None` value (the failure this ladder exists to prevent).

Rungs 1 and 3 have no client/flow implemented yet in this foundation (no
shared-store client, no device-flow auth exist in this repo) and are
stubbed cleanly: they raise the internal `_SecretRungUnavailable` so the
ladder falls through to the next rung, rather than pretending to succeed
with an empty value. Rung 2 (keychain) is implemented for real via the
macOS `security` CLI. Rung 4 (secure paste) only engages on an interactive
TTY, so a non-interactive process (CI, a background scheduler, a headless
`copilot update`) never blocks waiting on input -- it falls through to the
final `SecretResolutionError` instead.

Phase 1 note: this module is not reachable from any command yet (it is
only ever constructed by `SecretRefSource`, which `settings.py` only builds
when `resolve_cli_layer_chain()` returns a manifest -- and Phase 1 ships
with no manifest present anywhere). It exists now so the ladder's shape is
frozen before Phase 2 wires overlays that declare `requires_secret`.
"""

from __future__ import annotations

import getpass
import subprocess
import sys
from typing import TYPE_CHECKING

from copilot_cli.shared.errors import CopilotError

if TYPE_CHECKING:
    from copilot_cli.config.layers import CliLayer

KEYCHAIN_SERVICE = "copilot-cli"


class SecretResolutionError(CopilotError):
    """No ladder rung resolved a declared `requires_secret` reference.

    Surfaces as the existing `Signed-out` finding (`credentials-and-boundary.md`
    §1.4 / §1.6.3) -- this is the fail-closed exit, never a silent
    empty-string fallback used past this point.
    """

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            f"Signed-out: no credential-ladder rung resolved secret '{name}'.",
            service="config",
            hint=(
                f"Configure '{name}' via a managed secret store, the OS "
                "keychain, device sign-in, or a one-time secure paste."
            ),
        )


class _SecretRungUnavailable(Exception):
    """Internal only: this rung cannot resolve *any* secret right now
    (config absent, rung not implemented, non-interactive session, etc).
    Caught by `resolve_secret` to fall through to the next rung -- never
    surfaced to a caller directly."""


def _rung_managed_store(name: str, chain: list[CliLayer]) -> str:
    """Rung 1: tier-scoped managed secret store (e.g. Infisical `/shared`).

    Per `credentials-and-boundary.md` §1.6.2 step 6: if no
    `shared_secret_store_url` is present in the inherited tier config, this
    rung is *absent*, not misconfigured -- fall through without guessing a
    URL from convention or environment. Tier resolution for this rung
    follows the same nearest-wins precedence as the chain itself: a
    personal-tier reference never checks a shared store; a department-tier
    reference checks department, then org, never upward.

    No shared-store client exists in this foundation yet, so this rung is a
    clean stub: it falls through for every layer rather than guessing or
    silently succeeding. Phase 2+ wires the real client behind this same
    signature so callers never need to change.
    """
    for _layer in chain:
        # Config-only lookup point -- no network client implemented yet.
        # A real implementation would read `shared_secret_store_url` from
        # this layer's non-secret `.env` and, if present, perform a scoped
        # authenticated read here. Absent that client, every layer falls
        # through cleanly.
        continue
    raise _SecretRungUnavailable("managed secret store client not implemented")


def _rung_keychain(name: str, chain: list[CliLayer]) -> str:
    """Rung 2: per-user OS keychain (`security find-generic-password`)."""
    del chain
    if sys.platform != "darwin":
        raise _SecretRungUnavailable("OS keychain rung is macOS-only")
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _SecretRungUnavailable(f"keychain lookup failed: {exc}") from exc
    if result.returncode != 0:
        raise _SecretRungUnavailable("no keychain entry")
    value = result.stdout.strip()
    if not value:
        raise _SecretRungUnavailable("empty keychain entry")
    return value


def _rung_device_flow(name: str, chain: list[CliLayer]) -> str:
    """Rung 3: interactive OAuth/device-code flow. Not implemented in this
    foundation yet (queued for WS-A, per the CLI auth device-flow seam)."""
    del name, chain
    raise _SecretRungUnavailable("device-code sign-in not implemented")


def _rung_secure_paste(name: str, chain: list[CliLayer]) -> str:
    """Rung 4: one-time secure interactive paste (manual floor, TTY only).

    Never caches to disk; the caller (`SecretRefSource`) only ever holds the
    value in-process for the lifetime of the command.
    """
    del chain
    if not sys.stdin.isatty():
        raise _SecretRungUnavailable("not an interactive terminal")
    value = getpass.getpass(f"Enter value for '{name}' (one-time, not stored): ")
    if not value:
        raise _SecretRungUnavailable("empty paste")
    return value


_LADDER = (_rung_managed_store, _rung_keychain, _rung_device_flow, _rung_secure_paste)


def resolve_secret(name: str, chain: list[CliLayer]) -> str:
    """Resolve *name* through the fail-closed ladder.

    Raises `SecretResolutionError` if every rung misses. Never returns an
    empty string or `None` -- a caller either gets a real value or an
    exception, by construction.
    """
    for rung in _LADDER:
        try:
            value = rung(name, chain)
        except _SecretRungUnavailable:
            continue
        if value:
            return value
    raise SecretResolutionError(name)
