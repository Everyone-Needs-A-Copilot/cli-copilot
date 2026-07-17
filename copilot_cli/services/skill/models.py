"""Pydantic models for skill specifications."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParamType(str, Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    PATH = "path"


class SkillParam(BaseModel):
    """A declared parameter for a skill's execution."""

    name: str
    type: ParamType = ParamType.STRING
    required: bool = True
    default: Any = None
    description: str = ""


class ExecutionStep(BaseModel):
    """A single step in a skill's execution plan."""

    name: str
    script: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    skip_if: str | None = None
    description: str = ""


class VerifyCheck(BaseModel):
    """A verification check to validate skill execution."""

    name: str
    command: str
    expect: str = "exit_code == 0"
    description: str = ""


class ExecutionSpec(BaseModel):
    """The execution specification block from SKILL.md frontmatter."""

    params: list[SkillParam] = Field(default_factory=list)
    steps: list[ExecutionStep] = Field(default_factory=list)
    verify: list[VerifyCheck] = Field(default_factory=list)


class SkillFrontmatter(BaseModel):
    """Parsed YAML frontmatter from SKILL.md."""

    name: str
    description: str = ""
    triggers: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: str = Field(default="", alias="allowed-tools")
    execution: ExecutionSpec | None = None

    model_config = {"populate_by_name": True}


class SkillInfo(BaseModel):
    """Full skill metadata including filesystem context."""

    name: str
    description: str = ""
    path: str
    skill_file: str
    source: str  # "local", "shared", or "env"
    has_scripts: bool = False
    has_reference: bool = False
    has_execution_spec: bool = False
    script_count: int = 0
    reference_count: int = 0
    frontmatter: SkillFrontmatter | None = None
    quality_tests: list[dict[str, str]] = Field(default_factory=list)


class StepResult(BaseModel):
    """Result of executing a single step."""

    step_name: str
    status: str  # "success", "failed", "skipped"
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    skipped_reason: str = ""


class SkillRunResult(BaseModel):
    """Result of a complete skill execution."""

    skill_name: str
    status: str  # "success", "failed", "partial"
    steps: list[StepResult] = Field(default_factory=list)
    params_used: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class VerifyResult(BaseModel):
    """Result of a single verification check."""

    check_name: str
    status: str  # "pass", "fail", "error"
    command: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    expectation: str = ""
    message: str = ""


class AuditCheck(BaseModel):
    """A single audit check result."""

    check: str
    status: str  # "PASS", "WARN", "MISSING"
    message: str


class AuditResult(BaseModel):
    """Result of auditing a single skill."""

    skill_name: str
    path: str
    checks: list[AuditCheck] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    missing_count: int = 0
    total_count: int = 0
    score_percent: int = 0
