#!/usr/bin/env python3
"""クエリ書き換え前後の実行プラン比較スクリプト

JOBベンチマークの各クエリについて、オリジナルSQLと
QueryRewriterが生成した書き換え後SQLの両方をEXPLAIN (ANALYZE, BUFFERS)
で実行し、実行時間・バッファ使用量・プラン構造を比較する。

事前に run_experiment.py で該当アルゴリズムのMVをDBに作成しておく必要がある:

    python scripts/run_experiment.py --algorithms normal --workload-type job \\
        --start-from mv_creation --end-at mv_creation --output <output_dir>

使い方:
    python scripts/compare_rewrite_plans.py normal Output/job_plan_regression_analysis
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
ORIGINAL_SQL_DIR = PROJECT_ROOT / "dataset/RED_SQL/job"
STATEMENT_TIMEOUT_MS = 45_000
_WHITESPACE_RE = re.compile(r"\s+")


def connect(host: str, port: int, dbname: str, user: str, password: str) -> psycopg2.extensions.connection:
    """PostgreSQLへ接続する(autocommitモード)。"""
    conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=10)
    conn.autocommit = True
    return conn


def explain_sql(conn: psycopg2.extensions.connection, sql: str) -> tuple[dict[str, Any] | None, float | None, str | None]:
    """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) を実行する。

    Args:
        conn: DB接続
        sql: 実行するSQL

    Returns:
        (plan_json, wall_clock_seconds, error_message) のタプル。成功時は error_message は None。
    """
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        try:
            t0 = time.time()
            cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, TIMING, COSTS) {sql}")
            plan = cur.fetchone()[0][0]
            return plan, time.time() - t0, None
        except Exception as e:  # noqa: BLE001 - EXPLAINの失敗理由は多様なため広く捕捉する
            conn.rollback()
            return None, None, str(e)[:300]


def root_buffers(root_node: dict[str, Any]) -> dict[str, int]:
    """クエリ全体の shared buffer 使用量 (hit/read/written) を取得する。

    EXPLAIN (ANALYZE, BUFFERS) の各ノードの値は子ノードを含む累積値のため、
    ルートノードの値がそのままクエリ全体の合計になる(子ノードを個別に
    加算すると二重カウントになるので行わない)。
    """
    return {
        "hit": root_node.get("Shared Hit Blocks", 0),
        "read": root_node.get("Shared Read Blocks", 0),
        "written": root_node.get("Shared Written Blocks", 0),
    }


def plan_node_types(node: dict[str, Any], out: list[str] | None = None) -> list[str]:
    """プランツリー中に現れる Node Type の多重集合(ソート済み)を返す。"""
    if out is None:
        out = []
    out.append(node.get("Node Type", "?"))
    for child in node.get("Plans", []):
        plan_node_types(child, out)
    return sorted(out)


def normalize_sql(sql: str) -> str:
    return _WHITESPACE_RE.sub(" ", sql).strip().rstrip(";")


def compare_all(conn: psycopg2.extensions.connection, algorithm: str, output_dir: Path) -> list[dict[str, Any]]:
    """JOB全クエリについてオリジナル/書き換え後のEXPLAIN比較を行う。

    Args:
        conn: DB接続(比較対象アルゴリズムのMVが事前に作成済みであること)
        algorithm: run_experiment.py に渡したアルゴリズム名(例: "normal", "bigsubs")
        output_dir: run_experiment.py の --output と同じディレクトリ

    Returns:
        クエリごとの比較結果のリスト
    """
    rewritten_dir = output_dir / "query_rewrite" / "re_sql" / algorithm
    results: list[dict[str, Any]] = []

    for orig_file in sorted(ORIGINAL_SQL_DIR.glob("*.sql")):
        qid = orig_file.stem
        orig_sql = orig_file.read_text()
        rewritten_file = rewritten_dir / f"{qid}.sql"
        rewritten_sql = rewritten_file.read_text() if rewritten_file.exists() else None
        changed = rewritten_sql is not None and normalize_sql(orig_sql) != normalize_sql(rewritten_sql)

        entry: dict[str, Any] = {"query_id": qid, "algorithm": algorithm, "rewritten": changed}

        plan, wall, err = explain_sql(conn, orig_sql)
        entry["original"] = {
            "error": err,
            "exec_time_ms": plan["Execution Time"] if plan else None,
            "wall_s": wall,
            "buffers": root_buffers(plan["Plan"]) if plan else None,
            "node_types": plan_node_types(plan["Plan"]) if plan else None,
        }

        if changed:
            plan2, wall2, err2 = explain_sql(conn, rewritten_sql)
            entry["rewritten_result"] = {
                "error": err2,
                "exec_time_ms": plan2["Execution Time"] if plan2 else None,
                "wall_s": wall2,
                "buffers": root_buffers(plan2["Plan"]) if plan2 else None,
                "node_types": plan_node_types(plan2["Plan"]) if plan2 else None,
            }

        results.append(entry)
        print(f"  {qid}: rewritten={changed}", file=sys.stderr)

    return results


def print_regressions(results: list[dict[str, Any]], ratio_threshold: float = 1.2, min_delta_ms: float = 20.0) -> None:
    """オリジナルよりrewritten後の方が遅いクエリを一覧表示する。"""
    rows = []
    for e in results:
        if not e["rewritten"]:
            continue
        orig, rew = e["original"], e.get("rewritten_result")
        if not rew or orig.get("error") or rew.get("error"):
            continue
        o_ms, r_ms = orig["exec_time_ms"], rew["exec_time_ms"]
        if o_ms is None or r_ms is None or o_ms <= 0:
            continue
        ratio = r_ms / o_ms
        if ratio > ratio_threshold and (r_ms - o_ms) > min_delta_ms:
            rows.append((e["query_id"], o_ms, r_ms, ratio))

    rows.sort(key=lambda r: -r[3])
    print(f"\n=== 回帰クエリ (rewritten > {ratio_threshold}x original AND +{min_delta_ms}ms以上): {len(rows)}件 ===")
    for qid, o_ms, r_ms, ratio in rows:
        print(f"  {qid}: {o_ms:.1f}ms -> {r_ms:.1f}ms (x{ratio:.2f})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("algorithm", help="run_experiment.py に渡したアルゴリズム名 (例: normal, bigsubs)")
    parser.add_argument("output_dir", type=Path, help="run_experiment.py の --output ディレクトリ")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="imdbload")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="pass")
    parser.add_argument("--json-out", type=Path, default=None, help="詳細結果の保存先JSONパス")
    args = parser.parse_args()

    conn = connect(args.host, args.port, args.dbname, args.user, args.password)
    try:
        results = compare_all(conn, args.algorithm, args.output_dir)
    finally:
        conn.close()

    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"Wrote {len(results)} entries to {args.json_out}")

    print_regressions(results)


if __name__ == "__main__":
    main()
