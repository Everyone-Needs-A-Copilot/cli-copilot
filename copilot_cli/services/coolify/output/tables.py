"""Rich table builders for each resource type."""

from __future__ import annotations

from rich.table import Table

from copilot_cli.services.coolify.output.formatters import (
    bool_icon,
    relative_time,
    status_badge,
    truncate,
)


def server_table(servers: list[dict]) -> Table:
    """Build a table for servers."""
    table = Table(title="Servers", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("Reachable")
    for s in servers:
        table.add_row(
            s.get("name", ""),
            s.get("uuid", ""),
            s.get("ip", ""),
            status_badge(s.get("status")),
            bool_icon(s.get("is_reachable")),
        )
    return table


def application_table(apps: list[dict]) -> Table:
    """Build a table for applications."""
    table = Table(title="Applications", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Status")
    table.add_column("Domain")
    table.add_column("Branch")
    for a in apps:
        table.add_row(
            a.get("name", ""),
            a.get("uuid", ""),
            status_badge(a.get("status")),
            truncate(a.get("fqdn") or "\u2014", 40),
            a.get("git_branch") or "\u2014",
        )
    return table


def database_table(dbs: list[dict]) -> Table:
    """Build a table for databases."""
    table = Table(title="Databases", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Public")
    for db in dbs:
        db_type = db.get("type") or db.get("database_type") or "\u2014"
        table.add_row(
            db.get("name", ""),
            db.get("uuid", ""),
            db_type,
            status_badge(db.get("status")),
            bool_icon(db.get("is_public")),
        )
    return table


def service_table(services: list[dict]) -> Table:
    """Build a table for services."""
    table = Table(title="Services", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Domains")
    for svc in services:
        domains = svc.get("domains") or []
        table.add_row(
            svc.get("name", ""),
            svc.get("uuid", ""),
            svc.get("type") or "\u2014",
            status_badge(svc.get("status")),
            ", ".join(domains) if domains else "\u2014",
        )
    return table


def project_table(projects: list[dict]) -> Table:
    """Build a table for projects."""
    table = Table(title="Projects", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Description")
    table.add_column("Environments")
    for p in projects:
        envs = p.get("environments") or []
        env_names = ", ".join(e.get("name", "") for e in envs) if envs else "\u2014"
        table.add_row(
            p.get("name", ""),
            p.get("uuid", ""),
            truncate(p.get("description") or "\u2014", 40),
            env_names,
        )
    return table


def deployment_table(deployments: list[dict]) -> Table:
    """Build a table for deployments."""
    table = Table(title="Deployments", show_lines=False)
    table.add_column("UUID", style="uuid")
    table.add_column("App")
    table.add_column("Status")
    table.add_column("Commit")
    table.add_column("Server")
    table.add_column("When")
    for d in deployments:
        table.add_row(
            d.get("deployment_uuid") or d.get("uuid", ""),
            d.get("application_name") or "\u2014",
            status_badge(d.get("status")),
            truncate(d.get("commit") or "\u2014", 12),
            d.get("server_name") or "\u2014",
            relative_time(d.get("created_at")),
        )
    return table


def envvar_table(envvars: list[dict]) -> Table:
    """Build a table for environment variables."""
    table = Table(title="Environment Variables", show_lines=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_column("Build Time")
    table.add_column("UUID", style="uuid")
    for v in envvars:
        value = v.get("value", "")
        # Mask long values
        display_value = truncate(value, 50) if len(value) > 50 else value
        table.add_row(
            v.get("key", ""),
            display_value,
            bool_icon(v.get("is_build_time")),
            v.get("uuid", ""),
        )
    return table


def team_table(teams: list[dict]) -> Table:
    """Build a table for teams."""
    table = Table(title="Teams", show_lines=False)
    table.add_column("ID")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Personal")
    for t in teams:
        table.add_row(
            str(t.get("id", "")),
            t.get("name", ""),
            truncate(t.get("description") or "\u2014", 40),
            bool_icon(t.get("personal_team")),
        )
    return table


def team_member_table(members: list[dict]) -> Table:
    """Build a table for team members."""
    table = Table(title="Team Members", show_lines=False)
    table.add_column("ID")
    table.add_column("Name", style="bold")
    table.add_column("Email")
    table.add_column("Role")
    for m in members:
        table.add_row(
            str(m.get("id", "")),
            m.get("name", ""),
            m.get("email", ""),
            m.get("role") or "\u2014",
        )
    return table


def private_key_table(keys: list[dict]) -> Table:
    """Build a table for private keys."""
    table = Table(title="Private Keys", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Fingerprint")
    table.add_column("Git Related")
    for k in keys:
        table.add_row(
            k.get("name", ""),
            k.get("uuid", ""),
            k.get("fingerprint") or "\u2014",
            bool_icon(k.get("is_git_related")),
        )
    return table


def github_app_table(apps: list[dict]) -> Table:
    """Build a table for GitHub apps."""
    table = Table(title="GitHub Apps", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("ID")
    table.add_column("UUID", style="uuid")
    table.add_column("Organization")
    table.add_column("App ID")
    table.add_column("Public")
    for a in apps:
        table.add_row(
            a.get("name", ""),
            str(a.get("id", "")),
            a.get("uuid", ""),
            a.get("organization") or "\u2014",
            str(a.get("app_id") or "\u2014"),
            bool_icon(a.get("is_public")),
        )
    return table


def backup_table(backups: list[dict]) -> Table:
    """Build a table for database backups."""
    table = Table(title="Database Backups", show_lines=False)
    table.add_column("UUID", style="uuid")
    table.add_column("Status")
    table.add_column("Frequency")
    table.add_column("Enabled")
    table.add_column("S3")
    table.add_column("Updated")
    for b in backups:
        table.add_row(
            b.get("uuid", ""),
            status_badge(b.get("status")),
            b.get("frequency", ""),
            bool_icon(b.get("enabled")),
            bool_icon(b.get("save_s3")),
            relative_time(b.get("updated_at")),
        )
    return table


def server_resource_table(resources: list[dict]) -> Table:
    """Build a table for server resources."""
    table = Table(title="Server Resources", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Type")
    table.add_column("Status")
    for r in resources:
        table.add_row(
            r.get("name", ""),
            r.get("uuid", ""),
            r.get("type", ""),
            status_badge(r.get("status")),
        )
    return table


def environment_table(envs: list[dict]) -> Table:
    """Build a table for environments."""
    table = Table(title="Environments", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("UUID", style="uuid")
    table.add_column("Description")
    table.add_column("Updated")
    for e in envs:
        table.add_row(
            e.get("name", ""),
            e.get("uuid", ""),
            truncate(e.get("description") or "\u2014", 40),
            relative_time(e.get("updated_at")),
        )
    return table
