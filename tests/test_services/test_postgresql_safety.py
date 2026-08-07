"""Tests for the PostgreSQL connection safety guard.

These tests exist to enforce the project policy that destructive database
operations are forbidden on non-local connections and require explicit
confirmation on local ones. If any of these break, the policy enforcement
has regressed and the tool may be one bug away from removing production data.
"""

from __future__ import annotations

import pytest

from copilot_cli.services.postgresql.safety import (
    ConnectionKind,
    PolicyViolation,
    assert_destructive_allowed,
    assert_local_writeable,
    classify_connection,
    is_destructive_sql,
    register_tunneled,
    unregister_tunneled,
)

LOCAL_URL = "postgresql://u:p@localhost:5432/main"
LOCAL_IP_URL = "postgresql://u:p@127.0.0.1:5432/main"
LOCAL_IPV6_URL = "postgresql://u:p@[::1]:5432/main"
TUNNELED_URL = "postgresql://u:p@localhost:54321/remote"
REMOTE_URL = "postgresql://u:p@db.example.com:5432/prod"
REMOTE_IP_URL = "postgresql://u:p@10.0.0.5:5432/prod"


@pytest.fixture(autouse=True)
def _clear_tunnel_registry():
    """Ensure tunnel registry isolation between tests."""
    yield
    for url in (TUNNELED_URL, LOCAL_URL, LOCAL_IP_URL, LOCAL_IPV6_URL):
        unregister_tunneled(url)


# ---------------------------------------------------------------------------
# classify_connection
# ---------------------------------------------------------------------------


class TestClassifyConnection:
    def test_localhost_is_local(self):
        assert classify_connection(LOCAL_URL) is ConnectionKind.LOCAL

    def test_loopback_ipv4_is_local(self):
        assert classify_connection(LOCAL_IP_URL) is ConnectionKind.LOCAL

    def test_loopback_ipv6_is_local(self):
        assert classify_connection(LOCAL_IPV6_URL) is ConnectionKind.LOCAL

    def test_external_hostname_is_direct_remote(self):
        assert classify_connection(REMOTE_URL) is ConnectionKind.DIRECT_REMOTE

    def test_external_ip_is_direct_remote(self):
        assert classify_connection(REMOTE_IP_URL) is ConnectionKind.DIRECT_REMOTE

    def test_loopback_in_tunnel_registry_is_tunneled(self):
        register_tunneled(TUNNELED_URL)
        assert classify_connection(TUNNELED_URL) is ConnectionKind.TUNNELED_REMOTE

    def test_unregistering_tunnel_reverts_to_local(self):
        register_tunneled(TUNNELED_URL)
        assert classify_connection(TUNNELED_URL) is ConnectionKind.TUNNELED_REMOTE
        unregister_tunneled(TUNNELED_URL)
        assert classify_connection(TUNNELED_URL) is ConnectionKind.LOCAL

    def test_unregister_unknown_url_is_silent(self):
        unregister_tunneled("postgresql://nope")  # must not raise


# ---------------------------------------------------------------------------
# is_destructive_sql
# ---------------------------------------------------------------------------


class TestIsDestructiveSql:
    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE users",
            "drop database prod",
            "DROP   SCHEMA public CASCADE",
            "DROP MATERIALIZED VIEW daily_summary",
            "DROP INDEX idx_users_email",
            "TRUNCATE users",
            "TRUNCATE TABLE users",
            "TRUNCATE ONLY TABLE users",
            "DELETE FROM users",
            "DELETE FROM users WHERE id = 1",
            'ALTER TABLE "users" DROP COLUMN email',
            "alter table public.users drop constraint fk_x",
            "BEGIN; DROP TABLE x; COMMIT;",
            "SELECT 1; DROP TABLE x",
        ],
    )
    def test_detects_destructive(self, sql: str):
        assert is_destructive_sql(sql), f"should detect: {sql!r}"

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "INSERT INTO users (id) VALUES (1)",
            "UPDATE users SET name='x' WHERE id=1",
            "CREATE TABLE foo (id int)",
            "CREATE INDEX idx ON users(id)",
            "ALTER TABLE users ADD COLUMN email text",
            "ALTER TABLE users RENAME TO clients",
            "VACUUM ANALYZE",
            "EXPLAIN SELECT * FROM users",
            "",
        ],
    )
    def test_allows_non_destructive(self, sql: str):
        assert not is_destructive_sql(sql), f"should not flag: {sql!r}"

    def test_destructive_inside_line_comment_is_ignored(self):
        assert not is_destructive_sql("SELECT 1 -- DROP TABLE users")

    def test_destructive_inside_block_comment_is_ignored(self):
        assert not is_destructive_sql("/* DROP TABLE users */ SELECT 1")

    def test_destructive_outside_comment_still_caught(self):
        assert is_destructive_sql("/* harmless */ DROP TABLE users")

    def test_drop_keyword_in_string_literal_is_a_known_false_positive(self):
        # Documented limitation: we do not parse string literals. A DROP keyword
        # inside a string would be flagged. This test pins the behavior so that
        # if someone improves the regex to handle quoted strings, they update
        # this test consciously.
        assert is_destructive_sql("SELECT 'DROP TABLE x' AS warning")


# ---------------------------------------------------------------------------
# assert_destructive_allowed
# ---------------------------------------------------------------------------


class TestAssertDestructiveAllowed:
    def test_non_destructive_always_allowed(self):
        # No raise on remote, no raise on local, regardless of token.
        assert_destructive_allowed(REMOTE_URL, "SELECT 1")
        assert_destructive_allowed(LOCAL_URL, "INSERT INTO t VALUES (1)")

    def test_destructive_on_remote_refused(self):
        with pytest.raises(PolicyViolation, match="direct-remote"):
            assert_destructive_allowed(REMOTE_URL, "DROP TABLE users")

    def test_destructive_on_tunneled_remote_refused(self):
        register_tunneled(TUNNELED_URL)
        with pytest.raises(PolicyViolation, match="tunneled-remote"):
            assert_destructive_allowed(TUNNELED_URL, "DROP TABLE users")

    def test_destructive_on_remote_refused_even_with_correct_token(self):
        # Token confirmation is irrelevant for non-local connections.
        with pytest.raises(PolicyViolation, match="direct-remote"):
            assert_destructive_allowed(
                REMOTE_URL,
                "DROP TABLE users",
                confirm_token="users",
                expected_token="users",
            )

    def test_destructive_on_local_without_token_refused(self):
        with pytest.raises(PolicyViolation, match="confirmation token"):
            assert_destructive_allowed(LOCAL_URL, "DROP TABLE users")

    def test_destructive_on_local_with_wrong_token_refused(self):
        with pytest.raises(PolicyViolation, match="confirmation token"):
            assert_destructive_allowed(
                LOCAL_URL,
                "DROP TABLE users",
                confirm_token="wrong",
                expected_token="users",
            )

    def test_destructive_on_local_with_matching_token_allowed(self):
        # No raise.
        assert_destructive_allowed(
            LOCAL_URL,
            "DROP TABLE users",
            confirm_token="users",
            expected_token="users",
        )

    def test_destructive_on_local_with_only_one_token_supplied_refused(self):
        with pytest.raises(PolicyViolation):
            assert_destructive_allowed(
                LOCAL_URL,
                "DROP TABLE users",
                confirm_token="users",
                expected_token=None,
            )
        with pytest.raises(PolicyViolation):
            assert_destructive_allowed(
                LOCAL_URL,
                "DROP TABLE users",
                confirm_token=None,
                expected_token="users",
            )


# ---------------------------------------------------------------------------
# assert_local_writeable
# ---------------------------------------------------------------------------


class TestAssertLocalWriteable:
    def test_local_loopback_allowed(self):
        assert_local_writeable(LOCAL_URL)
        assert_local_writeable(LOCAL_IP_URL)

    def test_remote_refused(self):
        with pytest.raises(PolicyViolation, match="direct-remote"):
            assert_local_writeable(REMOTE_URL)

    def test_tunneled_remote_refused(self):
        register_tunneled(TUNNELED_URL)
        with pytest.raises(PolicyViolation, match="tunneled-remote"):
            assert_local_writeable(TUNNELED_URL)
