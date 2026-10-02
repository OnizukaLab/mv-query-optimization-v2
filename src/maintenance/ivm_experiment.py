"""pg_ivm を使った差分更新実験.

選択された MV を IMMV として作成し、実際の更新クエリを実行して
IVM トリガーの動作と時間を計測する。

使い方::

    python -m src.maintenance.ivm_experiment
    python -m src.maintenance.ivm_experiment --node-ids leaf_122 leaf_83 --n-queries 5
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from src.maintenance.update_query_generator import UpdateQueryGenerator, UpdateQuery
from src.maintenance.mv_sql_expander import expand_mv_sql, get_immv_body


PLANS_PATH = PROJECT_ROOT / "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json"


# ──────────────────────────────────────────────────────────────────────────────
# データクラス
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IMMVResult:
    node_id: str
    immv_name: str
    base_table: str
    immv_rows: int
    create_time_sec: float
    query_results: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def avg_trigger_ms(self) -> float:
        times = [r["elapsed_ms"] for r in self.query_results if r["success"]]
        return statistics.mean(times) if times else 0.0

    @property
    def median_trigger_ms(self) -> float:
        times = [r["elapsed_ms"] for r in self.query_results if r["success"]]
        return statistics.median(times) if times else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# IMMV 作成ロジック
# ──────────────────────────────────────────────────────────────────────────────

def _get_base_table(node_id: str, mv_sql: str) -> Optional[str]:
    """MV SQL から直接参照されるベーステーブル名を取得する (MV 以外)."""
    from_tables = re.findall(r'FROM\s+([a-z_]+)\s+AS\s+', mv_sql, re.IGNORECASE)
    base = [t for t in from_tables
            if not t.startswith("leaf_") and not t.startswith("non_leaf_")]
    return base[0] if base else None


# _expand_mv_sql は mv_sql_expander.expand_mv_sql としてインポート済み
_expand_mv_sql = expand_mv_sql


def create_immv(conn, immv_name: str, query_body: str) -> tuple[int, float]:
    """pg_ivm で IMMV を作成し (行数, 作成時間) を返す."""
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
    conn.commit()

    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            # query_body を %s パラメータで渡す → '%internet%' 等の % が正しくエスケープされる
            cur.execute(
                "SELECT pgivm.create_immv(%s, %s)",
                (immv_name, query_body),
            )
            cur.fetchone()  # create_immv の戻り値を消費する
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise

    elapsed = time.perf_counter() - t0

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {immv_name}")
        rows = cur.fetchone()[0]

    return rows, elapsed


# ──────────────────────────────────────────────────────────────────────────────
# 更新クエリ実行 & 計測
# ──────────────────────────────────────────────────────────────────────────────

def run_update_queries(
    conn,
    queries: list[UpdateQuery],
    immv_name: str,
    verbose: bool = True,
) -> list[dict]:
    """各更新クエリを BEGIN → 実行 → 計測 → ROLLBACK で計測する."""
    results = []
    for q in queries:
        if verbose:
            print(f"    [{q.op_type}] {q.description[:70]}")

        # IMMV の更新前の行数を確認
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {immv_name}")
            rows_before = cur.fetchone()[0]

        # BEGIN → UPDATE → 計測 → ROLLBACK
        try:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                t0 = time.perf_counter()
                cur.execute(q.sql)
                elapsed = time.perf_counter() - t0
                affected = cur.rowcount

                # IMMV の行数変化を確認 (トリガーが走ったか)
                cur.execute(f"SELECT COUNT(*) FROM {immv_name}")
                rows_after = cur.fetchone()[0]
                cur.execute("ROLLBACK")
            conn.rollback()

            delta = rows_after - rows_before
            if verbose:
                symbol = "+" if delta > 0 else ("−" if delta < 0 else "≈")
                print(f"      → {elapsed*1000:.2f}ms | IMMV rows: {rows_before} {symbol}{abs(delta)} | base affected: {affected}")

            results.append({
                "op_type": q.op_type,
                "description": q.description,
                "sql": q.sql,
                "elapsed_ms": elapsed * 1000,
                "affected_rows": affected,
                "immv_rows_before": rows_before,
                "immv_rows_after": rows_after,
                "immv_delta": delta,
                "success": True,
            })

        except Exception as e:
            conn.rollback()
            if verbose:
                print(f"      → ERROR: {e}")
            results.append({
                "op_type": q.op_type,
                "description": q.description,
                "sql": q.sql,
                "elapsed_ms": 0.0,
                "error": str(e),
                "success": False,
            })

    return results


# ──────────────────────────────────────────────────────────────────────────────
# メイン実験
# ──────────────────────────────────────────────────────────────────────────────

def run_ivm_experiment(
    node_ids: list[str],
    n_queries: int = 5,
    settings: Optional[Settings] = None,
    output_path: Optional[Path] = None,
    verbose: bool = True,
) -> list[IMMVResult]:
    """指定 MV ノードの IMMV を作成して更新クエリ実験を実行する."""
    if settings is None:
        settings = Settings()

    s = settings.database
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database,
        user=s.user, password=s.password,
    )
    conn.autocommit = False

    with open(PLANS_PATH) as f:
        plans = json.load(f)

    results: list[IMMVResult] = []
    gen = UpdateQueryGenerator(conn)

    for node_id in node_ids:
        immv_name = "immv_" + node_id.replace("_", "")
        mv_sql = plans.get(node_id, {}).get("[]", "")
        base_table = _get_base_table(node_id, mv_sql)

        print()
        print(f"{'='*65}")
        print(f"  ノード: {node_id}  →  IMMV: {immv_name}")
        print(f"  ベーステーブル: {base_table}")
        print(f"{'='*65}")

        if base_table is None:
            print("  [SKIP] ベーステーブルが特定できません")
            continue

        # ─ STEP 1: IMMV の SQL を展開 ─
        query_body = _expand_mv_sql(node_id, plans)
        if query_body is None:
            print("  [SKIP] SQL 展開に失敗しました")
            results.append(IMMVResult(node_id, immv_name, base_table or "", 0, 0.0,
                                      error="SQL expansion failed"))
            continue

        if verbose:
            body_preview = query_body[:200].replace("\n", " ")
            print(f"\n  [SQL 展開結果] {body_preview}...")

        # ─ STEP 2: IMMV 作成 ─
        print(f"\n  [1/3] IMMV 作成中...")
        try:
            rows, create_time = create_immv(conn, immv_name, query_body)
            print(f"        完了: {rows:,} 行, 作成時間: {create_time:.2f}s")
        except Exception as e:
            print(f"        ERROR: {e}")
            results.append(IMMVResult(node_id, immv_name, base_table, 0, 0.0,
                                      error=str(e)[:200]))
            continue

        # ─ STEP 3: 更新クエリ生成 ─
        where_clause = UpdateQueryGenerator.extract_where_clause(mv_sql)
        queries = gen.generate_all_op_types(
            base_table=base_table,
            where_clause=where_clause,
            n_each=max(1, n_queries // 3),
        )

        print(f"\n  [2/3] 更新クエリ生成: {len(queries)} 件")
        if verbose:
            for q in queries:
                print(f"    {q.op_type:8}  {q.description[:65]}")

        # ─ STEP 4: 更新クエリ実行 & 計測 ─
        print(f"\n  [3/3] 実行 + IVM トリガー計測:")
        query_results = run_update_queries(conn, queries, immv_name, verbose=verbose)

        # ─ STEP 5: 結果サマリー ─
        r = IMMVResult(
            node_id=node_id,
            immv_name=immv_name,
            base_table=base_table,
            immv_rows=rows,
            create_time_sec=create_time,
            query_results=query_results,
        )
        results.append(r)

        ok = [x for x in query_results if x["success"]]
        triggered = [x for x in ok if x.get("immv_delta", 0) != 0]
        print(f"\n  ─── サマリー ───")
        print(f"  IMMV 行数        : {rows:,}")
        print(f"  成功クエリ       : {len(ok)}/{len(queries)}")
        print(f"  IMMV 変化あり    : {len(triggered)}/{len(ok)}")
        if ok:
            print(f"  平均 IVM 時間    : {r.avg_trigger_ms:.2f}ms")
            print(f"  中央値 IVM 時間  : {r.median_trigger_ms:.2f}ms")

        # ─ STEP 6: IMMV を削除 ─
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
        conn.commit()
        print(f"  IMMV を削除しました")

    conn.close()

    # 保存
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out = []
        for r in results:
            out.append({
                "node_id": r.node_id,
                "immv_name": r.immv_name,
                "base_table": r.base_table,
                "immv_rows": r.immv_rows,
                "create_time_sec": r.create_time_sec,
                "avg_trigger_ms": r.avg_trigger_ms,
                "median_trigger_ms": r.median_trigger_ms,
                "error": r.error,
                "query_results": r.query_results,
            })
        with open(output_path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"\n結果を保存: {output_path}")

    return results


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="pg_ivm 差分更新実験")
    parser.add_argument(
        "--node-ids", nargs="+",
        default=["leaf_83", "leaf_122"],
        help="実験対象の MV ノード ID (デフォルト: leaf_83 leaf_122)",
    )
    parser.add_argument("--n-queries", type=int, default=6,
                        help="1 ノードあたりの更新クエリ数 (デフォルト: 6)")
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "Output/ivm_experiment/results.json"),
        help="結果 JSON の保存先",
    )
    args = parser.parse_args()

    results = run_ivm_experiment(
        node_ids=args.node_ids,
        n_queries=args.n_queries,
        output_path=Path(args.output),
    )

    # 最終比較表
    print("\n" + "=" * 65)
    print("全ノード IVM 計測結果")
    print("=" * 65)
    print(f"{'node_id':20} {'table':18} {'IMMV行数':>10} {'作成(s)':>8} {'平均(ms)':>9} {'中央値(ms)':>10}")
    print("-" * 65)
    for r in results:
        if r.error:
            print(f"{r.node_id:20} {'ERROR':18} {r.error[:30]}")
        else:
            print(f"{r.node_id:20} {r.base_table:18} {r.immv_rows:>10,} "
                  f"{r.create_time_sec:>8.2f} {r.avg_trigger_ms:>9.2f} {r.median_trigger_ms:>10.2f}")


if __name__ == "__main__":
    main()
