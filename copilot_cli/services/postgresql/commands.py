"""Typer subcommand group for PostgreSQL database operations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from copilot_cli.shared.errors import CopilotError
from copilot_cli.shared.output import print_error, print_json, print_success, print_table

app = typer.Typer(no_args_is_help=True)


def _client():
    """Lazy-import to avoid heavy startup cost."""
    from copilot_cli.services.postgresql.client import PostgreSQLClient

    return PostgreSQLClient()


def _resolve_local_url(name: str) -> str:
    """Look up *name* in the configured local database map.

    Raises:
        CopilotError: If the name is unknown.
    """
    from copilot_cli.config.settings import get_settings

    configs = get_settings().get_database_configs()
    if name not in configs:
        available = ", ".join(sorted(configs)) or "(none configured)"
        raise CopilotError(
            f"Unknown local database '{name}'. Available: {available}",
            service="postgresql",
            hint="Add a *_DATABASE_URL to your .env file.",
        )
    return configs[name]


def _resolve_remote_db(coolify_query: str) -> dict:
    """Resolve a Coolify database name/UUID to its full record (with credentials).

    Returns the dict directly from the Coolify API. Raises on failure.
    """
    from copilot_cli.services.coolify.core.api_client import CoolifyClient
    from copilot_cli.services.coolify.core.config import require_settings as require_cf
    from copilot_cli.services.coolify.core.resolver import resolve_database
    from copilot_cli.services.coolify.main import run_async

    cf = require_cf()
    cl = CoolifyClient(cf.api.base_url, cf.api.access_token)
    uuid = run_async(resolve_database(cl, coolify_query))
    return run_async(cl.get_database(uuid))


def _ssh_target_from_coolify_settings():
    """Build an SSHTarget from the Coolify CLI's [ssh] config block."""
    from copilot_cli.services.coolify.core.config import load_settings as load_cf
    from copilot_cli.services.postgresql.transfer import SSHTarget

    cf = load_cf()
    if not cf.ssh.host:
        raise CopilotError(
            "No SSH host configured for Coolify. Set [ssh] in ~/.coolify-cli/config.toml "
            "or COOLIFY_SSH_HOST in your environment.",
            service="postgresql",
            hint="See docs/services/15-coolify.md § SSH Access.",
        )
    return SSHTarget(user=cf.ssh.user, host=cf.ssh.host, port=cf.ssh.port, key_file=cf.ssh.key_file)


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def query(
    database: str = typer.Argument(..., help="Logical database name (e.g. nocodb, n8n)."),
    sql: str = typer.Argument(..., help="SQL query to execute."),
    timeout: int = typer.Option(30000, "--timeout", help="Statement timeout in milliseconds."),
    confirm_token: str = typer.Option(
        "",
        "--confirm-token",
        help="For destructive SQL on a local DB, must equal the database short-name.",
    ),
) -> None:
    """Execute a SQL query against a named database.

    Destructive SQL (DROP, TRUNCATE, DELETE, ALTER DROP) on a non-local database
    is refused. On a local database, destructive SQL requires --confirm-token
    to match the database short-name.
    """
    try:
        result = _client().query(
            database=database,
            query=sql,
            timeout=timeout,
            confirm_token=confirm_token or None,
        )
        if result["rows"]:
            print_table(result["rows"], title=f"Query Results ({result['row_count']} rows)")
        else:
            print_json(result, title="Query Result")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def tables(
    database: str = typer.Argument(..., help="Logical database name."),
    schema: str = typer.Option("public", "--schema", help="Schema name."),
    pattern: str | None = typer.Option(
        None, "--pattern", help="LIKE pattern to filter table names."
    ),
) -> None:
    """List tables in a database schema."""
    try:
        result = _client().get_tables(database=database, schema=schema, pattern=pattern)
        print_table(result, title=f"Tables in {database}.{schema}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def columns(
    database: str = typer.Argument(..., help="Logical database name."),
    table: str = typer.Argument(..., help="Table name."),
    schema: str = typer.Option("public", "--schema", help="Schema name."),
) -> None:
    """List columns for a table."""
    try:
        result = _client().get_columns(database=database, table=table, schema=schema)
        print_table(result, title=f"Columns in {database}.{schema}.{table}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def relationships(
    database: str = typer.Argument(..., help="Logical database name."),
    table: str | None = typer.Option(None, "--table", help="Filter by table name."),
    schema: str = typer.Option("public", "--schema", help="Schema name."),
) -> None:
    """Show foreign-key relationships."""
    try:
        result = _client().get_relationships(database=database, table=table, schema=schema)
        print_table(result, title=f"Foreign Keys in {database}.{schema}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def schema(
    database: str = typer.Argument(..., help="Logical database name."),
) -> None:
    """Full schema introspection for a database."""
    try:
        result = _client().introspect_schema(database=database)
        print_json(result, title=f"Schema: {database}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def explain(
    database: str = typer.Argument(..., help="Logical database name."),
    sql: str = typer.Argument(..., help="SQL query to explain."),
    analyze: bool = typer.Option(
        False, "--analyze", help="Run EXPLAIN ANALYZE (executes the query)."
    ),
) -> None:
    """Show the execution plan for a query."""
    try:
        result = _client().analyze_query(database=database, query=sql, analyze=analyze)
        print_json(result, title="Query Plan")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def stats(
    database: str | None = typer.Option(None, "--database", help="Limit to a specific database."),
) -> None:
    """Show connection pool statistics."""
    try:
        result = _client().connection_stats(database=database)
        print_json(result, title="Connection Stats")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def backup(
    database: str = typer.Argument(..., help="Logical database name."),
    table: str = typer.Argument(..., help="Table to back up."),
    schema: str = typer.Option("public", "--schema", help="Schema name."),
    where: str | None = typer.Option(
        None, "--where", help="WHERE clause filter (without 'WHERE' keyword)."
    ),
) -> None:
    """Backup table data as JSON."""
    try:
        result = _client().backup_table(database=database, table=table, schema=schema, where=where)
        print_json(result, title=f"Backup: {result['table']} ({result['row_count']} rows)")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def vacuum(
    database: str = typer.Argument(..., help="Logical database name."),
    table: str | None = typer.Option(None, "--table", help="Target table (omit for all tables)."),
    operation: str = typer.Option(
        "vacuum_analyze",
        "--operation",
        help="Operation: vacuum, analyze, or vacuum_analyze.",
    ),
) -> None:
    """Run VACUUM and/or ANALYZE on a database or table."""
    try:
        result = _client().vacuum_analyze(database=database, table=table, operation=operation)
        print_success(f"{result['operation']} on {result['table']}: {result['status']}")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def dump(
    coolify_db: str = typer.Argument(..., help="Coolify database name or UUID."),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output file. Default: <BACKUP_DIR>/<dbname>-<timestamp>.dump",
    ),
    fmt: str = typer.Option(
        "custom", "--format", "-F", help="Dump format: 'custom' (pg_restore) or 'plain' (psql)."
    ),
    schema_only: bool = typer.Option(False, "--schema-only", help="Dump DDL only."),
    data_only: bool = typer.Option(False, "--data-only", help="Dump rows only."),
    table: str | None = typer.Option(None, "--table", "-t", help="Restrict to a single table."),
) -> None:
    """Dump a remote Coolify-managed database to a local file via SSH + docker exec.

    The dump runs inside the database's container, so the version of pg_dump
    used always matches the server. Output is streamed straight to disk.
    """
    from copilot_cli.config.settings import get_settings
    from copilot_cli.services.postgresql.transfer import remote_pg_dump

    try:
        record = _resolve_remote_db(coolify_db)
        db_type = record.get("database_type", "")
        if "postgres" not in db_type:
            raise CopilotError(
                f"Database '{coolify_db}' is {db_type}, not PostgreSQL.",
                service="postgresql",
                hint="Only standalone-postgresql databases are supported.",
            )

        container = record["uuid"]
        db_user = record["postgres_user"]
        db_name = record["postgres_db"]

        if out is None:
            backup_dir = get_settings().get_backup_dir()
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            ext = ".dump" if fmt == "custom" else ".sql"
            safe_name = (record.get("name") or db_name).replace(" ", "-").replace("/", "-")
            out = backup_dir / f"{safe_name}-{ts}{ext}"

        result = remote_pg_dump(
            ssh=_ssh_target_from_coolify_settings(),
            container=container,
            db_user=db_user,
            db_name=db_name,
            output_path=out,
            fmt=fmt,
            schema_only=schema_only,
            data_only=data_only,
            table=table,
        )
        print_success(
            f"Dumped {record.get('name', container)} → {result['path']} "
            f"({result['size_bytes']:,} bytes, {result['format']} format)"
        )
        print_json(result, title="Dump Result")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


def _confirm_destructive_local(local_db_name: str, supplied_token: str | None) -> str:
    """Get a confirmation token for a destructive local op.

    If *supplied_token* is non-empty, return it as-is. Otherwise prompt
    interactively. The caller will validate it against the expected token.
    """
    if supplied_token:
        return supplied_token
    return typer.prompt(
        f"This will overwrite local database '{local_db_name}'. Type the database name to confirm",
        default="",
        show_default=False,
    )


@app.command()
def restore(
    dump_file: Path = typer.Argument(..., help="Path to a pg_dump file."),
    to: str = typer.Option(..., "--to", help="Local database short-name (must be configured)."),
    clean: bool = typer.Option(
        False, "--clean", help="For custom-format dumps: drop existing objects first."
    ),
    confirm_token: str = typer.Option(
        "",
        "--confirm-token",
        help="Non-interactive confirmation token (must equal --to value).",
    ),
) -> None:
    """Restore a dump file into a LOCAL database.

    The target must be a configured local database whose connection URL points
    at loopback. Restores against remote databases are refused unconditionally.
    """
    from copilot_cli.services.postgresql.safety import (
        PolicyViolation,
        assert_local_writeable,
    )
    from copilot_cli.services.postgresql.transfer import local_pg_restore

    try:
        target_url = _resolve_local_url(to)
        assert_local_writeable(target_url)

        token = _confirm_destructive_local(to, confirm_token)
        if token != to:
            raise PolicyViolation(
                f"Confirmation mismatch: expected '{to}', got {token!r}. Aborting.",
                service="postgresql",
            )

        result = local_pg_restore(dump_path=dump_file, target_url=target_url, clean=clean)
        print_success(f"Restored {dump_file} → {to} (via {result['tool']})")
        print_json(result, title="Restore Result")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def pull(
    coolify_db: str = typer.Argument(..., help="Coolify database name or UUID."),
    to: str = typer.Option(..., "--to", help="Local database short-name to restore into."),
    keep_dump: bool = typer.Option(False, "--keep-dump", help="Keep the intermediate dump file."),
    clean: bool = typer.Option(
        True,
        "--clean/--no-clean",
        help="Drop existing objects in the local target before restoring.",
    ),
    confirm_token: str = typer.Option(
        "",
        "--confirm-token",
        help="Non-interactive confirmation token (must equal --to value).",
    ),
) -> None:
    """Convenience: dump a remote Coolify database, then restore into a local one.

    Equivalent to running ``db dump`` then ``db restore`` in sequence.
    """
    from copilot_cli.config.settings import get_settings
    from copilot_cli.services.postgresql.safety import (
        PolicyViolation,
        assert_local_writeable,
    )
    from copilot_cli.services.postgresql.transfer import (
        local_pg_restore,
        remote_pg_dump,
    )

    try:
        target_url = _resolve_local_url(to)
        assert_local_writeable(target_url)

        token = _confirm_destructive_local(to, confirm_token)
        if token != to:
            raise PolicyViolation(
                f"Confirmation mismatch: expected '{to}', got {token!r}. Aborting.",
                service="postgresql",
            )

        record = _resolve_remote_db(coolify_db)
        if "postgres" not in record.get("database_type", ""):
            raise CopilotError(
                f"Source '{coolify_db}' is not a PostgreSQL database.",
                service="postgresql",
            )

        backup_dir = get_settings().get_backup_dir()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = (record.get("name") or record["postgres_db"]).replace(" ", "-")
        dump_path = backup_dir / f"{safe_name}-{ts}.dump"

        dump_result = remote_pg_dump(
            ssh=_ssh_target_from_coolify_settings(),
            container=record["uuid"],
            db_user=record["postgres_user"],
            db_name=record["postgres_db"],
            output_path=dump_path,
            fmt="custom",
        )
        restore_result = local_pg_restore(dump_path=dump_path, target_url=target_url, clean=clean)

        if not keep_dump:
            dump_path.unlink(missing_ok=True)

        print_success(
            f"Pulled {record.get('name', coolify_db)} → local '{to}' "
            f"({dump_result['size_bytes']:,} bytes via {restore_result['tool']})"
        )
        print_json(
            {"dump": dump_result, "restore": restore_result, "kept_dump": keep_dump},
            title="Pull Result",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def transition(
    source: str = typer.Argument(
        ..., help="Source: a local DB short-name OR a Coolify DB name/UUID."
    ),
    target: str = typer.Option(
        ..., "--to", help="Target local DB short-name (must be configured)."
    ),
    keep_dump: bool = typer.Option(False, "--keep-dump", help="Keep the intermediate dump file."),
    clean: bool = typer.Option(
        True,
        "--clean/--no-clean",
        help="Drop existing objects in the target before restoring.",
    ),
    confirm_token: str = typer.Option(
        "",
        "--confirm-token",
        help="Non-interactive confirmation token (must equal --to value).",
    ),
) -> None:
    """Copy a database from one environment into a local database.

    *source* may be either a local DB short-name (from configured
    ``*_DATABASE_URL`` env vars) or a Coolify-managed remote DB. Local sources
    are detected first; anything else is resolved through the Coolify API.
    The target must be a configured local database.
    """
    from copilot_cli.config.settings import get_settings
    from copilot_cli.services.postgresql.safety import (
        PolicyViolation,
        assert_local_writeable,
    )
    from copilot_cli.services.postgresql.transfer import (
        local_pg_dump,
        local_pg_restore,
        remote_pg_dump,
    )

    try:
        target_url = _resolve_local_url(target)
        assert_local_writeable(target_url)
        if source == target:
            raise CopilotError(
                f"Source and target are the same ('{source}'); refusing to overwrite a DB with itself.",
                service="postgresql",
            )

        token = _confirm_destructive_local(target, confirm_token)
        if token != target:
            raise PolicyViolation(
                f"Confirmation mismatch: expected '{target}', got {token!r}. Aborting.",
                service="postgresql",
            )

        backup_dir = get_settings().get_backup_dir()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        local_configs = get_settings().get_database_configs()
        if source in local_configs:
            # Local → local
            source_url = local_configs[source]
            dump_path = backup_dir / f"{source}-{ts}.dump"
            dump_result = local_pg_dump(source_url=source_url, output_path=dump_path)
            source_label = source
        else:
            # Treat as Coolify remote
            record = _resolve_remote_db(source)
            if "postgres" not in record.get("database_type", ""):
                raise CopilotError(
                    f"Source '{source}' is not a PostgreSQL database.",
                    service="postgresql",
                )
            safe_name = (record.get("name") or record["postgres_db"]).replace(" ", "-")
            dump_path = backup_dir / f"{safe_name}-{ts}.dump"
            dump_result = remote_pg_dump(
                ssh=_ssh_target_from_coolify_settings(),
                container=record["uuid"],
                db_user=record["postgres_user"],
                db_name=record["postgres_db"],
                output_path=dump_path,
            )
            source_label = record.get("name", source)

        restore_result = local_pg_restore(dump_path=dump_path, target_url=target_url, clean=clean)

        if not keep_dump:
            dump_path.unlink(missing_ok=True)

        print_success(
            f"Transitioned {source_label} → local '{target}' "
            f"({dump_result['size_bytes']:,} bytes via {restore_result['tool']})"
        )
        print_json(
            {
                "source": source_label,
                "target": target,
                "dump": dump_result,
                "restore": restore_result,
                "kept_dump": keep_dump,
            },
            title="Transition Result",
        )
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command("remote-query")
def remote_query(
    coolify_db: str = typer.Argument(..., help="Coolify database name or UUID."),
    sql: str = typer.Argument(..., help="SQL query to execute."),
    timeout: int = typer.Option(30000, "--timeout", help="Statement timeout in ms."),
) -> None:
    """Run a query against a remote Coolify-managed DB via SSH tunnel.

    The connection is tagged as tunneled-remote, so the destructive-ops policy
    refuses any DROP / TRUNCATE / DELETE / ALTER DROP regardless of flags.
    Reads and ordinary writes go through.
    """
    import psycopg2
    import psycopg2.extras

    from copilot_cli.services.coolify.core.tunnel import open_tunnel
    from copilot_cli.services.postgresql.safety import assert_destructive_allowed

    try:
        record = _resolve_remote_db(coolify_db)
        if "postgres" not in record.get("database_type", ""):
            raise CopilotError(
                f"Database '{coolify_db}' is not PostgreSQL.",
                service="postgresql",
            )
        with open_tunnel(
            ssh=_ssh_target_from_coolify_settings(),
            container=record["uuid"],
            db_user=record["postgres_user"],
            db_password=record["postgres_password"],
            db_name=record["postgres_db"],
        ) as url:
            assert_destructive_allowed(url, sql)
            conn = psycopg2.connect(url)
            conn.autocommit = True
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(f"SET statement_timeout = {int(timeout)}")
                    cur.execute(sql)
                    if cur.description is None:
                        rows: list[dict] = []
                    else:
                        rows = [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        if rows:
            print_table(rows, title=f"Remote Query: {record.get('name', coolify_db)}")
        else:
            print_json({"rows": [], "row_count": 0}, title="Remote Query")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Health-check all configured database connections."""
    try:
        result = _client().health()
        if result["healthy"]:
            print_success(f"All databases healthy ({len(result['databases'])} checked)")
        else:
            print_error("One or more databases are unhealthy")
        print_json(result, title="Database Health")
    except CopilotError as exc:
        print_error(str(exc), hint=exc.hint)
        raise typer.Exit(1)
