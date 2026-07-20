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


class TestRequiresSecretRoutingHint:
    """Item #3: the optional per-`requires_secret` `from:` routing hint.
    Bare-string entries (the pre-existing shape) must keep parsing/resolving
    exactly as before; the new mapping form only ever ADDS a hint alongside
    the unchanged `requires_secret` name tuple -- see `_parse_requires_secret`
    and `secrets_ladder._RUNG_SUBSET_FOR_HINT`."""

    def test_bare_string_entries_are_back_compat(self, tmp_path):
        """A plain `requires_secret: [NAME]` list -- today's only shape --
        still parses into the identical `requires_secret` tuple with an EMPTY
        hints map (default `"any"`, i.e. unrestricted/current behavior)."""
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {"adopt": [{"service": "uspto", "requires_secret": ["USPTO_CLI_API_KEY"]}]}
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.adopt[0].requires_secret == ("USPTO_CLI_API_KEY",)
        assert overlay.adopt[0].requires_secret_hints == {}
        assert overlay.all_requires_secret() == ("USPTO_CLI_API_KEY",)
        assert overlay.all_requires_secret_hints() == {}

    def test_mapping_form_parses_name_and_hint(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {
                    "provides": [
                        {
                            "service": "discord",
                            "module": "pkg.mod",
                            "requires_secret": [{"name": "DISCORD_BOT_TOKEN", "from": "keychain"}],
                        }
                    ]
                }
            )
        )
        overlay = load_tier_overlay(overlay_path)
        # The name still lands in the unchanged bare tuple -- every existing
        # reader (`all_requires_secret`, `_loader.py`, `SecretRefSource`'s
        # `_collect_secret_names` set-membership check) keeps working.
        assert overlay.provides[0].requires_secret == ("DISCORD_BOT_TOKEN",)
        assert overlay.provides[0].requires_secret_hints == {"DISCORD_BOT_TOKEN": "keychain"}
        assert overlay.all_requires_secret() == ("DISCORD_BOT_TOKEN",)
        assert overlay.all_requires_secret_hints() == {"DISCORD_BOT_TOKEN": "keychain"}

    def test_mapping_form_store_hint(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {"adopt": [{"service": "uspto", "requires_secret": [{"name": "X", "from": "store"}]}]}
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.adopt[0].requires_secret == ("X",)
        assert overlay.adopt[0].requires_secret_hints == {"X": "store"}

    def test_mapping_form_explicit_any_is_not_stored_as_a_hint(self, tmp_path):
        """`from: any` is the default -- explicitly spelling it out must not
        appear in `requires_secret_hints` (keeps the "absent == any" contract
        `SecretRefSource` relies on via `dict.get(name)` -> `None`)."""
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {"adopt": [{"service": "uspto", "requires_secret": [{"name": "X", "from": "any"}]}]}
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.adopt[0].requires_secret == ("X",)
        assert overlay.adopt[0].requires_secret_hints == {}

    def test_mixed_bare_and_mapping_entries_preserve_order(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {
                    "adopt": [
                        {
                            "service": "uspto",
                            "requires_secret": [
                                "PLAIN_ONE",
                                {"name": "HINTED", "from": "keychain"},
                                "PLAIN_TWO",
                            ],
                        }
                    ]
                }
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.adopt[0].requires_secret == ("PLAIN_ONE", "HINTED", "PLAIN_TWO")
        assert overlay.adopt[0].requires_secret_hints == {"HINTED": "keychain"}

    def test_invalid_from_value_raises(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {"adopt": [{"service": "uspto", "requires_secret": [{"name": "X", "from": "cloud"}]}]}
            )
        )
        with pytest.raises(LayersManifestError, match="'from' must be one of"):
            load_tier_overlay(overlay_path)

    def test_mapping_entry_missing_name_raises(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump({"adopt": [{"service": "uspto", "requires_secret": [{"from": "keychain"}]}]})
        )
        with pytest.raises(LayersManifestError, match="missing required key 'name'"):
            load_tier_overlay(overlay_path)

    def test_non_string_non_mapping_entry_raises(self, tmp_path):
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump({"adopt": [{"service": "uspto", "requires_secret": [123]}]})
        )
        with pytest.raises(LayersManifestError, match="must be a string or a"):
            load_tier_overlay(overlay_path)

    def test_hints_merge_across_adopt_provides_override_nearest_first_wins(self, tmp_path):
        """`all_requires_secret_hints()` merges all three sections; a
        duplicate name's FIRST declaration wins, mirroring
        `all_requires_secret()`'s own dedup order."""
        overlay_path = tmp_path / "cli.overlay.yml"
        overlay_path.write_text(
            yaml.safe_dump(
                {
                    "adopt": [
                        {"service": "a", "requires_secret": [{"name": "SHARED", "from": "keychain"}]}
                    ],
                    "provides": [
                        {
                            "service": "b",
                            "module": "pkg.mod",
                            "requires_secret": [{"name": "SHARED", "from": "store"}],
                        }
                    ],
                }
            )
        )
        overlay = load_tier_overlay(overlay_path)
        assert overlay.all_requires_secret_hints() == {"SHARED": "keychain"}
