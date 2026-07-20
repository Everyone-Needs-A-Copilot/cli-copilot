"""Store-readiness REPORT for `copilot update` (#2b, cred-boundary QA F9).

Ratified decision: `copilot update` syncs mirrors and REPORTS whether the
tier-scoped managed secret store (`config/managed_store.py`'s Infisical
backend) looks reachable-in-principle on THIS machine -- it never
provisions, never performs a network auth round-trip, and never reads,
prints, or logs a secret VALUE. This is the presence-only half of
`credentials-and-boundary.md` §1.6.2; the actual secret-value resolution
(and any real auth) only ever happens later, on demand, via the credential
ladder (`config/secrets_ladder.py`).

Two presence checks, both boolean-only:

  1. Is store CONFIG declared by any layer in the chain (an
     `INFISICAL_WORKSPACE_ID`)? Reuses `managed_store._find_store_layer`,
     which is pure YAML/`.env` parsing -- no network, no `Settings()`
     construction (recursion-safe, mirroring how `managed_store.py` itself
     stays import-cycle-free).
  2. Are the bootstrap credentials (`INFISICAL_CLIENT_ID`/`_SECRET`)
     PRESENT on this machine (keychain, then that tier's `.env`)? Reuses
     `managed_store._read_bootstrap_cred`, which does the same lookup the
     real store rung uses -- but here the returned value is only ever
     coerced to a boolean (`bool(...)`) and immediately discarded; it is
     never assigned to a field on `StoreReadiness`, never formatted into
     `detail`, and never returned to any caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from copilot_cli.config.layers import CliLayer

_READY = "store: ready"
_CREDS_MISSING = (
    "store: config present, bootstrap creds missing on this machine "
    "(provision to authenticate)"
)
_NONE_DECLARED = "store: none declared"


@dataclass(frozen=True)
class StoreReadiness:
    """Presence-only report -- never carries a secret value.

    `status` is one of ``"ready"`` | ``"creds_missing"`` | ``"none"``.
    `detail` is the human-readable line shared by both the human and
    `--json` output. `layer_id` is the nearest layer declaring the store,
    or `None` when no layer declares one at all.
    """

    status: str
    detail: str
    layer_id: str | None = None


def check_store_readiness(chain: list[CliLayer]) -> StoreReadiness:
    """Presence-only report for *chain* (highest-precedence-first, as
    returned by `resolve_cli_layer_chain`). Never makes a network call,
    never provisions, never emits a secret value -- see module docstring.
    """
    # Local import: keeps this module free of any import-time dependency on
    # `managed_store`/`secrets_ladder` beyond what a single call needs, the
    # same containment `managed_store.py` itself uses for its own
    # keychain/ladder imports.
    from copilot_cli.config.managed_store import _find_store_layer, _read_bootstrap_cred

    found = _find_store_layer(chain)
    if found is None:
        return StoreReadiness(status="none", detail=_NONE_DECLARED)

    layer, cfg = found
    client_id_present = bool(_read_bootstrap_cred("INFISICAL_CLIENT_ID", cfg))
    client_secret_present = bool(_read_bootstrap_cred("INFISICAL_CLIENT_SECRET", cfg))

    if client_id_present and client_secret_present:
        return StoreReadiness(status="ready", detail=_READY, layer_id=layer.id)

    return StoreReadiness(status="creds_missing", detail=_CREDS_MISSING, layer_id=layer.id)
