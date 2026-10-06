"""JOB workload queries (dataset/RED_SQL/job/*.sql)."""

import re
from pathlib import Path
from typing import Any

_ID_RE = re.compile(r"^(\d+)([a-z]+)$")


class QueryNotFoundError(KeyError):
    """Unknown query id."""


def _natural_key(query_id: str) -> tuple[int, str]:
    m = _ID_RE.match(query_id)
    return (int(m.group(1)), m.group(2)) if m else (10**9, query_id)


def _count_tables(sql: str) -> int:
    """Number of aliased tables in the FROM clause (JOB queries alias every table)."""
    m = re.search(r"\bFROM\b(.*?)\bWHERE\b", sql, re.IGNORECASE | re.DOTALL)
    return len(re.findall(r"\bAS\s+\w+", m.group(1), re.IGNORECASE)) if m else 0


class QueryService:
    """Lists and reads the 113 JOB queries."""

    def __init__(self, sql_dir: Path):
        self._dir = sql_dir

    def _ids(self) -> list[str]:
        if not self._dir.is_dir():
            return []
        return sorted((p.stem for p in self._dir.glob("*.sql") if _ID_RE.match(p.stem)), key=_natural_key)

    def list_queries(self) -> list[dict[str, Any]]:
        """All queries in natural order (1a, 1b, ..., 2a, ...)."""
        out = []
        for qid in self._ids():
            m = _ID_RE.match(qid)
            sql = (self._dir / f"{qid}.sql").read_text()
            out.append(
                {
                    "id": qid,
                    "family": int(m.group(1)),  # type: ignore[union-attr]
                    "tables": _count_tables(sql),
                }
            )
        return out

    def get_query(self, query_id: str) -> dict[str, Any]:
        """One query's SQL.

        Raises:
            QueryNotFoundError: If the id is not a JOB query file.
        """
        # Validating against the listing (not the raw string) blocks path traversal.
        if query_id not in self._ids():
            raise QueryNotFoundError(query_id)
        return {"id": query_id, "sql": (self._dir / f"{query_id}.sql").read_text().strip()}
