"""
database.py
-----------
sqlite3 driver for executing generated SQL safely.

Safety layers:
1. `assert_read_only` -- a keyword guard rejecting anything that isn't a
   pure SELECT, before the query ever touches the database. Also blocks
   direct enumeration of sqlite_master/sqlite_temp_master -- these expose
   the full table/column layout, which isn't part of this app's intended
   surface (the schema is already fully documented in db_schema.py; there's
   no legitimate reason a generated query needs to read it back from the
   database itself). This was added after red-teaming with eval_harness.py
   surfaced it as a real, if minor, information-disclosure vector.
2. `_get_connection` -- explicitly checks the DB file exists and has the
   expected tables BEFORE connecting for real. sqlite3.connect() does NOT
   raise an error for a missing file -- it silently creates a new, empty
   database.

NOTE: for production use with Postgres, pair this with running the app
under a database ROLE that only has SELECT privileges, so a bug here isn't
your only safety net.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, List

from app.config import DB_PATH

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)

# Schema-enumeration tables. Reading these isn't destructive, but it lets a
# query recover the full table/column layout beyond what the app exposes --
# a reconnaissance step, not a legitimate query need.
_FORBIDDEN_SCHEMA_TABLES = re.compile(
    r"\b(sqlite_master|sqlite_temp_master)\b",
    re.IGNORECASE,
)

_EXPECTED_TABLES = {"customers", "products", "orders", "order_items", "payments"}


class UnsafeSQLError(Exception):
    """Raised when generated SQL fails the read-only safety check."""


class SQLExecutionError(Exception):
    """Raised when sqlite3 fails to execute an otherwise 'safe' query, or
    when the configured database file/schema is invalid."""


@dataclass
class QueryResult:
    columns: List[str]
    rows: List[tuple]

    def as_dicts(self) -> List[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    def is_empty(self) -> bool:
        return len(self.rows) == 0


def assert_read_only(sql: str) -> None:
    """Raise UnsafeSQLError if the SQL is not a plain read-only SELECT."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        raise UnsafeSQLError(
            f"Generated statement does not start with SELECT: {stripped[:80]}..."
        )
    if _FORBIDDEN_KEYWORDS.search(stripped):
        raise UnsafeSQLError(
            f"Generated statement contains a forbidden keyword: {stripped[:120]}..."
        )
    if _FORBIDDEN_SCHEMA_TABLES.search(stripped):
        raise UnsafeSQLError(
            f"Generated statement attempts to enumerate schema metadata: {stripped[:120]}..."
        )
    if ";" in stripped:
        raise UnsafeSQLError("Multiple statements are not allowed.")


def _get_connection() -> sqlite3.Connection:
    """
    Open a connection to DB_PATH, but only after confirming the file exists
    and looks like the right database. Raises SQLExecutionError with a
    clear, actionable message instead of letting sqlite3 silently create an
    empty database at a wrong path.
    """
    if not os.path.exists(DB_PATH):
        raise SQLExecutionError(
            f"Database file not found at: {DB_PATH}\n"
            "  This is almost always a DB_PATH problem, not a SQL problem. "
            "Check the DB_PATH value in your .env file, or delete it to use "
            "the default (company.db next to config.py)."
        )

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    actual_tables = {row[0] for row in cur.fetchall()}
    missing = _EXPECTED_TABLES - actual_tables
    if missing:
        conn.close()
        raise SQLExecutionError(
            f"Database at {DB_PATH} is missing expected table(s): {sorted(missing)}. "
            "This usually means DB_PATH points at the wrong file, or an "
            "empty file that sqlite3 silently created because the real "
            "company.db wasn't found there."
        )
    return conn


def run_query(sql: str, row_limit: int = 500) -> QueryResult:
    """
    Execute a validated SELECT statement and return the results.

    Raises:
        UnsafeSQLError: if the SQL fails the safety check.
        SQLExecutionError: if the database file/schema is invalid, or if
            sqlite3 raises during execution (e.g. bad column name -- caught
            by the caller for a self-correction retry).
    """
    assert_read_only(sql)

    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(row_limit)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        return QueryResult(columns=columns, rows=rows)
    except sqlite3.Error as e:
        raise SQLExecutionError(str(e)) from e
    finally:
        conn.close()
