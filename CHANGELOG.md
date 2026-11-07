# Changelog

## [0.3.15] - 2026-11-07

- Resolve CLI configuration and service overlays from the active central release instead of retired mirror directories. Organization and department commands now use the selected immutable component snapshots, while personal content keeps its recorded live link. Repository/ref, signer policy, component identity and path checks reject conflicting manifests without falling back to stale mirrors. Machines without a central pointer keep legacy mirror resolution. Python package version is 1.4.15.

## [0.3.14] - 2026-11-07

- Central resolution: add a stable `copilot` launcher installer (`scripts/install-cli.py`, `copilot_cli/launcher_install.py`) that resolves through the `~/.copilot/current` release pointer, with idempotent install and receipt, dev mode, check, and rollback that follows `cc release rollback` lineage (`--steps`, `--to`) after verifying the framework `cc` identity. `--version` shows the release commit.
- Retire the fanout paths: this source repository no longer carries synced framework copies (`.claude/commands`, `.claude/fitness-check.sh`, `.claude/hooks/copilot-hook.sh`) or `copilot.lock.json`; `copilot.project.json` is the marker and the framework resolves through the release pointer.

## [0.3.13] - 2026-11-05

- Forward `copilot docker tests` to the managed `cc resources` runner (PR #14).
- Document CLI intent and command discovery, make help output safe, and add CLI guide contract checks (PR #15).
- Includes framework update 5.33.1 (claude) / 0.15.0 (codex) tiered verification.

## [0.3.12] - 2026-10-21

- Publish reviewed native agent instructions, preserving current repository rules, supported commands and project ownership.
- Retain existing runtime and skill behavior; this release includes instruction alignment and release metadata.
