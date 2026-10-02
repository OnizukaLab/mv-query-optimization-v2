"""反復的近傍拡大による候補選出 + WST 階層的絞り込み (UtilityPrunerIterative).

UtilityPruner との違い:
- 事前に全近傍を拡大せず、各 WST ノードで反復的に拡大
- 各ノードでの処理:
  1. (Seed + 近傍) ∪ (親境界 MV + 近傍) で最適化（イテレーション1）
  2. 選ばれた MV の近傍をさらに追加
  3. 拡大した候補で再最適化
  4. 収束するまで繰り返し

期待される効果:
- より効率的な候補絞り込み（必要な近傍のみ追加）
- 解の品質向上（反復的な探索）
- 親境界MVの近傍も含めることで探索範囲を拡大
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Set, Optional

from experiments.small_test_ver2.core.local_ilp_optimizer import LocalILPOptimizer
from experiments.small_test_ver2.core.workload_summary_tree import (
    TreeNode,
    WorkloadSummaryTree,
)

logger = logging.getLogger(__name__)


class UtilityPrunerIterative:
    """反復的近傍拡大 + WST 階層的絞り込み.

    処理の流れ:
    1. 各タイムステップの Seed (UtilityOptimizerV2 結果) を受け取る
    2. WST を構築し、各ノードで反復的最適化:
       a. (Seed + 近傍) ∪ (親境界 MV + 近傍) で最適化
       b. 選ばれた MV の近傍をさらに追加
       c. 拡大した候補で再最適化
       d. 選択が変わらなくなるまで繰り返し
    3. 全ノードで選ばれた MV の和集合を「有望候補」として返す
    """

    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        timesteps: List[str],
        migration_cost: Dict[int, float],
        query_frequency_by_timestep: Dict[str, List[float]],
        per_timestep_seeds: Dict[str, Set[int]],
        # 近傍拡大用
        qm,  # QueryModel
        position_node_id: Dict,
        deeplist: List,
        gurobi_output: int = 0,
        local_mip_gap: Optional[float] = None,
        max_iterations: int = 5,  # 各ノードでの最大イテレーション数
        use_parallel: bool = False,
        max_workers: Optional[int] = None,
        inherit_parent_constraints: bool = True,
    ):
        """初期化.

        Args:
            node_list: ノード ID のリスト
            u_ij: 利得行列 [I][J]
            X: 包含行列 [J][J]
            b_j: 各 MV のサイズ
            B_max: ストレージ予算
            timesteps: タイムステップ名リスト
            migration_cost: マイグレーションコスト {j: cost}
            query_frequency_by_timestep: タイムステップごとのクエリ頻度
            per_timestep_seeds: Step 1 結果 {timestep_name: Set[mv_index]}
            qm: QueryModel（近傍拡大用）
            position_node_id: (query_id, position) → node_id マッピング
            deeplist: 各クエリの深さ情報
            gurobi_output: Gurobi 出力レベル (0=off)
            local_mip_gap: WSTローカルILPに適用するGurobi相対ギャップ (例: 0.01=1%)
            max_iterations: 各ノードでの最大イテレーション数
            use_parallel: 並列処理を有効にするか (default: False)
            max_workers: 最大ワーカー数 (default: CPU数)
            inherit_parent_constraints: 親ノードの境界制約を子ノードに伝播するか (default: True)
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.timesteps = timesteps
        self.migration_cost = migration_cost
        self.freq = query_frequency_by_timestep
        self.per_timestep_seeds = per_timestep_seeds
        self.gurobi_output = gurobi_output
        self.local_mip_gap = local_mip_gap
        self.max_iterations = max_iterations
        self.inherit_parent_constraints = inherit_parent_constraints

        # 近傍拡大用
        self.qm = qm
        self.position_node_id = position_node_id
        self.deeplist = deeplist

        self.I = len(u_ij)
        self.T = len(timesteps)
        self.J = len(node_list)

        # 並列処理設定
        self.use_parallel = use_parallel
        if max_workers is None:
            self.max_workers = os.cpu_count() or 1
        else:
            self.max_workers = max_workers

        # 進捗トラッキング用
        self.node_count = 0
        self.total_nodes = 0
        self.total_iterations = 0  # 全ノードでの総イテレーション数

    # ------------------------------------------------------------------
    # 近傍拡大ロジック（UtilityPruner と同一）
    # ------------------------------------------------------------------

    def _find_parent(self, query_id: int, position: int):
        """クエリツリーでの親ポジションを見つける."""
        if not self.deeplist or query_id >= len(self.deeplist):
            return None

        depth_list = self.deeplist[query_id]
        if position >= len(depth_list) or depth_list[position] == 0:
            return None

        target_depth = depth_list[position] - 1
        for i in range(1, position + 1):
            if position - i >= 0 and depth_list[position - i] == target_depth:
                return (query_id, position - i)

        return None

    def expand_neighbors(self, seed_indices: Set[int], silent: bool = False) -> Set[int]:
        """近傍拡大: 親ノード + 子ノードを追加.

        Args:
            seed_indices: 元の MV インデックス集合
            silent: ログ出力を抑制するかどうか

        Returns:
            拡大後の MV インデックス集合（元のセットを含む）
        """
        expanded = set(seed_indices)
        neighbors = set()

        for j in seed_indices:
            node_id = self.node_list[j]

            # 上方向: 親ノードを追加
            if hasattr(self.qm, 'subquery_positions') and node_id in self.qm.subquery_positions:
                for query_id, position in self.qm.subquery_positions[node_id]:
                    parent_pos = self._find_parent(query_id, position)
                    if parent_pos is not None:
                        q_id, p_id = parent_pos
                        if (q_id, p_id) in self.position_node_id:
                            parent_node_id = self.position_node_id[(q_id, p_id)]
                            try:
                                parent_j = self.node_list.index(parent_node_id)
                                neighbors.add(parent_j)
                            except ValueError:
                                pass

            # 下方向: 子ノードを追加
            if node_id.startswith("non_leaf_"):
                if hasattr(self.qm, 'non_leaf_nodes_map_r') and node_id in self.qm.non_leaf_nodes_map_r:
                    for child_node_id in self.qm.non_leaf_nodes_map_r[node_id]:
                        try:
                            child_j = self.node_list.index(child_node_id)
                            neighbors.add(child_j)
                        except ValueError:
                            pass

        expanded.update(neighbors)
        
        if not silent:
            logger.info(
                f"近傍拡大: {len(seed_indices)} → {len(expanded)} "
                f"(+{len(neighbors - seed_indices)} neighbors)"
            )
        
        return expanded

    # ------------------------------------------------------------------
    # WST 走査 + 反復的候補収集
    # ------------------------------------------------------------------

    def prune_candidates(self) -> Set[int]:
        """WST ベースの反復的階層的絞り込みを実行し、有望候補を返す.

        処理:
        1. WST を構築
        2. 各ノードで反復的最適化
           - Seed + その近傍 + 親境界MV + その近傍から開始
           - 反復的に候補を拡大しながら最適化
        3. 全ノードで選ばれた MV の和集合を返す

        Returns:
            有望 MV インデックスの集合
        """
        logger.info("=" * 70)
        logger.info("UtilityPrunerIterative: 反復的 WST 階層的絞り込み開始")
        logger.info("=" * 70)

        t0 = time.time()

        # Seed の統計（初期候補構築時に近傍拡大される）
        all_seed_union = set()
        for seeds in self.per_timestep_seeds.values():
            all_seed_union.update(seeds)

        logger.info(f"全 Seed 和集合: {len(all_seed_union)} candidates (各ノードで近傍拡大)")

        # --- WST 構築 ---
        if self.T < 3:
            logger.info("タイムステップ < 3: WST 不要、Seed 和集合をそのまま返す")
            return all_seed_union

        tree = WorkloadSummaryTree(self.T)
        self.total_nodes = len(tree.get_all_nodes())
        self.node_count = 0
        self.total_iterations = 0

        logger.info(f"WST: depth={tree.get_depth()}, nodes={self.total_nodes}")
        logger.info(f"最大イテレーション数/ノード: {self.max_iterations}")
        logger.info(f"モード: {'並列' if self.use_parallel else '直列'}")
        if self.use_parallel:
            logger.info(f"ワーカー数: {self.max_workers}")
        logger.info("-" * 70)

        # --- 並列 or 直列で実行 ---
        if self.use_parallel:
            promising_mvs = self._prune_candidates_parallel(tree)
        else:
            promising_mvs = self._prune_candidates_sequential(tree)

        elapsed = time.time() - t0

        logger.info("-" * 70)
        logger.info(f"UtilityPrunerIterative 完了: {len(promising_mvs)} promising MVs")
        logger.info(
            f"  全 Seed 和集合: {len(all_seed_union)}, "
            f"WST 後: {len(promising_mvs)}, "
            f"総イテレーション数: {self.total_iterations}, "
            f"時間: {elapsed:.2f}秒"
        )
        logger.info("=" * 70)

        self.pruning_time = elapsed
        self.all_seed_count = len(all_seed_union)

        return promising_mvs

    def _prune_candidates_sequential(self, tree: WorkloadSummaryTree) -> Set[int]:
        """直列実装: 再帰的に WST を走査して候補を収集."""
        promising_mvs: Set[int] = set()

        self._recursive_solve(
            tree_node=tree.root,
            parent_min_mvs=set(),
            parent_max_mvs=set(),
            promising_mvs=promising_mvs,
            is_left_child=False,
            is_right_child=False,
        )

        return promising_mvs

    def _prune_candidates_parallel(self, tree: WorkloadSummaryTree) -> Set[int]:
        """並列実装: レベルごとに BFS で WST を走査し、同じレベルのノードを並列処理.

        各レベルのノードは独立しているため、並列実行可能。
        親ノードの結果を子ノードに渡すため、レベルごとに同期する。
        """
        promising_mvs: Set[int] = set()

        if not tree.root:
            return promising_mvs

        # レベルごとに処理 (BFS アプローチ)
        # 各要素: (node, parent_min_mvs, parent_max_mvs, is_left, is_right)
        current_level = [(tree.root, set(), set(), False, False)]

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            while current_level:
                logger.info(f"並列処理: レベル処理開始 ({len(current_level)} ノード)")

                # 同じレベルのノードを並列実行
                futures = {}
                for node, parent_min_mvs, parent_max_mvs, is_left, is_right in current_level:
                    future = executor.submit(
                        _solve_node_iterative_static,
                        node=node,
                        parent_min_mvs=parent_min_mvs,
                        parent_max_mvs=parent_max_mvs,
                        is_left_child=is_left,
                        is_right_child=is_right,
                        # データ
                        node_list=self.node_list,
                        u_ij=self.u_ij,
                        X=self.X,
                        b_j=self.b_j,
                        B_max=self.B_max,
                        timesteps=self.timesteps,
                        migration_cost=self.migration_cost,
                        freq=self.freq,
                        per_timestep_seeds=self.per_timestep_seeds,
                        qm=self.qm,
                        position_node_id=self.position_node_id,
                        deeplist=self.deeplist,
                        gurobi_output=self.gurobi_output,
                        local_mip_gap=self.local_mip_gap,
                        max_iterations=self.max_iterations,
                        inherit_parent_constraints=self.inherit_parent_constraints,
                    )
                    futures[future] = node

                # 結果を収集し、次のレベルを準備
                next_level = []
                for future in as_completed(futures):
                    node = futures[future]
                    try:
                        result = future.result()

                        # 進捗カウント
                        self.node_count += 1
                        self.total_iterations += result.get("iterations_used", 0)

                        # 有望候補に追加
                        selected_mvs_all = result["selected_mvs"] | result.get("pool_mvs", set())
                        before_count = len(promising_mvs)
                        promising_mvs.update(selected_mvs_all)
                        new_mvs = len(promising_mvs) - before_count

                        progress = f"[{self.node_count}/{self.total_nodes}]"
                        logger.info(
                            f"{progress} 完了: timesteps "
                            f"[{node.min_idx}, {node.median_idx}, {node.max_idx}], "
                            f"selected={len(selected_mvs_all)}, +{new_mvs} new"
                        )
                        print(
                            f"{progress} 完了: T[{node.min_idx},{node.median_idx},{node.max_idx}] "
                            f"選択={len(selected_mvs_all)}, イテレーション={result.get('iterations_used', 0)}"
                        )

                        # 子ノードを次のレベルに追加
                        min_mvs = result["min_mvs"]
                        median_mvs = result["median_mvs"]
                        max_mvs = result["max_mvs"]

                        if node.left_child:
                            next_level.append(
                                (node.left_child, min_mvs, median_mvs, True, False)
                            )

                        if node.right_child:
                            next_level.append(
                                (node.right_child, median_mvs, max_mvs, False, True)
                            )

                    except Exception as e:
                        logger.error(f"ノード処理エラー: {e}")
                        raise

                # 次のレベルへ
                current_level = next_level

        return promising_mvs

    def _build_initial_candidates(
        self,
        tree_node: TreeNode,
        parent_boundary_mvs: Set[int],
    ) -> tuple[Set[int], dict]:
        """初期候補集合を構築（近傍拡大あり）.

        候補 = (範囲内タイムステップの Seed + 近傍拡大) ∪ (親境界 MV + 近傍拡大)

        Args:
            tree_node: 現在の WST ノード
            parent_boundary_mvs: 親ノードの境界で使われた MV

        Returns:
            (初期候補インデックスの集合, 統計情報)
        """
        seed_indices = set()
        for t_idx in range(tree_node.min_idx, tree_node.max_idx + 1):
            if t_idx < len(self.timesteps):
                ts_name = self.timesteps[t_idx]
                if ts_name in self.per_timestep_seeds:
                    seed_indices.update(self.per_timestep_seeds[ts_name])

        # Seedを近傍拡大
        expanded_seeds = self.expand_neighbors(seed_indices, silent=True)
        seed_neighbors = expanded_seeds - seed_indices
        
        # 親境界MVも近傍拡大
        expanded_boundary = self.expand_neighbors(parent_boundary_mvs, silent=True)
        boundary_neighbors = expanded_boundary - parent_boundary_mvs
        
        # 統合
        candidate_set = expanded_seeds | expanded_boundary
        
        stats = {
            "num_seeds": len(seed_indices),
            "num_seed_neighbors": len(seed_neighbors),
            "num_boundary": len(parent_boundary_mvs),
            "num_boundary_neighbors": len(boundary_neighbors),
            "total": len(candidate_set)
        }
        
        return candidate_set, stats

    def _aggregate_frequencies(self, tree_node: TreeNode) -> Dict[str, List[float]]:
        """ノードの期間内の全頻度を、代表3時点に集約する."""
        start_idx = tree_node.min_idx
        end_idx = tree_node.max_idx
        duration = end_idx - start_idx
        
        aggregated_freq: Dict[str, List[float]] = {}
        num_queries = self.I

        if duration < 3:
            for t_idx in [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]:
                ts_name = self.timesteps[t_idx]
                aggregated_freq[ts_name] = self.freq[ts_name]
            return aggregated_freq

        partition_size = duration / 3.0
        b1 = int(start_idx + partition_size)
        b2 = int(start_idx + partition_size * 2)
        
        ranges = [
            (start_idx, b1),
            (b1, b2),
            (b2, end_idx + 1)
        ]
        
        target_indices = [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]
        
        for range_idx, (r_start, r_end) in enumerate(ranges):
            total_freqs = [0.0] * num_queries
            
            for t in range(r_start, r_end):
                if t >= len(self.timesteps):
                    continue
                
                ts_name = self.timesteps[t]
                current_freqs = self.freq[ts_name]
                
                for q in range(num_queries):
                    total_freqs[q] += current_freqs[q]
            
            target_ts_name = self.timesteps[target_indices[range_idx]]
            aggregated_freq[target_ts_name] = total_freqs

        return aggregated_freq

    def _iterative_node_optimization(
        self,
        tree_node: TreeNode,
        fixed_mvs_by_timestep: Dict[int, Set[int]],
        parent_boundary_mvs: Set[int],
        aggregated_freq: Dict[str, List[float]],
    ) -> dict:
        """WST ノードで反復的最適化を実行.

        処理フロー:
        1. 初期候補 = (Seed + 近傍) ∪ (親境界MV + 近傍) で最適化
        2. 選ばれた MV の近傍をさらに追加
        3. 拡大した候補で再最適化
        4. 選択が変わらなくなるまで繰り返し

        Args:
            tree_node: 現在の WST ノード
            fixed_mvs_by_timestep: 固定する MV（境界制約）
            parent_boundary_mvs: 親ノードの境界 MV
            aggregated_freq: 集約済み頻度

        Returns:
            最終最適化結果（selected_mvs_by_timestep, pool_mvs など）
        """
        timestep_indices = [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]
        
        # 初期候補: Seed + 近傍 + 親境界 + その近傍
        current_candidates, initial_stats = self._build_initial_candidates(tree_node, parent_boundary_mvs)
        
        indent = "  " * tree_node.depth
        logger.info(f"{indent}  反復最適化開始: 初期候補 {len(current_candidates)} MVs "
                   f"(Seed: {initial_stats['num_seeds']}, "
                   f"Seed近傍: {initial_stats['num_seed_neighbors']}, "
                   f"Boundary: {initial_stats['num_boundary']}, "
                   f"Boundary近傍: {initial_stats['num_boundary_neighbors']})")
        print(f"{indent}  反復最適化開始: 初期候補 {len(current_candidates)} MVs "
              f"(Seed+Neighbor+Boundary+BoundaryNeighbor)")
        
        previous_selected: Optional[Set[int]] = None
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            self.total_iterations += 1
            
            # 最適化実行
            local_optimizer = LocalILPOptimizer(
                node_list=self.node_list,
                u_ij=self.u_ij,
                X=self.X,
                b_j=self.b_j,
                B_max=self.B_max,
                timestep_indices=timestep_indices,
                all_timesteps=self.timesteps,
                migration_cost=self.migration_cost,
                query_frequency_by_timestep=aggregated_freq,
                fixed_mvs_by_timestep=fixed_mvs_by_timestep,
                candidate_indices=sorted(current_candidates),
                gurobi_output=self.gurobi_output,
                mip_gap=self.local_mip_gap,
            )
            
            result = local_optimizer.optimize()
            
            # 選択された MV の集計
            current_selected: Set[int] = set()
            for mvs in result["selected_mvs_by_timestep"].values():
                current_selected.update(mvs)
            
            pool_mvs = result.get("pool_mvs", set())
            current_selected_all = current_selected | pool_mvs
            
            logger.info(
                f"{indent}  Iter {iteration}: 候補 {len(current_candidates)}, "
                f"選択 {len(current_selected_all)} MVs "
                f"(optimal: {len(current_selected)}, pool: {len(pool_mvs)})"
            )
            print(
                f"{indent}  Iter {iteration}: 候補 {len(current_candidates)}, "
                f"選択 {len(current_selected_all)} MVs"
            )
            
            # 収束判定
            if previous_selected is not None and current_selected == previous_selected:
                logger.info(f"{indent}  → 収束（選択が変化なし）")
                print(f"{indent}  → 収束（選択が変化なし、{iteration}回で完了）")
                break
            
            # 近傍拡大
            expanded_candidates = self.expand_neighbors(current_selected_all, silent=True)
            
            # 親境界を含める
            expanded_candidates.update(parent_boundary_mvs)
            
            new_candidates = expanded_candidates - current_candidates
            
            if not new_candidates:
                logger.info(f"{indent}  → 収束（新規候補なし）")
                print(f"{indent}  → 収束（新規候補なし、{iteration}回で完了）")
                break
            
            logger.info(f"{indent}  → 近傍拡大: +{len(new_candidates)} 新規候補")
            print(f"{indent}  → 近傍拡大: +{len(new_candidates)} 新規候補")
            
            # 次イテレーションの準備
            current_candidates = expanded_candidates
            previous_selected = current_selected.copy()
        
        if iteration >= self.max_iterations:
            logger.info(f"{indent}  → 最大イテレーション数 ({self.max_iterations}) に到達")
            print(f"{indent}  → 最大イテレーション数 ({self.max_iterations}) に到達")
        
        print(f"{indent}  反復最適化完了: 総イテレーション数 {iteration}回")
        return result

    def _recursive_solve(
        self,
        tree_node: TreeNode,
        parent_min_mvs: Set[int],
        parent_max_mvs: Set[int],
        promising_mvs: Set[int],
        is_left_child: bool = False,
        is_right_child: bool = False,
    ) -> dict:
        """WST ノードで反復的最適化を実行し、再帰的に子ノードへ伝播.

        Args:
            tree_node: 現在の WST ノード
            parent_min_mvs: 親の min 時刻の MV (境界制約)
            parent_max_mvs: 親の max 時刻の MV (境界制約)
            promising_mvs: 有望 MV の蓄積用集合 (in-place 更新)
            is_left_child: 左子ノードかどうか
            is_right_child: 右子ノードかどうか

        Returns:
            {min_mvs, median_mvs, max_mvs} 辞書
        """
        self.node_count += 1
        progress = f"[{self.node_count}/{self.total_nodes}]"

        logger.info(
            f"{progress} Processing node: timesteps "
            f"[{tree_node.min_idx}, {tree_node.median_idx}, {tree_node.max_idx}], "
            f"depth={tree_node.depth}"
        )

        # --- 固定境界の構築 ---
        fixed_mvs_by_timestep: Dict[int, Set[int]] = {}

        if self.inherit_parent_constraints:
            if is_left_child and parent_min_mvs:
                fixed_mvs_by_timestep[tree_node.min_idx] = parent_min_mvs.copy()
                logger.info(f"  → Left child: fixing min (t={tree_node.min_idx}) with {len(parent_min_mvs)} MVs")
            if is_left_child and parent_max_mvs:
                fixed_mvs_by_timestep[tree_node.max_idx] = parent_max_mvs.copy()
                logger.info(f"  → Left child: fixing max (t={tree_node.max_idx}) with {len(parent_max_mvs)} MVs")

            if is_right_child and parent_min_mvs:
                fixed_mvs_by_timestep[tree_node.min_idx] = parent_min_mvs.copy()
                logger.info(f"  → Right child: fixing min (t={tree_node.min_idx}) with {len(parent_min_mvs)} MVs")
            if is_right_child and parent_max_mvs:
                fixed_mvs_by_timestep[tree_node.max_idx] = parent_max_mvs.copy()
                logger.info(f"  → Right child: fixing max (t={tree_node.max_idx}) with {len(parent_max_mvs)} MVs")

        # 親境界 MV の集約
        parent_boundary_mvs = set()
        for fixed_set in fixed_mvs_by_timestep.values():
            parent_boundary_mvs.update(fixed_set)

        # --- 初期候補の統計表示 ---
        initial_candidates, initial_stats = self._build_initial_candidates(tree_node, parent_boundary_mvs)
        
        # ターミナルへの詳細出力
        indent = "  " * tree_node.depth
        print(f"{indent}Node {progress} T[{tree_node.min_idx}:{tree_node.max_idx}] "
              f"Seed:{initial_stats['num_seeds']}+{initial_stats['num_seed_neighbors']}, "
              f"Boundary:{initial_stats['num_boundary']}+{initial_stats['num_boundary_neighbors']} "
              f"-> Initial:{initial_stats['total']}")

        # --- 頻度の集約 ---
        aggregated_freq = self._aggregate_frequencies(tree_node)

        # --- 反復的最適化の実行 ---
        result = self._iterative_node_optimization(
            tree_node=tree_node,
            fixed_mvs_by_timestep=fixed_mvs_by_timestep,
            parent_boundary_mvs=parent_boundary_mvs,
            aggregated_freq=aggregated_freq,
        )

        # --- 結果の収集 ---
        selected_mvs_optimal: Set[int] = set()
        for t_idx, mvs in result["selected_mvs_by_timestep"].items():
            selected_mvs_optimal.update(mvs)

        pool_mvs = result.get("pool_mvs", set())
        selected_mvs_all = selected_mvs_optimal.copy()
        if pool_mvs:
            selected_mvs_all.update(pool_mvs)

        before_count = len(promising_mvs)
        promising_mvs.update(selected_mvs_all)
        new_mvs = len(promising_mvs) - before_count

        logger.info(
            f"  ✓ Selected {len(selected_mvs_all)} MVs "
            f"(optimal: {len(selected_mvs_optimal)}, pool: {len(pool_mvs)}, "
            f"+{new_mvs} new, total: {len(promising_mvs)})"
        )

        # --- 子ノードへの境界伝播 ---
        min_mvs = result["selected_mvs_by_timestep"].get(tree_node.min_idx, set())
        median_mvs = result["selected_mvs_by_timestep"].get(tree_node.median_idx, set())
        max_mvs = result["selected_mvs_by_timestep"].get(tree_node.max_idx, set())

        if tree_node.left_child:
            self._recursive_solve(
                tree_node=tree_node.left_child,
                parent_min_mvs=min_mvs,
                parent_max_mvs=median_mvs,
                promising_mvs=promising_mvs,
                is_left_child=True,
                is_right_child=False,
            )

        if tree_node.right_child:
            self._recursive_solve(
                tree_node=tree_node.right_child,
                parent_min_mvs=median_mvs,
                parent_max_mvs=max_mvs,
                promising_mvs=promising_mvs,
                is_left_child=False,
                is_right_child=True,
            )

        return {
            "min_mvs": min_mvs,
            "median_mvs": median_mvs,
            "max_mvs": max_mvs,
        }

    def get_pruning_info(self, promising_mvs: Set[int]) -> dict:
        """絞り込み結果の統計情報を返す."""
        return {
            "total_candidates": self.J,
            "seed_union_count": getattr(self, "all_seed_count", 0),
            "promising_candidates": len(promising_mvs),
            "filtered_out": self.J - len(promising_mvs),
            "retention_rate": len(promising_mvs) / self.J if self.J > 0 else 0.0,
            "reduction_rate": 1.0 - (len(promising_mvs) / self.J) if self.J > 0 else 0.0,
            "pruning_time_sec": getattr(self, "pruning_time", 0.0),
            "total_iterations": self.total_iterations,
            "avg_iterations_per_node": self.total_iterations / self.total_nodes if self.total_nodes > 0 else 0.0,
        }


# ==============================================================================
# モジュールレベル関数（並列処理用）
# ==============================================================================

def _solve_node_iterative_static(
    node: TreeNode,
    parent_min_mvs: Set[int],
    parent_max_mvs: Set[int],
    is_left_child: bool,
    is_right_child: bool,
    node_list: List[str],
    u_ij: List[List[float]],
    X: List[List[int]],
    b_j: List[float],
    B_max: float,
    timesteps: List[str],
    migration_cost: Dict[int, float],
    freq: Dict[str, List[float]],
    per_timestep_seeds: Dict[str, Set[int]],
    qm,
    position_node_id: Dict,
    deeplist: List,
    gurobi_output: int,
    local_mip_gap: Optional[float],
    max_iterations: int,
    inherit_parent_constraints: bool = True,
) -> dict:
    """WST ノードで反復的最適化を実行（並列処理用の静的関数）.

    Args:
        node: 現在の WST ノード
        parent_min_mvs: 親の min 時刻の MV
        parent_max_mvs: 親の max 時刻の MV
        is_left_child: 左子ノードかどうか
        is_right_child: 右子ノードかどうか
        (その他のパラメータは UtilityPrunerIterative と同じ)

    Returns:
        最適化結果の辞書
    """
    from experiments.small_test_ver2.core.utility_pruner_iterative_helpers import (
        build_initial_candidates_static,
        aggregate_frequencies_static,
        expand_neighbors_static,
    )

    # --- 固定境界の構築 ---
    fixed_mvs_by_timestep: Dict[int, Set[int]] = {}

    if inherit_parent_constraints:
        if is_left_child and parent_min_mvs:
            fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
        if is_left_child and parent_max_mvs:
            fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()

        if is_right_child and parent_min_mvs:
            fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
        if is_right_child and parent_max_mvs:
            fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()

    # 親境界 MV の集約
    parent_boundary_mvs = set()
    for fixed_set in fixed_mvs_by_timestep.values():
        parent_boundary_mvs.update(fixed_set)

    # --- 初期候補の構築 ---
    current_candidates, initial_stats = build_initial_candidates_static(
        tree_node=node,
        parent_boundary_mvs=parent_boundary_mvs,
        timesteps=timesteps,
        per_timestep_seeds=per_timestep_seeds,
        node_list=node_list,
        qm=qm,
        position_node_id=position_node_id,
        deeplist=deeplist,
    )

    # --- 頻度の集約 ---
    num_queries = len(u_ij)
    aggregated_freq = aggregate_frequencies_static(
        tree_node=node,
        timesteps=timesteps,
        freq=freq,
        num_queries=num_queries,
    )

    # --- 反復的最適化 ---
    timestep_indices = [node.min_idx, node.median_idx, node.max_idx]
    previous_selected: Optional[Set[int]] = None
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # ILP 最適化を実行
        local_optimizer = LocalILPOptimizer(
            node_list=node_list,
            u_ij=u_ij,
            X=X,
            b_j=b_j,
            B_max=B_max,
            timestep_indices=timestep_indices,
            all_timesteps=timesteps,
            migration_cost=migration_cost,
            query_frequency_by_timestep=aggregated_freq,
            fixed_mvs_by_timestep=fixed_mvs_by_timestep,
            candidate_indices=sorted(current_candidates),
            gurobi_output=gurobi_output,
            mip_gap=local_mip_gap,
        )

        result = local_optimizer.optimize()

        # 選択された MV の集計
        current_selected: Set[int] = set()
        for mvs in result["selected_mvs_by_timestep"].values():
            current_selected.update(mvs)

        pool_mvs = result.get("pool_mvs", set())
        current_selected_all = current_selected | pool_mvs

        # 収束判定
        if previous_selected is not None and current_selected == previous_selected:
            break

        # 近傍拡大
        expanded_candidates = expand_neighbors_static(
            current_selected_all, node_list, qm, position_node_id, deeplist
        )

        # 親境界を含める
        expanded_candidates.update(parent_boundary_mvs)

        new_candidates = expanded_candidates - current_candidates

        if not new_candidates:
            break

        # 次イテレーションの準備
        current_candidates = expanded_candidates
        previous_selected = current_selected.copy()

    # --- 結果の抽出 ---
    selected_mvs_optimal: Set[int] = set()
    for t_idx, mvs in result["selected_mvs_by_timestep"].items():
        selected_mvs_optimal.update(mvs)

    pool_mvs = result.get("pool_mvs", set())

    # 境界 MV の抽出
    min_mvs = result["selected_mvs_by_timestep"].get(node.min_idx, set())
    median_mvs = result["selected_mvs_by_timestep"].get(node.median_idx, set())
    max_mvs = result["selected_mvs_by_timestep"].get(node.max_idx, set())

    return {
        "selected_mvs": selected_mvs_optimal,
        "pool_mvs": pool_mvs,
        "min_mvs": min_mvs,
        "median_mvs": median_mvs,
        "max_mvs": max_mvs,
        "iterations_used": iteration,
    }
