"""Unit tests for `services/_loader.py` -- the manifest-driven
service-discovery loader (tier-inheritance design §2, Option C). Exercises
the composition mechanics (adopt/provides/override, nearest-tier-wins) that
Phase 1 ships but does not yet exercise in production (no manifest exists
anywhere on the machine). The Phase-1 hard-gate ("no manifest -> base 12,
byte-identical") lives in `tests/test_tier_inheritance_parity.py`.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from copilot_cli.config.layers import CliLayer, LayersManifestError
from copilot_cli.services._loader import _BASE_SERVICES, _compose, load_service


def _layer(tmp_path, layer_id: str, rank: int, subdir: str | None = None) -> CliLayer:
    root = tmp_path / (subdir or layer_id)
    root.mkdir(parents=True, exist_ok=True)
    return CliLayer(
        id=layer_id,
        role="org",
        rank=rank,
        repo=f"git@github-work:acme/{layer_id}.git",
        ref="main",
        auth="ssh-work",
        root=root,
    )


def _write_overlay_pkg(root, pkg_name: str, subpath: str, app_var: str = "app") -> None:
    """Write a minimal importable Typer-app module under `root/pkg_name/subpath`."""
    parts = pkg_name.split(".") + subpath.split(".")
    current = root
    for i, part in enumerate(parts):
        current = current / part
        if i < len(parts) - 1:
            current.mkdir(parents=True, exist_ok=True)
            init = current / "__init__.py"
            if not init.exists():
                init.write_text("")
    module_path = current.with_suffix(".py")
    module_path.write_text(
        textwrap.dedent(
            f"""
            import typer

            {app_var} = typer.Typer(name="{pkg_name}.{subpath}")
            """
        )
    )


@pytest.fixture(autouse=True)
def _clean_sys_path_and_modules():
    before_path = list(sys.path)
    before_modules = set(sys.modules)
    yield
    sys.path[:] = before_path
    for name in list(sys.modules):
        if name not in before_modules:
            del sys.modules[name]


class TestComposeAdopt:
    def test_adopt_keeps_base_module_marks_provenance(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        (layer.root / "cli.overlay.yml").write_text(
            "adopt:\n"
            "  - service: uspto\n"
            "    config:\n"
            "      uspto_cli_base_url: https://internal-uspto.example\n"
            "    requires_secret:\n"
            "      - USPTO_CLI_API_KEY\n"
        )

        resolved = _compose([layer])
        by_name = {svc.name: svc for svc in resolved}

        uspto = by_name["uspto"]
        assert uspto.tier == "org-acme"
        assert uspto.mode == "adopt"
        # Zero code -- same package/module as base.
        base_uspto = next(s for s in _BASE_SERVICES if s.name == "uspto")
        assert uspto.package == base_uspto.package
        assert uspto.commands_module == base_uspto.commands_module

        # Every other service is untouched.
        for svc in resolved:
            if svc.name != "uspto":
                assert svc.tier == "foundation"
                assert svc.mode == "base"

    def test_adopt_unknown_service_raises(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        (layer.root / "cli.overlay.yml").write_text(
            "adopt:\n  - service: not-a-real-service\n"
        )
        with pytest.raises(LayersManifestError, match="unknown base service"):
            _compose([layer])


class TestComposeProvides:
    def test_provides_adds_a_new_service_from_overlay_package(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        _write_overlay_pkg(layer.root, "copilot_overlay_test_provides", "services.coolify.commands")
        (layer.root / "cli.overlay.yml").write_text(
            "provides:\n"
            "  - service: coolify\n"
            "    module: copilot_overlay_test_provides.services.coolify.commands\n"
            "    help: Coolify infrastructure operations\n"
        )

        resolved = _compose([layer])
        by_name = {svc.name: svc for svc in resolved}

        assert "coolify" in by_name
        coolify = by_name["coolify"]
        assert coolify.tier == "org-acme"
        assert coolify.mode == "provides"
        assert coolify.help == "Coolify infrastructure operations"

        # The overlay module is genuinely importable via the loader's own
        # sys.path insertion -- proves the git-synced path-import mechanism
        # (D2), not just data-shape correctness.
        app = coolify.app
        assert app is not None

        # Base 12 are untouched and still present.
        assert len(resolved) == len(_BASE_SERVICES) + 1

    def test_provides_colliding_with_existing_name_without_override_is_refused(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        _write_overlay_pkg(layer.root, "copilot_overlay_test_collide", "services.uspto.commands")
        (layer.root / "cli.overlay.yml").write_text(
            "provides:\n"
            "  - service: uspto\n"
            "    module: copilot_overlay_test_collide.services.uspto.commands\n"
        )
        with pytest.raises(LayersManifestError, match="collides"):
            _compose([layer])


class TestComposeOverride:
    def test_override_replaces_base_service_module_keeps_base_help(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        _write_overlay_pkg(layer.root, "copilot_overlay_test_override", "services.db_coolify.commands")
        (layer.root / "cli.overlay.yml").write_text(
            "override:\n"
            "  - service: db\n"
            "    module: copilot_overlay_test_override.services.db_coolify.commands\n"
        )

        resolved = _compose([layer])
        by_name = {svc.name: svc for svc in resolved}

        db = by_name["db"]
        assert db.tier == "org-acme"
        assert db.mode == "override"
        assert db.package == "copilot_overlay_test_override.services.db_coolify"
        base_db = next(s for s in _BASE_SERVICES if s.name == "db")
        assert db.help == base_db.help  # help text preserved from base

    def test_override_unknown_service_raises(self, tmp_path):
        layer = _layer(tmp_path, "org-acme", rank=30)
        (layer.root / "cli.overlay.yml").write_text(
            "override:\n  - service: not-a-real-service\n    module: some.module\n"
        )
        with pytest.raises(LayersManifestError, match="unknown service"):
            _compose([layer])


class TestPrecedenceNearestWins:
    def test_higher_precedence_tier_wins_when_both_override_the_same_service(self, tmp_path):
        org_layer = _layer(tmp_path, "org-acme", rank=30, subdir="org")
        personal_layer = _layer(tmp_path, "personal-pablo", rank=10, subdir="personal")

        _write_overlay_pkg(org_layer.root, "copilot_overlay_org", "services.db_org.commands")
        (org_layer.root / "cli.overlay.yml").write_text(
            "override:\n  - service: db\n    module: copilot_overlay_org.services.db_org.commands\n"
        )
        _write_overlay_pkg(personal_layer.root, "copilot_overlay_personal", "services.db_personal.commands")
        (personal_layer.root / "cli.overlay.yml").write_text(
            "override:\n"
            "  - service: db\n"
            "    module: copilot_overlay_personal.services.db_personal.commands\n"
        )

        # resolve_cli_layer_chain() returns highest-precedence first:
        # personal (rank 10) then org (rank 30).
        chain = [personal_layer, org_layer]
        resolved = _compose(chain)
        by_name = {svc.name: svc for svc in resolved}

        assert by_name["db"].tier == "personal-pablo"
        assert by_name["db"].package == "copilot_overlay_personal.services.db_personal"


class TestLoadService:
    def test_load_service_returns_none_for_unknown_name(self):
        assert load_service("definitely-not-a-service") is None

    def test_load_service_returns_base_entry_by_name(self):
        svc = load_service("git")
        assert svc is not None
        assert svc.name == "git"
        assert svc.package == "copilot_cli.services.git"
