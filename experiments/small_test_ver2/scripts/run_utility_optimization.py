"""時間依存利得ベース最適化 (UtilityOptimizerV2 + 頻度重み付け)

各タイムステップの頻度で利得を重み付けし、UtilityOptimizerV2 を
各時刻ごとに独立して実行する。

Usage:
    python3 experiments/small_test_ver2/scripts/run_utility_optimization.py --query-set job --storage-mb 1024 --freq-suffix _16_1_10
"""

import argparse
import copy
import json
import multiprocessing
import pickle
import time
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# プロジェクトルートをsys.pathに追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import Settings
from experiments.small_test_ver2.core.io_loaders import (
    load_full_build_costs_and_sizes,
    load_timesteps_and_frequencies,
)
from experiments.small_test_ver2.core.utility_v2 import UtilityOptimizerV2
from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
from experiments.small_test_ver2.core.utility_pruner import UtilityPruner
from experiments.small_test_ver2.core.utility_pruner_iterative import UtilityPrunerIterative


# ========== ヘルパー関数 ==========

def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_info(msg: str):
    print(f"  → {msg}")


def print_success(msg: str):
    print(f"  [OK] {msg}")


def build_weighted_u_ij(base_u_ij, frequencies_for_timestep, query_count):
    """頻度で重み付けした u_ij を生成する.

    Args:
        base_u_ij: 元の利得行列 (utility 値で上書き済み)
        frequencies_for_timestep: このタイムステップでの各クエリの頻度リスト
        query_count: クエリ数 (u_ij の行数)

    Returns:
        頻度重み付き u_ij (deepcopy)
    """
    weighted = copy.deepcopy(base_u_ij)

    # 頻度リストの長さを調整
    freq = list(frequencies_for_timestep)
    if len(freq) < query_count:
        freq.extend([1.0] * (query_count - len(freq)))
    else:
        freq = freq[:query_count]

    for i in range(query_count):
        for j in range(len(weighted[i])):
            weighted[i][j] *= freq[i]

    return weighted


def run_single_timestep_greedy(timestep_name, common_kwargs, weighted_u_ij):
    """単一タイムステップの貪欲候補収集を実行する（ILP最適化なし、オーバーサンプリングなし）.

    Args:
        timestep_name: タイムステップ名 (表示用)
        common_kwargs: UtilityOptimizerV2 の共通引数
        weighted_u_ij: 頻度重み付き u_ij

    Returns:
        結果の辞書
    """
    kwargs = {**common_kwargs, "u_ij": weighted_u_ij}
    optimizer = UtilityOptimizerV2(**kwargs)

    start_time = time.time()
    z_j = optimizer.initialize_greedy(budget_multiplier=1.0)
    elapsed = time.time() - start_time

    selected_mv_indices = [j for j, v in enumerate(z_j) if v == 1]
    selected_mvs = [optimizer.node_list[j] for j in selected_mv_indices]
    total_size = sum(optimizer.b_j[j] for j in selected_mv_indices)

    return {
        "timestep": timestep_name,
        "selected_mvs": selected_mvs,
        "selected_mv_indices": selected_mv_indices,
        "mv_count": len(selected_mv_indices),
        "total_size": total_size,
        "objective_value": None,
        "execution_time": elapsed,
        "iterations": 0,
    }


def run_single_timestep(timestep_name, common_kwargs, weighted_u_ij):
    """単一タイムステップの最適化を実行する.

    Args:
        timestep_name: タイムステップ名 (表示用)
        common_kwargs: UtilityOptimizerV2 の共通引数
        weighted_u_ij: 頻度重み付き u_ij

    Returns:
        結果の辞書
    """
    kwargs = {**common_kwargs, "u_ij": weighted_u_ij}
    optimizer = UtilityOptimizerV2(**kwargs)

    start_time = time.time()
    result = optimizer.optimize()
    elapsed = time.time() - start_time

    selected_mvs = [mv.node_id for mv in result.selected_views]
    selected_mv_indices = result.metadata.get("selected_indices", [])

    return {
        "timestep": timestep_name,
        "selected_mvs": selected_mvs,
        "selected_mv_indices": selected_mv_indices,
        "mv_count": len(selected_mvs),
        "total_size": result.total_storage,
        "objective_value": result.total_utility,
        "execution_time": elapsed,
        "iterations": result.metadata.get("iterations"),
    }


def _run_timestep_worker(task: tuple) -> tuple:
    """各タイムステップ最適化のワーカー関数 (ProcessPoolExecutor 用).

    モジュールレベルで定義することで pickle 可能にする。

    Args:
        task: (t_idx, timestep_name, common_kwargs, weighted_u_ij, is_greedy) のタプル

    Returns:
        (t_idx, result_dict) のタプル
    """
    t_idx, timestep_name, common_kwargs, weighted_u_ij, is_greedy = task
    if is_greedy:
        result = run_single_timestep_greedy(timestep_name, common_kwargs, weighted_u_ij)
    else:
        result = run_single_timestep(timestep_name, common_kwargs, weighted_u_ij)
    return t_idx, result


def main():
    parser = argparse.ArgumentParser(
        description="時間依存利得ベース最適化（UtilityOptimizerV2 × 各タイムステップ）"
    )
    parser.add_argument(
        "--query-set", type=str, default="job",
        help="クエリセット名 (default: job)"
    )
    parser.add_argument(
        "--storage-mb", type=float, default=100.0,
        help="ストレージ予算 MB (default: 100)"
    )
    parser.add_argument(
        "--freq-suffix", type=str, default="",
        help="頻度ファイルのサフィックス (e.g. _16_1_10)"
    )
    parser.add_argument(
        "--pruning-method", type=str, default="basic",
        choices=["basic", "iterative", "step1_only", "step2_only", "greedy"],
        help="候補削減手法 (basic: WSTシングルパス, iterative: WST反復, "
             "step1_only: タイムステップ別最適化のみ, step2_only: WST反復のみ, "
             "greedy: 各時刻で貪欲収集のみ→WST) (default: basic)"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5,
        help="反復的削減の最大イテレーション数/ノード (default: 5)"
    )
    parser.add_argument(
        "--use-parallel-step1", action="store_true",
        help="Step 1（各タイムステップ最適化）の並列処理を有効にする (default: False)"
    )
    parser.add_argument(
        "--use-parallel", action="store_true",
        help="WSTノードの並列処理を有効にする (default: False)"
    )
    parser.add_argument(
        "--max-workers", type=int, default=None,
        help="並列処理の最大ワーカー数（Step 1・WST 共通） (default: CPU数)"
    )
    parser.add_argument(
        "--gurobi-output", type=int, default=0, choices=[0, 1],
        help="Gurobiログ出力 (0=off, 1=on, default: 0)"
    )
    parser.add_argument(
        "--no-wst-parent-constraints", action="store_true",
        help="WSTにおける親ノードからの境界制約伝播を無効化する (default: 有効)"
    )
    args = parser.parse_args()

    exp_dir = project_root / "experiments" / "small_test_ver2"
    query_set = args.query_set
    B_max = float(args.storage_mb * 1024 * 1024)

    print_header("時間依存利得ベース最適化 (UtilityOptimizerV2)")
    print_info(f"クエリセット: {query_set}")
    print_info(f"ストレージ予算: {args.storage_mb:.0f} MB ({B_max:.0f} bytes)")
    print_info(f"頻度サフィックス: '{args.freq_suffix}'")
    print_info(f"Gurobiログ: {'ON' if args.gurobi_output == 1 else 'OFF'}")

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

    # u_ij を utility 値で上書き
    print_info("u_ij を utility 値で上書き中...")
    base_u_ij = copy.deepcopy(qp.u_ij)

    updated_count = 0
    for i in range(len(base_u_ij)):
        for j in range(len(base_u_ij[i])):
            if base_u_ij[i][j] > 0:
                if j in utilities:
                    base_u_ij[i][j] = utilities[j]
                    updated_count += 1

    print_success(f"{updated_count}箇所の利得エントリを更新")

    # ========== 3. 頻度ファイル読み込み ==========
    print_info("頻度ファイル読み込み中...")
    timesteps, frequencies = load_timesteps_and_frequencies(
        str(exp_dir), query_set, freq_suffix=args.freq_suffix
    )
    print_success(f"{len(timesteps)}個のタイムステップを読み込み完了")

    # ========== 4. 共通パラメータ ==========
    m_cost = [0.0] * len(qp.node_list)
    settings = Settings()
    query_count = len(base_u_ij)

    common_kwargs = dict(
        qm=qp.qm,
        s_num=len(qp.node_list),
        m_cost=m_cost,
        node_list=qp.node_list,
        B_max=B_max,
        b_j=b_j_from_json,
        u_ij=base_u_ij,  # placeholder, overridden per timestep
        X=qp.X,
        q_s_list=qp.q_s_list,
        settings=settings,
        position_node_id=getattr(qp, "position_node_id", {}),
        deeplist=getattr(qp, "deeplist", []),
        gurobi_output=args.gurobi_output,
    )

    # ========== 5. 各タイムステップで最適化実行 (Step 1) ==========
    pipeline_start = time.time()

    if args.pruning_method != "step2_only":
        results = []
        total_start = time.time()
        is_greedy_mode = args.pruning_method == "greedy"
        max_workers_step1 = args.max_workers or multiprocessing.cpu_count()

        if is_greedy_mode:
            print_info("貪欲モード: 各時刻でオーバーサンプリングなしの貪欲収集を実行")

        if args.use_parallel_step1:
            print_info(f"Step 1 並列処理: ワーカー数 = {max_workers_step1}")

            # 全タイムステップ分のタスクを事前構築
            tasks = []
            for t_idx, timestep in enumerate(timesteps):
                freq_list = frequencies[timestep]
                weighted_u_ij = build_weighted_u_ij(base_u_ij, freq_list, query_count)
                tasks.append((t_idx, timestep, common_kwargs, weighted_u_ij, is_greedy_mode))

            ordered_results = [None] * len(timesteps)
            completed = 0

            with ProcessPoolExecutor(max_workers=max_workers_step1) as executor:
                futures = {
                    executor.submit(_run_timestep_worker, task): task[0]
                    for task in tasks
                }
                for future in as_completed(futures):
                    t_idx, result = future.result()
                    ordered_results[t_idx] = result
                    completed += 1

                    obj_str = (f"{result['objective_value']:.4f}"
                               if result['objective_value'] is not None else "N/A")
                    print_success(f"タイムステップ {result['timestep']} 完了 "
                                  f"({completed}/{len(timesteps)}): "
                                  f"MV数: {result['mv_count']}, "
                                  f"ストレージ: {result['total_size']/1024/1024:.2f} MB, "
                                  f"目的関数値: {obj_str}, "
                                  f"実行時間: {result['execution_time']:.3f}秒")

            results = ordered_results

        else:
            for t_idx, timestep in enumerate(timesteps):
                freq_list = frequencies[timestep]
                weighted_u_ij = build_weighted_u_ij(base_u_ij, freq_list, query_count)

                nonzero_freq = [f for f in freq_list[:query_count] if f > 0]
                active_queries = len(nonzero_freq)

                print_info(f"タイムステップ {timestep} ({t_idx+1}/{len(timesteps)}): "
                           f"アクティブクエリ {active_queries}/{query_count}")

                if is_greedy_mode:
                    result = run_single_timestep_greedy(timestep, common_kwargs, weighted_u_ij)
                else:
                    result = run_single_timestep(timestep, common_kwargs, weighted_u_ij)
                results.append(result)

                obj_str = (f"{result['objective_value']:.4f}"
                           if result['objective_value'] is not None else "N/A")
                print_success(f"  MV数: {result['mv_count']}, "
                              f"ストレージ: {result['total_size']/1024/1024:.2f} MB, "
                              f"目的関数値: {obj_str}, "
                              f"実行時間: {result['execution_time']:.3f}秒")

        total_elapsed = time.time() - total_start

        # ========== 6. 結果サマリ ==========
        print_header("結果サマリ")
        print(f"  {'Timestep':>10s}  {'MV数':>6s}  {'ストレージ(MB)':>14s}  {'目的関数値':>16s}  {'実行時間(秒)':>12s}")
        print(f"  {'─'*10}  {'─'*6}  {'─'*14}  {'─'*16}  {'─'*12}")
        for r in results:
            obj_str = (f"{r['objective_value']:>16.4f}"
                       if r['objective_value'] is not None else f"{'N/A':>16s}")
            print(f"  {r['timestep']:>10s}  {r['mv_count']:>6d}  "
                  f"{r['total_size']/1024/1024:>14.2f}  "
                  f"{obj_str}  "
                  f"{r['execution_time']:>12.3f}")
        print(f"\n  合計実行時間: {total_elapsed:.3f}秒")

        # タイムステップ間での MV の変動を分析
        print_header("タイムステップ間 MV 変動")
        for i in range(1, len(results)):
            prev_mvs = set(results[i-1]['selected_mvs'])
            curr_mvs = set(results[i]['selected_mvs'])
            added = curr_mvs - prev_mvs
            removed = prev_mvs - curr_mvs
            common = prev_mvs & curr_mvs
            print(f"  {results[i-1]['timestep']} → {results[i]['timestep']}: "
                  f"共通 {len(common)}, 追加 {len(added)}, 削除 {len(removed)}")
    else:
        results = []
        total_elapsed = 0.0
        print_info("step2_only モード: タイムステップ別最適化をスキップ")

    # ========== 7. Seed 候補の収集 ==========
    print_header("Step 1: Seed 候補の収集")

    node_name_to_idx = {name: idx for idx, name in enumerate(qp.node_list)}

    # 全候補数の計算
    all_candidates_with_utility = set()
    for i in range(len(base_u_ij)):
        for j in range(len(base_u_ij[i])):
            if base_u_ij[i][j] > 0:
                all_candidates_with_utility.add(j)

    per_timestep_seeds: dict[str, set[int]] = {}
    seed_union = set()

    if args.pruning_method != "step2_only":
        # 各タイムステップの選択結果を Seed として収集
        for r in results:
            ts_seeds = set(r['selected_mv_indices'])
            per_timestep_seeds[r['timestep']] = ts_seeds
            seed_union.update(ts_seeds)
    else:
        # step2_only: 全候補をseedとして使用（タイムステップ別最適化をスキップ）
        seed_union = set(all_candidates_with_utility)
        for ts in timesteps:
            per_timestep_seeds[ts] = set(all_candidates_with_utility)

    print_info(f"Seed 和集合: {len(seed_union)} / {len(all_candidates_with_utility)} "
               f"({100.0 * (1 - len(seed_union) / max(len(all_candidates_with_utility), 1)):.1f}% 削減)")

    # ========== 7b. WST 階層的絞り込み (Step 2-3) ==========
    wst_start = time.time()

    if args.pruning_method == "step1_only":
        print_header("Step 2-3: WST スキップ（step1_only モード）")
        print_info("タイムステップ別最適化の結果をそのまま候補として使用")
        promising_candidates = set(seed_union)
        pruning_info = {
            "reduction_rate": 1.0 - len(promising_candidates) / max(len(all_candidates_with_utility), 1),
        }
        wst_elapsed = 0.0
    else:
        print_header("Step 2-3: WST 階層的絞り込み")
        print_info(f"削減手法: {args.pruning_method}")
        print_info("WSTローカルILP MIPGap: 0.01%")

        inherit_constraints = not args.no_wst_parent_constraints
        print_info(f"WST親制約伝播: {'有効' if inherit_constraints else '無効'}")

        pruner_kwargs = dict(
            node_list=qp.node_list,
            u_ij=base_u_ij,
            X=qp.X,
            b_j=b_j_from_json,
            B_max=B_max,
            timesteps=timesteps,
            migration_cost=migration_costs,
            query_frequency_by_timestep=frequencies,
            per_timestep_seeds=per_timestep_seeds,
            qm=qp.qm,
            position_node_id=getattr(qp, "position_node_id", {}),
            deeplist=getattr(qp, "deeplist", []),
            gurobi_output=0,
            local_mip_gap=0.0001,
            inherit_parent_constraints=inherit_constraints,
        )

        if args.pruning_method in ("iterative", "greedy"):
            print_info(f"反復的削減: 最大イテレーション数/ノード = {args.max_iterations}")
            if args.use_parallel:
                print_info(f"並列処理: 有効, ワーカー数 = {args.max_workers or 'CPU数'}")
            pruner = UtilityPrunerIterative(
                **pruner_kwargs,
                max_iterations=args.max_iterations,
                use_parallel=args.use_parallel,
                max_workers=args.max_workers,
            )
        else:
            pruner = UtilityPruner(**pruner_kwargs)

        promising_candidates = pruner.prune_candidates()
        pruning_info = pruner.get_pruning_info(promising_candidates)
        wst_elapsed = time.time() - wst_start

        print_info(f"WST 後の有望候補数: {len(promising_candidates)} / {len(all_candidates_with_utility)} "
                   f"({pruning_info['reduction_rate']*100:.1f}% 削減)")
        print_info(f"WST 実行時間: {wst_elapsed:.2f} 秒")

        if args.pruning_method == "iterative":
            print_info(f"総イテレーション数: {pruning_info['total_iterations']}")
            print_info(f"平均イテレーション/ノード: {pruning_info['avg_iterations_per_node']:.2f}")

    reduction_rate = pruning_info["reduction_rate"]

    # ========== 8. 全時刻での時間依存最適化 (Step 4) ==========
    print_header("Step 4: 全時刻での時間依存最適化 (候補フィルタリング済み)")

    td_optimizer = TimeDependentOptimizer(
        node_list=qp.node_list,
        u_ij=base_u_ij,
        X=qp.X,
        b_j=b_j_from_json,
        B_max=B_max,
        timesteps=timesteps,
        migration_cost=migration_costs,
        query_frequency_by_timestep=frequencies,
        gurobi_output=1,
    )

    # 候補をフィルタリング（Phase 6 と同じ方法）
    original_cand_count = len(td_optimizer.cand_j)
    td_optimizer.set_candidates([j for j in td_optimizer.cand_j if j in promising_candidates])
    print_info(f"候補をフィルタリング: {original_cand_count} → {len(td_optimizer.cand_j)}")

    td_start = time.time()
    td_result = td_optimizer.optimize()
    td_elapsed = time.time() - td_start

    print_success("時間依存最適化完了")
    print_info(f"  総目的関数値: {td_result['objective']:.4f}")
    print_info(f"  ワークロードコスト: {td_result['workload_cost']:.4f}")
    print_info(f"  マイグレーションコスト: {td_result['migration_cost']:.4f}")
    print_info(f"  ILP求解時間: {td_result['solve_time_sec']:.2f} 秒")
    
    pipeline_elapsed = time.time() - pipeline_start
    print_info(f"  総実行時間（ステップ1〜4合計）: {pipeline_elapsed:.2f} 秒")
    
    # === 時間の詳細な内訳 ===
    time_breakdown = {
        "initial_solution_time_sec": total_elapsed,
        "wst_pruning_time_sec": wst_elapsed,
        "final_optimization_time_sec": td_elapsed,
        "total_pipeline_time_sec": pipeline_elapsed,
    }
    
    print()
    print_info(f"時間内訳:")
    print_info(f"  初期解生成 (Step 1): {time_breakdown['initial_solution_time_sec']:.2f} 秒")
    print_info(f"  WST候補削減 (Step 2-3): {time_breakdown['wst_pruning_time_sec']:.2f} 秒")
    print_info(f"  最終最適化 (Step 4): {time_breakdown['final_optimization_time_sec']:.2f} 秒")
    print_info(f"  合計: {time_breakdown['total_pipeline_time_sec']:.2f} 秒")

    # タイムステップごとの MV 数を表示
    print()
    for t_idx, ts_name in enumerate(timesteps):
        z_t = td_result['z_by_timestep'][t_idx]
        mv_count_t = sum(z_t)
        storage_t = sum(b_j_from_json[j] for j in range(len(z_t)) if z_t[j] == 1)
        print_info(f"  タイムステップ {ts_name}: MV数 {mv_count_t}, "
                   f"ストレージ {storage_t/1024/1024:.2f} MB")

    # ========== 9. 結果を JSON に保存 ==========
    output_dir = exp_dir / "time_dependent_output" / query_set
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 9a. 利得ベース候補選定結果 ---
    cand_filename = f"utility_candidate_selection{args.freq_suffix}.json"
    candidate_path = output_dir / cand_filename
    candidate_data = {
        "parameters": {
            "query_set": query_set,
            "storage_mb": args.storage_mb,
            "freq_suffix": args.freq_suffix,
            "num_timesteps": len(timesteps),
            "pruning_method": args.pruning_method,
            "max_iterations": args.max_iterations if args.pruning_method == "iterative" else None,
        },
        "candidate_selection": {
            "total_candidates": len(all_candidates_with_utility),
            "promising_candidates": len(promising_candidates),
            "reduction_rate": reduction_rate,
            "selection_time": total_elapsed,
        },
        "total_pipeline_time_sec": pipeline_elapsed,
        "per_timestep_results": [],
    }
    for r in results:
        candidate_data["per_timestep_results"].append({
            "timestep": r["timestep"],
            "mv_count": r["mv_count"],
            "total_size_bytes": r["total_size"],
            "objective_value": r["objective_value"],
            "execution_time": r["execution_time"],
            "selected_mvs": r["selected_mvs"],
            "iterations": r["iterations"],
        })
    with open(candidate_path, "w", encoding="utf-8") as f:
        json.dump(candidate_data, f, indent=2, ensure_ascii=False)
    print_success(f"候補選定結果を {candidate_path} に保存")

    # --- 9b. 全時刻最適化結果 (Phase 6 と同一形式) ---
    # マイグレーション遷移分析
    z_by_timestep = td_result["z_by_timestep"]
    migration_analysis = []

    for t in range(len(timesteps)):
        ts_name = timesteps[t]
        current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)

        selected_nodes = [qp.node_list[j] for j in sorted(current_mvs)]
        total_size = sum(b_j_from_json[j] for j in current_mvs)
        utilization = (total_size / B_max * 100) if B_max > 0 else 0

        timestep_info = {
            "timestep": ts_name,
            "selected_mvs": selected_nodes,
            "mv_count": len(current_mvs),
            "total_size": round(total_size, 2),
            "storage_budget": round(B_max, 2),
            "utilization_percent": round(utilization, 2),
        }

        if t > 0:
            prev_mvs = set(j for j, v in enumerate(z_by_timestep[t-1]) if v == 1)
            maintained = current_mvs & prev_mvs
            created = current_mvs - prev_mvs
            deleted = prev_mvs - current_mvs

            creation_cost = 0.0
            creation_details = []
            for j in sorted(created):
                cost = migration_costs.get(j, 0.0)
                creation_cost += cost
                creation_details.append({
                    "mv": qp.node_list[j],
                    "size": round(b_j_from_json[j], 2),
                    "cost": round(cost, 2),
                    "dependencies": [],
                })

            timestep_info["migration"] = {
                "from_timestep": timesteps[t-1],
                "to_timestep": ts_name,
                "maintained": {
                    "count": len(maintained),
                    "mvs": [qp.node_list[j] for j in sorted(maintained)],
                    "total_size": round(sum(b_j_from_json[j] for j in maintained), 2),
                },
                "created": {
                    "count": len(created),
                    "mvs": [qp.node_list[j] for j in sorted(created)],
                    "total_size": round(sum(b_j_from_json[j] for j in created), 2),
                },
                "deleted": {
                    "count": len(deleted),
                    "mvs": [qp.node_list[j] for j in sorted(deleted)],
                    "total_size": round(sum(b_j_from_json[j] for j in deleted), 2),
                },
                "creation_cost": round(creation_cost, 2),
                "creation_details": creation_details,
            }
        else:
            initial_cost = 0.0
            creation_details = []
            for j in sorted(current_mvs):
                cost = migration_costs.get(j, 0.0)
                initial_cost += cost
                creation_details.append({
                    "mv": qp.node_list[j],
                    "size": round(b_j_from_json[j], 2),
                    "cost": round(cost, 2),
                    "dependencies": [],
                })
            timestep_info["initial_creation"] = {
                "total_cost": round(initial_cost, 2),
                "creation_details": creation_details,
            }

        migration_analysis.append(timestep_info)

    # サマリー統計
    total_created = sum(
        len(ma.get("migration", {}).get("created", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )
    total_deleted = sum(
        len(ma.get("migration", {}).get("deleted", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )
    total_maintained = sum(
        len(ma.get("migration", {}).get("maintained", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )

    td_output = {
        "timesteps": td_result["timesteps"],
        "node_list": td_result["node_list"],
        "objective": td_result["objective"],
        "workload_cost": td_result["workload_cost"],
        "migration_cost": td_result["migration_cost"],
        "solve_time_sec": td_result["solve_time_sec"],
        "phase_time_sec": total_elapsed + td_elapsed,
        "total_pipeline_time_sec": pipeline_elapsed,
        "migration_analysis": migration_analysis,
        "summary": {
            "total_timesteps": len(timesteps),
            "total_mvs_created": total_created + len(
                migration_analysis[0].get("initial_creation", {}).get("creation_details", [])
            ),
            "total_mvs_deleted": total_deleted,
            "total_transitions_maintained": total_maintained,
            "avg_mvs_per_timestep": round(
                sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2
            ),
            "avg_storage_utilization": round(
                sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2
            ),
        },
        "pruning_info": {
            "method": f"utility_based_candidate_selection_{args.pruning_method}",
            "total_candidates": len(all_candidates_with_utility),
            "initial_solution_mvs": sorted([qp.node_list[j] for j in seed_union]),
            "initial_solution_count": len(seed_union),
            "promising_candidates": len(promising_candidates),
            "promising_mv_names": sorted([qp.node_list[j] for j in promising_candidates]),
            "filtered_out": len(all_candidates_with_utility) - len(promising_candidates),
            "retention_rate": 1.0 - reduction_rate,
            "reduction_rate": reduction_rate,
            "static_protected_count": 0,
            "static_protected_mv_names": [],
            **({"total_iterations": pruning_info["total_iterations"],
                "avg_iterations_per_node": pruning_info["avg_iterations_per_node"]}
               if args.pruning_method == "iterative" else {}),
        },
        "time_breakdown": time_breakdown,
    }

    td_filename = f"td_mv_optimization_result_utility{args.freq_suffix}.json"
    td_path = output_dir / td_filename
    with open(td_path, "w", encoding="utf-8") as f:
        json.dump(td_output, f, indent=2, ensure_ascii=False)
    print_success(f"全時刻最適化結果を {td_path} に保存")

    return 0


if __name__ == "__main__":
    exit(main())
