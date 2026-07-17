"""Database connection safety guard.

Enforces the project policy on destructive database operations:

- No destructive ops on any non-local database, ever (includes connections that
  reach a remote DB through an SSH tunnel even though their URL is loopback).
- Destructive ops on a local DB require an explicit per-call confirmation token
  matching a value the caller supplies (typically the database name typed by the
  user at an interactive prompt).

A "destructive" statement is one that removes or restructures data:
``DROP``, ``TRUNCATE``, ``DELETE FROM``, ``ALTER TABLE ... DROP``. Reads and
ordinary writes (``INSERT``/``UPDATE``) are not blocked by this guard — callers
that want to forbid remote writes should use :func:`assert_local_writeable`.
"""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlparse

from copilot_cli.shared.errors import CopilotError

LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", ""})


class ConnectionKind(str, Enum):
    """How a database connection should be treated for safety purposes."""

    LOCAL = "local"
    TUNNELED_REMOTE = "tunneled-remote"
    DIRECT_REMOTE = "direct-remote"


class PolicyViolation(CopilotError):
    """A database operation was refused because it would violate policy."""


_tunneled_urls: set[str] = set()


def register_tunneled(url: str) -> None:
    """Mark *url* as a connection that reaches a remote DB via SSH tunnel.

    A tunneled connection's URL is loopback (e.g. ``localhost:54321``) but the
    actual database lives on a remote host, so the safety guard must treat it as
    remote even though the host check alone would say local.
    """
    _tunneled_urls.add(url)


def unregister_tunneled(url: str) -> None:
    """Remove *url* from the tunnel registry. No-op if absent."""
    _tunneled_urls.discard(url)


def is_tunneled(url: str) -> bool:
    """Return whether *url* is currently registered as a tunneled connection."""
    return url in _tunneled_urls


def classify_connection(url: str) -> ConnectionKind:
    """Classify *url* as local, tunneled-remote, or direct-remote.

    Args:
        url: A PostgreSQL connection URL (``postgres://user:pass@host:port/db``)
             or any URL whose host portion can be parsed by ``urllib.parse``.

    Returns:
        - ``LOCAL`` if the host is loopback AND the URL is not in the tunnel
          registry.
        - ``TUNNELED_REMOTE`` if the host is loopback AND the URL is registered
          as tunneled.
        - ``DIRECT_REMOTE`` otherwise.
    """
    host = (urlparse(url).hostname or "").lower()
    if host in LOOPBACK_HOSTS:
        return ConnectionKind.TUNNELED_REMOTE if url in _tunneled_urls else ConnectionKind.LOCAL
    return ConnectionKind.DIRECT_REMOTE


# ---------------------------------------------------------------------------
# Destructive-SQL detection
# ---------------------------------------------------------------------------

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

_DESTRUCTIVE_KEYWORDS = re.compile(
    r"\b(?:"
    r"DROP\s+(?:DATABASE|TABLE|SCHEMA|INDEX|VIEW|MATERIALIZED\s+VIEW|"
    r"FUNCTION|PROCEDURE|TYPE|SEQUENCE|TRIGGER|ROLE|USER|EXTENSION|"
    r"PUBLICATION|SUBSCRIPTION|TABLESPACE)"
    r"|TRUNCATE(?:\s+(?:ONLY\s+)?TABLE)?"
    r"|DELETE\s+FROM"
    r"|ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?[\w.\"]+\s+DROP\s+"
    r"(?:COLUMN|CONSTRAINT)"
    r")\b",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* … */`` block comments from *sql*."""
    return _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql))


def is_destructive_sql(sql: str) -> bool:
    """Return True if *sql* contains a destructive statement.

    Comments are stripped before matching so a destructive keyword hidden inside
    a comment does not count, and conversely a destructive statement preceded by
    a misleading comment is still detected.
    """
    return bool(_DESTRUCTIVE_KEYWORDS.search(_strip_comments(sql)))


# ---------------------------------------------------------------------------
# Assertions used by command-handler code
# ---------------------------------------------------------------------------


def assert_destructive_allowed(
    url: str,
    sql: str,
    *,
    confirm_token: str | None = None,
    expected_token: str | None = None,
) -> None:
    """Raise :class:`PolicyViolation` if running *sql* against *url* is forbidden.

    Non-destructive SQL is always allowed and this function returns without
    raising. For destructive SQL:

    - On a non-local connection (direct-remote OR tunneled-remote), the call is
      always refused.
    - On a local connection, the caller must pass a *confirm_token* that matches
      *expected_token* exactly. Both being ``None`` counts as a missing token
      and is refused.

    Args:
        url: Target connection URL.
        sql: SQL statement (or batch) about to be executed.
        confirm_token: Token supplied by the caller, typically read from an
            interactive prompt asking the user to type the DB or table name.
        expected_token: Token the caller expects (typically derived from the
            target — DB name, table name, etc.) so that copy-pasting a wrong
            confirmation is also refused.
    """
    if not is_destructive_sql(sql):
        return

    kind = classify_connection(url)
    if kind is not ConnectionKind.LOCAL:
        raise PolicyViolation(
            f"Refused: destructive SQL is not allowed on a {kind.value} connection. "
            "This tool may only run destructive operations against a local database, "
            "and only with an explicit per-call confirmation.",
            service="postgresql",
            hint="Run the operation from outside this tool, or target a local DB.",
        )

    if expected_token is None or confirm_token is None or confirm_token != expected_token:
        raise PolicyViolation(
            "Refused: destructive SQL on a local database requires an explicit "
            "confirmation token that matches the target. "
            "Re-run with the matching token (typically the database or table name).",
            service="postgresql",
            hint="Interactive callers should prompt the user to type the target name.",
        )


def assert_local_writeable(url: str) -> None:
    """Raise :class:`PolicyViolation` unless *url* is a local non-tunneled DB.

    Used by paths that overwrite or restructure the target without running raw
    SQL — for example, ``pg_restore`` against a database, where the restore
    itself implies destructive intent on whatever the target currently holds.
    """
    kind = classify_connection(url)
    if kind is ConnectionKind.LOCAL:
        return
    raise PolicyViolation(
        f"Refused: target is a {kind.value} connection. This tool only writes to local databases.",
        service="postgresql",
        hint="Point the operation at a local database (loopback, not tunneled).",
    )
