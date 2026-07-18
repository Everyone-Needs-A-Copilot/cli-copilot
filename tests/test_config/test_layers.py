"""Unit tests for `config/layers.py`: the `copilot.layers.yml` manifest
resolver and per-tier `cli.overlay.yml` parser (the CLI tier-inheritance
Phase-1 contract freeze). The Phase-1 hard-gate parity assertions live in
`tests/test_tier_inheritance_parity.py`; this file exercises the resolver's
behavior once a manifest *does* exist, which Phase 1 ships but does not yet
exercise in production.
"""

from __future__ import annotations

import pytest
import yaml

from copilot_cli.config.layers import (
    LayersManifestError,
    load_tier_overlay,
    resolve_cli_layer_chain,
)


def _write_manifest(path, layers: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"version": 1, "layers": layers}))


class TestFindAndResolveNoManifest:
    def test_missing_file_returns_none(self, tmp_path):
        assert resolve_cli_layer_chain(tmp_path / "does-not-exist.yml") is None

    def test_manifest_with_zero_cli_entries_returns_none(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        _write_manifest(
            manifest,
            [
                {
                    "id": "org-acme",
                    "role": "org",
                    "component": "claude",  # not "cli"
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/claude-copilot.git"},
                    "auth": "ssh-work",
                }
            ],
        )
        assert resolve_cli_layer_chain(manifest) is None


class TestResolveWithCliEntries:
    def test_resolves_and_sorts_by_rank_ascending(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        _write_manifest(
            manifest,
            [
                {
                    "id": "foundation",
                    "role": "foundation",
                    "component": "cli",
                    "rank": 40,
                    "source": {"repo": "https://github.com/example/cli-copilot.git", "ref": "^1.4.5"},
                    "auth": "anon",
                },
                {
                    "id": "personal-pablo",
                    "role": "personal",
                    "component": "cli",
                    "rank": 10,
                    "source": {"repo": "git@github-personal:pablo/cli-copilot-private.git"},
                    "auth": "ssh-personal",
                },
                {
                    "id": "org-acme",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:acme/cli-copilot-internal.git", "ref": "v1.x"},
                    "auth": "ssh-work",
                    "unit": "engineering",
                },
            ],
        )
        chain = resolve_cli_layer_chain(manifest)
        assert chain is not None
        assert [layer.id for layer in chain] == ["personal-pablo", "org-acme", "foundation"]
        assert [layer.rank for layer in chain] == [10, 30, 40]
        assert chain[1].unit == "engineering"
        assert chain[2].ref == "^1.4.5"
        assert chain[0].auth == "ssh-personal"

    def test_filters_out_non_cli_components(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        _write_manifest(
            manifest,
            [
                {
                    "id": "cli-foundation",
                    "role": "foundation",
                    "component": "cli",
                    "rank": 40,
                    "source": {"repo": "https://github.com/example/cli-copilot.git"},
                    "auth": "anon",
                },
                {
                    "id": "claude-foundation",
                    "role": "foundation",
                    "component": "claude",
                    "rank": 40,
                    "source": {"repo": "https://github.com/example/claude-copilot.git"},
                    "auth": "anon",
                },
            ],
        )
        chain = resolve_cli_layer_chain(manifest)
        assert chain is not None
        assert [layer.id for layer in chain] == ["cli-foundation"]

    def test_duplicate_rank_among_cli_layers_is_a_hard_error(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        _write_manifest(
            manifest,
            [
                {
                    "id": "org-a",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:a/cli-copilot-a.git"},
                    "auth": "ssh-work",
                },
                {
                    "id": "org-b",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    "source": {"repo": "git@github-work:b/cli-copilot-b.git"},
                    "auth": "ssh-work",
                },
            ],
        )
        with pytest.raises(LayersManifestError, match="duplicate rank"):
            resolve_cli_layer_chain(manifest)

    def test_malformed_entry_raises_layers_manifest_error(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        _write_manifest(
            manifest,
            [
                {
                    "id": "org-acme",
                    "role": "org",
                    "component": "cli",
                    "rank": 30,
                    # missing 'source' entirely
                    "auth": "ssh-work",
                }
            ],
        )
        with pytest.raises(LayersManifestError):
            resolve_cli_layer_chain(manifest)

    def test_missing_layers_key_raises(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        manifest.write_text(yaml.safe_dump({"version": 1}))
        with pytest.raises(LayersManifestError, match="layers"):
            resolve_cli_layer_chain(manifest)

    def test_invalid_yaml_raises(self, tmp_path):
        manifest = tmp_path / "copilot.layers.yml"
        manifest.write_text("layers: [this is not: valid: yaml: [")
        with pytest.raises(LayersManifestError):
            resolve_cli_layer_chain(manifest)


class TestLoadTierOverlay:
    def test_missing_overlay_file_returns_empty_overlay(self, tmp_path):
        overlay = load_tier_overlay(tmp_path / "cli.overlay.yml")
        assert overlay.adopt == ()
        assert overlay.provides == ()
        assert overlay.override == ()
        assert overlay.all_requires_secret() == ()

    def test_parses_adopt_provides_override(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "adopt": [
                        {
                            "service": "uspto",
                            "config": {"uspto_cli_base_url": "https://internal-uspto.example"},
                            "requires_secret": ["USPTO_CLI_API_KEY"],
                        }
                    ],
                    "provides": [
                        {
                            "service": "coolify",
                            "module": "copilot_overlay_internal.services.coolify.commands",
                            "help": "Coolify infrastructure operations",
                            "requires_secret": ["COOLIFY_API_TOKEN"],
                        }
                    ],
                    "override": [
                        {
                            "service": "db",
                            "module": "copilot_overlay_internal.services.db_coolify.commands",
                        }
                    ],
                }
            )
        )
        overlay = load_tier_overlay(overlay_path)

        assert len(overlay.adopt) == 1
        assert overlay.adopt[0].service == "uspto"
        assert overlay.adopt[0].config == {"uspto_cli_base_url": "https://internal-uspto.example"}
        assert overlay.adopt[0].requires_secret == ("USPTO_CLI_API_KEY",)

        assert len(overlay.provides) == 1
        assert overlay.provides[0].service == "coolify"
        assert overlay.provides[0].module == "copilot_overlay_internal.services.coolify.commands"

        assert len(overlay.override) == 1
        assert overlay.override[0].service == "db"

        assert overlay.all_requires_secret() == ("USPTO_CLI_API_KEY", "COOLIFY_API_TOKEN")

    def test_all_requires_secret_dedupes_preserving_order(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {
                    "adopt": [
                        {"service": "uspto", "requires_secret": ["SHARED_NAME", "A"]},
                    ],
                    "provides": [
                        {
                            "service": "extra",
                            "module": "pkg.mod",
                            "requires_secret": ["SHARED_NAME", "B"],
                        },
                    ],
                }
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.all_requires_secret() == ("SHARED_NAME", "A", "B")

    def test_malformed_overlay_entry_raises(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(yaml.safe_dump({"adopt": [{"config": {}}]}))  # missing 'service'
        with pytest.raises(LayersManifestError):
            load_tier_overlay(overlay_path)
