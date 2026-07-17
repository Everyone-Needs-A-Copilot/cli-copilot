"""Skill runtime — discovery, parsing, execution, verification, and auditing."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import (
    CopilotError,
    NotFoundError,
    TimeoutError,
    ValidationError,
)

from .models import (
    AuditCheck,
    AuditResult,
    ExecutionSpec,
    ExecutionStep,
    ParamType,
    SkillFrontmatter,
    SkillInfo,
    SkillRunResult,
    StepResult,
    VerifyCheck,
    VerifyResult,
)

SERVICE = "skill"


class SkillClient:
    """Skill discovery, parsing, execution, verification, and auditing."""

    def __init__(self) -> None:
        settings = get_settings()
        self._local_path = self._find_local_skills()
        self._extra_paths = self._resolve_paths(settings.skill_paths)
        self._cache: dict[str, SkillInfo] | None = None

    # ── Discovery ──────────────────────────────────────────────

    @staticmethod
    def _find_local_skills() -> Path | None:
        """Find .claude/skills/ relative to CWD or project root."""
        current = Path.cwd()
        root_markers = {".git", "pyproject.toml", ".mcp.json", "package.json"}
        for parent in [current, *current.parents]:
            candidate = parent / ".claude" / "skills"
            if candidate.is_dir():
                return candidate
            if any((parent / m).exists() for m in root_markers):
                candidate = parent / ".claude" / "skills"
                return candidate if candidate.is_dir() else None
        return None

    @staticmethod
    def _resolve_paths(setting: str) -> list[Path]:
        """Resolve skill paths from settings and environment."""
        paths: list[Path] = []

        # SKILL_PATHS env var (colon-separated, Unix convention)
        env_paths = os.environ.get("SKILL_PATHS", "")
        if env_paths:
            for p in env_paths.split(":"):
                p = p.strip()
                if p:
                    paths.append(Path(p))

        # Settings (comma-separated)
        if setting:
            for p in setting.split(","):
                p = p.strip()
                if p:
                    paths.append(Path(p))

        return [p for p in paths if p.is_dir()]

    def _discover_skills(self) -> dict[str, SkillInfo]:
        """Walk all configured paths and discover skills."""
        skills: dict[str, SkillInfo] = {}

        # Shared/env paths (lower priority — added first, overwritten by local)
        for search_path in self._extra_paths:
            for skill_dir in sorted(search_path.iterdir()):
                if not skill_dir.is_dir():
                    continue
                info = self._parse_skill_dir(skill_dir, "shared")
                if info:
                    skills[info.name] = info

        # Local path (highest priority — overwrites shared)
        if self._local_path and self._local_path.is_dir():
            for skill_dir in sorted(self._local_path.iterdir()):
                if not skill_dir.is_dir():
                    continue
                info = self._parse_skill_dir(skill_dir, "local")
                if info:
                    skills[info.name] = info

        return skills

    def _parse_skill_dir(self, path: Path, source: str) -> SkillInfo | None:
        """Parse a single skill directory into SkillInfo."""
        skill_file = path / "SKILL.md"
        if not skill_file.is_file():
            return None

        content = skill_file.read_text(encoding="utf-8", errors="replace")
        frontmatter = self._parse_frontmatter(content)

        if not frontmatter:
            # Minimal info for skills with unparseable frontmatter
            return SkillInfo(
                name=path.name,
                path=str(path),
                skill_file=str(skill_file),
                source=source,
            )

        scripts_dir = path / "scripts"
        reference_dir = path / "reference"
        script_count = 0
        reference_count = 0

        if scripts_dir.is_dir():
            script_count = len([f for f in scripts_dir.iterdir() if f.suffix in (".sh", ".py")])
        if reference_dir.is_dir():
            reference_count = len([f for f in reference_dir.iterdir() if f.suffix == ".md"])

        return SkillInfo(
            name=frontmatter.name,
            description=frontmatter.description,
            path=str(path),
            skill_file=str(skill_file),
            source=source,
            has_scripts=script_count > 0,
            has_reference=reference_count > 0,
            has_execution_spec=frontmatter.execution is not None,
            script_count=script_count,
            reference_count=reference_count,
            frontmatter=frontmatter,
            quality_tests=self._parse_quality_tests(content),
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> SkillFrontmatter | None:
        """Extract and parse YAML frontmatter from SKILL.md content."""
        if not content.startswith("---"):
            return None

        # Find closing ---
        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            return None

        yaml_text = content[4:end_idx]
        try:
            data = yaml.safe_load(yaml_text)
            if not isinstance(data, dict) or "name" not in data:
                return None
            return SkillFrontmatter.model_validate(data)
        except Exception:
            return None

    @staticmethod
    def _parse_quality_tests(content: str) -> list[dict[str, str]]:
        """Extract quality test names and descriptions from ## Quality Tests."""
        tests: list[dict[str, str]] = []
        in_section = False

        for line in content.splitlines():
            if line.startswith("## Quality Tests"):
                in_section = True
                continue
            if in_section and line.startswith("## ") and "Quality Tests" not in line:
                break
            if in_section and line.startswith("### "):
                test_name = line[4:].strip()
                tests.append({"name": test_name, "pass": "", "fail": ""})
            if in_section and tests:
                if line.strip().startswith("- **PASS:**"):
                    tests[-1]["pass"] = line.strip()[11:].strip()
                elif line.strip().startswith("- **FAIL:**"):
                    tests[-1]["fail"] = line.strip()[11:].strip()

        return tests

    def _get_cache(self) -> dict[str, SkillInfo]:
        if self._cache is None:
            self._cache = self._discover_skills()
        return self._cache

    # ── Public: list / show / health ───────────────────────────

    def list_skills(
        self, source: str | None = None, executable_only: bool = False
    ) -> list[SkillInfo]:
        """List all discovered skills, optionally filtered."""
        self._cache = None  # Force refresh
        skills = list(self._get_cache().values())
        if source:
            skills = [s for s in skills if s.source == source]
        if executable_only:
            skills = [s for s in skills if s.has_execution_spec]
        return sorted(skills, key=lambda s: (s.source, s.name))

    def get_skill(self, name: str) -> SkillInfo:
        """Get a skill by name. Raises NotFoundError if not found."""
        cache = self._get_cache()
        if name not in cache:
            available = ", ".join(sorted(cache.keys())[:10])
            raise NotFoundError(
                f"Skill '{name}' not found",
                service=SERVICE,
                hint=f"Available skills: {available}",
            )
        return cache[name]

    def health(self) -> dict[str, Any]:
        """Return skill service health."""
        try:
            skills = self._get_cache()
            sources: list[dict[str, Any]] = []
            if self._local_path:
                sources.append(
                    {
                        "type": "local",
                        "path": str(self._local_path),
                        "exists": self._local_path.is_dir(),
                    }
                )
            for p in self._extra_paths:
                sources.append({"type": "shared", "path": str(p), "exists": p.is_dir()})
            return {
                "healthy": True,
                "skill_count": len(skills),
                "executable_count": sum(1 for s in skills.values() if s.has_execution_spec),
                "sources": sources,
            }
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    # ── Public: plan (dry run) ─────────────────────────────────

    def plan(self, name: str, params: dict[str, Any]) -> list[dict[str, str]]:
        """Show what would happen when running a skill (dry run)."""
        skill = self.get_skill(name)
        spec = self._require_execution_spec(skill)
        resolved_params = self._validate_params(spec, params)

        plan_steps: list[dict[str, str]] = []
        for i, step in enumerate(spec.steps, 1):
            entry: dict[str, str] = {"step": str(i), "name": step.name}

            if step.skip_if and self._evaluate_condition(step.skip_if, resolved_params):
                entry["action"] = "SKIP"
                entry["reason"] = f"Condition: {step.skip_if}"
            elif step.script:
                script_path = Path(skill.path) / step.script
                args = [self._interpolate(a, resolved_params) for a in step.args]
                entry["action"] = "RUN SCRIPT"
                entry["command"] = f"{script_path} {' '.join(args)}".strip()
            elif step.command:
                entry["action"] = "RUN COMMAND"
                entry["command"] = self._interpolate(step.command, resolved_params)
            else:
                entry["action"] = "NO-OP"

            plan_steps.append(entry)

        return plan_steps

    # ── Public: run (execution) ────────────────────────────────

    def run(self, name: str, params: dict[str, Any], timeout: int = 300) -> SkillRunResult:
        """Execute a skill's steps sequentially."""
        skill = self.get_skill(name)
        spec = self._require_execution_spec(skill)
        resolved_params = self._validate_params(spec, params)

        steps_results: list[StepResult] = []
        overall_start = time.monotonic()
        overall_status = "success"

        for step in spec.steps:
            result = self._execute_step(step, Path(skill.path), resolved_params, timeout)
            steps_results.append(result)

            if result.status == "failed":
                overall_status = "failed"
                break

        if overall_status == "success" and any(r.status == "skipped" for r in steps_results):
            overall_status = "success"  # Skips don't affect overall status

        duration_ms = int((time.monotonic() - overall_start) * 1000)

        return SkillRunResult(
            skill_name=name,
            status=overall_status,
            steps=steps_results,
            params_used=resolved_params,
            duration_ms=duration_ms,
        )

    # ── Public: verify ─────────────────────────────────────────

    def verify(self, name: str, params: dict[str, Any], timeout: int = 60) -> list[VerifyResult]:
        """Run verification checks for a skill."""
        skill = self.get_skill(name)
        checks: list[VerifyCheck] = []

        # Source 1: execution.verify from frontmatter
        if skill.frontmatter and skill.frontmatter.execution:
            checks.extend(skill.frontmatter.execution.verify)

        if not checks:
            raise CopilotError(
                f"Skill '{name}' has no executable verify checks",
                service=SERVICE,
                hint="Add execution.verify to SKILL.md frontmatter.",
            )

        resolved_params = {}
        if skill.frontmatter and skill.frontmatter.execution:
            resolved_params = self._validate_params(skill.frontmatter.execution, params)

        results: list[VerifyResult] = []
        for check in checks:
            cmd = self._interpolate(check.command, resolved_params)
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=skill.path,
                )
                passed = self._evaluate_expect(check.expect, proc.returncode, proc.stdout)
                results.append(
                    VerifyResult(
                        check_name=check.name,
                        status="pass" if passed else "fail",
                        command=cmd,
                        exit_code=proc.returncode,
                        stdout=proc.stdout[:500],
                        stderr=proc.stderr[:500],
                        expectation=check.expect,
                        message="OK" if passed else f"Expected: {check.expect}",
                    )
                )
            except subprocess.TimeoutExpired:
                results.append(
                    VerifyResult(
                        check_name=check.name,
                        status="error",
                        command=cmd,
                        expectation=check.expect,
                        message=f"Timed out after {timeout}s",
                    )
                )
            except Exception as exc:
                results.append(
                    VerifyResult(
                        check_name=check.name,
                        status="error",
                        command=cmd,
                        expectation=check.expect,
                        message=str(exc),
                    )
                )

        return results

    # ── Public: audit ──────────────────────────────────────────

    def audit(self, path: str | None = None) -> list[AuditResult]:
        """Audit skill(s) against quality standards."""
        if path:
            target = Path(path)
            if target.is_dir() and (target / "SKILL.md").exists():
                return [self.audit_single(target)]
            # Directory of skills
            results: list[AuditResult] = []
            for child in sorted(target.iterdir()):
                if child.is_dir() and (child / "SKILL.md").exists():
                    results.append(self.audit_single(child))
            return results
        else:
            # Audit all discovered skills
            return [self.audit_single(Path(s.path)) for s in self.list_skills()]

    def audit_single(self, skill_dir: Path) -> AuditResult:
        """Run 15-check audit on a single skill directory."""
        skill_file = skill_dir / "SKILL.md"
        name = skill_dir.name
        checks: list[AuditCheck] = []

        def check(status: str, check_name: str, message: str) -> None:
            checks.append(AuditCheck(check=check_name, status=status, message=message))

        if not skill_file.is_file() or skill_file.stat().st_size == 0:
            check("MISSING", "skill_md", "SKILL.md not found or empty")
            return AuditResult(
                skill_name=name,
                path=str(skill_dir),
                checks=checks,
                missing_count=1,
                total_count=1,
            )

        content = skill_file.read_text(encoding="utf-8", errors="replace")

        # 1. SKILL.md exists
        check("PASS", "skill_md", "SKILL.md exists and non-empty")

        # 2. Frontmatter block
        if content.startswith("---"):
            check("PASS", "frontmatter", "Frontmatter block present")
        else:
            check("MISSING", "frontmatter", "Frontmatter block (---) not found")

        # 3-6. Frontmatter fields
        for field, level in [
            ("name:", "MISSING"),
            ("description:", "MISSING"),
            ("keywords:", "WARN"),
            ("allowed-tools:", "WARN"),
        ]:
            pattern = f"^{re.escape(field)}" if field != "keywords:" else "keywords:"
            if re.search(pattern, content, re.MULTILINE):
                check("PASS", field.rstrip(":"), f"Frontmatter: {field}")
            else:
                label = "(recommended)" if level == "WARN" else ""
                check(level, field.rstrip(":"), f"Frontmatter: {field} {label}".strip())

        # 7. Instructions/Framework or domain-specific H2s
        if re.search(r"^## (Instructions|Framework)", content, re.MULTILINE):
            check("PASS", "instructions", "Body: Instructions/Framework section")
        else:
            structural = r"^## (Overview|Define Done|Quality Tests|Examples|Guidelines|References|Anti-Patterns|Error Handling|Conclusion|Table of Contents)"
            all_h2 = len(re.findall(r"^## ", content, re.MULTILINE))
            structural_h2 = len(re.findall(structural, content, re.MULTILINE))
            content_h2 = all_h2 - structural_h2
            if content_h2 >= 2:
                check(
                    "PASS",
                    "instructions",
                    f"Body: {content_h2} domain-specific H2s (knowledge skill)",
                )
            else:
                check("MISSING", "instructions", "Body: Instructions or Framework section")

        # 8-10. Optional sections
        for section, field_name in [
            ("Examples", "examples"),
            ("Guidelines", "guidelines"),
            ("Error Handling", "error_handling"),
        ]:
            if re.search(rf"^## {section}", content, re.MULTILINE):
                check("PASS", field_name, f"Body: {section} section")
            else:
                check("WARN", field_name, f"Body: {section} section (recommended)")

        # 11-12. Required sections
        for section, field_name in [
            ("Define Done", "define_done"),
            ("Quality Tests", "quality_tests"),
        ]:
            if re.search(rf"^## {section}", content, re.MULTILINE):
                check("PASS", field_name, f"Body: {section} section")
            else:
                check("MISSING", field_name, f"Body: {section} section")

        # 13. scripts/ directory
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.is_dir() and any(scripts_dir.iterdir()):
            count = len([f for f in scripts_dir.iterdir() if f.is_file()])
            check("PASS", "scripts", f"scripts/ directory ({count} file(s))")
        else:
            check("WARN", "scripts", "scripts/ directory (not present)")

        # 14. reference/ directory
        ref_dir = skill_dir / "reference"
        if ref_dir.is_dir() and any(ref_dir.iterdir()):
            count = len([f for f in ref_dir.iterdir() if f.is_file()])
            check("PASS", "reference", f"reference/ directory ({count} file(s))")
        else:
            check("WARN", "reference", "reference/ directory (not present)")

        # 15. Required/optional marking
        if re.search(r"\(REQUIRED\)|\(OPTIONAL\)", content):
            check("PASS", "step_marking", "Steps marked REQUIRED/OPTIONAL")
        else:
            check("WARN", "step_marking", "Steps not marked REQUIRED/OPTIONAL")

        pass_count = sum(1 for c in checks if c.status == "PASS")
        warn_count = sum(1 for c in checks if c.status == "WARN")
        missing_count = sum(1 for c in checks if c.status == "MISSING")
        total = len(checks)

        return AuditResult(
            skill_name=name,
            path=str(skill_dir),
            checks=checks,
            pass_count=pass_count,
            warn_count=warn_count,
            missing_count=missing_count,
            total_count=total,
            score_percent=int((pass_count * 100) / total) if total > 0 else 0,
        )

    # ── Internal: execution engine ─────────────────────────────

    def _require_execution_spec(self, skill: SkillInfo) -> ExecutionSpec:
        """Get execution spec or raise a clear error."""
        if not skill.frontmatter or not skill.frontmatter.execution:
            raise CopilotError(
                f"Skill '{skill.name}' is documentation-only (no execution spec)",
                service=SERVICE,
                hint="Add an 'execution:' block to the SKILL.md frontmatter to make it executable.",
            )
        return skill.frontmatter.execution

    @staticmethod
    def _validate_params(spec: ExecutionSpec, raw_params: dict[str, Any]) -> dict[str, Any]:
        """Validate and coerce parameters against the spec."""
        resolved: dict[str, Any] = {}

        for param in spec.params:
            if param.name in raw_params:
                value = raw_params[param.name]
            elif not param.required and param.default is not None:
                value = param.default
            elif not param.required:
                value = None
                resolved[param.name] = value
                continue
            else:
                raise ValidationError(
                    f"Required parameter '{param.name}' not provided",
                    service=SERVICE,
                    hint=f"Use --param {param.name}=<value>. {param.description}",
                )

            # Type coercion
            if param.type == ParamType.INT:
                value = int(value)
            elif param.type == ParamType.FLOAT:
                value = float(value)
            elif param.type == ParamType.BOOL:
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes")
            elif param.type == ParamType.PATH:
                value = str(Path(value).resolve())

            resolved[param.name] = value

        return resolved

    @staticmethod
    def _interpolate(template: str, params: dict[str, Any]) -> str:
        """Replace {{ params.x }} placeholders with resolved values."""

        def replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            if key.startswith("params."):
                param_name = key[7:]
                if param_name in params:
                    return str(params[param_name])
            return match.group(0)

        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replacer, template)

    @staticmethod
    def _evaluate_condition(condition: str, params: dict[str, Any]) -> bool:
        """Evaluate a skip_if condition against params."""
        condition = condition.strip()
        negate = False
        if condition.startswith("not "):
            negate = True
            condition = condition[4:].strip()

        if condition.startswith("params."):
            param_name = condition[7:]
            value = params.get(param_name)
            result = bool(value)
            return not result if negate else result

        return False

    def _execute_step(
        self,
        step: ExecutionStep,
        skill_dir: Path,
        params: dict[str, Any],
        timeout: int,
    ) -> StepResult:
        """Execute a single step."""
        # Check skip condition
        if step.skip_if and self._evaluate_condition(step.skip_if, params):
            return StepResult(
                step_name=step.name,
                status="skipped",
                skipped_reason=f"Condition met: {step.skip_if}",
            )

        start = time.monotonic()

        try:
            if step.script:
                script_path = skill_dir / step.script
                if not script_path.is_file():
                    return StepResult(
                        step_name=step.name,
                        status="failed",
                        stderr=f"Script not found: {script_path}",
                    )
                args = [self._interpolate(a, params) for a in step.args]
                cmd = ["bash", str(script_path), *args]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(skill_dir),
                )
            elif step.command:
                cmd_str = self._interpolate(step.command, params)
                proc = subprocess.run(
                    cmd_str,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(skill_dir),
                )
            else:
                return StepResult(
                    step_name=step.name,
                    status="skipped",
                    skipped_reason="No script or command defined",
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                step_name=step.name,
                status="success" if proc.returncode == 0 else "failed",
                exit_code=proc.returncode,
                stdout=proc.stdout[:2000],
                stderr=proc.stderr[:2000],
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Step '{step.name}' timed out after {timeout}s",
                service=SERVICE,
                hint="Increase timeout with --timeout flag.",
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                step_name=step.name,
                status="failed",
                stderr=str(exc),
                duration_ms=duration_ms,
            )

    @staticmethod
    def _evaluate_expect(expect: str, exit_code: int, stdout: str) -> bool:
        """Evaluate an expectation expression against command results."""
        expect = expect.strip()

        # exit_code == N
        m = re.match(r"exit_code\s*==\s*(\d+)", expect)
        if m:
            return exit_code == int(m.group(1))

        # exit_code != N
        m = re.match(r"exit_code\s*!=\s*(\d+)", expect)
        if m:
            return exit_code != int(m.group(1))

        # stdout contains "text"
        m = re.match(r'stdout\s+contains\s+"(.+?)"', expect)
        if m:
            return m.group(1) in stdout

        # Default: exit code 0
        return exit_code == 0
