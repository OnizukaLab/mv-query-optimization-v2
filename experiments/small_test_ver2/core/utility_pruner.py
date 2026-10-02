"""利得ベース候補選出 + WST 階層的絞り込み (UtilityPruner).

Step 1（近傍拡大）+ Step 2-3（WST 走査・候補収集）を担当する新クラス。

既存クラスとの関係:
- WorkloadSummaryTree: そのまま import して WST を構築
- LocalILPOptimizer: そのまま import して 3時点 ILP を解く
- CFPruner._recursive_solve: ロジックを参考に再実装
  （候補集合の構築方法が異なる: Seed 和集合 + 近傍 ベース）
- UtilityOptimizerV2.neighbor_search: ロジックを移植
  （parent/child ノード展開）
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Optional

from experiments.small_test_ver2.core.local_ilp_optimizer import LocalILPOptimizer
from experiments.small_test_ver2.core.workload_summary_tree import (
    TreeNode,
    WorkloadSummaryTree,
)

logger = logging.getLogger(__name__)


class UtilityPruner:
    """利得ベース候補選出 + WST 階層的絞り込み.

    処理の流れ:
    1. 各タイムステップの Seed (UtilityOptimizerV2 結果) を受け取る
    2. Seed に対して近傍拡大（親ノード + 子ノード）を行う
    3. WST を構築し、各ノードで局所 ILP を解く
       - 候補集合 = 範囲内タイムステップの Seed 和集合（+ 近傍）+ 親境界 MV
    4. 全ノードで選ばれた MV の和集合を「有望候補」として返す
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
        # 近傍拡大用（UtilityOptimizerV2.neighbor_search と同等）
        qm,  # QueryModel
        position_node_id: Dict,
        deeplist: List,
        gurobi_output: int = 0,
        local_mip_gap: Optional[float] = None,
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
        self.inherit_parent_constraints = inherit_parent_constraints

        # 近傍拡大用
        self.qm = qm
        self.position_node_id = position_node_id
        self.deeplist = deeplist

        self.I = len(u_ij)
        self.T = len(timesteps)
        self.J = len(node_list)

        # 進捗トラッキング用
        self.node_count = 0
        self.total_nodes = 0

    # ------------------------------------------------------------------
    # Step 1: 近傍拡大
    # ------------------------------------------------------------------
    # 以下は UtilityOptimizerV2.neighbor_search / _find_parent と同等のロジック

    def _find_parent(self, query_id: int, position: int):
        """クエリツリーでの親ポジションを見つける.

        UtilityOptimizerV2._find_parent と同一ロジック。
        """
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

    def expand_neighbors(self, seed_indices: Set[int]) -> Set[int]:
        """近傍拡大: 親ノード + 子ノードを追加.

        UtilityOptimizerV2.neighbor_search と同等のロジック。
        選ばれた MV の親ノード（上方向）と子ノード（下方向）を候補に加える。

        Args:
            seed_indices: 元の MV インデックス集合

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
        logger.info(
            f"近傍拡大: {len(seed_indices)} → {len(expanded)} "
            f"(+{len(neighbors - seed_indices)} neighbors)"
        )
        return expanded

    # ------------------------------------------------------------------
    # Step 2-3: WST 走査 + 候補収集
    # ------------------------------------------------------------------

    def prune_candidates(self) -> Set[int]:
        """WST ベースの階層的絞り込みを実行し、有望候補を返す.

        処理:
        1. 各タイムステップの Seed を近傍拡大
        2. WST を構築してルートから再帰的に局所 ILP を解く
        3. 全ノードで選ばれた MV の和集合を返す

        Returns:
            有望 MV インデックスの集合
        """
        logger.info("=" * 70)
        logger.info("UtilityPruner: WST 階層的絞り込み開始")
        logger.info("=" * 70)

        t0 = time.time()

        # --- Step 1b: 各タイムステップの seeds を収集（近傍拡大なし）---
        all_seed_union = set()
        for seeds in self.per_timestep_seeds.values():
            all_seed_union.update(seeds)

        logger.info(f"全 Seed 和集合: {len(all_seed_union)} candidates")

        # --- WST 構築 ---
        if self.T < 3:
            logger.info("タイムステップ < 3: WST 不要、Seed 和集合をそのまま返す")
            return all_seed_union

        tree = WorkloadSummaryTree(self.T)
        self.total_nodes = len(tree.get_all_nodes())
        self.node_count = 0

        logger.info(f"WST: depth={tree.get_depth()}, nodes={self.total_nodes}")
        logger.info("-" * 70)

        # --- 再帰的に局所 ILP を解く ---
        promising_mvs: Set[int] = set()

        self._recursive_solve(
            tree_node=tree.root,
            parent_min_mvs=set(),
            parent_max_mvs=set(),
            promising_mvs=promising_mvs,
            is_left_child=False,
            is_right_child=False,
        )

        elapsed = time.time() - t0

        logger.info("-" * 70)
        logger.info(f"UtilityPruner 完了: {len(promising_mvs)} promising MVs")
        logger.info(
            f"  全 Seed 和集合: {len(all_seed_union)}, "
            f"WST 後: {len(promising_mvs)}, "
            f"時間: {elapsed:.2f}秒"
        )
        logger.info("=" * 70)

        self.pruning_time = elapsed
        self.all_seed_count = len(all_seed_union)

        return promising_mvs

    def _build_node_candidates(
        self,
        tree_node: TreeNode,
        parent_boundary_mvs: Set[int],
    ) -> tuple[List[int], dict]:
        """WST ノードの候補集合を構築する.

        候補 = 範囲内タイムステップの元の Seed ∪ 親境界 MV（近傍拡大なし）

        Args:
            tree_node: 現在の WST ノード
            parent_boundary_mvs: 親ノードの境界で使われた MV

        Returns:
            (候補インデックスのリスト, 統計情報)
        """
        seed_indices = set()
        for t_idx in range(tree_node.min_idx, tree_node.max_idx + 1):
            if t_idx < len(self.timesteps):
                ts_name = self.timesteps[t_idx]
                if ts_name in self.per_timestep_seeds:
                    seed_indices.update(self.per_timestep_seeds[ts_name])

        boundary_indices = parent_boundary_mvs - seed_indices
        candidate_set = seed_indices | parent_boundary_mvs

        stats = {
            "num_seeds": len(seed_indices),
            "num_neighbors": 0,
            "num_boundary": len(boundary_indices),
            "total": len(candidate_set)
        }

        return sorted(candidate_set), stats

    def _aggregate_frequencies(self, tree_node: TreeNode) -> Dict[str, List[float]]:
        """ノードの期間内の全頻度を、代表3時点に集約する.

        CFPruner._solve_node_static と同等のロジック。
        期間 [min, max] を3分割し、それぞれの合計頻度を min, median, max に割り当てる。
        """
        start_idx = tree_node.min_idx
        end_idx = tree_node.max_idx
        duration = end_idx - start_idx
        
        aggregated_freq: Dict[str, List[float]] = {}
        num_queries = self.I

        # 期間が短すぎる場合は分割できないため、元の頻度をそのまま使う
        if duration < 3:
            for t_idx in [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]:
                ts_name = self.timesteps[t_idx]
                aggregated_freq[ts_name] = self.freq[ts_name]
            return aggregated_freq

        # 均等3分割の計算
        partition_size = duration / 3.0
        
        # 区間の境界インデックスを計算
        b1 = int(start_idx + partition_size)
        b2 = int(start_idx + partition_size * 2)
        
        # 3つの区間を定義
        ranges = [
            (start_idx, b1),      # Mapped to min_idx
            (b1, b2),             # Mapped to median_idx
            (b2, end_idx + 1)     # Mapped to max_idx
        ]
        
        # マッピング先の時刻インデックス
        target_indices = [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]
        
        for range_idx, (r_start, r_end) in enumerate(ranges):
            # 集計用配列の初期化
            total_freqs = [0.0] * num_queries
            
            # 区間内の全タイムステップについて頻度を加算
            for t in range(r_start, r_end):
                if t >= len(self.timesteps): continue
                
                ts_name = self.timesteps[t]
                current_freqs = self.freq[ts_name]
                
                for q in range(num_queries):
                    total_freqs[q] += current_freqs[q]
            
            # 集計結果を代表時刻の頻度として登録
            target_ts_name = self.timesteps[target_indices[range_idx]]
            aggregated_freq[target_ts_name] = total_freqs

        return aggregated_freq

    def _recursive_solve(
        self,
        tree_node: TreeNode,
        parent_min_mvs: Set[int],
        parent_max_mvs: Set[int],
        promising_mvs: Set[int],
        is_left_child: bool = False,
        is_right_child: bool = False,
    ) -> dict:
        """WST ノードで局所 ILP を解き、再帰的に子ノードへ伝播.

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

        timestep_indices = [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]

        # --- 固定境界の構築 (CFPruner と同一) ---
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

        # --- 候補集合の構築 ---
        parent_boundary_mvs = set()
        for fixed_set in fixed_mvs_by_timestep.values():
            parent_boundary_mvs.update(fixed_set)

        node_candidates, stats = self._build_node_candidates(
            tree_node, parent_boundary_mvs
        )
        
        # ターミナルへの詳細出力
        indent = "  " * tree_node.depth
        print(f"{indent}Node {progress} T[{tree_node.min_idx}:{tree_node.max_idx}] "
              f"Seed:{stats['num_seeds']}, Neighbor:{stats['num_neighbors']}, "
              f"Boundary:{stats['num_boundary']} -> Total:{stats['total']}")

        # --- 局所 ILP を解く ---
        # 頻度の集約
        aggregated_freq = self._aggregate_frequencies(tree_node)

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
            candidate_indices=node_candidates,
            gurobi_output=self.gurobi_output,
            mip_gap=self.local_mip_gap,
        )

        result = local_optimizer.optimize()

        # --- 結果の収集 (CFPruner と同一) ---
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

        # --- 子ノードへの境界伝播 (CFPruner と同一) ---
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
        """絞り込み結果の統計情報を返す.

        CFPruner.get_filtering_info と同等。
        """
        return {
            "total_candidates": self.J,
            "seed_union_count": getattr(self, "all_seed_count", 0),
            "promising_candidates": len(promising_mvs),
            "filtered_out": self.J - len(promising_mvs),
            "retention_rate": len(promising_mvs) / self.J if self.J > 0 else 0.0,
            "reduction_rate": 1.0 - (len(promising_mvs) / self.J) if self.J > 0 else 0.0,
            "pruning_time_sec": getattr(self, "pruning_time", 0.0),
        }
