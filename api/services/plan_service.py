"""Query plan retrieval through ``src.database``.

Safety: statements run in a READ ONLY transaction that is always rolled back,
with a statement_timeout, and only a single statement is accepted.
"""

import dataclasses
import logging
from typing import Any

import psycopg2
import sqlparse

from config.settings import DatabaseConfig
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

_ALLOWED_FIRST_KEYWORDS = {"SELECT", "WITH", "VALUES", "TABLE"}


class InvalidQueryError(ValueError):
    """The submitted SQL is not an acceptable single read-only statement."""


class PlanError(RuntimeError):
    """PostgreSQL rejected the statement or the connection failed."""


def validate_sql(sql: str) -> str:
    """Validate that ``sql`` is a single SELECT-like statement.

    Args:
        sql: User-supplied SQL.

    Returns:
        The statement without a trailing semicolon.

    Raises:
        InvalidQueryError: If empty, multi-statement, or not a read query.
    """
    statements = [s for s in sqlparse.parse(sql) if str(s).strip().strip(";").strip()]
    if len(statements) != 1:
        raise InvalidQueryError("Exactly one SQL statement is required")
    stmt = statements[0]
    first = stmt.token_first(skip_cm=True)
    keyword = first.normalized.upper() if first is not None else ""
    if keyword not in _ALLOWED_FIRST_KEYWORDS:
        raise InvalidQueryError("Only SELECT/WITH queries can be explained")
    return str(stmt).strip().rstrip(";").strip()


class PlanService:
    """Fetches EXPLAIN (FORMAT JSON) plans from PostgreSQL."""

    def __init__(self, db_config: DatabaseConfig):
        self._config = db_config

    def get_plan(self, sql: str, analyze: bool = False, timeout_s: int = 30) -> dict[str, Any]:
        """Return the top-level EXPLAIN JSON object.

        Args:
            sql: Single read-only statement.
            analyze: Use EXPLAIN ANALYZE (still inside a read-only transaction).
            timeout_s: statement_timeout in seconds.

        Returns:
            Dict with ``Plan`` and, for ANALYZE, timing keys.

        Raises:
            InvalidQueryError: If ``sql`` fails validation.
            PlanError: On database errors.
        """
        statement = validate_sql(sql)
        options = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
        db = DatabaseConnection(dataclasses.replace(self._config, timeout=timeout_s))
        try:
            conn = db.get_connection()
            conn.set_session(readonly=True, autocommit=False)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"EXPLAIN ({options}) {statement}")
                    row = cur.fetchone()
            finally:
                conn.rollback()
        except psycopg2.Error as e:
            logger.warning(f"EXPLAIN failed: {e}")
            raise PlanError(str(e).strip()) from e
        finally:
            db.close()
        return row[0][0]

    def ping(self) -> None:
        """Raise ``PlanError`` if the database is unreachable."""
        db = DatabaseConnection(self._config)
        try:
            db.fetch_one("SELECT 1")
        except psycopg2.Error as e:
            raise PlanError(str(e).strip()) from e
        finally:
            db.close()
