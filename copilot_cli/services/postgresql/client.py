"""PostgreSQL multi-database client using psycopg2."""

from __future__ import annotations

import time
from typing import Any

import psycopg2
import psycopg2.extras

from copilot_cli.config.settings import get_settings
from copilot_cli.shared.errors import ConfigError, CopilotError


class PostgreSQLClient:
    """Multi-database PostgreSQL client with connection caching.

    Loads database connection URLs from settings and provides a unified
    interface for querying, introspection, and maintenance across all
    configured databases.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._configs: dict[str, str] = settings.get_database_configs()
        self._connections: dict[str, psycopg2.extensions.connection] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _validate_database(self, database: str) -> None:
        """Raise ConfigError if the database name is not configured.

        Args:
            database: Logical database name (e.g. ``nocodb``, ``n8n``).

        Raises:
            ConfigError: If the name is not present in settings.
        """
        if database not in self._configs:
            available = ", ".join(sorted(self._configs.keys())) or "(none)"
            raise ConfigError(
                f"Unknown database '{database}'. Available: {available}",
                service="postgresql",
                hint="Check your .env file for *_DATABASE_URL variables.",
            )

    def _get_connection(self, database: str) -> psycopg2.extensions.connection:
        """Return a cached connection for *database*, creating one if needed.

        Args:
            database: Logical database name.

        Returns:
            An open psycopg2 connection.

        Raises:
            ConfigError: If the database name is unknown.
            CopilotError: If the connection attempt fails.
        """
        self._validate_database(database)

        conn = self._connections.get(database)
        if conn is not None and not conn.closed:
            return conn

        try:
            conn = psycopg2.connect(self._configs[database])
            conn.autocommit = True
            self._connections[database] = conn
            return conn
        except psycopg2.Error as exc:
            raise CopilotError(
                f"Cannot connect to database '{database}': {exc}",
                service="postgresql",
                hint="Verify the connection URL and that the server is reachable.",
            ) from exc

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def _assert_safe(
        self,
        database: str,
        sql: str,
        confirm_token: str | None,
    ) -> None:
        """Apply the project's destructive-ops policy before executing *sql*.

        Args:
            database: Logical database short-name used as the expected
                confirmation token for destructive ops on a local database.
            sql: Statement about to be executed.
            confirm_token: Token supplied by the caller — must equal
                *database* if the statement is destructive and the target
                is local. Ignored when *sql* is non-destructive.

        Raises:
            PolicyViolation: When the operation is forbidden by policy.
        """
        from copilot_cli.services.postgresql.safety import (
            assert_destructive_allowed,
        )

        assert_destructive_allowed(
            self._configs[database],
            sql,
            confirm_token=confirm_token,
            expected_token=database,
        )

    def query(
        self,
        database: str,
        query: str,
        params: tuple | list | None = None,
        timeout: int = 30000,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Execute a SQL query and return the results.

        Args:
            database: Logical database name.
            query: SQL statement to execute.
            params: Optional bind parameters for the query.
            timeout: Statement timeout in milliseconds.
            confirm_token: When *query* is destructive (``DROP``, ``TRUNCATE``,
                ``DELETE FROM``, ``ALTER ... DROP``) on a local database, this
                token must equal *database*. Destructive SQL on a non-local
                database is refused unconditionally.

        Returns:
            Dict with ``rows`` (list of dicts), ``row_count``, and ``columns``.

        Raises:
            CopilotError: On any database error.
            PolicyViolation: When the destructive-ops policy is violated.
        """
        self._validate_database(database)
        self._assert_safe(database, query, confirm_token)
        conn = self._get_connection(database)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SET statement_timeout = {int(timeout)}")
                cur.execute(query, params)

                if cur.description is None:
                    return {
                        "rows": [],
                        "row_count": cur.rowcount,
                        "columns": [],
                    }

                columns = [desc[0] for desc in cur.description]
                rows = [dict(row) for row in cur.fetchall()]
                return {
                    "rows": rows,
                    "row_count": len(rows),
                    "columns": columns,
                }
        except psycopg2.Error as exc:
            raise CopilotError(
                f"Query failed on '{database}': {exc}",
                service="postgresql",
                hint="Check your SQL syntax and parameters.",
            ) from exc

    def transaction(
        self,
        database: str,
        operations: list[dict[str, Any]],
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Execute multiple queries inside a single transaction.

        Args:
            database: Logical database name.
            operations: List of dicts, each with a ``query`` key and an
                optional ``params`` key.
            confirm_token: Required when any operation is destructive on a
                local database. Same semantics as :meth:`query`.

        Returns:
            Dict with ``results`` (list of per-operation result dicts) and
            ``operation_count``.

        Raises:
            CopilotError: If any operation fails (the transaction is rolled
            back).
            PolicyViolation: When the destructive-ops policy is violated.
        """
        self._validate_database(database)
        for op in operations:
            self._assert_safe(database, op["query"], confirm_token)
        conn = self._get_connection(database)
        old_autocommit = conn.autocommit
        conn.autocommit = False
        results: list[dict[str, Any]] = []
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for op in operations:
                    sql = op["query"]
                    params = op.get("params")
                    cur.execute(sql, params)

                    if cur.description is not None:
                        columns = [desc[0] for desc in cur.description]
                        rows = [dict(row) for row in cur.fetchall()]
                    else:
                        columns = []
                        rows = []

                    results.append(
                        {
                            "rows": rows,
                            "row_count": cur.rowcount,
                            "columns": columns,
                        }
                    )
            conn.commit()
            return {"results": results, "operation_count": len(results)}
        except psycopg2.Error as exc:
            conn.rollback()
            raise CopilotError(
                f"Transaction failed on '{database}': {exc}",
                service="postgresql",
                hint="All operations have been rolled back.",
            ) from exc
        finally:
            conn.autocommit = old_autocommit

    def batch_query(
        self,
        database: str,
        queries: list[str],
        confirm_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute multiple independent queries and collect results.

        Each query is executed separately; a failure in one does not affect
        the others. The destructive-ops policy applies per query — pass
        *confirm_token* if any of the statements is destructive on a local DB.

        Args:
            database: Logical database name.
            queries: List of SQL statements.
            confirm_token: Optional confirmation token (see :meth:`query`).

        Returns:
            List of result dicts (same shape as :meth:`query`). On per-query
            failure the entry contains an ``error`` key instead.
        """
        results: list[dict[str, Any]] = []
        for sql in queries:
            try:
                results.append(self.query(database, sql, confirm_token=confirm_token))
            except CopilotError as exc:
                results.append({"error": str(exc)})
        return results

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def get_tables(
        self,
        database: str,
        schema: str = "public",
        pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """List tables in a schema.

        Args:
            database: Logical database name.
            schema: PostgreSQL schema name.
            pattern: Optional LIKE pattern to filter table names.

        Returns:
            List of dicts with ``table_name``, ``table_type``, and ``schema``.
        """
        sql = (
            "SELECT tablename AS table_name, "
            "       'BASE TABLE' AS table_type, "
            "       schemaname AS schema "
            "FROM pg_tables "
            "WHERE schemaname = %s"
        )
        params: list[Any] = [schema]

        if pattern:
            sql += " AND tablename LIKE %s"
            params.append(pattern)

        sql += " ORDER BY tablename"

        result = self.query(database, sql, params)
        return result["rows"]

    def get_columns(
        self,
        database: str,
        table: str,
        schema: str = "public",
    ) -> list[dict[str, Any]]:
        """List columns for a table.

        Args:
            database: Logical database name.
            table: Table name.
            schema: PostgreSQL schema name.

        Returns:
            List of dicts with column metadata (name, type, nullable, default,
            ordinal position).
        """
        sql = (
            "SELECT column_name, data_type, is_nullable, column_default, "
            "       ordinal_position, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position"
        )
        result = self.query(database, sql, [schema, table])
        return result["rows"]

    def get_relationships(
        self,
        database: str,
        table: str | None = None,
        schema: str = "public",
    ) -> list[dict[str, Any]]:
        """List foreign-key relationships.

        Args:
            database: Logical database name.
            table: Optional table name to filter by.
            schema: PostgreSQL schema name.

        Returns:
            List of dicts describing each foreign-key constraint.
        """
        sql = (
            "SELECT "
            "  tc.constraint_name, "
            "  tc.table_name AS source_table, "
            "  kcu.column_name AS source_column, "
            "  ccu.table_name AS target_table, "
            "  ccu.column_name AS target_column "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "  AND ccu.table_schema = tc.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = %s"
        )
        params: list[Any] = [schema]

        if table:
            sql += " AND tc.table_name = %s"
            params.append(table)

        sql += " ORDER BY tc.table_name, kcu.column_name"

        result = self.query(database, sql, params)
        return result["rows"]

    def introspect_schema(self, database: str) -> dict[str, Any]:
        """Return a full schema introspection for all public tables.

        Gathers tables, their columns, and foreign-key constraints into a
        single dict keyed by table name.

        Args:
            database: Logical database name.

        Returns:
            Dict with ``database``, ``table_count``, and ``tables`` (a dict
            mapping table names to their columns and relationships).
        """
        tables = self.get_tables(database)
        schema: dict[str, Any] = {}

        for tbl in tables:
            name = tbl["table_name"]
            schema[name] = {
                "columns": self.get_columns(database, name),
                "relationships": self.get_relationships(database, table=name),
            }

        return {
            "database": database,
            "table_count": len(tables),
            "tables": schema,
        }

    # ------------------------------------------------------------------
    # Query analysis
    # ------------------------------------------------------------------

    def analyze_query(
        self,
        database: str,
        query: str,
        params: tuple | list | None = None,
        analyze: bool = False,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Run EXPLAIN on a query and return the plan.

        ``EXPLAIN ANALYZE`` actually executes the underlying query, so a
        destructive statement under ``analyze=True`` triggers the
        destructive-ops policy. Plain ``EXPLAIN`` is read-only and is allowed
        regardless.

        Args:
            database: Logical database name.
            query: SQL statement to explain.
            params: Optional bind parameters.
            analyze: If ``True``, run ``EXPLAIN ANALYZE`` (actually executes
                the query).
            confirm_token: Required when *analyze* is True and the underlying
                query is destructive on a local database.

        Returns:
            Dict with the ``plan`` (list of plan lines) and ``analyze`` flag.
        """
        prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
        explain_sql = f"{prefix} {query}"

        if analyze:
            self._validate_database(database)
            self._assert_safe(database, query, confirm_token)
        conn = self._get_connection(database)
        try:
            with conn.cursor() as cur:
                cur.execute(explain_sql, params)
                plan_rows = cur.fetchall()
                plan = [row[0] for row in plan_rows]
                return {"plan": plan, "analyze": analyze}
        except psycopg2.Error as exc:
            raise CopilotError(
                f"EXPLAIN failed on '{database}': {exc}",
                service="postgresql",
                hint="Verify the SQL syntax.",
            ) from exc

    # ------------------------------------------------------------------
    # Maintenance & stats
    # ------------------------------------------------------------------

    def connection_stats(self, database: str | None = None) -> dict[str, Any]:
        """Return connection pool statistics.

        Args:
            database: If given, return stats for only that database.
                Otherwise return stats for all configured databases.

        Returns:
            Dict mapping database names to their connection state info.
        """
        targets = [database] if database else list(self._configs.keys())
        stats: dict[str, Any] = {}
        for db in targets:
            conn = self._connections.get(db)
            if conn is not None and not conn.closed:
                stats[db] = {
                    "connected": True,
                    "server_version": conn.server_version,
                    "encoding": conn.encoding,
                    "status": conn.status,
                }
            else:
                stats[db] = {"connected": False}
        return stats

    def backup_table(
        self,
        database: str,
        table: str,
        schema: str = "public",
        where: str | None = None,
    ) -> dict[str, Any]:
        """Select all rows from a table (optionally filtered).

        This is a logical backup -- it returns the data as a list of dicts.

        Args:
            database: Logical database name.
            table: Table name.
            schema: PostgreSQL schema name.
            where: Optional WHERE clause (without the ``WHERE`` keyword).

        Returns:
            Dict with ``table``, ``row_count``, and ``data``.
        """
        # Use quoting for identifiers to prevent SQL injection
        sql = f'SELECT * FROM "{schema}"."{table}"'
        if where:
            sql += f" WHERE {where}"

        result = self.query(database, sql)
        return {
            "table": f"{schema}.{table}",
            "row_count": result["row_count"],
            "data": result["rows"],
        }

    def vacuum_analyze(
        self,
        database: str,
        table: str | None = None,
        operation: str = "vacuum_analyze",
    ) -> dict[str, Any]:
        """Run VACUUM and/or ANALYZE on a database or table.

        Args:
            database: Logical database name.
            table: Optional table name. If omitted the operation targets the
                entire database.
            operation: One of ``vacuum``, ``analyze``, or ``vacuum_analyze``.

        Returns:
            Dict with ``operation``, ``table``, and ``status``.

        Raises:
            CopilotError: On invalid operation or database error.
        """
        valid_ops = {"vacuum", "analyze", "vacuum_analyze"}
        if operation not in valid_ops:
            raise CopilotError(
                f"Invalid operation '{operation}'. Choose from: {', '.join(sorted(valid_ops))}",
                service="postgresql",
            )

        conn = self._get_connection(database)
        # VACUUM cannot run inside a transaction block
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            target = f'"{table}"' if table else ""
            if operation == "vacuum":
                sql = f"VACUUM {target}"
            elif operation == "analyze":
                sql = f"ANALYZE {target}"
            else:
                sql = f"VACUUM ANALYZE {target}"

            with conn.cursor() as cur:
                cur.execute(sql.strip())

            return {
                "operation": operation,
                "table": table or "(all tables)",
                "status": "completed",
            }
        except psycopg2.Error as exc:
            raise CopilotError(
                f"VACUUM/ANALYZE failed on '{database}': {exc}",
                service="postgresql",
            ) from exc
        finally:
            conn.autocommit = old_autocommit

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Test connectivity to all configured databases.

        Returns:
            Dict with ``healthy`` (bool) and ``databases`` (per-database
            status with latency).
        """
        databases: dict[str, Any] = {}
        all_healthy = True

        for name in self._configs:
            start = time.monotonic()
            try:
                conn = self._get_connection(name)
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                elapsed_ms = round((time.monotonic() - start) * 1000, 2)
                databases[name] = {
                    "healthy": True,
                    "latency_ms": elapsed_ms,
                }
            except Exception as exc:
                all_healthy = False
                databases[name] = {
                    "healthy": False,
                    "error": str(exc),
                }

        return {"healthy": all_healthy, "databases": databases}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all cached database connections."""
        for _name, conn in self._connections.items():
            try:
                if not conn.closed:
                    conn.close()
            except Exception:
                pass
        self._connections.clear()
