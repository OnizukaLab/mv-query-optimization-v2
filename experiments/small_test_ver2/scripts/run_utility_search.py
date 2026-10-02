#!/usr/bin/env python3
"""利得ベース静的最適化 - UtilityOptimizerV2 と NormalOptimizer の比較

simple_migration_costs.json の utility 値で pickle の u_ij を置換し、
2つのアルゴリズムで最適化を実行して結果を比較する。

メンテナンスコストとインデックス作成コストは考慮しない（全て0）。
頻度による重み付けは行わない。

Usage:
    python3 experiments/small_test_ver2/scripts/run_utility_search.py --query-set job
    python3 experiments/small_test_ver2/scripts/run_utility_search.py --query-set job --storage-mb 200
"""

import argparse
import copy
import json
import pickle
import sys
import time
from pathlib import Path

# プロジェクトルートを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 実験ディレクトリも追加（io_loaders用）
experiment_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(experiment_dir))

from config.settings import Settings
from experiments.small_test_ver2.core.io_loaders import load_full_build_costs_and_sizes
from experiments.small_test_ver2.core.utility_v2 import UtilityOptimizerV2
from src.optimization.normal import NormalOptimizer


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_info(msg: str):
    print(f"  → {msg}")


def print_success(msg: str):
    print(f"  [OK] {msg}")


def run_optimizer(name, optimizer_cls, common_kwargs, extra_kwargs=None):
    """オプティマイザを実行し結果を返す"""
    kwargs = {**common_kwargs}
    if extra_kwargs:
        kwargs.update(extra_kwargs)

    optimizer = optimizer_cls(**kwargs)

    start_time = time.time()
    result = optimizer.optimize()
    total_time = time.time() - start_time

    selected_mvs = [mv.node_id for mv in result.selected_views]
    total_size = result.total_storage

    return {
        "name": name,
        "result": result,
        "selected_mvs": selected_mvs,
        "mv_count": len(selected_mvs),
        "total_size": total_size,
        "objective_value": result.total_utility,
        "execution_time": total_time,
        "iterations": result.metadata.get("iterations"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="利得ベース静的最適化（UtilityOptimizerV2 vs NormalOptimizer）"
    )
    parser.add_argument(
        "--query-set", type=str, default="job",
        help="クエリセット名 (default: job)"
    )
    parser.add_argument(
        "--storage-mb", type=float, default=100.0,
        help="ストレージ予算 MB (default: 100)"
    )
    args = parser.parse_args()

    exp_dir = project_root / "experiments" / "small_test_ver2"
    query_set = args.query_set
    B_max = float(args.storage_mb * 1024 * 1024)

    print_header("利得ベース静的最適化")
    print_info(f"クエリセット: {query_set}")
    print_info(f"ストレージ予算: {args.storage_mb:.0f} MB ({B_max:.0f} bytes)")

    # ========== 1. Pickle読み込み ==========
    pickle_path = exp_dir / "03_parsed" / query_set / "qp_class.pkl"
    if not pickle_path.exists():
        print(f"  [ERROR] Pickle not found: {pickle_path}")
        print("  先にフェーズ2を実行してください")
        return 1

    print_info(f"Pickle読み込み中: {pickle_path}")
    with open(pickle_path, "rb") as f:
        qp = pickle.load(f)
    print_success(f"{qp.s_num}個のノードを読み込み完了")

    # ========== 2. JSON から utility / size を読み込み ==========
    print_info("simple_migration_costs.json から utility / size を読み込み中...")
    migration_costs, utilities, b_j_from_json = load_full_build_costs_and_sizes(
        str(exp_dir), qp.node_list, query_set
    )
    print_success(f"{len(utilities)}個のノードの utility を取得")

    # ========== 3. u_ij を utility 値で置換 ==========
    print_info("u_ij を utility 値で上書き中...")
    u_ij = copy.deepcopy(qp.u_ij)

    updated_count = 0
    for i in range(len(u_ij)):
        for j in range(len(u_ij[i])):
            if u_ij[i][j] > 0:
                if j in utilities:
                    u_ij[i][j] = utilities[j]
                    updated_count += 1

    print_success(f"{updated_count}箇所の利得エントリを更新")

    # 利得の統計を表示
    all_utils = [v for v in utilities.values() if v > 0]
    if all_utils:
        print_info(f"  utility > 0 のノード数: {len(all_utils)}")
        print_info(f"  utility 範囲: {min(all_utils):.2f} ~ {max(all_utils):.2f}")
        print_info(f"  utility 平均: {sum(all_utils)/len(all_utils):.2f}")

    # ========== 4. 共通パラメータ ==========
    m_cost = [0.0] * len(qp.node_list)
    settings = Settings()

    common_kwargs = dict(
        qm=qp.qm,
        s_num=len(qp.node_list),
        m_cost=m_cost,
        node_list=qp.node_list,
        B_max=B_max,
        b_j=b_j_from_json,
        u_ij=u_ij,
        X=qp.X,
        q_s_list=qp.q_s_list,
        settings=settings,
    )

    results = []

    # ========== 5. NormalOptimizer 実行 ==========
    print_header("NormalOptimizer 実行")
    normal_result = run_optimizer(
        "NormalOptimizer",
        NormalOptimizer,
        common_kwargs,
    )
    results.append(normal_result)
    print_success(f"完了 - MV数: {normal_result['mv_count']}, "
                  f"ストレージ: {normal_result['total_size']/1024/1024:.2f} MB, "
                  f"目的関数値: {normal_result['objective_value']:.4f}, "
                  f"実行時間: {normal_result['execution_time']:.3f}秒")

    # ========== 6. UtilityOptimizerV2 実行 ==========
    print_header("UtilityOptimizerV2 実行")
    utility_result = run_optimizer(
        "UtilityOptimizerV2",
        UtilityOptimizerV2,
        common_kwargs,
        extra_kwargs=dict(
            position_node_id=getattr(qp, "position_node_id", {}),
            deeplist=getattr(qp, "deeplist", []),
        ),
    )
    results.append(utility_result)
    print_success(f"完了 - MV数: {utility_result['mv_count']}, "
                  f"ストレージ: {utility_result['total_size']/1024/1024:.2f} MB, "
                  f"目的関数値: {utility_result['objective_value']:.4f}, "
                  f"実行時間: {utility_result['execution_time']:.3f}秒")

    # ========== 7. 比較テーブル ==========
    print_header("比較結果")

    col_w = 22
    print(f"  {'':24s}", end="")
    for r in results:
        print(f" {r['name']:>{col_w}s}", end="")
    print()
    print(f"  {'─' * (24 + (col_w + 1) * len(results))}")

    print(f"  {'MV数':24s}", end="")
    for r in results:
        print(f" {r['mv_count']:>{col_w}}", end="")
    print()

    print(f"  {'ストレージ (MB)':24s}", end="")
    for r in results:
        print(f" {r['total_size']/1024/1024:>{col_w}.2f}", end="")
    print()

    print(f"  {'ストレージ利用率 (%)':24s}", end="")
    for r in results:
        pct = r['total_size'] / B_max * 100 if B_max > 0 else 0
        print(f" {pct:>{col_w}.1f}", end="")
    print()

    print(f"  {'目的関数値':24s}", end="")
    for r in results:
        print(f" {r['objective_value']:>{col_w}.4f}", end="")
    print()

    print(f"  {'実行時間 (秒)':24s}", end="")
    for r in results:
        print(f" {r['execution_time']:>{col_w}.3f}", end="")
    print()

    print(f"  {'反復回数':24s}", end="")
    for r in results:
        itr = r.get('iterations')
        val = str(itr) if itr is not None else "N/A"
        print(f" {val:>{col_w}s}", end="")
    print()

    # 共通MV
    set_normal = set(normal_result['selected_mvs'])
    set_utility = set(utility_result['selected_mvs'])
    common = set_normal & set_utility
    only_normal = set_normal - set_utility
    only_utility = set_utility - set_normal

    print(f"\n  共通MV: {len(common)}個")
    print(f"  NormalOptimizerのみ: {len(only_normal)}個")
    print(f"  UtilityOptimizerV2のみ: {len(only_utility)}個")

    # ========== 8. 結果保存 ==========
    result_dir = exp_dir / "time_dependent_output" / query_set
    result_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "comparison": []
    }
    for r in results:
        output["comparison"].append({
            "algorithm": r["name"],
            "selected_mvs": r["selected_mvs"],
            "mv_count": r["mv_count"],
            "total_size": r["total_size"],
            "storage_budget": B_max,
            "utilization_percent": (r["total_size"] / B_max * 100) if B_max > 0 else 0,
            "objective_value": r["objective_value"],
            "execution_time": r["execution_time"],
            "iterations": r.get("iterations"),
        })
    output["common_mvs"] = sorted(list(common))
    output["only_normal"] = sorted(list(only_normal))
    output["only_utility"] = sorted(list(only_utility))
    output["u_ij_updated_entries"] = updated_count
    output["utility_source"] = "simple_migration_costs.json"

    result_file = result_dir / "utility_search_result.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print_success(f"\n結果を {result_file} に保存")

    return 0


if __name__ == "__main__":
    sys.exit(main())
