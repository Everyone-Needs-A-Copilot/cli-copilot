"""Output module — Rich console, formatters, tables, panels, and structured output."""

from copilot_cli.services.coolify.output.console import console, err_console
from copilot_cli.services.coolify.output.formatters import (
    bool_icon,
    deployment_status_icon,
    format_bytes,
    relative_time,
    status_badge,
    truncate,
)
from copilot_cli.services.coolify.output.json_out import output_data, print_json, print_yaml
from copilot_cli.services.coolify.output.panels import (
    application_detail_panel,
    database_detail_panel,
    deployment_detail_panel,
    diagnostic_panel,
    project_detail_panel,
    server_detail_panel,
    service_detail_panel,
)
from copilot_cli.services.coolify.output.tables import (
    application_table,
    backup_table,
    database_table,
    deployment_table,
    environment_table,
    envvar_table,
    github_app_table,
    private_key_table,
    project_table,
    server_resource_table,
    server_table,
    service_table,
    team_member_table,
    team_table,
)

__all__ = [
    # Panels
    "application_detail_panel",
    # Tables
    "application_table",
    "backup_table",
    # Formatters
    "bool_icon",
    # Console
    "console",
    "database_detail_panel",
    "database_table",
    "deployment_detail_panel",
    "deployment_status_icon",
    "deployment_table",
    "diagnostic_panel",
    "environment_table",
    "envvar_table",
    "err_console",
    "format_bytes",
    "github_app_table",
    # JSON/YAML output
    "output_data",
    "print_json",
    "print_yaml",
    "private_key_table",
    "project_detail_panel",
    "project_table",
    "relative_time",
    "server_detail_panel",
    "server_resource_table",
    "server_table",
    "service_detail_panel",
    "service_table",
    "status_badge",
    "team_member_table",
    "team_table",
    "truncate",
]
