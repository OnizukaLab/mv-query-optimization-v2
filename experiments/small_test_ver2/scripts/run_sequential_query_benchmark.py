#!/usr/bin/env python3
"""Simple sequential query benchmark.

What it does:
1. Drop all existing materialized views in public schema.
2. Run ANALYZE on base tables.
3. Execute all .sql files in a query directory sequentially.
4. Measure per-query execution time and total execution time.
5. Save results to JSON.

Example:
    .venv/bin/python experiments/small_test_ver2/scripts/run_sequential_query_benchmark.py \
        --query-dir experiments/small_test_ver2/01_queries/cluster_55_26_3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2

# Add project root to import Settings
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings

# JOB(IMDB) base tables
BASE_TABLES = [
    "title",
    "cast_info",
    "movie_info",
    "movie_companies",
    "movie_keyword",
    "name",
    "person_info",
    "movie_info_idx",
    "aka_name",
    "aka_title",
    "char_name",
    "complete_cast",
    "movie_link",
    "keyword",
    "company_name",
    "company_type",
    "info_type",
    "kind_type",
    "role_type",
    "link_type",
    "comp_cast_type",
]


def natural_sort_key(path: Path) -> list[Any]:
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"([0-9]+)", path.name)]


def connect(host: str, database: str, user: str, password: str):
    conn = psycopg2.connect(host=host, database=database, user=user, password=password)
    conn.autocommit = True
    return conn


def drop_all_materialized_views(conn) -> int:
    dropped = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schemaname, matviewname
            FROM pg_matviews
            WHERE schemaname = 'public'
            """
        )
        mvs = cur.fetchall()

        for schema, mv_name in mvs:
            cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {schema}.{mv_name} CASCADE;")
            dropped += 1

    return dropped


def analyze_base_tables(conn) -> int:
    analyzed = 0
    with conn.cursor() as cur:
        # Keep consistent with phase 9 behavior
        cur.execute("SET default_statistics_target = 1000;")
        cur.execute("SET random_page_cost = 1.1;")

        for table in BASE_TABLES:
            try:
                cur.execute(f"ANALYZE {table};")
                analyzed += 1
            except Exception:
                # Skip missing tables
                conn.rollback()

    return analyzed


def execute_query(conn, sql: str, timeout_sec: int | None = None) -> tuple[bool, float, str | None]:
    with conn.cursor() as cur:
        if timeout_sec is not None and timeout_sec > 0:
            cur.execute(f"SET statement_timeout = {int(timeout_sec * 1000)};")
        else:
            cur.execute("SET statement_timeout = 0;")

        started = time.perf_counter()
        try:
            cur.execute(sql)
            elapsed = time.perf_counter() - started
            return True, elapsed, None
        except Exception as e:
            elapsed = time.perf_counter() - started
            conn.rollback()
            return False, elapsed, str(e)


def run_benchmark(query_dir: Path, output_json: Path, host: str, database: str, user: str, password: str, timeout_sec: int | None) -> None:
    if not query_dir.exists():
        raise FileNotFoundError(f"Query directory not found: {query_dir}")

    query_files = sorted(query_dir.glob("*.sql"), key=natural_sort_key)
    if not query_files:
        raise FileNotFoundError(f"No .sql files found in: {query_dir}")

    conn = connect(host=host, database=database, user=user, password=password)
    try:
        print("[1/3] Dropping existing materialized views...")
        dropped = drop_all_materialized_views(conn)
        print(f"  dropped_mvs={dropped}")

        print("[2/3] Running ANALYZE on base tables...")
        analyzed = analyze_base_tables(conn)
        print(f"  analyzed_tables={analyzed}")

        print("[3/3] Executing queries sequentially...")
        bench_start = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()

        results = []
        success_count = 0
        failure_count = 0

        for idx, qf in enumerate(query_files, start=1):
            sql = qf.read_text(encoding="utf-8")
            ok, elapsed, err = execute_query(conn, sql, timeout_sec=timeout_sec)

            if ok:
                success_count += 1
            else:
                failure_count += 1

            print(f"  [{idx:>4}/{len(query_files)}] {qf.name} -> {'OK' if ok else 'FAIL'} {elapsed:.3f}s")

            results.append(
                {
                    "query_file": str(qf),
                    "query_name": qf.stem,
                    "success": ok,
                    "execution_time_sec": round(elapsed, 6),
                    "error": err,
                }
            )

        total_elapsed = time.perf_counter() - bench_start
        ended_at = datetime.now(timezone.utc).isoformat()

        output = {
            "query_dir": str(query_dir),
            "query_count": len(query_files),
            "setup": {
                "dropped_materialized_views": dropped,
                "analyzed_base_tables": analyzed,
            },
            "benchmark": {
                "started_at_utc": started_at,
                "ended_at_utc": ended_at,
                "total_time_sec": round(total_elapsed, 6),
                "successful_queries": success_count,
                "failed_queries": failure_count,
                "timeout_sec": timeout_sec,
            },
            "queries": results,
        }

        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

        print("\nDone")
        print(f"  total_time_sec={total_elapsed:.3f}")
        print(f"  success={success_count}, failed={failure_count}")
        print(f"  output={output_json}")

    finally:
        conn.close()


def main() -> int:
    settings = Settings()

    parser = argparse.ArgumentParser(description="Run simple sequential benchmark for .sql files")
    parser.add_argument(
        "--query-dir",
        type=Path,
        default=Path("experiments/small_test_ver2/01_queries/cluster_55_26_3"),
        help="Directory containing .sql query files",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("experiments/small_test_ver2/time_dependent_output/cluster_55_25_26_3/sequential_benchmark_results.json"),
        help="Output JSON file path",
    )
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--database", type=str, default=settings.database.database)
    parser.add_argument("--user", type=str, default=settings.database.user)
    parser.add_argument("--password", type=str, default=settings.database.password)
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=3600,
        help="Per-query statement timeout in seconds (0 for no timeout)",
    )

    args = parser.parse_args()

    timeout_sec = None if args.timeout_sec == 0 else args.timeout_sec

    run_benchmark(
        query_dir=args.query_dir,
        output_json=args.output_json,
        host=args.host,
        database=args.database,
        user=args.user,
        password=args.password,
        timeout_sec=timeout_sec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
