"""UtilityPrunerIterative のモジュールレベルヘルパー関数.

並列処理で pickle 可能にするため、インスタンスメソッドではなく
モジュールレベル関数として実装する。
"""

from typing import Dict, List, Set, Optional
from experiments.small_test_ver2.core.local_ilp_optimizer import LocalILPOptimizer
from experiments.small_test_ver2.core.workload_summary_tree import TreeNode


def _find_parent_static(query_id: int, position: int, deeplist: List) -> Optional[tuple]:
    """クエリツリーでの親ポジションを見つける（静的版）."""
    if not deeplist or query_id >= len(deeplist):
        return None

    depth_list = deeplist[query_id]
    if position >= len(depth_list) or depth_list[position] == 0:
        return None

    target_depth = depth_list[position] - 1
    for i in range(1, position + 1):
        if position - i >= 0 and depth_list[position - i] == target_depth:
            return (query_id, position - i)

    return None


def expand_neighbors_static(
    seed_indices: Set[int],
    node_list: List[str],
    qm,
    position_node_id: Dict,
    deeplist: List,
) -> Set[int]:
    """近傍拡大: 親ノード + 子ノードを追加（静的版）."""
    expanded = set(seed_indices)
    neighbors = set()

    for j in seed_indices:
        node_id = node_list[j]

        # 上方向: 親ノードを追加
        if hasattr(qm, 'subquery_positions') and node_id in qm.subquery_positions:
            for query_id, position in qm.subquery_positions[node_id]:
                parent_pos = _find_parent_static(query_id, position, deeplist)
                if parent_pos is not None:
                    q_id, p_id = parent_pos
                    if (q_id, p_id) in position_node_id:
                        parent_node_id = position_node_id[(q_id, p_id)]
                        try:
                            parent_j = node_list.index(parent_node_id)
                            neighbors.add(parent_j)
                        except ValueError:
                            pass

        # 下方向: 子ノードを追加
        if node_id.startswith("non_leaf_"):
            if hasattr(qm, 'non_leaf_nodes_map_r') and node_id in qm.non_leaf_nodes_map_r:
                for child_node_id in qm.non_leaf_nodes_map_r[node_id]:
                    try:
                        child_j = node_list.index(child_node_id)
                        neighbors.add(child_j)
                    except ValueError:
                        pass

    expanded.update(neighbors)
    return expanded


def build_initial_candidates_static(
    tree_node: TreeNode,
    parent_boundary_mvs: Set[int],
    timesteps: List[str],
    per_timestep_seeds: Dict[str, Set[int]],
    node_list: List[str],
    qm,
    position_node_id: Dict,
    deeplist: List,
) -> tuple[Set[int], dict]:
    """初期候補集合を構築（静的版）."""
    seed_indices = set()
    for t_idx in range(tree_node.min_idx, tree_node.max_idx + 1):
        if t_idx < len(timesteps):
            ts_name = timesteps[t_idx]
            if ts_name in per_timestep_seeds:
                seed_indices.update(per_timestep_seeds[ts_name])

    # Seed を近傍拡大
    expanded_seeds = expand_neighbors_static(
        seed_indices, node_list, qm, position_node_id, deeplist
    )
    seed_neighbors = expanded_seeds - seed_indices

    # 親境界 MV も近傍拡大
    expanded_boundary = expand_neighbors_static(
        parent_boundary_mvs, node_list, qm, position_node_id, deeplist
    )
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


def aggregate_frequencies_static(
    tree_node: TreeNode,
    timesteps: List[str],
    freq: Dict[str, List[float]],
    num_queries: int,
) -> Dict[str, List[float]]:
    """ノードの期間内の全頻度を、代表3時点に集約する（静的版）."""
    start_idx = tree_node.min_idx
    end_idx = tree_node.max_idx
    duration = end_idx - start_idx

    aggregated_freq: Dict[str, List[float]] = {}

    if duration < 3:
        for t_idx in [tree_node.min_idx, tree_node.median_idx, tree_node.max_idx]:
            ts_name = timesteps[t_idx]
            aggregated_freq[ts_name] = freq[ts_name]
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
            if t >= len(timesteps):
                continue

            ts_name = timesteps[t]
            current_freqs = freq[ts_name]

            for q in range(num_queries):
                total_freqs[q] += current_freqs[q]

        target_ts_name = timesteps[target_indices[range_idx]]
        aggregated_freq[target_ts_name] = total_freqs

    return aggregated_freq
