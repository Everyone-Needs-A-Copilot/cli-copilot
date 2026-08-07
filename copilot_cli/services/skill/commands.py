"""Typer subcommand group for skill runtime operations."""

from __future__ import annotations

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import (
    print_error,
    print_health,
    print_json,
    print_success,
    print_table,
    print_warning,
)

app = typer.Typer(no_args_is_help=True)


def _client():
    """Lazy-import the skill client."""
    from copilot_cli.services.skill.client import SkillClient

    return SkillClient()


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command("list")
def list_skills(
    source: str | None = typer.Option(None, help="Filter by source: local, shared, env"),
    executable: bool = typer.Option(
        False, "--executable", help="Only show skills with execution specs"
    ),
) -> None:
    """List all discovered skills."""
    try:
        skills = _client().list_skills(source=source, executable_only=executable)
        if not skills:
            print_warning("No skills found. Check SKILL_PATHS or .claude/skills/")
            return

        rows = [
            {
                "name": s.name,
                "source": s.source,
                "exec": "yes" if s.has_execution_spec else "-",
                "scripts": str(s.script_count) if s.has_scripts else "-",
                "description": (
                    s.description[:60] + "..." if len(s.description) > 60 else s.description
                ),
            }
            for s in skills
        ]
        print_table(
            rows,
            title=f"Skills ({len(skills)})",
            columns=["name", "source", "exec", "scripts", "description"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def show(
    name: str = typer.Argument(help="Skill name"),
) -> None:
    """Show detailed information about a skill."""
    try:
        skill = _client().get_skill(name)
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        from copilot_cli.shared.output import is_json_mode

        if is_json_mode():
            print_json(skill.model_dump())
            return

        console = Console()

        # Header
        exec_badge = (
            "[green]executable[/green]"
            if skill.has_execution_spec
            else "[dim]documentation-only[/dim]"
        )
        console.print(
            Panel(
                f"[bold]{skill.name}[/bold]  {exec_badge}\n\n{skill.description}",
                title="Skill",
                border_style="blue",
            )
        )

        # Metadata
        meta = Table(show_header=False, box=None, padding=(0, 2))
        meta.add_column(style="dim")
        meta.add_column()
        meta.add_row("Path", skill.path)
        meta.add_row("Source", skill.source)
        meta.add_row("Scripts", str(skill.script_count) if skill.has_scripts else "none")
        meta.add_row("References", str(skill.reference_count) if skill.has_reference else "none")
        console.print(meta)
        console.print()

        # Params (if executable)
        if skill.frontmatter and skill.frontmatter.execution:
            spec = skill.frontmatter.execution
            if spec.params:
                param_rows = [
                    {
                        "name": p.name,
                        "type": p.type.value,
                        "required": "yes" if p.required else "no",
                        "default": str(p.default) if p.default is not None else "-",
                        "description": p.description,
                    }
                    for p in spec.params
                ]
                print_table(
                    param_rows,
                    title="Parameters",
                    columns=["name", "type", "required", "default", "description"],
                )

            if spec.steps:
                step_rows = [
                    {
                        "step": str(i),
                        "name": s.name,
                        "type": "script" if s.script else "command",
                        "target": s.script or s.command or "-",
                    }
                    for i, s in enumerate(spec.steps, 1)
                ]
                print_table(
                    step_rows, title="Execution Steps", columns=["step", "name", "type", "target"]
                )

            if spec.verify:
                verify_rows = [{"name": v.name, "expect": v.expect} for v in spec.verify]
                print_table(verify_rows, title="Verify Checks", columns=["name", "expect"])

        # Quality tests
        if skill.quality_tests:
            qt_rows = [{"name": t["name"]} for t in skill.quality_tests]
            print_table(qt_rows, title="Quality Tests", columns=["name"])

    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def plan(
    name: str = typer.Argument(help="Skill name"),
    param: list[str] = typer.Option(
        [], "--param", "-p", help="Parameter as KEY=VALUE (repeatable)"
    ),
) -> None:
    """Dry run — show what a skill execution would do."""
    try:
        params = _parse_params(param)
        steps = _client().plan(name, params)

        from copilot_cli.shared.output import is_json_mode

        if is_json_mode():
            print_json(steps)
            return

        rows = [
            {
                "step": s["step"],
                "name": s["name"],
                "action": s["action"],
                "command": s.get("command", s.get("reason", "")),
            }
            for s in steps
        ]
        print_table(
            rows,
            title=f"Plan: {name}",
            columns=["step", "name", "action", "command"],
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def run(
    name: str = typer.Argument(help="Skill name"),
    param: list[str] = typer.Option(
        [], "--param", "-p", help="Parameter as KEY=VALUE (repeatable)"
    ),
    timeout: int = typer.Option(300, help="Timeout per step in seconds"),
) -> None:
    """Execute a skill's steps."""
    try:
        params = _parse_params(param)
        client = _client()

        from rich.console import Console

        from copilot_cli.shared.output import is_json_mode

        if is_json_mode():
            result = client.run(name, params, timeout=timeout)
            print_json(result.model_dump())
            return

        console = Console(stderr=True)

        # Show plan first
        console.print(f"\n[bold]Running skill:[/bold] {name}")
        console.print(f"[dim]Params: {params}[/dim]\n")

        result = client.run(name, params, timeout=timeout)

        # Display results
        out = Console()
        for step in result.steps:
            if step.status == "success":
                icon = "[green]OK[/green]"
            elif step.status == "skipped":
                icon = "[yellow]SKIP[/yellow]"
            else:
                icon = "[red]FAIL[/red]"

            out.print(f"  {step.step_name:.<40s} {icon}  ({step.duration_ms}ms)")

            if step.status == "failed" and step.stderr:
                out.print(f"    [red]{step.stderr[:200]}[/red]")

        out.print()
        if result.status == "success":
            print_success(f"Skill '{name}' completed in {result.duration_ms}ms")
        else:
            print_error(
                f"Skill '{name}' failed",
                hint="Check step output above. Fix the issue and re-run.",
            )
            raise typer.Exit(1)

    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def verify(
    name: str = typer.Argument(help="Skill name"),
    param: list[str] = typer.Option(
        [], "--param", "-p", help="Parameter as KEY=VALUE (repeatable)"
    ),
    timeout: int = typer.Option(60, help="Timeout per check in seconds"),
) -> None:
    """Run verification checks for a skill."""
    try:
        params = _parse_params(param)
        results = _client().verify(name, params, timeout=timeout)

        from copilot_cli.shared.output import is_json_mode

        if is_json_mode():
            print_json([r.model_dump() for r in results])
            return

        rows = [
            {
                "check": r.check_name,
                "status": r.status.upper(),
                "expect": r.expectation,
                "message": r.message,
            }
            for r in results
        ]
        print_table(
            rows,
            title=f"Verify: {name}",
            columns=["check", "status", "expect", "message"],
        )

        passed = sum(1 for r in results if r.status == "pass")
        total = len(results)
        if passed == total:
            print_success(f"All {total} checks passed")
        else:
            print_error(f"{total - passed} of {total} checks failed")
            raise typer.Exit(1)

    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def audit(
    path: str | None = typer.Option(None, "--path", help="Path to skill or skills directory"),
) -> None:
    """Audit skill(s) against quality standards."""
    try:
        results = _client().audit(path)

        from copilot_cli.shared.output import is_json_mode

        if is_json_mode():
            print_json([r.model_dump() for r in results])
            return

        from rich.console import Console

        console = Console()

        for r in results:
            console.print(f"\n[bold]=== {r.skill_name} ===[/bold]  [dim]{r.path}[/dim]")
            for c in r.checks:
                if c.status == "PASS":
                    style = "[green]PASS[/green]"
                elif c.status == "WARN":
                    style = "[yellow]WARN[/yellow]"
                else:
                    style = "[red]MISS[/red]"
                console.print(f"  {style:>20s}  {c.message}")
            console.print(
                f"  [dim]Score: {r.pass_count}/{r.total_count} ({r.score_percent}%) "
                f"| {r.warn_count} warnings | {r.missing_count} missing[/dim]"
            )

        # Summary
        total_skills = len(results)
        passing = sum(1 for r in results if r.missing_count == 0)
        console.print(f"\n[bold]Summary:[/bold] {passing}/{total_skills} skills fully passing")

        if passing < total_skills:
            raise typer.Exit(1)

    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Check skill service health."""
    try:
        result = _client().health()
        is_healthy = result.get("healthy", False)
        print_health("skill", is_healthy, result if not is_healthy else None)
        if is_healthy:
            print_success(
                f"Skills OK — {result.get('skill_count', 0)} discovered, "
                f"{result.get('executable_count', 0)} executable"
            )
        else:
            raise typer.Exit(1)
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_params(param_list: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE param strings into a dict."""
    params: dict[str, str] = {}
    for p in param_list:
        if "=" not in p:
            raise CopilotError(
                f"Invalid param format: '{p}'",
                service="skill",
                hint="Use --param KEY=VALUE format.",
            )
        key, _, value = p.partition("=")
        params[key.strip()] = value.strip()
    return params
