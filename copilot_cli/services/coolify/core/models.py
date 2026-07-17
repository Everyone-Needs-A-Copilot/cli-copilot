"""Pydantic models for Coolify API resources."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ─── Enums ────────────────────────────────────────────────────────────────────


class BuildPack(str, Enum):
    NIXPACKS = "nixpacks"
    STATIC = "static"
    DOCKERFILE = "dockerfile"
    DOCKERCOMPOSE = "dockercompose"
    DOCKERIMAGE = "dockerimage"


class DatabaseType(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    MONGODB = "mongodb"
    REDIS = "redis"
    KEYDB = "keydb"
    CLICKHOUSE = "clickhouse"
    DRAGONFLY = "dragonfly"


class ResourceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    BUILDING = "building"
    DEPLOYING = "deploying"
    RESTARTING = "restarting"
    UNKNOWN = "unknown"


class DeploymentStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DiagnosticHealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ProxyType(str, Enum):
    TRAEFIK = "traefik"
    CADDY = "caddy"
    NONE = "none"


# ─── Common ───────────────────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str


class UuidResponse(BaseModel):
    uuid: str


# ─── Server ───────────────────────────────────────────────────────────────────


class ServerSettings(BaseModel):
    id: int = 0
    server_id: int = 0
    concurrent_builds: int = 2
    dynamic_timeout: int = 30
    force_disabled: bool = False
    force_docker_cleanup: bool = False
    docker_cleanup_frequency: str = ""
    docker_cleanup_threshold: int = 0
    is_cloudflare_tunnel: bool = False
    is_jump_server: bool = False
    is_metrics_enabled: bool = False
    is_reachable: bool = False
    is_sentinel_enabled: bool = False
    is_swarm_manager: bool = False
    is_swarm_worker: bool = False
    is_usable: bool = False
    wildcard_domain: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class Server(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    ip: str = ""
    user: str = "root"
    port: int = 22
    status: str | None = None
    is_reachable: bool | None = None
    is_usable: bool | None = None
    is_swarm_manager: bool | None = None
    is_swarm_worker: bool | None = None
    is_build_server: bool | None = None
    proxy_type: str | None = None
    proxy_status: str | None = None
    settings: ServerSettings | None = None
    team_id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class ServerSummary(BaseModel):
    uuid: str = ""
    name: str = ""
    ip: str = ""
    status: str | None = None
    is_reachable: bool | None = None


class ServerResource(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    type: str = ""
    status: str = ""
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class ServerDomain(BaseModel):
    ip: str = ""
    domains: list[str] = Field(default_factory=list)


class ServerValidation(BaseModel):
    message: str = ""
    validation_logs: str | None = None


# ─── Project ──────────────────────────────────────────────────────────────────


class Environment(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    project_id: int | None = None
    project_uuid: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class Project(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    team_id: int | None = None
    environments: list[Environment] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"extra": "allow"}


class ProjectSummary(BaseModel):
    uuid: str = ""
    name: str = ""
    description: str | None = None


# ─── Application ──────────────────────────────────────────────────────────────


class Application(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    fqdn: str | None = None
    git_repository: str | None = None
    git_branch: str | None = None
    git_commit_sha: str | None = None
    build_pack: str | None = None
    ports_exposes: str | None = None
    ports_mappings: str | None = None
    dockerfile: str | None = None
    dockerfile_location: str | None = None
    docker_registry_image_name: str | None = None
    docker_registry_image_tag: str | None = None
    docker_compose_location: str | None = None
    docker_compose_raw: str | None = None
    base_directory: str | None = None
    publish_directory: str | None = None
    install_command: str | None = None
    build_command: str | None = None
    start_command: str | None = None
    health_check_enabled: bool | None = None
    health_check_path: str | None = None
    limits_memory: str | None = None
    limits_cpus: str | None = None
    status: str | None = None
    project_uuid: str | None = None
    environment_uuid: str | None = None
    server_uuid: str | None = None
    environment_id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class ApplicationSummary(BaseModel):
    uuid: str = ""
    name: str = ""
    status: str | None = None
    fqdn: str | None = None
    git_repository: str | None = None
    git_branch: str | None = None


# ─── Database ─────────────────────────────────────────────────────────────────


class Database(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    type: str | None = None
    database_type: str | None = None
    status: str | None = None
    is_public: bool = False
    public_port: int | None = None
    image: str = ""
    started_at: str | None = None
    internal_db_url: str | None = None
    external_db_url: str | None = None
    project_uuid: str | None = None
    environment_uuid: str | None = None
    environment_name: str | None = None
    server_uuid: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}

    @property
    def db_type(self) -> str:
        return self.type or self.database_type or "unknown"


class DatabaseSummary(BaseModel):
    uuid: str = ""
    name: str = ""
    type: str | None = None
    status: str | None = None
    is_public: bool = False


# ─── Service ──────────────────────────────────────────────────────────────────


class Service(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    type: str | None = None
    status: str | None = None
    project_uuid: str | None = None
    environment_name: str | None = None
    environment_uuid: str | None = None
    server_uuid: str | None = None
    destination_uuid: str | None = None
    domains: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class ServiceSummary(BaseModel):
    uuid: str = ""
    name: str = ""
    type: str | None = None
    status: str | None = None
    domains: list[str] = Field(default_factory=list)


# ─── Environment Variable ────────────────────────────────────────────────────


class EnvironmentVariable(BaseModel):
    id: int = 0
    uuid: str = ""
    key: str = ""
    value: str = ""
    is_build_time: bool = False
    is_literal: bool = False
    is_multiline: bool = False
    is_preview: bool = False
    is_shared: bool = False
    is_shown_once: bool = False
    real_value: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class EnvVarSummary(BaseModel):
    uuid: str = ""
    key: str = ""
    value: str = ""
    is_build_time: bool = False


# ─── Deployment ───────────────────────────────────────────────────────────────


class Deployment(BaseModel):
    id: int = 0
    uuid: str = ""
    application_id: int | None = None
    application_uuid: str | None = None
    application_name: str | None = None
    deployment_uuid: str = ""
    pull_request_id: int | None = None
    force_rebuild: bool = False
    commit: str | None = None
    status: str = ""
    is_webhook: bool = False
    is_api: bool = False
    logs: str | None = None
    restart_only: bool = False
    server_id: int | None = None
    server_name: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class DeploymentSummary(BaseModel):
    uuid: str = ""
    deployment_uuid: str = ""
    application_name: str | None = None
    status: str = ""
    created_at: str = ""


# ─── Team ─────────────────────────────────────────────────────────────────────


class TeamMember(BaseModel):
    id: int = 0
    name: str = ""
    email: str = ""
    role: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class Team(BaseModel):
    id: int = 0
    uuid: str | None = None
    name: str = ""
    description: str | None = None
    personal_team: bool = False
    members: list[TeamMember] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


# ─── Private Key ──────────────────────────────────────────────────────────────


class PrivateKey(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    description: str | None = None
    private_key: str = ""
    public_key: str | None = None
    fingerprint: str | None = None
    is_git_related: bool = False
    team_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


# ─── GitHub App ───────────────────────────────────────────────────────────────


class GitHubApp(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    organization: str | None = None
    api_url: str = ""
    html_url: str = ""
    custom_user: str = "git"
    custom_port: int = 22
    app_id: int | None = None
    installation_id: int | None = None
    client_id: str | None = None
    is_system_wide: bool = False
    is_public: bool = False
    team_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class GitHubAppSummary(BaseModel):
    id: int = 0
    uuid: str = ""
    name: str = ""
    organization: str | None = None
    is_public: bool = False
    app_id: int | None = None


# ─── Database Backup ──────────────────────────────────────────────────────────


class DatabaseBackup(BaseModel):
    id: int = 0
    uuid: str = ""
    database_id: int = 0
    database_type: str | None = None
    status: str = ""
    filename: str | None = None
    size: int | None = None
    frequency: str = ""
    enabled: bool = True
    save_s3: bool = False
    s3_storage_id: int | None = None
    databases_to_backup: str | None = None
    dump_all: bool = False
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


class BackupExecution(BaseModel):
    id: int = 0
    uuid: str = ""
    scheduled_database_backup_id: int = 0
    status: str = ""
    message: str | None = None
    size: int | None = None
    filename: str | None = None
    created_at: str = ""
    updated_at: str = ""

    model_config = {"extra": "allow"}


# ─── Diagnostics ──────────────────────────────────────────────────────────────


class HealthReport(BaseModel):
    status: str = "unknown"
    issues: list[str] = Field(default_factory=list)


class ApplicationDiagnostic(BaseModel):
    application: dict[str, Any] | None = None
    health: HealthReport = Field(default_factory=HealthReport)
    logs: str | None = None
    environment_variables: dict[str, Any] = Field(default_factory=dict)
    recent_deployments: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ServerDiagnostic(BaseModel):
    server: dict[str, Any] | None = None
    health: HealthReport = Field(default_factory=HealthReport)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    domains: list[dict[str, Any]] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class InfrastructureIssue(BaseModel):
    type: str = ""
    uuid: str = ""
    name: str = ""
    issue: str = ""
    status: str = ""


class InfrastructureIssuesReport(BaseModel):
    summary: dict[str, int] = Field(default_factory=dict)
    issues: list[InfrastructureIssue] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ─── Batch Operations ────────────────────────────────────────────────────────


class BatchResult(BaseModel):
    summary: dict[str, int] = Field(
        default_factory=lambda: {"total": 0, "succeeded": 0, "failed": 0}
    )
    succeeded: list[dict[str, str]] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
