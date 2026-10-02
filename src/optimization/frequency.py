"""Frequency-based ILP optimization algorithm.

This module implements the frequency-based greedy initialization,
selecting MVs based on usage frequency.
"""

import time

from ..core.models import OptimizationResult
from .base import BaseILPOptimizer


class FrequencyOptimizer(BaseILPOptimizer):
    """Frequency-based ILP optimizer.

    This algorithm uses a greedy initialization based on subquery usage
    frequency (number of queries using the subquery).
    """

    def __init__(self, *args, position_node_id=None, deeplist=None, query_frequencies=None, **kwargs):
        """Initialize frequency optimizer.

        Args:
            *args: Positional arguments for BaseILPOptimizer
            position_node_id: Mapping from (query_id, position) to node_id
            deeplist: List of depth information for each query
            query_frequencies: Dict mapping query_id to Redset occurrence count.
                Used to weight subquery priority by workload repetition.
            **kwargs: Keyword arguments for BaseILPOptimizer
        """
        super().__init__(*args, **kwargs)
        self.position_node_id = position_node_id or {}
        self.deeplist = deeplist or []
        # query_frequencies: {query_id (int) -> occurrence count in Redset workload}
        self.query_frequencies = query_frequencies or {}

    def initialize_greedy(self) -> list[int]:
        """Initialize solution using frequency-based greedy heuristic.

        Selects MVs in order of usage frequency until storage budget
        is exhausted. MVs used by more queries are prioritized.
        
        Note: Does not enforce subsumption constraints here - they will be
        enforced by the ILP solver in the optimization phase.

        Returns:
            Binary list indicating initial MV selection
        """
        mv_list = [0] * self.s_num

        # Calculate Redset-weighted frequency for each node.
        # If query_frequencies is available, weight each occurrence by the
        # Redset repetition count for that query (e.g. query appears 50 times
        # in the workload → counts 50 instead of 1). This matches the paper's
        # topk-F which prioritizes subqueries used by frequently-repeated queries.
        freq_list = {}
        for i in range(len(self.node_list)):
            node_id = self.node_list[i]
            if self.query_frequencies:
                weighted = sum(
                    self.query_frequencies.get(pos[0], 1)
                    for pos in self.qm.subquery_positions[node_id]
                )
                freq_list[node_id] = weighted
            else:
                freq_list[node_id] = len(self.qm.subquery_positions[node_id])

        # Sort by frequency (descending)
        freq_list_sorted = sorted(freq_list.items(), key=lambda x: x[1], reverse=True)

        # Greedily select MVs until budget exhausted
        b_now = 0
        for node_id, frequency in freq_list_sorted:
            node_idx = self.node_list.index(node_id)
            if b_now + self.qm.subquery_sizes[node_id] <= self.B_max:
                mv_list[node_idx] = 1
                b_now += self.qm.subquery_sizes[node_id]

        return mv_list

    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates using greedy frequency-based heuristic.

        Returns:
            Tuple of (cand_i, cand_j):
                cand_i: Queries that can benefit from MVs
                cand_j: Subqueries selected by greedy initialization
        """
        # Get greedy initial solution
        z_j = self.initialize_greedy()

        # Build M: beneficial subqueries for each query
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

        # Candidate queries
        cand_i = []
        for i in range(len(M)):
            if len(M[i]) != 0:
                cand_i.append(i)

        # Candidate subqueries
        cand_j = []
        for j in range(len(z_j)):
            if z_j[j] == 1:
                cand_j.append(j)

        return cand_i, cand_j

    def neighbor_search(self, z_j: list[int]) -> list[int]:
        """Perform neighborhood search to expand candidates.

        Adds parent nodes (upward) and child nodes (downward) of currently
        selected MVs to the candidate set.
        
        Note: Does not enforce subsumption constraints here - they will be
        enforced by the ILP solver in the optimization phase.

        Args:
            z_j: Current MV selection

        Returns:
            Updated MV selection with neighbors added
        """
        new_list_j = []

        for i in range(len(z_j)):
            if z_j[i] == 1:
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

        # Add neighbors to current selection
        for j in new_list_j:
            z_j[j] = 1

        return z_j

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
        """Execute the frequency-based ILP optimization with neighborhood search.

        This implements the original algorithm with iterative improvement:
        1. Initialize with greedy heuristic
        2. Perform neighborhood search
        3. Solve ILP
        4. Repeat until no improvement

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()

        # Initialize with greedy heuristic
        z_j = self.initialize_greedy()
        U_pre = 0
        iter_count = 0
        max_iterations = 100  # Safety limit to prevent infinite loops
        
        # Initialize variables to store best solution
        y_ij = None
        U_cur = 0

        # Iterative improvement loop
        while iter_count < max_iterations:
            # Expand candidates with neighborhood search
            z_j = self.neighbor_search(z_j)

            # Build M: beneficial subqueries for each query
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

            # Identify candidate queries and subqueries
            cand_i = [i for i in range(len(M)) if len(M[i]) != 0]
            cand_j = [j for j in range(len(z_j)) if z_j[j] == 1]

            # Build and solve ILP model with candidates
            y, z = self.build_ilp_model_with_candidates(cand_i, cand_j)
            self.add_constraints_with_candidates(y, z, cand_i, cand_j)
            self.set_objective_with_candidates(y, z, cand_i, cand_j)
            y_ij, z_j_temp, U_cur = self.solve_ilp_with_candidates(y, z, cand_i, cand_j)

            # Check convergence
            if U_pre >= U_cur:
                # Current solution is not better, stop iterating
                # Keep the previous (better) solution in y_ij and z_j
                break

            # Current solution is better, accept it
            U_pre = U_cur
            z_j = z_j_temp
            iter_count += 1

        execution_time = time.time() - start_time

        # Extract final z_j from y_ij (the actual ILP solution)
        # Note: Do not use the z_j variable here, as it may contain neighbor_search candidates
        # that were not validated by the ILP solver
        final_z_j = [0] * len(self.b_j)
        for j in range(len(self.b_j)):
            # A node is materialized if it's used by any query in the ILP solution
            if any(y_ij[i][j] == 1 for i in range(len(y_ij))):
                final_z_j[j] = 1

        # Calculate metrics using the ILP solution
        B_cur = self.calculate_storage_used(final_z_j)
        mat_list = [j for j in range(len(final_z_j)) if final_z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)

        # Create result
        result = self.create_result(
            y_ij=y_ij,
            z_j=final_z_j,
            obj_val=U_cur,
            execution_time=execution_time,
            storage_used=B_cur,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            initialization="frequency_greedy",
            iterations=iter_count,
        )

        return result
