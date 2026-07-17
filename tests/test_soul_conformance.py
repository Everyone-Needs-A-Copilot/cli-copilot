"""SOUL.md §6 Quality Bar — mechanical conformance scorecard.

SOUL.md's "Quality Bar" (section 6) lists seven non-negotiables a service
must meet before it counts as *done*. Until this file existed, nothing
enforced them: a service could ship without `health()`, without a test
file, with its own exception hierarchy, or with undocumented config, and
nothing would fail. Per the ecosystem rule "a rule that isn't checked
mechanically is a wish," this file makes each non-negotiable a test.

Service discovery is never hardcoded: `discover_service_groups()` parses
`copilot_cli/main.py`'s own `app.add_typer(...)` registrations via `ast`,
so adding or removing a service updates this suite's coverage on the next
run with zero edits here. The *service* identity used throughout is the
module name under `copilot_cli/services/` (e.g. "nocodb"), not the CLI
verb it's registered under (e.g. "crm") — confirmed against
`_collect_health_checks()` in `main.py`, whose check names are always the
module name, and against `docs/services/*.md` and
`tests/test_services/test_*.py`, which are both named after the module.

Each (service, criterion) pair is its own parametrized test case, so a
`pytest -v` (or the failure list from a plain run) IS the scorecard: one
line per service per non-negotiable. Where SOUL is legitimately violated
*today*, the case is `xfail(strict=True)` with a reason describing the
gap — the suite stays green, but the gap stays visible in `-rxX` output,
and if someone fixes the underlying issue the xfail flips to XPASS and
the suite goes red until the tracking marker is removed. That is the
"gap stays visible, never silently passed" mechanism this file uses.

Criterion (g) — "--json yields clean machine-readable output" — is
exercised once for the shared `health` command plumbing all services run
through, not per service (see TestHealthJSONCleanliness below); testing
JSON-shape once per service would just re-run the same shared code path.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from copilot_cli.config.settings import Settings as SharedSettings
from copilot_cli.main import _collect_health_checks, app
from copilot_cli.shared.output import set_json_mode

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "copilot_cli" / "main.py"
SERVICES_DIR = REPO_ROOT / "copilot_cli" / "services"
TEST_SERVICES_DIR = REPO_ROOT / "tests" / "test_services"
DOCS_SERVICES_DIR = REPO_ROOT / "docs" / "services"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


# ------------------------------------------------------------------ #
# Discovery — service groups come from main.py's app.add_typer calls.
# ------------------------------------------------------------------ #


def discover_service_groups() -> dict[str, str]:
    """Return {service_module_name: cli_command_name} for every service
    registered in main.py, parsed via ast (never hardcoded).
    """
    tree = ast.parse(MAIN_PY.read_text(), filename=str(MAIN_PY))

    alias_to_module: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("services."):
            parts = node.module.split(".")
            if len(parts) >= 2:
                mod = parts[1]
                for alias in node.names:
                    if alias.name == "app":
                        alias_to_module[alias.asname or alias.name] = mod

    module_to_command: dict[str, str] = {}
    for node in ast.walk(tree):
        is_add_typer = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_typer"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "app"
        )
        if not is_add_typer or not node.args or not isinstance(node.args[0], ast.Name):
            continue
        mod = alias_to_module.get(node.args[0].id)
        if mod is None:
            continue
        cmd_name = mod
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                cmd_name = kw.value.value
        module_to_command[mod] = cmd_name

    return module_to_command


SERVICE_GROUPS: dict[str, str] = discover_service_groups()
SERVICE_NAMES: list[str] = sorted(SERVICE_GROUPS)


def test_discovery_found_a_plausible_number_of_services():
    """Guard against the ast parse silently finding zero/one service (a
    main.py refactor that changes the import/add_typer shape would break
    discover_service_groups() silently otherwise)."""
    assert len(SERVICE_NAMES) >= 15, SERVICE_NAMES


# ------------------------------------------------------------------ #
# Known, tracked gaps — today's real SOUL violations. strict=True: if the
# underlying issue is fixed, the xfail becomes an XPASS failure until the
# marker below is deleted, so this table can't silently drift stale.
# ------------------------------------------------------------------ #

KNOWN_GAPS: dict[tuple[str, str], str] = {
    # fireflies and reddit were cut (zero usage signal, no credentials
    # configured for either) -- their KNOWN_GAPS entries are removed along
    # with the services themselves rather than left dangling.
}


def _marks_for(service: str, criterion: str) -> list:
    reason = KNOWN_GAPS.get((service, criterion))
    if reason is None:
        return []
    return [pytest.mark.xfail(reason=reason, strict=True)]


def _cases(criterion: str) -> list:
    return [pytest.param(svc, id=svc, marks=_marks_for(svc, criterion)) for svc in SERVICE_NAMES]


def test_known_gaps_table_only_references_real_services_and_criteria():
    """Catches typos in KNOWN_GAPS before they silently no-op."""
    valid_criteria = {
        "health_registered",
        "test_file_exists",
        "copilot_error_hierarchy",
        "lazy_import",
        "config_documented",
        "docs_entry",
    }
    for service, criterion in KNOWN_GAPS:
        assert service in SERVICE_NAMES, f"KNOWN_GAPS references unknown service {service!r}"
        assert criterion in valid_criteria, f"KNOWN_GAPS references unknown criterion {criterion!r}"


# ------------------------------------------------------------------ #
# (a) health() registered in the health command's check list
# ------------------------------------------------------------------ #


class TestHealthRegistered:
    @pytest.mark.parametrize("service", _cases("health_registered"))
    def test_health_registered(self, service):
        checks, _skipped = _collect_health_checks()
        registered = {name for name, _ in checks}
        assert service in registered, (
            f"'{service}' is not in the executed check list of "
            f"_collect_health_checks() -- `copilot health` will not report it"
        )


# ------------------------------------------------------------------ #
# (b) a dedicated test file exists in tests/test_services/
# ------------------------------------------------------------------ #


def _test_files_for(service: str) -> list[str]:
    prefix = f"test_{service}"
    return sorted(
        f.name
        for f in TEST_SERVICES_DIR.glob("test_*.py")
        if f.stem == prefix or f.stem.startswith(prefix + "_")
    )


class TestDedicatedTestFileExists:
    @pytest.mark.parametrize("service", _cases("test_file_exists"))
    def test_dedicated_test_file_exists(self, service):
        matches = _test_files_for(service)
        assert matches, f"no tests/test_services/test_{service}*.py found"


# ------------------------------------------------------------------ #
# (c) the service raises CopilotError-hierarchy errors
# ------------------------------------------------------------------ #

_ERRORS_IMPORT_RE = re.compile(r"from\s+copilot_cli\.shared\.errors\s+import")


def _uses_copilot_error_hierarchy(service: str) -> bool:
    for py in (SERVICES_DIR / service).rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        if _ERRORS_IMPORT_RE.search(py.read_text(errors="ignore")):
            return True
    return False


class TestCopilotErrorHierarchy:
    @pytest.mark.parametrize("service", _cases("copilot_error_hierarchy"))
    def test_raises_copilot_error_hierarchy(self, service):
        assert _uses_copilot_error_hierarchy(service), (
            f"no file under copilot_cli/services/{service}/ imports "
            f"copilot_cli.shared.errors -- errors are not raised through the "
            f"CopilotError hierarchy (static: import-presence check, see module docstring)"
        )


# ------------------------------------------------------------------ #
# (d) lazy import — no client instantiation at module top level
# ------------------------------------------------------------------ #


def _walk_import_time_nodes(node: ast.AST):
    """Yield nodes that execute at *import* time: module top level and
    class bodies (class-level statements run at import time), pruning
    function/async-function bodies entirely (those only run when called).
    This is a documented static heuristic, not a full data-flow analysis:
    it will not catch instantiation hidden behind e.g. `exec()` or a
    decorator factory, but it does catch the actual failure mode SOUL.md
    names ("importing the module connects to nothing")."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(child, ast.ClassDef):
            yield from _walk_import_time_nodes(child)
            continue
        yield child
        yield from _walk_import_time_nodes(child)


_CLIENT_NAME_RE = re.compile(r"^[A-Z]\w*Client$")


def _find_eager_client_instantiations(service: str) -> list[str]:
    findings: list[str] = []
    for py in sorted((SERVICES_DIR / service).rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(errors="ignore"), filename=str(py))
        except SyntaxError:
            continue
        for node in _walk_import_time_nodes(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name and _CLIENT_NAME_RE.match(name):
                findings.append(f"{py.relative_to(REPO_ROOT)}:{node.lineno}: {name}(...)")
    return findings


class TestLazyImport:
    @pytest.mark.parametrize("service", _cases("lazy_import"))
    def test_no_eager_client_instantiation(self, service):
        findings = _find_eager_client_instantiations(service)
        assert not findings, (
            f"apparent module-import-time *Client(...) instantiation in {service}: {findings}"
        )


# ------------------------------------------------------------------ #
# (e) config vars documented in .env.example
# ------------------------------------------------------------------ #

_ENV_EXAMPLE_TEXT = ENV_EXAMPLE.read_text() if ENV_EXAMPLE.is_file() else ""

_SETTINGS_ATTR_RE = re.compile(r"(?:\bsettings\.|get_settings\(\)\.)(\w+)")

# Settings helper methods that read more than one underlying field --
# each one gets expanded to the fields it actually touches.
_HELPER_METHOD_FIELDS: dict[str, list[str]] = {
    "get_allowed_volumes": ["allowed_volumes"],
    "get_discord_allowed_user_ids": ["discord_allowed_user_ids"],
    "get_backup_dir": ["backup_dir"],
    "get_brevo_api_key": ["brevo_api_key"],
    "get_database_configs": [
        "database_url",
        "nocodb_database_url",
        "n8n_database_url",
        "formbricks_database_url",
    ],
}


def _env_candidates_for_field(field_name: str, field_info) -> list[str]:
    alias = getattr(field_info, "validation_alias", None)
    if alias is not None:
        choices = getattr(alias, "choices", None)
        if choices:
            return [c for c in choices if isinstance(c, str)]
        if isinstance(alias, str):
            return [alias]
    return [field_name.upper()]


def _documented_in_env_example(name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b\s*=", _ENV_EXAMPLE_TEXT) is not None


def _shared_settings_env_gaps(service: str) -> list[str]:
    """Fields the service's own source references on the shared
    `copilot_cli.config.settings.Settings` singleton, for which none of
    the resolved env var name's alias choices appear in .env.example."""
    used_fields: set[str] = set()
    for py in (SERVICES_DIR / service).rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        used_fields.update(_SETTINGS_ATTR_RE.findall(py.read_text(errors="ignore")))

    model_fields = SharedSettings.model_fields
    gaps: list[str] = []
    for attr in sorted(used_fields):
        if attr in _HELPER_METHOD_FIELDS:
            underlying = _HELPER_METHOD_FIELDS[attr]
        elif attr in model_fields:
            underlying = [attr]
        else:
            continue  # not a Settings field/known helper -- not our concern here
        for field_name in underlying:
            info = model_fields.get(field_name)
            if info is None:
                continue
            candidates = _env_candidates_for_field(field_name, info)
            if not any(_documented_in_env_example(c) for c in candidates):
                gaps.append(f"{field_name} (expected one of {candidates} in .env.example)")
    return gaps


def _coolify_env_gaps() -> list[str]:
    from copilot_cli.services.coolify.core.config import (
        APIConfig,
        DefaultsConfig,
        MonitoringConfig,
        SSHConfig,
    )

    gaps: list[str] = []
    for cls in (APIConfig, SSHConfig, DefaultsConfig, MonitoringConfig):
        prefix = cls.model_config.get("env_prefix", "")
        for field_name in cls.model_fields:
            env_name = f"{prefix}{field_name}".upper()
            if not _documented_in_env_example(env_name):
                gaps.append(f"{env_name} ({cls.__name__}.{field_name})")
    return gaps


def _infisical_env_gaps() -> list[str]:
    from copilot_cli.services.infisical.core.config import InfisicalSettings

    prefix = InfisicalSettings.model_config.get("env_prefix", "")
    return [
        f"{prefix}{field_name}".upper()
        for field_name in InfisicalSettings.model_fields
        if not _documented_in_env_example(f"{prefix}{field_name}".upper())
    ]


def config_env_gaps(service: str) -> list[str]:
    if service == "coolify":
        return _coolify_env_gaps()
    if service == "infisical":
        return _infisical_env_gaps()
    return _shared_settings_env_gaps(service)


class TestConfigDocumented:
    @pytest.mark.parametrize("service", _cases("config_documented"))
    def test_config_vars_documented(self, service):
        gaps = config_env_gaps(service)
        assert not gaps, f"{service} references undocumented env var(s): {gaps}"


# ------------------------------------------------------------------ #
# (f) docs/services/ entry exists for the service
# ------------------------------------------------------------------ #


def _docs_entry_exists(service: str) -> bool:
    slug = service.replace("_", "-")
    for f in DOCS_SERVICES_DIR.glob("*.md"):
        if f.name == "00-service-index.md":
            continue
        match = re.match(r"^\d+-(.+)$", f.stem)
        name_part = match.group(1) if match else f.stem
        if name_part == slug:
            return True
    return False


class TestDocsEntryExists:
    @pytest.mark.parametrize("service", _cases("docs_entry"))
    def test_docs_entry_exists(self, service):
        assert _docs_entry_exists(service), f"no docs/services/*.md entry for '{service}'"


# ------------------------------------------------------------------ #
# (g) --json cleanliness for health -- one shared-plumbing test, not
# per service (see module docstring). Every check function is stubbed,
# so this makes zero live network/subprocess/filesystem calls, matching
# SOUL's Lazy & Mockable principle and this repo's existing convention
# in tests/test_services/test_health_completion.py.
# ------------------------------------------------------------------ #


class TestHealthJSONCleanliness:
    def test_json_health_output_parses_cleanly_with_no_rich_leakage(self):
        stub_checks = [(name, lambda: {"healthy": True}) for name in SERVICE_NAMES]
        runner = CliRunner()
        try:
            with mock.patch(
                "copilot_cli.main._collect_health_checks", return_value=(stub_checks, [])
            ):
                result = runner.invoke(app, ["--json", "health"])
        finally:
            set_json_mode(False)

        assert result.exit_code == 0
        # No Rich markup or ANSI escape leakage into --json output.
        assert "[bold]" not in result.output
        assert "\x1b[" not in result.output

        seen: set[str] = set()
        for line in result.output.strip().splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            data = json.loads(line)  # must parse cleanly -- the assertion itself
            assert set(data.keys()) <= {"service", "status", "details"}
            seen.add(data["service"])
        assert seen == set(SERVICE_NAMES)


# ------------------------------------------------------------------ #
# PART 2 — Portability (SOUL Principle 3): the binary must resolve its
# config from COPILOT_ENV_FILE when invoked from a directory that is not
# this repo, proving "the exact command works in any project with only a
# different .env." Env-file resolution is baked into the Settings class's
# model_config at *module import time* (see copilot_cli/config/settings.py
# _find_env_file()), so in-process monkeypatching of os.environ or cwd
# cannot exercise it once the module is already imported in this pytest
# process -- a genuinely separate interpreter (subprocess) is required.
# ------------------------------------------------------------------ #


class TestPortability:
    def test_env_resolution_order_from_foreign_directory(self, tmp_path):
        """A fresh interpreter, cwd outside this repo, COPILOT_ENV_FILE
        pointing at a synthetic env file: the loaded setting must come
        from that file, not from this repo's own .env or an empty
        default -- proving COPILOT_ENV_FILE resolution works foreign-cwd."""
        foreign_cwd = tmp_path / "not-this-repo"
        foreign_cwd.mkdir()
        env_file = tmp_path / "synthetic.env"
        sentinel = "portability-sentinel-93f2"
        env_file.write_text(f"GIT_USER_NAME={sentinel}\n")

        env = {**os.environ, "COPILOT_ENV_FILE": str(env_file)}
        script = (
            "from copilot_cli.config.settings import get_settings; "
            "print(get_settings().git_user_name)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(foreign_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == sentinel

    def test_cli_help_runs_from_foreign_cwd(self, tmp_path):
        """`copilot --help` from a foreign cwd, with COPILOT_ENV_FILE set
        to .env.example, must succeed without any import-time connection
        error -- --help never touches a client, so this makes zero
        network calls by construction."""
        foreign_cwd = tmp_path / "not-this-repo"
        foreign_cwd.mkdir()
        assert ENV_EXAMPLE.is_file()

        env = {**os.environ, "COPILOT_ENV_FILE": str(ENV_EXAMPLE)}
        result = subprocess.run(
            [sys.executable, "-m", "copilot_cli.main", "--help"],
            cwd=str(foreign_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    def test_json_health_runs_from_foreign_cwd(self, tmp_path, monkeypatch):
        """`copilot --json health` invoked with a foreign cwd and
        COPILOT_ENV_FILE set must produce clean per-service JSON lines.
        Every check function is stubbed (mocked per repo convention, see
        TestHealthJSONCleanliness above) so this makes zero live network
        calls; the live E2E equivalent already exists gated behind
        COPILOT_E2E_LIVE in tests/e2e/test_cli_connectivity.py."""
        foreign_cwd = tmp_path / "not-this-repo"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)
        monkeypatch.setenv("COPILOT_ENV_FILE", str(ENV_EXAMPLE))

        stub_checks = [(name, lambda: {"healthy": True}) for name in SERVICE_NAMES]
        runner = CliRunner()
        try:
            with mock.patch(
                "copilot_cli.main._collect_health_checks", return_value=(stub_checks, [])
            ):
                result = runner.invoke(app, ["--json", "health"])
        finally:
            set_json_mode(False)

        assert result.exit_code == 0
        json_lines = [ln for ln in result.output.strip().splitlines() if ln.strip().startswith("{")]
        assert len(json_lines) == len(SERVICE_NAMES)
        for line in json_lines:
            json.loads(line)  # must parse cleanly
