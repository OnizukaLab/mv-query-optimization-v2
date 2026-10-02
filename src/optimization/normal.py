"""Normal ILP optimization algorithm.

This module implements the basic (normal) ILP-based materialized view
selection algorithm without any special initialization heuristics.
"""

import time

from ..core.models import OptimizationResult
from .base import BaseILPOptimizer


class NormalOptimizer(BaseILPOptimizer):
    """Normal ILP optimization without special heuristics.

    This is the baseline algorithm that solves the ILP directly without
    any preprocessing or candidate filtering beyond basic feasibility checks.
    """

    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates using basic feasibility.

        Selects all subqueries with non-zero utility as candidates.

        Returns:
            Tuple of (cand_i, cand_j):
                cand_i: Queries that can benefit from MVs
                cand_j: Subqueries that are viable MV candidates
        """
        # Initialize z_j (all nodes are initially candidates)
        z_j = [1] * self.s_num

        # Find queries with potential utility
        M = []  # Set of beneficial subqueries for each query
        for i in range(len(self.q_s_list)):
            M_i = []
            M_i_ = []
            for j in range(len(z_j)):
                if self.u_ij[i][j] > 0:
                    M_i.append(j)
                if z_j[j] > 0:
                    M_i_.append(j)

            # Intersection of utility-providing and candidate nodes
            k = list(set(M_i) & set(M_i_))
            M.append(k)

        # Candidate queries: those that can use at least one MV
        cand_i = []
        for i in range(len(M)):
            if len(M[i]) != 0:
                cand_i.append(i)

        # Candidate subqueries: all initially feasible ones
        cand_j = []
        for j in range(len(z_j)):
            if z_j[j] == 1:
                cand_j.append(j)

        return cand_i, cand_j

    def optimize(self, **kwargs) -> OptimizationResult:
        """Execute the normal ILP optimization algorithm.

        This implements the standard ILP formulation for materialized view
        selection without any special preprocessing or heuristics.

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()

        # Initialize candidates
        cand_i, cand_j = self.initialize_candidates()

        # Build ILP model
        y, z = self.build_ilp_model(cand_i, cand_j)

        # Add constraints
        self.add_common_constraints(y, z, cand_i, cand_j)

        # Set objective
        self.set_objective(y, z, cand_i, cand_j)

        # Solve
        y_ij, z_j, obj_val = self.solve_ilp(y, z)

        execution_time = time.time() - start_time

        # Calculate storage used
        B_cur = self.calculate_storage_used(z_j)

        # Get materialized view list
        mat_list = [j for j in range(len(z_j)) if z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)

        # Create result
        result = self.create_result(
            y_ij=y_ij,
            z_j=z_j,
            obj_val=obj_val,
            execution_time=execution_time,
            storage_used=B_cur,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
        )

        return result
