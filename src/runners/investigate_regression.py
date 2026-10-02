"""クエリ書き換え後の性能劣化調査スクリプト.

bigsubs と topk-F の実行結果を比較し、
- どのクエリで差が出ているか
- 書き換えが適用されているか
- EXPLAIN で実行プランが変わっているか
を診断する。

使い方:
    python -m src.runners.investigate_regression
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


RESULT_DIR = PROJECT_ROOT / "Output/redbench_edbt_result"
ORIGINAL_SQL_DIR = PROJECT_ROOT / "dataset/RED_SQL/job"


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: クエリごとの実行時間を比較
# ──────────────────────────────────────────────────────────────────────────────

def load_query_times(algo_label: str) -> dict[str, float]:
    path = RESULT_DIR / algo_label / "benchmark/benchmark_results.json"
    with open(path) as f:
        d = json.load(f)
    return {q["query_id"]: q["execution_time"] for q in d["queries"] if q["success"]}


def compare_query_times(bs_times: dict, fr_times: dict, top_n: int = 20):
    """topk-F が bigsubs より遅いクエリを差分降順で表示."""
    common = set(bs_times) & set(fr_times)
    diffs = []
    for qid in common:
        diff = fr_times[qid] - bs_times[qid]   # + なら topk-F が遅い
        diffs.append((qid, bs_times[qid], fr_times[qid], diff))
    diffs.sort(key=lambda x: -x[3])  # topk-F が遅い順

    print("\n" + "=" * 70)
    print(f"topk-F が bigsubs より遅い上位 {top_n} クエリ (差分降順)")
    print("=" * 70)
    print(f"{'query':>8}  {'bigsubs':>9}  {'topk-F':>9}  {'差分(s)':>10}  {'比率':>6}")
    print("-" * 70)
    for qid, bs, fr, diff in diffs[:top_n]:
        ratio = fr / bs if bs > 0 else float("inf")
        mark = " ←遅" if diff > 1.0 else ""
        print(f"{qid:>8}  {bs:>9.3f}  {fr:>9.3f}  {diff:>10.3f}  {ratio:>6.2f}x{mark}")

    # 逆方向（topk-F が速い）
    faster = [(qid, bs, fr, fr - bs) for qid, bs, fr, _ in diffs if fr < bs]
    faster.sort(key=lambda x: x[3])
    print(f"\ntopk-F が bigsubs より速いクエリ: {len(faster)}件")
    if faster:
        for qid, bs, fr, diff in faster[:5]:
            print(f"  {qid}: {bs:.3f}s → {fr:.3f}s ({diff:+.3f}s)")

    return diffs


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: クエリ書き換えの適用状況を確認
# ──────────────────────────────────────────────────────────────────────────────

def _is_rewritten(orig_sql: str, rewritten_sql: str) -> bool:
    """書き換え前後で SQL が変わっているか判定."""
    # コメントと空白を除去して比較
    def clean(s):
        return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", s)).strip().lower()
    return clean(orig_sql) != clean(rewritten_sql)


def check_rewrite_coverage(algo_label: str, query_ids: list[str]) -> dict[str, bool]:
    """指定クエリが実際に書き換えられているか確認."""
    rewrite_dir = RESULT_DIR / "query_rewrite/re_sql" / algo_label
    results = {}
    for qid in query_ids:
        orig_file = ORIGINAL_SQL_DIR / f"{qid}.sql"
        rewr_file = rewrite_dir / f"{qid}.sql"
        if not orig_file.exists() or not rewr_file.exists():
            results[qid] = None  # 不明
            continue
        orig = orig_file.read_text()
        rewr = rewr_file.read_text()
        results[qid] = _is_rewritten(orig, rewr)
    return results


def show_rewrite_diff(algo_label: str, query_id: str):
    """書き換え前後の SQL を並べて表示."""
    rewrite_dir = RESULT_DIR / "query_rewrite/re_sql" / algo_label
    orig_file = ORIGINAL_SQL_DIR / f"{query_id}.sql"
    rewr_file = rewrite_dir / f"{query_id}.sql"
    if not orig_file.exists():
        print(f"  [不明] {orig_file} が見つかりません")
        return
    if not rewr_file.exists():
        print(f"  [書き換えなし] {rewr_file} が見つかりません")
        return

    orig = orig_file.read_text().strip()
    rewr = rewr_file.read_text().strip()

    if orig.lower() == rewr.lower():
        print(f"  [{query_id}] 書き換えなし（オリジナルと同じ）")
    else:
        print(f"\n  [{query_id}] 書き換えあり:")
        print("  --- Original ---")
        for line in orig.split("\n")[:15]:
            print("  " + line)
        print("  --- Rewritten ---")
        for line in rewr.split("\n")[:15]:
            print("  " + line)
        print()


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: EXPLAIN で実行プランを比較
# ──────────────────────────────────────────────────────────────────────────────

def run_explain(sql: str, settings) -> Optional[dict]:
    """EXPLAIN (FORMAT JSON) を実行してプランを返す."""
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=settings.database.host,
            port=settings.database.port,
            dbname=settings.database.database,
            user=settings.database.user,
            password=settings.database.password,
        )
        with conn.cursor() as cur:
            # EXPLAIN 前に SET してプランナを安定させる
            cur.execute("SET enable_material = on;")
            explain_sql = f"EXPLAIN (FORMAT JSON, ANALYZE false) {sql}"
            cur.execute(explain_sql)
            result = cur.fetchone()[0][0]
        conn.close()
        return result
    except Exception as e:
        print(f"    EXPLAIN error: {e}")
        return None


def explain_summary(plan: dict) -> dict:
    """プランから主要指標を抽出."""
    root = plan.get("Plan", {})
    return {
        "node_type": root.get("Node Type"),
        "total_cost": root.get("Total Cost"),
        "plan_rows": root.get("Plan Rows"),
        "join_type": root.get("Join Type"),
    }


def compare_explain(query_id: str, algo_label: str, settings, max_lines: int = 30):
    """オリジナルと書き換え後の EXPLAIN を比較."""
    rewrite_dir = RESULT_DIR / "query_rewrite/re_sql" / algo_label
    orig_file = ORIGINAL_SQL_DIR / f"{query_id}.sql"
    rewr_file = rewrite_dir / f"{query_id}.sql"

    if not orig_file.exists():
        print(f"  Original SQL not found: {orig_file}")
        return

    orig_sql = orig_file.read_text().strip().rstrip(";")
    rewr_sql = rewr_file.read_text().strip().rstrip(";") if rewr_file.exists() else orig_sql

    print(f"\n[EXPLAIN 比較: {query_id} / {algo_label}]")

    orig_plan = run_explain(orig_sql, settings)
    rewr_plan = run_explain(rewr_sql, settings)

    if orig_plan:
        s = explain_summary(orig_plan)
        print(f"  Original : cost={s['total_cost']:.1f}, rows={s['plan_rows']}, type={s['node_type']}")
    if rewr_plan:
        s = explain_summary(rewr_plan)
        print(f"  Rewritten: cost={s['total_cost']:.1f}, rows={s['plan_rows']}, type={s['node_type']}")

    # コスト比
    if orig_plan and rewr_plan:
        orig_cost = orig_plan["Plan"]["Total Cost"]
        rewr_cost = rewr_plan["Plan"]["Total Cost"]
        ratio = rewr_cost / orig_cost if orig_cost > 0 else float("inf")
        marker = "↑ (プランが悪化)" if ratio > 1.05 else ("↓ (改善)" if ratio < 0.95 else "≈ (同等)")
        print(f"  コスト比 rewritten/original = {ratio:.3f}  {marker}")

        # MV が使われているか確認（FROM 句に leaf_/non_leaf_ があるか）
        mv_used = bool(re.search(r"\b(leaf_|non_leaf_)\d+\b", rewr_sql))
        print(f"  MV使用  : {'あり' if mv_used else 'なし（書き換えなし or MV不使用）'}")

    return orig_plan, rewr_plan


# ──────────────────────────────────────────────────────────────────────────────
# Step 4: 選択 MV の内訳確認
# ──────────────────────────────────────────────────────────────────────────────

def summarize_selected_mvs():
    """bigsubs と topk-F が選んだ MV の種別（leaf/non_leaf）と推定サイズを表示."""
    print("\n" + "=" * 60)
    print("選択 MV の内訳")
    print("=" * 60)

    for algo, label in [("bigsubs", "bigsubs"), ("topkf", "frequency")]:
        opt_file = RESULT_DIR / label / "optimization/result.json"
        if not opt_file.exists():
            print(f"  {algo}: result.json が見つかりません")
            continue

        with open(opt_file) as f:
            d = json.load(f)

        views = d.get("selected_views", [])
        leaves = [v for v in views if v["node_id"].startswith("leaf_")]
        nonleaves = [v for v in views if v["node_id"].startswith("non_leaf_")]
        total_size = sum(v.get("size", 0) for v in views)

        print(f"\n{algo} ({len(views)} MVs):")
        print(f"  leaf nodes   : {len(leaves)}")
        print(f"  non_leaf nodes: {len(nonleaves)}")
        print(f"  総推定サイズ  : {total_size/1024/1024:.2f} MB")

        # サイズ上位 5 件
        views_sorted = sorted(views, key=lambda v: v.get("size", 0), reverse=True)
        print(f"  サイズ上位 5 件:")
        for v in views_sorted[:5]:
            print(f"    {v['node_id']}: {v['size']/1024/1024:.2f} MB")


# ──────────────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────────────

def main():
    from config.settings import Settings
    settings = Settings()

    # 1. クエリタイム比較
    bs_times = load_query_times("bigsubs")
    fr_times = load_query_times("frequency")
    diffs = compare_query_times(bs_times, fr_times, top_n=20)

    # 2. MV 内訳確認
    summarize_selected_mvs()

    # 3. 大きく遅いクエリの書き換え状況を確認
    slow_queries = [qid for qid, _, _, diff in diffs if diff > 1.0]
    print(f"\n\n{'='*60}")
    print(f"topk-F で 1秒以上遅いクエリ: {len(slow_queries)} 件")
    print('='*60)

    # frequency の書き換え適用状況
    if slow_queries:
        rewrite_status = check_rewrite_coverage("frequency", slow_queries[:10])
        rewritten_count = sum(1 for v in rewrite_status.values() if v)
        none_count = sum(1 for v in rewrite_status.values() if v is None)
        print(f"  書き換えあり : {rewritten_count}")
        print(f"  書き換えなし : {sum(1 for v in rewrite_status.values() if v is False)}")
        print(f"  ファイル不明 : {none_count}")

    # 4. 差分が大きい代表クエリの EXPLAIN 比較
    # topk-F で最も遅い上位 5 件 / bigsubs で最も遅い 2 件を比較
    top_slow = [qid for qid, _, _, diff in diffs if diff > 2.0][:5]
    print(f"\n\n{'='*60}")
    print("EXPLAIN コスト比較（topk-F で 2秒以上遅いクエリ）")
    print("="*60)

    for qid in top_slow:
        compare_explain(qid, "frequency", settings)

    # 5. bigsubs で速い代表クエリも確認
    very_slow_fr = [(qid, bs_times[qid], fr_times[qid]) for qid, _, _, diff in diffs if diff > 5.0]
    if very_slow_fr:
        print(f"\n\n{'='*60}")
        print("topk-F で 5秒以上遅いクエリの書き換え SQL")
        print("="*60)
        for qid, bs, fr in very_slow_fr[:3]:
            print(f"\n{qid}: bigsubs={bs:.2f}s, topk-F={fr:.2f}s")
            show_rewrite_diff("frequency", qid)


if __name__ == "__main__":
    main()
