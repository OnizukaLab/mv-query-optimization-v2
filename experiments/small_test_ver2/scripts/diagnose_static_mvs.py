#!/usr/bin/env python3
"""Execute MV creation SQL statements one by one and record results.

What this script does:
- Reads a SQL file that contains CREATE MATERIALIZED VIEW / ANALYZE statements.
- Executes statements sequentially with statement_timeout=5 minutes.
- Commits after each successful statement (including each MV creation).
- Rolls back on failure and continues to the next statement by default.
- Records success/failure in CSV and JSON summary files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection as PGConnection
from psycopg2.extensions import cursor as PGCursor
from psycopg2.extensions import QueryCanceledError


MV_COMMENT_RE = re.compile(r"^\s*--\s*MV:\s*(.+?)\s*$", re.IGNORECASE)
CREATE_MV_RE = re.compile(
    r"^\s*CREATE\s+MATERIALIZED\s+VIEW\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.DOTALL,
)
ANALYZE_RE = re.compile(r"^\s*ANALYZE\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


@dataclass
class StatementResult:
    seq: int
    mv_hint: Optional[str]
    statement_type: str
    target_name: Optional[str]
    status: str
    elapsed_sec: float
    error: str


def detect_statement_type(sql: str) -> Tuple[str, Optional[str]]:
    sql_strip = sql.strip()

    m_create = CREATE_MV_RE.match(sql_strip)
    if m_create:
        return "CREATE_MV", m_create.group(1)

    m_analyze = ANALYZE_RE.match(sql_strip)
    if m_analyze:
        return "ANALYZE", m_analyze.group(1)

    upper = sql_strip.upper()
    if upper.startswith("SET "):
        return "SET", None
    if upper.startswith("DROP "):
        return "DROP", None

    head = upper.split(None, 1)[0] if upper else "UNKNOWN"
    return head, None


def parse_sql_statements(sql_text: str) -> Iterable[Tuple[str, Optional[str]]]:
    """Yield (statement, mv_hint) while skipping psql meta commands and comments.

    The parser supports semicolon splitting while respecting single-quoted strings.
    """
    current_mv_hint: Optional[str] = None
    in_single_quote = False
    buf: List[str] = []

    lines = sql_text.splitlines(keepends=True)
    for line in lines:
        stripped = line.strip()

        # Skip psql meta commands such as "\\c imdbload"
        if stripped.startswith("\\"):
            continue

        mv_match = MV_COMMENT_RE.match(line)
        if mv_match:
            current_mv_hint = mv_match.group(1).strip()
            continue

        # Skip comments and blank lines
        if not stripped or stripped.startswith("--"):
            continue

        i = 0
        while i < len(line):
            ch = line[i]
            buf.append(ch)

            if ch == "'":
                # Handle escaped quote in SQL string: ''
                nxt = line[i + 1] if i + 1 < len(line) else ""
                if in_single_quote and nxt == "'":
                    buf.append(nxt)
                    i += 1
                else:
                    in_single_quote = not in_single_quote
            elif ch == ";" and not in_single_quote:
                statement = "".join(buf).strip()
                if statement:
                    yield statement, current_mv_hint
                buf = []
            i += 1

    # Tail fragment without semicolon
    tail = "".join(buf).strip()
    if tail:
        yield tail, current_mv_hint


def execute_statements(
    conn: PGConnection,
    statements: Iterable[Tuple[str, Optional[str]]],
    timeout_sec: int,
    stop_on_error: bool,
) -> List[StatementResult]:
    results: List[StatementResult] = []
    timeout_ms = timeout_sec * 1000

    cur: PGCursor
    with conn.cursor() as cur:
        for seq, (sql, mv_hint) in enumerate(statements, start=1):
            stmt_type, target_name = detect_statement_type(sql)
            start = time.time()
            status = "success"
            error = ""

            try:
                # Set timeout for each statement to keep behavior explicit.
                cur.execute(f"SET statement_timeout = '{timeout_ms}'")
                cur.execute(sql)
                conn.commit()
            except QueryCanceledError:
                conn.rollback()
                status = "failed"
                error = f"timeout ({timeout_sec}s)"
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                status = "failed"
                error = str(exc)

            elapsed = time.time() - start
            row = StatementResult(
                seq=seq,
                mv_hint=mv_hint,
                statement_type=stmt_type,
                target_name=target_name,
                status=status,
                elapsed_sec=round(elapsed, 5),
                error=error,
            )
            results.append(row)

            label = target_name or mv_hint or "(unknown)"
            print(
                f"[{seq}] {stmt_type:<10} {label:<30} -> {status} ({elapsed:.2f}s)",
                flush=True,
            )
            if error:
                print(f"      error: {error}", flush=True)

            if status == "failed" and stop_on_error:
                break

    return results


def write_csv(path: Path, rows: List[StatementResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seq",
                "mv_hint",
                "statement_type",
                "target_name",
                "status",
                "elapsed_sec",
                "error",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_summary_json(path: Path, rows: List[StatementResult], sql_file: Path) -> None:
    failed = [r for r in rows if r.status == "failed"]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sql_file": str(sql_file),
        "total_statements": len(rows),
        "success_count": len(rows) - len(failed),
        "failed_count": len(failed),
        "failures": [
            {
                "seq": r.seq,
                "mv_hint": r.mv_hint,
                "statement_type": r.statement_type,
                "target_name": r.target_name,
                "elapsed_sec": r.elapsed_sec,
                "error": r.error,
            }
            for r in failed
        ],
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run static_initial_mvs.sql sequentially with per-statement commit and logging"
    )
    parser.add_argument("--sql-file", required=True, help="Path to SQL file to execute")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="imdbload")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-sec", type=int, default=300, help="Statement timeout in seconds")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately on first failed statement (default: continue)",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Directory to write result CSV/JSON",
    )

    args = parser.parse_args()

    sql_file = Path(args.sql_file)
    if not sql_file.exists():
        print(f"SQL file not found: {sql_file}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"mv_execution_result_{timestamp}.csv"
    summary_path = out_dir / f"mv_execution_summary_{timestamp}.json"

    with sql_file.open("r", encoding="utf-8") as f:
        sql_text = f.read()

    statements = list(parse_sql_statements(sql_text))
    print(f"Loaded {len(statements)} statements from {sql_file}")
    print(f"statement_timeout={args.timeout_sec}s, stop_on_error={args.stop_on_error}")

    conn = None
    try:
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.user,
            password=args.password,
        )

        results = execute_statements(
            conn=conn,
            statements=statements,
            timeout_sec=args.timeout_sec,
            stop_on_error=args.stop_on_error,
        )

        write_csv(csv_path, results)
        write_summary_json(summary_path, results, sql_file)

        failed_count = sum(1 for r in results if r.status == "failed")
        print("\n=== Summary ===")
        print(f"Total:   {len(results)}")
        print(f"Success: {len(results) - failed_count}")
        print(f"Failed:  {failed_count}")
        print(f"CSV:     {csv_path}")
        print(f"JSON:    {summary_path}")

        return 0 if failed_count == 0 else 2

    finally:
        if conn is not None and not conn.closed:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
