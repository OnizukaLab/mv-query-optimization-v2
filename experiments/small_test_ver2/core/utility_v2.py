"""Utility-based ILP optimization algorithm (V2 - Bug-fixed).

This module is a corrected version of utility.py with the following fixes:
  1. initialize_greedy() uses self.b_j (constructor arg) instead of
     self.qm.subquery_sizes (pickle), ensuring consistent size values.
  2. optimize() correctly preserves the last good ILP solution on loop break,
     instead of using the neighbor-expanded z_j.
  3. neighbor_search() operates on a copy to avoid in-place mutation.

This version uses a deterministic greedy initialization followed by
iterative neighborhood search + ILP solving (Hill Climbing).
"""

import copy
import math
import random
import time

import sys
from pathlib import Path

# プロジェクトルートをsys.pathに追加
_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.core.models import OptimizationResult
from src.optimization.base import BaseILPOptimizer


class UtilityOptimizerV2(BaseILPOptimizer):
    """Utility-based ILP optimizer (bug-fixed version).

    This algorithm uses a deterministic greedy initialization followed by
    iterative neighborhood search + ILP solving. It continues as long as
    the objective value improves.
    """

    def __init__(self, *args, position_node_id=None, deeplist=None,
                 seed=None, **kwargs):
        """Initialize utility optimizer.

        Args:
            *args: Positional arguments for BaseILPOptimizer
            position_node_id: Mapping from (query_id, position) to node_id
            deeplist: List of depth information for each query
            seed: Random seed for reproducibility (default: None)
            **kwargs: Keyword arguments for BaseILPOptimizer
        """
        super().__init__(*args, **kwargs)
        self.position_node_id = position_node_id or {}
        self.deeplist = deeplist or []
        if seed is not None:
            random.seed(seed)

    def initialize_greedy(self, budget_multiplier: float = 5.0) -> list[int]:
        """Initialize solution using deterministic greedy heuristic.

        Selects MVs in order of (utility - maintenance_cost) / size
        (knapsack-style efficiency) until budget is exhausted.
        The real constraint is enforced by the ILP solver.

        Args:
            budget_multiplier: Multiplier applied to B_max for the greedy budget.
                               Default 5.0 (oversampling). Use 1.0 to disable
                               oversampling and respect the actual storage budget.

        Returns:
            Binary list indicating initial MV selection
        """
        mv_list = [0] * self.s_num

        greedy_budget = self.B_max * budget_multiplier

        # Calculate total utility for each node: sum of u_ij over all queries
        U_j_max = {}
        for j in range(self.s_num):
            U_j_max[j] = sum(self.u_ij[i][j] for i in range(len(self.u_ij)))

        # Calculate utility - maintenance cost for each node
        net_utility = {}
        for j in range(self.s_num):
            net_utility[j] = U_j_max[j] - self.m_cost[j]

        # Sort by efficiency = (utility - m_cost) / size (descending)
        # Skip nodes with non-positive utility or zero size
        candidates = []
        for j in range(self.s_num):
            if net_utility[j] <= 0:
                continue
            size = self.b_j[j]
            if size > 0:
                efficiency = net_utility[j] / size
            else:
                efficiency = float('inf')  # サイズ0なら最優先
            candidates.append((j, net_utility[j], efficiency))

        candidates.sort(key=lambda x: x[2], reverse=True)

        # Greedily select MVs until oversampled budget exhausted
        b_now = 0.0
        for j, utility, efficiency in candidates:
            if b_now + self.b_j[j] <= greedy_budget:
                mv_list[j] = 1
                b_now += self.b_j[j]

        return mv_list


    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates using greedy utility-based heuristic.

        Returns:
            Tuple of (cand_i, cand_j):
                cand_i: Queries that can benefit from MVs
                cand_j: Subqueries selected by greedy initialization
        """
        z_j = self.initialize_greedy()

        M = []
        for i in range(len(self.q_s_list)):
            M_i = []
            M_i_ = []
            for j in range(len(z_j)):
                if self.u_ij[i][j] > 0:
                    M_i.append(j)
                if z_j[j] > 0:
                    M_i_.append(j)
            k = list(set(M_i) & set(M_i_))
            M.append(k)

        cand_i = [i for i in range(len(M)) if len(M[i]) != 0]
        cand_j = [j for j in range(len(z_j)) if z_j[j] == 1]

        return cand_i, cand_j

    def neighbor_search(self, z_j: list[int]) -> list[int]:
        """Perform neighborhood search to expand candidates.

        Adds parent nodes (upward) and child nodes (downward) of currently
        selected MVs to the candidate set.

        Operates on a copy to avoid in-place mutation of the input.

        Args:
            z_j: Current MV selection

        Returns:
            New list with neighbors added (original is NOT modified)
        """
        z_j_expanded = list(z_j)

        new_list_j = []

        for i in range(len(z_j_expanded)):
            if z_j_expanded[i] == 1:
                node_id = self.node_list[i]

                # Upward search: add parent nodes
                uplist = []
                for query_id, position in self.qm.subquery_positions[node_id]:
                    parent_pos = self._find_parent(query_id, position)
                    if parent_pos is not None:
                        uplist.append(parent_pos)

                for query_id, position in uplist:
                    if (query_id, position) in self.position_node_id:
                        parent_node_id = self.position_node_id[(query_id, position)]
                        j = self.node_list.index(parent_node_id)
                        if j not in new_list_j:
                            new_list_j.append(j)

                # Downward search: add child nodes (for non-leaf nodes)
                if node_id.startswith("non_leaf_"):
                    if node_id in self.qm.non_leaf_nodes_map_r:
                        for child_node_id in self.qm.non_leaf_nodes_map_r[node_id]:
                            j = self.node_list.index(child_node_id)
                            if j not in new_list_j:
                                new_list_j.append(j)

        # Add neighbors to the copy
        for j in new_list_j:
            z_j_expanded[j] = 1

        return z_j_expanded

    def _find_parent(self, query_id: int, position: int) -> tuple[int, int] | None:
        """Find parent position in query tree.

        Args:
            query_id: Query index
            position: Current position in query

        Returns:
            (query_id, parent_position) or None if at root
        """
        if not self.deeplist or query_id >= len(self.deeplist):
            return None

        depth_list = self.deeplist[query_id]
        if position >= len(depth_list) or depth_list[position] == 0:
            # At root
            return None

        # Search backward for parent (depth - 1)
        target_depth = depth_list[position] - 1
        for i in range(1, position + 1):
            if position - i >= 0 and depth_list[position - i] == target_depth:
                return (query_id, position - i)

        return None

    def optimize(self, **kwargs) -> OptimizationResult:
        """Execute optimization with Simulated Annealing.

        Algorithm:
        1. Initialize with deterministic greedy heuristic
        2. Expand candidates via neighborhood search
        3. Solve ILP over expanded candidates
        4. If improved: always accept
           If worsened: accept with probability exp(delta / temperature)
        5. Cool temperature and repeat until cold or max iterations

        The global best solution is tracked separately and returned.

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()

        # Initialize with deterministic greedy heuristic
        z_j = self.initialize_greedy()
        U_cur = 0
        iter_count = 0
        max_iterations = 500

        # Track the global best solution (across all iterations)
        global_best_z_j = list(z_j)
        global_best_y_ij = None
        global_best_obj = 0

        # Iterative improvement loop (Hill Climbing)
        while iter_count < max_iterations:
            # Expand candidates with neighborhood search
            z_j_expanded = self.neighbor_search(z_j)

            # Build M: beneficial subqueries for each query
            M = []
            for i in range(len(self.q_s_list)):
                M_i = []
                M_i_ = []
                for j in range(len(z_j_expanded)):
                    if self.u_ij[i][j] > 0:
                        M_i.append(j)
                    if z_j_expanded[j] > 0:
                        M_i_.append(j)
                k = list(set(M_i) & set(M_i_))
                M.append(k)

            # Identify candidate queries and subqueries
            cand_i = [i for i in range(len(M)) if len(M[i]) != 0]
            cand_j = [j for j in range(len(z_j_expanded)) if z_j_expanded[j] == 1]

            # Build and solve ILP model with candidates
            y, z = self.build_ilp_model_with_candidates(cand_i, cand_j)
            self.add_constraints_with_candidates(y, z, cand_i, cand_j)
            self.set_objective_with_candidates(y, z, cand_i, cand_j)
            y_ij, z_j_temp, U_new = self.solve_ilp_with_candidates(y, z, cand_i, cand_j)

            # Check for improvement
            delta = U_new - U_cur

            if delta > 0:
                # Improvement: accept and continue
                U_cur = U_new
                z_j = z_j_temp
                
                # Update global best
                global_best_obj = U_new
                global_best_z_j = list(z_j_temp)
                global_best_y_ij = y_ij
            else:
                # No improvement: stop (converged to local optimum)
                break

            iter_count += 1

        execution_time = time.time() - start_time

        # Use the global best solution (not necessarily the last accepted one)
        B_cur = self.calculate_storage_used(global_best_z_j)
        mat_list = [j for j in range(len(global_best_z_j)) if global_best_z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)

        # Create result
        result = self.create_result(
            y_ij=global_best_y_ij,
            z_j=global_best_z_j,
            obj_val=global_best_obj,
            execution_time=execution_time,
            storage_used=B_cur,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            initialization="greedy_with_iterative_improvement",
            iterations=iter_count,
            selected_indices=mat_list,
        )

        return result
