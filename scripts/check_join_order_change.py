#!/usr/bin/env python3
"""書き換え前後で結合順序(=各ベーステーブルを最初にスキャンする相対順序)が
実際に変化したクエリ数を数えるツール。

単純にプラン内の演算子タイプの集合を比較するだけでは、
「ノード数は同じだが結合順序だけ入れ替わった」ケースを見逃す。
このツールは qp_class.pkl に保存されたMVノード定義(leaf_nodes_map_r /
non_leaf_nodes_map_r)を使い、MV名(leaf_X / non_leaf_X)を実際に含む
ベーステーブルの集合へ正規化してから、オリジナルと書き換え後で
各ベーステーブルの相対アクセス順序を比較する。

使い方:
    python scripts/check_join_order_change.py normal Output/job_plan_regression_analysis_docker
"""
from __future__ import annotations

import argparse
import pickle
import re
import sys
from pathlib import Path
from typing import Any

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # qp_class.pkl は src.core.query_parser を参照するため必要
ORIGINAL_SQL_DIR = PROJECT_ROOT / "dataset/RED_SQL/job"
_WHITESPACE_RE = re.compile(r"\s+")


def connect(host: str, port: int, dbname: str, user: str, password: str) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=10)
    conn.autocommit = True
    return conn


def explain_plan(conn: psycopg2.extensions.connection, sql: str, timeout_ms: int = 45_000) -> tuple[dict[str, Any] | None, str | None]:
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {timeout_ms}")
        try:
            cur.execute(f"EXPLAIN (FORMAT JSON, COSTS) {sql}")
            return cur.fetchone()[0][0]["Plan"], None
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            return None, str(e)[:200]


def leaf_scan_order(node: dict[str, Any], out: list[str] | None = None) -> list[str]:
    """スキャン系ノード(Plansを持たない末端)のRelation Nameを出現順(pre-order)で返す。"""
    if out is None:
        out = []
    if "Plans" not in node:
        rel = node.get("Relation Name")
        if rel:
            out.append(rel)
    else:
        for child in node["Plans"]:
            leaf_scan_order(child, out)
    return out


def build_base_table_resolver(qm: Any):
    """MVノードID(leaf_X / non_leaf_X)を、それが内部に含む実テーブル名の集合へ解決する関数を作る。"""
    cache: dict[str, frozenset[str]] = {}

    def base_tables(node_id: str) -> frozenset[str]:
        if node_id in cache:
            return cache[node_id]
        if node_id in qm.leaf_nodes_map_r:
            _, table, _, _ = qm.leaf_nodes_map_r[node_id]
            result = frozenset([table])
        elif node_id in qm.non_leaf_nodes_map_r:
            result = frozenset()
            for child in qm.non_leaf_nodes_map_r[node_id]:
                result = result | base_tables(child)
        else:
            result = frozenset([node_id])  # 通常のベーステーブル名そのもの
        cache[node_id] = result
        return result

    return base_tables


def normalize(sql: str) -> str:
    return _WHITESPACE_RE.sub(" ", sql).strip().rstrip(";")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("algorithm", help="run_experiment.py に渡したアルゴリズム名 (例: normal, bigsubs)")
    parser.add_argument("output_dir", type=Path, help="run_experiment.py の --output ディレクトリ(qp_class.pklを含む)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="imdbload")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="pass")
    args = parser.parse_args()

    with open(args.output_dir / "qp_class.pkl", "rb") as f:
        qp = pickle.load(f)
    resolve = build_base_table_resolver(qp.qm)

    conn = connect(args.host, args.port, args.dbname, args.user, args.password)
    rewritten_dir = args.output_dir / "query_rewrite" / "re_sql" / args.algorithm

    reordered: list[str] = []
    same_order: list[str] = []
    errors: list[str] = []

    for orig_file in sorted(ORIGINAL_SQL_DIR.glob("*.sql")):
        qid = orig_file.stem
        rewritten_file = rewritten_dir / f"{qid}.sql"
        if not rewritten_file.exists():
            continue
        orig_sql, rewritten_sql = orig_file.read_text(), rewritten_file.read_text()
        if normalize(orig_sql) == normalize(rewritten_sql):
            continue  # 書き換えなし

        orig_plan, err1 = explain_plan(conn, orig_sql)
        rewritten_plan, err2 = explain_plan(conn, rewritten_sql)
        if err1 or err2:
            errors.append(qid)
            continue

        orig_pos: dict[str, int] = {}
        for i, name in enumerate(leaf_scan_order(orig_plan)):
            orig_pos.setdefault(name, i)

        rewritten_pos: dict[str, int] = {}
        for i, name in enumerate(leaf_scan_order(rewritten_plan)):
            for table in resolve(name):
                rewritten_pos.setdefault(table, i)

        common_tables = [t for t in orig_pos if t in rewritten_pos]
        orig_rank = sorted(common_tables, key=lambda t: orig_pos[t])
        rewritten_rank = sorted(common_tables, key=lambda t: (rewritten_pos[t], orig_pos[t]))

        (same_order if orig_rank == rewritten_rank else reordered).append(qid)

    conn.close()

    total = len(reordered) + len(same_order)
    print(f"比較対象(書き換えあり & EXPLAIN成功): {total}")
    print(f"結合順序が変化: {len(reordered)} {reordered}")
    print(f"結合順序は同一: {len(same_order)}")
    if errors:
        print(f"EXPLAIN失敗: {errors}")


if __name__ == "__main__":
    main()
