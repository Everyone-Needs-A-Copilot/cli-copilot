"""Comprehensive tests for the Skill runtime service.

Covers:
- Frontmatter parsing (valid, missing fields, execution spec, no frontmatter)
- Quality tests extraction
- Skill discovery (local, shared, env paths)
- list / show / health
- Parameter validation and coercion
- Interpolation ({{ params.x }})
- Condition evaluation (skip_if)
- Plan (dry-run)
- Execution engine (run)
- Verification engine (verify)
- Audit engine (15-check audit)
- CLI commands
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.shared.errors import CopilotError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Helpers — create on-disk skill directories for testing
# ---------------------------------------------------------------------------


def _write_skill(tmp_path: Path, name: str, frontmatter: str, body: str = "") -> Path:
    """Create a minimal skill directory with SKILL.md."""
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")
    return skill_dir


BASIC_FRONTMATTER = textwrap.dedent("""\
    ---
    name: test-skill
    description: A test skill
    triggers:
      keywords:
        - test
        - example
    allowed-tools: Read, Write
    ---
    """)

BASIC_BODY = textwrap.dedent("""\

    ## Overview
    A simple test skill.

    ## Instructions
    Do things.

    ## Examples
    Example here.

    ## Guidelines
    Be careful.

    ## Error Handling
    Handle errors.

    ## Define Done
    - [ ] It works

    ## Quality Tests
    ### Smoke Test
    - **PASS:** It runs without errors
    - **FAIL:** It crashes
    """)


EXEC_FRONTMATTER = textwrap.dedent("""\
    ---
    name: exec-skill
    description: An executable skill
    triggers:
      keywords:
        - exec
    execution:
      params:
        - name: target
          type: string
          required: true
          description: Target name
        - name: verbose
          type: bool
          required: false
          default: "false"
          description: Enable verbose output
        - name: count
          type: int
          required: false
          default: "5"
          description: Repeat count
      steps:
        - name: greet
          command: echo "Hello {{ params.target }}"
        - name: optional-step
          command: echo "Verbose output"
          skip_if: "not params.verbose"
      verify:
        - name: check-greeting
          command: echo "Hello World"
          expect: 'exit_code == 0'
        - name: check-output
          command: echo "Hello World"
          expect: 'stdout contains "Hello"'
    ---
    """)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def skill_dir(tmp_path):
    """Create a local skills directory with sample skills."""
    skills_root = tmp_path / ".claude" / "skills"
    skills_root.mkdir(parents=True)

    # Basic skill (documentation-only)
    _write_skill(skills_root, "test-skill", BASIC_FRONTMATTER, BASIC_BODY)

    # Executable skill
    _write_skill(skills_root, "exec-skill", EXEC_FRONTMATTER, BASIC_BODY)

    # Skill with scripts
    script_skill = _write_skill(
        skills_root,
        "scripted-skill",
        textwrap.dedent("""\
            ---
            name: scripted-skill
            description: A skill with scripts
            execution:
              params:
                - name: name
                  type: string
                  required: true
              steps:
                - name: run-script
                  script: scripts/hello.sh
                  args:
                    - "{{ params.name }}"
            ---
            """),
        BASIC_BODY,
    )
    scripts_dir = script_skill / "scripts"
    scripts_dir.mkdir()
    hello_script = scripts_dir / "hello.sh"
    hello_script.write_text('#!/usr/bin/env bash\nset -euo pipefail\necho "Hello $1"\n')
    hello_script.chmod(0o755)

    # Skill with reference/
    ref_skill = _write_skill(
        skills_root,
        "ref-skill",
        textwrap.dedent("""\
            ---
            name: ref-skill
            description: A skill with reference files
            ---
            """),
        BASIC_BODY,
    )
    ref_dir = ref_skill / "reference"
    ref_dir.mkdir()
    (ref_dir / "patterns.md").write_text("# Patterns\n")

    return tmp_path


@pytest.fixture
def shared_dir(tmp_path):
    """Create a shared skills directory."""
    shared = tmp_path / "shared-skills"
    shared.mkdir()
    _write_skill(
        shared,
        "shared-skill",
        textwrap.dedent("""\
            ---
            name: shared-skill
            description: A shared skill
            triggers:
              keywords:
                - shared
            ---
            """),
        BASIC_BODY,
    )
    return shared


@pytest.fixture
def client(skill_dir, monkeypatch):
    """Create a SkillClient pointed at the test skill directory."""
    monkeypatch.chdir(skill_dir)
    monkeypatch.delenv("SKILL_PATHS", raising=False)

    from copilot_cli.services.skill.client import SkillClient

    return SkillClient()


@pytest.fixture
def client_with_shared(skill_dir, shared_dir, monkeypatch):
    """SkillClient with both local and shared paths."""
    monkeypatch.chdir(skill_dir)
    monkeypatch.setenv("SKILL_PATHS", str(shared_dir))

    from copilot_cli.services.skill.client import SkillClient

    return SkillClient()


# ======================================================================
# Frontmatter Parsing
# ======================================================================


class TestParseFrontmatter:
    """SkillClient._parse_frontmatter static method."""

    def test_basic_frontmatter(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter(BASIC_FRONTMATTER)
        assert fm is not None
        assert fm.name == "test-skill"
        assert fm.description == "A test skill"
        assert fm.execution is None

    def test_execution_spec_frontmatter(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter(EXEC_FRONTMATTER)
        assert fm is not None
        assert fm.name == "exec-skill"
        assert fm.execution is not None
        assert len(fm.execution.params) == 3
        assert fm.execution.params[0].name == "target"
        assert fm.execution.params[0].required is True
        assert len(fm.execution.steps) == 2
        assert fm.execution.steps[0].command == 'echo "Hello {{ params.target }}"'
        assert fm.execution.steps[1].skip_if == "not params.verbose"
        assert len(fm.execution.verify) == 2

    def test_no_frontmatter(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter("# Just a heading\nNo frontmatter here.")
        assert fm is None

    def test_incomplete_frontmatter_no_close(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter("---\nname: broken\n")
        assert fm is None

    def test_frontmatter_missing_name(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter("---\ndescription: no name\n---\n")
        assert fm is None

    def test_triggers_keywords(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter(BASIC_FRONTMATTER)
        assert fm is not None
        assert "keywords" in fm.triggers
        assert "test" in fm.triggers["keywords"]

    def test_allowed_tools(self):
        from copilot_cli.services.skill.client import SkillClient

        fm = SkillClient._parse_frontmatter(BASIC_FRONTMATTER)
        assert fm is not None
        assert fm.allowed_tools == "Read, Write"


# ======================================================================
# Quality Tests Extraction
# ======================================================================


class TestParseQualityTests:
    """SkillClient._parse_quality_tests static method."""

    def test_extracts_quality_tests(self):
        from copilot_cli.services.skill.client import SkillClient

        tests = SkillClient._parse_quality_tests(BASIC_BODY)
        assert len(tests) == 1
        assert tests[0]["name"] == "Smoke Test"
        assert "runs without errors" in tests[0]["pass"]
        assert "crashes" in tests[0]["fail"]

    def test_no_quality_tests_section(self):
        from copilot_cli.services.skill.client import SkillClient

        tests = SkillClient._parse_quality_tests("# No quality tests\nJust text.")
        assert tests == []

    def test_multiple_quality_tests(self):
        from copilot_cli.services.skill.client import SkillClient

        content = textwrap.dedent("""\
            ## Quality Tests
            ### Test A
            - **PASS:** A passes
            - **FAIL:** A fails
            ### Test B
            - **PASS:** B passes
            - **FAIL:** B fails
            ## Next Section
            """)
        tests = SkillClient._parse_quality_tests(content)
        assert len(tests) == 2
        assert tests[0]["name"] == "Test A"
        assert tests[1]["name"] == "Test B"


# ======================================================================
# Discovery
# ======================================================================


class TestDiscovery:
    """Skill discovery from local and shared paths."""

    def test_discovers_local_skills(self, client):
        skills = client.list_skills()
        names = [s.name for s in skills]
        assert "test-skill" in names
        assert "exec-skill" in names
        assert "scripted-skill" in names
        assert "ref-skill" in names

    def test_discovers_shared_skills(self, client_with_shared):
        skills = client_with_shared.list_skills()
        names = [s.name for s in skills]
        assert "shared-skill" in names

    def test_local_overrides_shared(self, skill_dir, shared_dir, monkeypatch):
        """Local skill with same name should override shared."""
        # Add a skill with same name to shared
        _write_skill(
            shared_dir,
            "test-skill",
            textwrap.dedent("""\
                ---
                name: test-skill
                description: Shared version
                ---
                """),
        )
        monkeypatch.chdir(skill_dir)
        monkeypatch.setenv("SKILL_PATHS", str(shared_dir))

        from copilot_cli.services.skill.client import SkillClient

        c = SkillClient()
        skill = c.get_skill("test-skill")
        assert skill.source == "local"  # Local wins
        assert skill.description == "A test skill"  # Local description

    def test_source_filtering(self, client_with_shared):
        local = client_with_shared.list_skills(source="local")
        shared = client_with_shared.list_skills(source="shared")
        assert all(s.source == "local" for s in local)
        assert all(s.source == "shared" for s in shared)

    def test_executable_filter(self, client):
        executable = client.list_skills(executable_only=True)
        names = [s.name for s in executable]
        assert "exec-skill" in names
        assert "scripted-skill" in names
        assert "test-skill" not in names  # doc-only

    def test_scripts_detected(self, client):
        skill = client.get_skill("scripted-skill")
        assert skill.has_scripts is True
        assert skill.script_count == 1

    def test_reference_detected(self, client):
        skill = client.get_skill("ref-skill")
        assert skill.has_reference is True
        assert skill.reference_count == 1

    def test_skill_not_found(self, client):
        with pytest.raises(NotFoundError, match="not found"):
            client.get_skill("nonexistent-skill")


# ======================================================================
# Health
# ======================================================================


class TestHealth:
    """SkillClient.health method."""

    def test_healthy(self, client):
        result = client.health()
        assert result["healthy"] is True
        assert result["skill_count"] >= 4

    def test_executable_count(self, client):
        result = client.health()
        assert result["executable_count"] >= 2  # exec-skill + scripted-skill

    def test_sources_reported(self, client):
        result = client.health()
        assert "sources" in result
        assert any(s["type"] == "local" for s in result["sources"])


# ======================================================================
# Parameter Validation
# ======================================================================


class TestValidateParams:
    """SkillClient._validate_params static method."""

    def test_required_param_provided(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="target", type="string", required=True)])
        result = SkillClient._validate_params(spec, {"target": "hello"})
        assert result["target"] == "hello"

    def test_required_param_missing_raises(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="target", type="string", required=True)])
        with pytest.raises(ValidationError, match="Required parameter"):
            SkillClient._validate_params(spec, {})

    def test_optional_with_default(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(
            params=[SkillParam(name="count", type="int", required=False, default="5")]
        )
        result = SkillClient._validate_params(spec, {})
        assert result["count"] == 5

    def test_optional_no_default(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="flag", type="bool", required=False)])
        result = SkillClient._validate_params(spec, {})
        assert result["flag"] is None

    def test_int_coercion(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="n", type="int", required=True)])
        result = SkillClient._validate_params(spec, {"n": "42"})
        assert result["n"] == 42

    def test_float_coercion(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="ratio", type="float", required=True)])
        result = SkillClient._validate_params(spec, {"ratio": "3.14"})
        assert result["ratio"] == pytest.approx(3.14)

    def test_bool_coercion_true(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="flag", type="bool", required=True)])
        for truthy in ("true", "1", "yes", "True", "YES"):
            result = SkillClient._validate_params(spec, {"flag": truthy})
            assert result["flag"] is True

    def test_bool_coercion_false(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="flag", type="bool", required=True)])
        result = SkillClient._validate_params(spec, {"flag": "false"})
        assert result["flag"] is False

    def test_path_coercion(self):
        from copilot_cli.services.skill.client import SkillClient
        from copilot_cli.services.skill.models import ExecutionSpec, SkillParam

        spec = ExecutionSpec(params=[SkillParam(name="dir", type="path", required=True)])
        result = SkillClient._validate_params(spec, {"dir": "/tmp"})
        assert result["dir"] == str(Path("/tmp").resolve())


# ======================================================================
# Interpolation
# ======================================================================


class TestInterpolation:
    """SkillClient._interpolate static method."""

    def test_simple_replacement(self):
        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient._interpolate("echo {{ params.name }}", {"name": "world"})
        assert result == "echo world"

    def test_multiple_replacements(self):
        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient._interpolate("{{ params.a }} and {{ params.b }}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_param_left_unchanged(self):
        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient._interpolate("echo {{ params.missing }}", {"other": "val"})
        assert "{{ params.missing }}" in result

    def test_non_params_key_left_unchanged(self):
        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient._interpolate("echo {{ env.HOME }}", {"HOME": "/home"})
        assert "{{ env.HOME }}" in result

    def test_whitespace_tolerant(self):
        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient._interpolate("echo {{params.x}}", {"x": "tight"})
        assert result == "echo tight"


# ======================================================================
# Condition Evaluation
# ======================================================================


class TestEvaluateCondition:
    """SkillClient._evaluate_condition static method."""

    def test_truthy_param(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("params.verbose", {"verbose": True}) is True

    def test_falsy_param(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("params.verbose", {"verbose": False}) is False

    def test_not_truthy(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("not params.verbose", {"verbose": True}) is False

    def test_not_falsy(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("not params.verbose", {"verbose": False}) is True

    def test_missing_param_is_falsy(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("params.missing", {}) is False

    def test_unknown_condition_returns_false(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_condition("something_else", {}) is False


# ======================================================================
# Expect Evaluation
# ======================================================================


class TestEvaluateExpect:
    """SkillClient._evaluate_expect static method."""

    def test_exit_code_equals_zero(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_expect("exit_code == 0", 0, "") is True
        assert SkillClient._evaluate_expect("exit_code == 0", 1, "") is False

    def test_exit_code_not_equals(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_expect("exit_code != 0", 1, "") is True
        assert SkillClient._evaluate_expect("exit_code != 0", 0, "") is False

    def test_stdout_contains(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_expect('stdout contains "Hello"', 0, "Hello World") is True
        assert SkillClient._evaluate_expect('stdout contains "Bye"', 0, "Hello World") is False

    def test_default_is_exit_zero(self):
        from copilot_cli.services.skill.client import SkillClient

        assert SkillClient._evaluate_expect("unknown expression", 0, "") is True
        assert SkillClient._evaluate_expect("unknown expression", 1, "") is False


# ======================================================================
# Plan (Dry Run)
# ======================================================================


class TestPlan:
    """SkillClient.plan method."""

    def test_plan_shows_steps(self, client):
        steps = client.plan("exec-skill", {"target": "World"})
        assert len(steps) == 2
        assert steps[0]["name"] == "greet"
        assert steps[0]["action"] == "RUN COMMAND"
        assert "Hello World" in steps[0]["command"]

    def test_plan_skip_condition(self, client):
        # verbose is false by default → "not params.verbose" is True → skip
        steps = client.plan("exec-skill", {"target": "World", "verbose": "false"})
        assert steps[1]["action"] == "SKIP"

    def test_plan_no_skip_when_condition_false(self, client):
        steps = client.plan("exec-skill", {"target": "World", "verbose": "true"})
        assert steps[1]["action"] == "RUN COMMAND"

    def test_plan_missing_required_param(self, client):
        with pytest.raises(ValidationError, match="Required parameter"):
            client.plan("exec-skill", {})

    def test_plan_doc_only_skill_raises(self, client):
        with pytest.raises(CopilotError, match="documentation-only"):
            client.plan("test-skill", {})

    def test_plan_script_step(self, client):
        steps = client.plan("scripted-skill", {"name": "Alice"})
        assert len(steps) == 1
        assert steps[0]["action"] == "RUN SCRIPT"
        assert "hello.sh" in steps[0]["command"]
        assert "Alice" in steps[0]["command"]


# ======================================================================
# Run (Execution)
# ======================================================================


class TestRun:
    """SkillClient.run method."""

    def test_run_command_step(self, client):
        result = client.run("exec-skill", {"target": "World"})
        assert result.skill_name == "exec-skill"
        assert result.status == "success"
        assert len(result.steps) == 2
        # First step: echo "Hello World"
        assert result.steps[0].status == "success"
        assert "Hello World" in result.steps[0].stdout
        assert result.steps[0].duration_ms >= 0

    def test_run_skipped_step(self, client):
        result = client.run("exec-skill", {"target": "World", "verbose": "false"})
        assert result.steps[1].status == "skipped"

    def test_run_with_verbose(self, client):
        result = client.run("exec-skill", {"target": "World", "verbose": "true"})
        assert result.steps[1].status == "success"
        assert "Verbose" in result.steps[1].stdout

    def test_run_script_step(self, client):
        result = client.run("scripted-skill", {"name": "Alice"})
        assert result.status == "success"
        assert result.steps[0].status == "success"
        assert "Hello Alice" in result.steps[0].stdout

    def test_run_failing_command(self, skill_dir, monkeypatch):
        """A step with a failing command stops execution."""
        skills_root = skill_dir / ".claude" / "skills"
        _write_skill(
            skills_root,
            "fail-skill",
            textwrap.dedent("""\
                ---
                name: fail-skill
                description: A skill that fails
                execution:
                  steps:
                    - name: will-fail
                      command: "exit 1"
                    - name: never-reached
                      command: echo "should not run"
                ---
                """),
        )
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)

        from copilot_cli.services.skill.client import SkillClient

        c = SkillClient()
        result = c.run("fail-skill", {})
        assert result.status == "failed"
        assert result.steps[0].status == "failed"
        assert result.steps[0].exit_code == 1
        assert len(result.steps) == 1  # Second step not executed

    def test_run_missing_script(self, skill_dir, monkeypatch):
        """A step referencing a missing script returns failed."""
        skills_root = skill_dir / ".claude" / "skills"
        _write_skill(
            skills_root,
            "missing-script-skill",
            textwrap.dedent("""\
                ---
                name: missing-script-skill
                description: Skill with missing script
                execution:
                  steps:
                    - name: missing
                      script: scripts/nonexistent.sh
                ---
                """),
        )
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)

        from copilot_cli.services.skill.client import SkillClient

        c = SkillClient()
        result = c.run("missing-script-skill", {})
        assert result.status == "failed"
        assert "Script not found" in result.steps[0].stderr

    def test_run_params_used_recorded(self, client):
        result = client.run("exec-skill", {"target": "World"})
        assert result.params_used["target"] == "World"

    def test_run_duration_recorded(self, client):
        result = client.run("exec-skill", {"target": "World"})
        assert result.duration_ms >= 0


# ======================================================================
# Verify
# ======================================================================


class TestVerify:
    """SkillClient.verify method."""

    def test_verify_passing_checks(self, client):
        results = client.verify("exec-skill", {"target": "World"})
        assert len(results) == 2
        assert all(r.status == "pass" for r in results)

    def test_verify_exit_code_check(self, client):
        results = client.verify("exec-skill", {"target": "World"})
        assert results[0].check_name == "check-greeting"
        assert results[0].exit_code == 0

    def test_verify_stdout_contains_check(self, client):
        results = client.verify("exec-skill", {"target": "World"})
        assert results[1].check_name == "check-output"
        assert results[1].status == "pass"

    def test_verify_no_checks_raises(self, client):
        with pytest.raises(CopilotError, match="no executable verify checks"):
            client.verify("test-skill", {})

    def test_verify_result_structure(self, client):
        results = client.verify("exec-skill", {"target": "World"})
        r = results[0]
        assert hasattr(r, "check_name")
        assert hasattr(r, "status")
        assert hasattr(r, "command")
        assert hasattr(r, "exit_code")
        assert hasattr(r, "expectation")


# ======================================================================
# Audit
# ======================================================================


class TestAudit:
    """SkillClient.audit and audit_single methods."""

    def test_audit_single_full_skill(self, client):
        skill = client.get_skill("test-skill")
        result = client.audit_single(Path(skill.path))
        assert result.skill_name == "test-skill"
        assert result.total_count == 15
        # test-skill has all required sections
        assert result.missing_count == 0

    def test_audit_checks_frontmatter_fields(self, client):
        skill = client.get_skill("test-skill")
        result = client.audit_single(Path(skill.path))
        check_names = [c.check for c in result.checks]
        assert "name" in check_names
        assert "description" in check_names
        assert "keywords" in check_names

    def test_audit_missing_frontmatter(self, tmp_path):
        """Skill without frontmatter fails audit."""
        skill_dir = _write_skill(tmp_path, "bad-skill", "# No frontmatter\nJust text.\n")

        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient.audit_single(None, skill_dir)
        missing = [c for c in result.checks if c.status == "MISSING"]
        assert any(c.check == "frontmatter" for c in missing)

    def test_audit_missing_skill_md(self, tmp_path):
        """Directory without SKILL.md gets 1 MISSING."""
        empty = tmp_path / "empty-skill"
        empty.mkdir()

        from copilot_cli.services.skill.client import SkillClient

        result = SkillClient.audit_single(None, empty)
        assert result.missing_count == 1
        assert result.total_count == 1

    def test_audit_detects_scripts(self, client):
        skill = client.get_skill("scripted-skill")
        result = client.audit_single(Path(skill.path))
        scripts_check = [c for c in result.checks if c.check == "scripts"]
        assert scripts_check[0].status == "PASS"

    def test_audit_detects_reference(self, client):
        skill = client.get_skill("ref-skill")
        result = client.audit_single(Path(skill.path))
        ref_check = [c for c in result.checks if c.check == "reference"]
        assert ref_check[0].status == "PASS"

    def test_audit_score_percent(self, client):
        skill = client.get_skill("test-skill")
        result = client.audit_single(Path(skill.path))
        assert 0 <= result.score_percent <= 100
        assert result.score_percent == int((result.pass_count * 100) / result.total_count)

    def test_audit_all_discovered(self, client):
        results = client.audit()
        assert len(results) >= 4  # test-skill, exec-skill, scripted-skill, ref-skill

    def test_audit_specific_path(self, client, skill_dir):
        skills_root = skill_dir / ".claude" / "skills"
        results = client.audit(str(skills_root))
        assert len(results) >= 4

    def test_audit_single_path(self, client, skill_dir):
        skill_path = skill_dir / ".claude" / "skills" / "test-skill"
        results = client.audit(str(skill_path))
        assert len(results) == 1
        assert results[0].skill_name == "test-skill"


# ======================================================================
# CLI Commands
# ======================================================================


class TestCLIListCommand:
    """CLI: copilot skill list."""

    def test_list_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "list")
        assert result.exit_code == 0
        assert "test-skill" in result.output

    def test_list_executable_filter(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "list", "--executable")
        assert result.exit_code == 0
        # exec-skill and scripted-skill should appear
        assert "exec-skill" in result.output

    def test_list_no_skills(self, cli, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "list")
        assert result.exit_code == 0
        assert "No skills found" in result.output


class TestCLIShowCommand:
    """CLI: copilot skill show."""

    def test_show_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "show", "test-skill")
        assert result.exit_code == 0
        assert "test-skill" in result.output

    def test_show_not_found(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "show", "nonexistent")
        assert result.exit_code == 1


class TestCLIHealthCommand:
    """CLI: copilot skill health."""

    def test_health_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "health")
        assert result.exit_code == 0
        assert "OK" in result.output or "Skills OK" in result.output


class TestCLIPlanCommand:
    """CLI: copilot skill plan."""

    def test_plan_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "plan", "exec-skill", "--param", "target=World")
        assert result.exit_code == 0
        assert "greet" in result.output

    def test_plan_missing_param(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "plan", "exec-skill")
        assert result.exit_code == 1


class TestCLIRunCommand:
    """CLI: copilot skill run."""

    def test_run_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "run", "exec-skill", "--param", "target=World")
        assert result.exit_code == 0

    def test_run_failure(self, cli, skill_dir, monkeypatch):
        """Running against doc-only skill returns error."""
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "run", "test-skill")
        assert result.exit_code == 1


class TestCLIVerifyCommand:
    """CLI: copilot skill verify."""

    def test_verify_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "verify", "exec-skill", "--param", "target=World")
        assert result.exit_code == 0


class TestCLIAuditCommand:
    """CLI: copilot skill audit."""

    def test_audit_success(self, cli, skill_dir, monkeypatch):
        monkeypatch.chdir(skill_dir)
        monkeypatch.delenv("SKILL_PATHS", raising=False)
        result = cli("skill", "audit")
        assert result.exit_code in (0, 1)  # Depends on audit results
        # Should show audit output for discovered skills
        assert "test-skill" in result.output or "exec-skill" in result.output
