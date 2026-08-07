"""Comprehensive tests for the PostgreSQL service (client + CLI commands)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import psycopg2
import pytest

from copilot_cli.services.postgresql.client import PostgreSQLClient
from copilot_cli.shared.errors import ConfigError, CopilotError

# ======================================================================
# Helpers
# ======================================================================


def _make_mock_conn(*, closed: bool = False) -> MagicMock:
    """Build a mock psycopg2 connection with a working cursor context manager.

    The returned connection has ``autocommit``, ``closed``,
    ``server_version``, ``encoding``, and ``status`` attributes and
    produces a mock cursor via the context-manager protocol.
    """
    mock_conn = MagicMock()
    mock_conn.closed = closed
    mock_conn.autocommit = True
    mock_conn.server_version = 150000
    mock_conn.encoding = "UTF8"
    mock_conn.status = 1  # STATUS_READY

    mock_cursor = MagicMock()
    mock_cursor.description = [("col1",), ("col2",)]
    mock_cursor.fetchall.return_value = [{"col1": "val1", "col2": "val2"}]
    mock_cursor.rowcount = 1

    # Make cursor() return a context manager that yields mock_cursor.
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    # Stash the cursor on the connection for easy assertion access.
    mock_conn._mock_cursor = mock_cursor
    return mock_conn


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(autouse=True)
def _patch_client_get_settings(mock_settings):
    """Ensure the client module's local ``get_settings`` reference returns
    the fake settings provided by the conftest ``mock_settings`` fixture.

    The conftest patches ``copilot_cli.config.settings.get_settings`` on
    the *settings* module, but the client does
    ``from copilot_cli.config.settings import get_settings`` which binds
    a local name.  This fixture patches the client module's own reference.
    """
    with patch(
        "copilot_cli.services.postgresql.client.get_settings",
        return_value=mock_settings,
    ):
        yield


# ======================================================================
# Client unit tests
# ======================================================================


class TestValidateDatabase:
    """Tests for PostgreSQLClient._validate_database."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_raises_config_error_for_unknown_database(self, _mock_pg):
        client = PostgreSQLClient()
        with pytest.raises(ConfigError, match="Unknown database 'nope'"):
            client._validate_database("nope")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_passes_for_configured_databases(self, _mock_pg):
        client = PostgreSQLClient()
        # These should not raise -- the autouse mock_settings provides
        # nocodb, n8n, and main.
        client._validate_database("nocodb")
        client._validate_database("n8n")
        client._validate_database("main")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_error_message_lists_available_databases(self, _mock_pg):
        client = PostgreSQLClient()
        with pytest.raises(ConfigError) as exc_info:
            client._validate_database("unknown")
        msg = str(exc_info.value)
        assert "main" in msg
        assert "n8n" in msg
        assert "nocodb" in msg


class TestGetConnection:
    """Tests for PostgreSQLClient._get_connection."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_creates_and_caches_connection(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        conn1 = client._get_connection("nocodb")
        conn2 = client._get_connection("nocodb")

        # Should reuse the cached connection, so psycopg2.connect is
        # called only once.
        assert conn1 is conn2
        mock_pg.connect.assert_called_once_with("postgresql://test:test@localhost:5432/nocodb")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_reconnects_when_connection_is_closed(self, mock_pg):
        closed_conn = _make_mock_conn(closed=True)
        fresh_conn = _make_mock_conn()
        mock_pg.connect.side_effect = [closed_conn, fresh_conn]

        client = PostgreSQLClient()
        first = client._get_connection("nocodb")
        # Simulate the connection going stale.
        first.closed = True
        second = client._get_connection("nocodb")

        assert second is fresh_conn
        assert mock_pg.connect.call_count == 2

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_raises_copilot_error_on_connect_failure(self, mock_pg):
        mock_pg.connect.side_effect = psycopg2.OperationalError("refused")
        mock_pg.Error = psycopg2.Error

        client = PostgreSQLClient()
        with pytest.raises(CopilotError, match="Cannot connect to database 'nocodb'"):
            client._get_connection("nocodb")


class TestQuery:
    """Tests for PostgreSQLClient.query."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_returns_rows_and_columns(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        result = client.query("nocodb", "SELECT col1, col2 FROM t")

        assert result["columns"] == ["col1", "col2"]
        assert result["row_count"] == 1
        assert result["rows"] == [{"col1": "val1", "col2": "val2"}]

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_sets_statement_timeout(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.query("nocodb", "SELECT 1", timeout=5000)

        # The first execute call should set the timeout.
        timeout_call = cursor.execute.call_args_list[0]
        assert timeout_call == call("SET statement_timeout = 5000")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_ddl_statement_returns_empty_rows(self, mock_pg):
        """DDL statements (CREATE, ALTER, DROP) have no description."""
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = None
        cursor.rowcount = 0

        client = PostgreSQLClient()
        result = client.query("nocodb", "CREATE TABLE test (id int)")

        assert result["rows"] == []
        assert result["columns"] == []
        assert result["row_count"] == 0

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_query_with_params(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.query("nocodb", "SELECT * FROM t WHERE id = %s", params=(42,))

        # Second execute call should be the actual query with params.
        query_call = cursor.execute.call_args_list[1]
        assert query_call == call("SELECT * FROM t WHERE id = %s", (42,))

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_query_raises_copilot_error_on_db_error(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        mock_pg.Error = psycopg2.Error
        cursor = mock_conn._mock_cursor
        cursor.execute.side_effect = psycopg2.ProgrammingError("syntax error")

        client = PostgreSQLClient()
        with pytest.raises(CopilotError, match="Query failed on 'nocodb'"):
            client.query("nocodb", "INVALID SQL")


class TestTransaction:
    """Tests for PostgreSQLClient.transaction."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_commits_on_success(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = None
        cursor.rowcount = 1

        ops = [
            {"query": "INSERT INTO t (name) VALUES (%s)", "params": ("a",)},
            {"query": "INSERT INTO t (name) VALUES (%s)", "params": ("b",)},
        ]

        client = PostgreSQLClient()
        result = client.transaction("nocodb", ops)

        assert result["operation_count"] == 2
        assert len(result["results"]) == 2
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_rolls_back_on_failure(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        mock_pg.Error = psycopg2.Error
        cursor = mock_conn._mock_cursor
        cursor.execute.side_effect = psycopg2.IntegrityError("unique violation")

        ops = [{"query": "INSERT INTO t VALUES (1)"}]

        client = PostgreSQLClient()
        with pytest.raises(CopilotError, match="Transaction failed"):
            client.transaction("nocodb", ops)

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_restores_autocommit_on_success(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_conn.autocommit = True
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = None
        cursor.rowcount = 0

        client = PostgreSQLClient()
        client.transaction("nocodb", [{"query": "SELECT 1"}])

        # autocommit should be restored to its original value (True).
        assert mock_conn.autocommit is True

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_restores_autocommit_on_failure(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_conn.autocommit = True
        mock_pg.connect.return_value = mock_conn
        mock_pg.Error = psycopg2.Error
        cursor = mock_conn._mock_cursor
        cursor.execute.side_effect = psycopg2.Error("fail")

        client = PostgreSQLClient()
        with pytest.raises(CopilotError):
            client.transaction("nocodb", [{"query": "BAD"}])

        # autocommit must be restored even on error (finally block).
        assert mock_conn.autocommit is True

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_transaction_with_select_returns_rows(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}]
        cursor.rowcount = 1

        ops = [{"query": "SELECT id, name FROM users"}]
        client = PostgreSQLClient()
        result = client.transaction("nocodb", ops)

        assert result["results"][0]["columns"] == ["id", "name"]
        assert result["results"][0]["rows"] == [{"id": 1, "name": "Alice"}]


class TestBatchQuery:
    """Tests for PostgreSQLClient.batch_query."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_collects_all_results(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        results = client.batch_query("nocodb", ["SELECT 1", "SELECT 2"])

        assert len(results) == 2
        for r in results:
            assert "rows" in r

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_mixed_success_and_failure(self, mock_pg):
        """A failing query should not prevent subsequent queries from running."""
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        mock_pg.Error = psycopg2.Error
        cursor = mock_conn._mock_cursor

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on the 4th execute call (2nd query's actual execute after
            # SET statement_timeout). Calls: 1=SET, 2=query1, 3=SET, 4=query2
            if call_count == 4:
                raise psycopg2.ProgrammingError("bad sql")

        cursor.execute.side_effect = side_effect

        client = PostgreSQLClient()
        results = client.batch_query("nocodb", ["SELECT 1", "BAD SQL", "SELECT 3"])

        # First query succeeds, second fails, third succeeds.
        assert "rows" in results[0]
        assert "error" in results[1]
        assert "rows" in results[2]


class TestGetTables:
    """Tests for PostgreSQLClient.get_tables."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_returns_table_list(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = [("table_name",), ("table_type",), ("schema",)]
        cursor.fetchall.return_value = [
            {"table_name": "users", "table_type": "BASE TABLE", "schema": "public"},
            {"table_name": "orders", "table_type": "BASE TABLE", "schema": "public"},
        ]

        client = PostgreSQLClient()
        tables = client.get_tables("nocodb")

        assert len(tables) == 2
        assert tables[0]["table_name"] == "users"
        assert tables[1]["table_name"] == "orders"

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_filters_by_pattern(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.get_tables("nocodb", pattern="user%")

        # Should have passed pattern as a second param. The second execute
        # call is the actual query (first is SET statement_timeout).
        actual_query_call = cursor.execute.call_args_list[1]
        sql_arg = actual_query_call[0][0]
        params_arg = actual_query_call[0][1]
        assert "LIKE %s" in sql_arg
        assert params_arg == ["public", "user%"]

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_custom_schema(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.get_tables("nocodb", schema="custom")

        actual_query_call = cursor.execute.call_args_list[1]
        params_arg = actual_query_call[0][1]
        assert params_arg[0] == "custom"


class TestGetColumns:
    """Tests for PostgreSQLClient.get_columns."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_returns_column_metadata(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = [
            ("column_name",),
            ("data_type",),
            ("is_nullable",),
            ("column_default",),
            ("ordinal_position",),
            ("character_maximum_length",),
        ]
        cursor.fetchall.return_value = [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "NO",
                "column_default": "nextval('users_id_seq')",
                "ordinal_position": 1,
                "character_maximum_length": None,
            },
        ]

        client = PostgreSQLClient()
        columns = client.get_columns("nocodb", "users")

        assert len(columns) == 1
        assert columns[0]["column_name"] == "id"
        assert columns[0]["data_type"] == "integer"

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_passes_schema_and_table_params(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.get_columns("nocodb", "orders", schema="sales")

        actual_query_call = cursor.execute.call_args_list[1]
        params_arg = actual_query_call[0][1]
        assert params_arg == ["sales", "orders"]


class TestGetRelationships:
    """Tests for PostgreSQLClient.get_relationships."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_returns_foreign_keys(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = [
            ("constraint_name",),
            ("source_table",),
            ("source_column",),
            ("target_table",),
            ("target_column",),
        ]
        cursor.fetchall.return_value = [
            {
                "constraint_name": "fk_order_user",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
            }
        ]

        client = PostgreSQLClient()
        rels = client.get_relationships("nocodb", table="orders")

        assert len(rels) == 1
        assert rels[0]["source_table"] == "orders"
        assert rels[0]["target_table"] == "users"

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_without_table_filter(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.get_relationships("nocodb")

        actual_query_call = cursor.execute.call_args_list[1]
        sql_arg = actual_query_call[0][0]
        # Without a table filter the query should not include
        # "AND tc.table_name = %s".
        assert "AND tc.table_name" not in sql_arg


class TestIntrospectSchema:
    """Tests for PostgreSQLClient.introspect_schema."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_assembles_full_schema(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        # get_tables will return one table, then get_columns and
        # get_relationships will be called for it.
        table_rows = [{"table_name": "users", "table_type": "BASE TABLE", "schema": "public"}]
        column_rows = [{"column_name": "id", "data_type": "integer"}]
        rel_rows: list = []

        # fetchall is called multiple times (once per query call).
        cursor.fetchall.side_effect = [
            table_rows,  # get_tables
            column_rows,  # get_columns("users")
            rel_rows,  # get_relationships("users")
        ]

        client = PostgreSQLClient()
        result = client.introspect_schema("nocodb")

        assert result["database"] == "nocodb"
        assert result["table_count"] == 1
        assert "users" in result["tables"]
        assert result["tables"]["users"]["columns"] == column_rows
        assert result["tables"]["users"]["relationships"] == rel_rows


class TestAnalyzeQuery:
    """Tests for PostgreSQLClient.analyze_query."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_explain_returns_plan(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.fetchall.return_value = [
            ("Seq Scan on users  (cost=0.00..1.05 rows=5 width=36)",),
        ]

        client = PostgreSQLClient()
        result = client.analyze_query("nocodb", "SELECT * FROM users")

        assert result["analyze"] is False
        assert "Seq Scan" in result["plan"][0]

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_explain_analyze_flag(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.fetchall.return_value = [("Plan row",)]

        client = PostgreSQLClient()
        result = client.analyze_query("nocodb", "SELECT 1", analyze=True)

        assert result["analyze"] is True
        # The SQL should start with EXPLAIN ANALYZE.
        executed_sql = cursor.execute.call_args[0][0]
        assert executed_sql.startswith("EXPLAIN ANALYZE")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_explain_raises_on_error(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        mock_pg.Error = psycopg2.Error
        cursor = mock_conn._mock_cursor
        cursor.execute.side_effect = psycopg2.ProgrammingError("bad sql")

        client = PostgreSQLClient()
        with pytest.raises(CopilotError, match="EXPLAIN failed"):
            client.analyze_query("nocodb", "INVALID")


class TestConnectionStats:
    """Tests for PostgreSQLClient.connection_stats."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_shows_connected_status(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        # Establish a connection first.
        client._get_connection("nocodb")

        stats = client.connection_stats("nocodb")
        assert stats["nocodb"]["connected"] is True
        assert stats["nocodb"]["server_version"] == 150000
        assert stats["nocodb"]["encoding"] == "UTF8"

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_shows_disconnected_for_unused_databases(self, mock_pg):
        client = PostgreSQLClient()
        stats = client.connection_stats()

        # All configured databases should appear but none are connected.
        for db in ("nocodb", "n8n", "main"):
            assert stats[db]["connected"] is False

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_filters_to_single_database(self, mock_pg):
        client = PostgreSQLClient()
        stats = client.connection_stats("n8n")

        assert "n8n" in stats
        assert "nocodb" not in stats
        assert "main" not in stats


class TestBackupTable:
    """Tests for PostgreSQLClient.backup_table."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_returns_all_rows(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        cursor.rowcount = 2

        client = PostgreSQLClient()
        result = client.backup_table("nocodb", "users")

        assert result["table"] == "public.users"
        assert result["row_count"] == 2
        assert len(result["data"]) == 2

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_with_where_clause(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        client.backup_table("nocodb", "users", where="active = true")

        # The actual query (2nd execute call) should include WHERE.
        actual_sql = cursor.execute.call_args_list[1][0][0]
        assert "WHERE active = true" in actual_sql

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_custom_schema_in_result(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        result = client.backup_table("nocodb", "users", schema="custom")

        assert result["table"] == "custom.users"


class TestVacuumAnalyze:
    """Tests for PostgreSQLClient.vacuum_analyze."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_vacuum_analyze_default(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        result = client.vacuum_analyze("nocodb")

        assert result["operation"] == "vacuum_analyze"
        assert result["status"] == "completed"
        assert result["table"] == "(all tables)"

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_vacuum_only(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        result = client.vacuum_analyze("nocodb", operation="vacuum")

        assert result["operation"] == "vacuum"
        executed_sql = cursor.execute.call_args[0][0]
        assert executed_sql.startswith("VACUUM")
        assert "ANALYZE" not in executed_sql

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_analyze_only(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        result = client.vacuum_analyze("nocodb", operation="analyze")

        assert result["operation"] == "analyze"
        executed_sql = cursor.execute.call_args[0][0]
        assert executed_sql.startswith("ANALYZE")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_targets_specific_table(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn
        cursor = mock_conn._mock_cursor

        client = PostgreSQLClient()
        result = client.vacuum_analyze("nocodb", table="users")

        assert result["table"] == "users"
        executed_sql = cursor.execute.call_args[0][0]
        assert '"users"' in executed_sql

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_rejects_invalid_operation(self, mock_pg):
        client = PostgreSQLClient()
        with pytest.raises(CopilotError, match="Invalid operation 'drop_all'"):
            client.vacuum_analyze("nocodb", operation="drop_all")

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_restores_autocommit(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_conn.autocommit = True
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        client.vacuum_analyze("nocodb")

        # autocommit should be restored to its original value.
        assert mock_conn.autocommit is True


class TestHealth:
    """Tests for PostgreSQLClient.health."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_all_healthy(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        result = client.health()

        assert result["healthy"] is True
        # All configured databases should be present.
        for db in ("nocodb", "n8n", "main"):
            assert db in result["databases"]
            assert result["databases"][db]["healthy"] is True
            assert "latency_ms" in result["databases"][db]

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_unhealthy_database(self, mock_pg):
        mock_pg.connect.side_effect = psycopg2.OperationalError("connection refused")
        mock_pg.Error = psycopg2.Error

        client = PostgreSQLClient()
        result = client.health()

        assert result["healthy"] is False
        for db_info in result["databases"].values():
            assert db_info["healthy"] is False
            assert "error" in db_info

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_mixed_health(self, mock_pg):
        """One database healthy, another not."""
        good_conn = _make_mock_conn()

        def connect_side_effect(url):
            if "nocodb" in url:
                return good_conn
            raise psycopg2.OperationalError("refused")

        mock_pg.connect.side_effect = connect_side_effect
        mock_pg.Error = psycopg2.Error

        client = PostgreSQLClient()
        result = client.health()

        assert result["healthy"] is False
        assert result["databases"]["nocodb"]["healthy"] is True
        assert result["databases"]["n8n"]["healthy"] is False


class TestClose:
    """Tests for PostgreSQLClient.close."""

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_closes_all_connections(self, mock_pg):
        mock_conn1 = _make_mock_conn()
        mock_conn2 = _make_mock_conn()
        mock_pg.connect.side_effect = [mock_conn1, mock_conn2]

        client = PostgreSQLClient()
        client._get_connection("nocodb")
        client._get_connection("n8n")

        client.close()

        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()
        assert client._connections == {}

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_skips_already_closed_connections(self, mock_pg):
        mock_conn = _make_mock_conn(closed=True)
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        # Manually inject a "closed" connection into the cache.
        client._connections["nocodb"] = mock_conn

        # Should not raise.
        client.close()
        mock_conn.close.assert_not_called()
        assert client._connections == {}

    @patch("copilot_cli.services.postgresql.client.psycopg2")
    def test_close_tolerates_exceptions(self, mock_pg):
        mock_conn = _make_mock_conn()
        mock_conn.close.side_effect = Exception("socket error")
        mock_pg.connect.return_value = mock_conn

        client = PostgreSQLClient()
        client._get_connection("nocodb")

        # Should not raise even though close() fails.
        client.close()
        assert client._connections == {}


# ======================================================================
# CLI command tests
# ======================================================================


class TestCLIDbQuery:
    """Tests for the ``db query`` CLI command."""

    def test_successful_query(self, cli):
        mock_client = MagicMock()
        mock_client.query.return_value = {
            "rows": [{"id": 1, "name": "Alice"}],
            "row_count": 1,
            "columns": ["id", "name"],
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "query", "nocodb", "SELECT * FROM users")

        assert result.exit_code == 0
        mock_client.query.assert_called_once_with(
            database="nocodb",
            query="SELECT * FROM users",
            timeout=30000,
            confirm_token=None,
        )

    def test_query_with_timeout(self, cli):
        mock_client = MagicMock()
        mock_client.query.return_value = {
            "rows": [],
            "row_count": 0,
            "columns": [],
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "query", "nocodb", "SELECT 1", "--timeout", "5000")

        assert result.exit_code == 0
        mock_client.query.assert_called_once_with(
            database="nocodb", query="SELECT 1", timeout=5000, confirm_token=None
        )

    def test_query_error_exits_with_code_1(self, cli):
        mock_client = MagicMock()
        mock_client.query.side_effect = CopilotError(
            "Query failed", service="postgresql", hint="Check SQL"
        )

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "query", "nocodb", "BAD SQL")

        assert result.exit_code == 1

    def test_query_no_rows_prints_json(self, cli):
        mock_client = MagicMock()
        mock_client.query.return_value = {
            "rows": [],
            "row_count": 0,
            "columns": [],
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "query", "nocodb", "CREATE TABLE t (id int)")

        assert result.exit_code == 0


class TestCLIDbTables:
    """Tests for the ``db tables`` CLI command."""

    def test_lists_tables(self, cli):
        mock_client = MagicMock()
        mock_client.get_tables.return_value = [
            {"table_name": "users", "table_type": "BASE TABLE", "schema": "public"},
        ]

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "tables", "nocodb")

        assert result.exit_code == 0
        mock_client.get_tables.assert_called_once_with(
            database="nocodb", schema="public", pattern=None
        )

    def test_tables_with_schema_and_pattern(self, cli):
        mock_client = MagicMock()
        mock_client.get_tables.return_value = []

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli(
                "db",
                "tables",
                "nocodb",
                "--schema",
                "custom",
                "--pattern",
                "user%",
            )

        assert result.exit_code == 0
        mock_client.get_tables.assert_called_once_with(
            database="nocodb", schema="custom", pattern="user%"
        )

    def test_tables_error_exits_with_code_1(self, cli):
        mock_client = MagicMock()
        mock_client.get_tables.side_effect = ConfigError(
            "Unknown database 'bad'", service="postgresql"
        )

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "tables", "bad")

        assert result.exit_code == 1


class TestCLIDbColumns:
    """Tests for the ``db columns`` CLI command."""

    def test_lists_columns(self, cli):
        mock_client = MagicMock()
        mock_client.get_columns.return_value = [
            {"column_name": "id", "data_type": "integer"},
        ]

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "columns", "nocodb", "users")

        assert result.exit_code == 0
        mock_client.get_columns.assert_called_once_with(
            database="nocodb", table="users", schema="public"
        )


class TestCLIDbHealth:
    """Tests for the ``db health`` CLI command."""

    def test_healthy_output(self, cli):
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": True,
            "databases": {
                "nocodb": {"healthy": True, "latency_ms": 1.5},
                "n8n": {"healthy": True, "latency_ms": 2.0},
            },
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "health")

        assert result.exit_code == 0
        assert "healthy" in result.output.lower() or "OK" in result.output

    def test_unhealthy_output(self, cli):
        mock_client = MagicMock()
        mock_client.health.return_value = {
            "healthy": False,
            "databases": {
                "nocodb": {"healthy": False, "error": "refused"},
            },
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "health")

        # The command prints an error message but does not raise Exit(1)
        # when the client itself does not raise.
        assert result.exit_code == 0


class TestCLIDbExplain:
    """Tests for the ``db explain`` CLI command."""

    def test_explain_query(self, cli):
        mock_client = MagicMock()
        mock_client.analyze_query.return_value = {
            "plan": ["Seq Scan on users"],
            "analyze": False,
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "explain", "nocodb", "SELECT * FROM users")

        assert result.exit_code == 0
        mock_client.analyze_query.assert_called_once_with(
            database="nocodb", query="SELECT * FROM users", analyze=False
        )

    def test_explain_analyze_flag(self, cli):
        mock_client = MagicMock()
        mock_client.analyze_query.return_value = {
            "plan": ["Seq Scan on users (actual rows=5)"],
            "analyze": True,
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "explain", "nocodb", "SELECT 1", "--analyze")

        assert result.exit_code == 0
        mock_client.analyze_query.assert_called_once_with(
            database="nocodb", query="SELECT 1", analyze=True
        )


class TestCLIDbStats:
    """Tests for the ``db stats`` CLI command."""

    def test_shows_all_stats(self, cli):
        mock_client = MagicMock()
        mock_client.connection_stats.return_value = {
            "nocodb": {"connected": False},
            "n8n": {"connected": False},
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "stats")

        assert result.exit_code == 0
        mock_client.connection_stats.assert_called_once_with(database=None)


class TestCLIDbBackup:
    """Tests for the ``db backup`` CLI command."""

    def test_backup_table(self, cli):
        mock_client = MagicMock()
        mock_client.backup_table.return_value = {
            "table": "public.users",
            "row_count": 3,
            "data": [{"id": 1}, {"id": 2}, {"id": 3}],
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "backup", "nocodb", "users")

        assert result.exit_code == 0
        mock_client.backup_table.assert_called_once_with(
            database="nocodb", table="users", schema="public", where=None
        )

    def test_backup_with_where(self, cli):
        mock_client = MagicMock()
        mock_client.backup_table.return_value = {
            "table": "public.users",
            "row_count": 1,
            "data": [{"id": 1}],
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "backup", "nocodb", "users", "--where", "id=1")

        assert result.exit_code == 0
        mock_client.backup_table.assert_called_once_with(
            database="nocodb", table="users", schema="public", where="id=1"
        )


class TestCLIDbVacuum:
    """Tests for the ``db vacuum`` CLI command."""

    def test_vacuum_default(self, cli):
        mock_client = MagicMock()
        mock_client.vacuum_analyze.return_value = {
            "operation": "vacuum_analyze",
            "table": "(all tables)",
            "status": "completed",
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "vacuum", "nocodb")

        assert result.exit_code == 0
        mock_client.vacuum_analyze.assert_called_once_with(
            database="nocodb", table=None, operation="vacuum_analyze"
        )

    def test_vacuum_with_table_and_operation(self, cli):
        mock_client = MagicMock()
        mock_client.vacuum_analyze.return_value = {
            "operation": "analyze",
            "table": "users",
            "status": "completed",
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli(
                "db",
                "vacuum",
                "nocodb",
                "--table",
                "users",
                "--operation",
                "analyze",
            )

        assert result.exit_code == 0
        mock_client.vacuum_analyze.assert_called_once_with(
            database="nocodb", table="users", operation="analyze"
        )


class TestCLIDbRelationships:
    """Tests for the ``db relationships`` CLI command."""

    def test_relationships_command(self, cli):
        mock_client = MagicMock()
        mock_client.get_relationships.return_value = [
            {
                "constraint_name": "fk_order_user",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
            }
        ]

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "relationships", "nocodb")

        assert result.exit_code == 0
        mock_client.get_relationships.assert_called_once_with(
            database="nocodb", table=None, schema="public"
        )


class TestCLIDbSchema:
    """Tests for the ``db schema`` CLI command."""

    def test_schema_command(self, cli):
        mock_client = MagicMock()
        mock_client.introspect_schema.return_value = {
            "database": "nocodb",
            "table_count": 1,
            "tables": {"users": {"columns": [], "relationships": []}},
        }

        with patch(
            "copilot_cli.services.postgresql.commands._client",
            return_value=mock_client,
        ):
            result = cli("db", "schema", "nocodb")

        assert result.exit_code == 0
        mock_client.introspect_schema.assert_called_once_with(database="nocodb")
