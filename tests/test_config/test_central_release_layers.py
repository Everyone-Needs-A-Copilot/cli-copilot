"""Central snapshots supply CLI tiers; custom or invalid records fail closed."""

import json
import sys
from pathlib import Path

import pytest
import yaml

from copilot_cli.config.layers import LayersManifestError, resolve_cli_layer_chain
from copilot_cli.services._loader import _compose


@pytest.fixture
def central(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    home = tmp_path / "copilot"
    root = home / "releases/20261107T000000Z-fixture"
    root.mkdir(parents=True)
    (home / "current").symlink_to(root, target_is_directory=True)
    monkeypatch.setenv("COPILOT_HOME", str(home))
    monkeypatch.setenv("COPILOT_MIRRORS_ROOT", str(tmp_path / "unused-mirrors"))
    rows, layers = [], []
    for name, tier, rank in [
        ("cli-copilot", "framework", 40),
        ("cli/organization", "organization", 30),
        ("cli/department-accounting", "department-accounting", 20),
        ("cli/personal", "personal", 10),
    ]:
        personal = tier == "personal"
        source = tmp_path / ("source-" + tier)
        source.mkdir()
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if personal:
            target.symlink_to(source, target_is_directory=True)
        else:
            target.mkdir()
        row = {
            "name": name,
            "tier": tier,
            "path": name,
            "kind": "live-link" if personal else "signed-tag",
            "source": str(source),
            "ref": "main" if personal else "v1.2.3",
            "commit": "" if personal else "a" * 40,
            "signer": "" if personal else "SHA256:fixture",
            "version": "" if personal else "1.2.3",
        }
        role = (
            "foundation"
            if tier == "framework"
            else "department"
            if tier.startswith("department-")
            else tier
        )
        layer = {
            "id": name.replace("/", "-"),
            "role": role,
            "rank": rank,
            "product": "cli",
            "activation": "always",
            "source": {
                "repo": str(source),
                "ref": row["ref"],
                "path": str(home / "current" / name),
            },
        }
        if role == "department":
            layer["unit"] = "accounting"
        rows.append(row)
        layers.append(layer)
    metadata = {
        "schema": 1,
        "release": root.name,
        "created": "2026-11-07T00:00:00Z",
        "previous": None,
        "components": rows,
    }
    manifest = tmp_path / "layers.yml"

    def write():
        (root / "release.json").write_text(json.dumps(metadata))
        manifest.write_text(yaml.safe_dump({"version": 1, "layers": layers}))

    write()
    return home, root, metadata, layers, manifest, write


def test_central_snapshot_paths_and_nearest_tier_provenance(central):
    home, root, _, layers, manifest, _ = central
    for name, service in [
        ("organization", "org_service"),
        ("department-accounting", "dept_service"),
    ]:
        (root / "cli" / name / "cli.overlay.yml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "provides": [
                        {"service": service, "module": "fixture.commands", "help": service}
                    ],
                }
            )
        )
    (root / "cli/personal/cli.overlay.yml").write_text(
        yaml.safe_dump(
            {"version": 1, "override": [{"service": "org_service", "module": "personal.commands"}]}
        )
    )
    chain = resolve_cli_layer_chain(manifest)
    assert [row.rank for row in chain] == [10, 20, 30, 40]
    assert [row.root for row in chain] == [
        (home / "current" / row["source"]["path"]).resolve() for row in reversed(layers)
    ]
    services = {row.name: row for row in _compose(chain)}
    assert services["org_service"].tier == "cli-personal"
    assert services["org_service"].package == "personal"
    assert services["dept_service"].tier == "cli-department-accounting"


def test_recorded_checkout_declaration_still_reads_snapshot(central):
    _, root, metadata, layers, manifest, write = central
    for layer, row in zip(layers, metadata["components"], strict=True):
        layer["source"]["path"] = row["source"]
    write()
    chain = resolve_cli_layer_chain(manifest)
    assert chain[-1].root == root / "cli-copilot"
    assert chain[2].root == root / "cli/organization"


@pytest.mark.parametrize(
    "bad",
    [
        "schema",
        "identity",
        "duplicate",
        "path",
        "tier",
        "kind",
        "ref",
        "repo",
        "declared-path",
        "relative-path",
        "signer",
        "commit",
        "policy",
        "subpath",
        "unit",
        "activation",
        "missing",
        "signed-symlink",
        "live-link",
    ],
)
def test_invalid_central_record_never_falls_back_to_mirror(central, bad, tmp_path):
    _, root, metadata, layers, manifest, write = central
    row = metadata["components"][1]
    layer = layers[1]
    if bad == "schema":
        metadata["schema"] = 2
    elif bad == "identity":
        metadata["release"] = "20261107T000000Z-other"
    elif bad == "duplicate":
        metadata["components"].append(dict(row))
    elif bad == "path":
        row["path"] = "../escape"
    elif bad == "tier":
        row["tier"] = "personal"
    elif bad == "kind":
        row["kind"] = "live-link"
    elif bad == "ref":
        layer["source"]["ref"] = "main"
    elif bad == "repo":
        layer["source"]["repo"] = str(tmp_path / "unrelated")
    elif bad == "declared-path":
        layer["source"]["path"] = str(tmp_path / "unrelated")
    elif bad == "relative-path":
        layer["source"]["path"] = "cli/organization"
    elif bad == "signer":
        row["signer"] = ""
    elif bad == "commit":
        row["commit"] = "invalid"
    elif bad == "policy":
        layer["policy"] = {"allowed_signers": ["SHA256:other"]}
    elif bad == "subpath":
        layer["source"]["subpath"] = "other"
    elif bad == "unit":
        layers[2]["unit"] = "../other"
    elif bad == "activation":
        layer["activation"] = "manual"
    elif bad == "missing":
        metadata["components"].pop(1)
    elif bad == "signed-symlink":
        (root / "cli/organization").rename(root / "preserved-org")
        (root / "cli/organization").symlink_to(root / "preserved-org", target_is_directory=True)
    elif bad == "live-link":
        metadata["components"][3]["source"] = str(tmp_path / "unrelated-personal")
    write()
    with pytest.raises(LayersManifestError):
        resolve_cli_layer_chain(manifest)


def test_no_current_pointer_keeps_legacy_mirrors(central):
    home, _, _, _, manifest, _ = central
    (home / "current").rename(home / "preserved-current")
    chain = resolve_cli_layer_chain(manifest)
    assert all("unused-mirrors/mirrors/cli" in str(layer.root) for layer in chain)


def test_dangling_pointer_is_not_legacy_mode(central):
    home, _, _, _, manifest, _ = central
    (home / "current").rename(home / "preserved-current")
    (home / "current").symlink_to(home / "releases/missing")
    with pytest.raises(LayersManifestError):
        resolve_cli_layer_chain(manifest)


@pytest.mark.parametrize(
    "bad", ["boolean-schema", "extra-field", "nonstring-field", "off-store-pointer"]
)
def test_malformed_metadata_and_pointer_are_rejected(central, bad, tmp_path):
    home, _root, metadata, _, manifest, write = central
    if bad == "boolean-schema":
        metadata["schema"] = True
    elif bad == "extra-field":
        metadata["components"][1]["unexpected"] = "custom"
    elif bad == "nonstring-field":
        metadata["components"][1]["signer"] = ["SHA256:fixture"]
    else:
        (home / "current").rename(home / "preserved-current")
        other = tmp_path / "external"
        other.mkdir()
        (home / "current").symlink_to(other, target_is_directory=True)
    write()
    with pytest.raises(LayersManifestError):
        resolve_cli_layer_chain(manifest)


def test_repository_transport_alias_matches_selected_source(central):
    _, _, metadata, layers, manifest, write = central
    metadata["components"][1]["source"] = "https://github.com/Example/cli-layer.git"
    layers[1]["source"]["repo"] = "git@github-work:example/cli-layer.git"
    write()
    assert resolve_cli_layer_chain(manifest)[2].role == "organization"
