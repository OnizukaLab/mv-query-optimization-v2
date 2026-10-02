"""BigSubs ILP optimization algorithm.

This module implements the BigSubs algorithm which uses randomized
initialization and iterative refinement with local ILP solving.
"""

import logging
import random
import time

import gurobipy as gp

logger = logging.getLogger(__name__)

from ..core.models import OptimizationResult
from .base import BaseILPOptimizer


class BigSubsOptimizer(BaseILPOptimizer):
    """BigSubs optimization with randomized search and local ILP.

    This algorithm uses:
    1. Random initialization of MV candidates
    2. Iterative refinement based on flip probabilities
    3. Local ILP solving for each query's edge labeling
    """

    def __init__(self, *args, **kwargs):
        """Initialize BigSubs optimizer.

        Args:
            *args: Positional arguments for BaseILPOptimizer
            **kwargs: Keyword arguments for BaseILPOptimizer
        """
        # Extract BigSubs-specific parameters before calling super().__init__
        self.U_j_max = kwargs.pop("U_j_max", None)
        self.U_max = kwargs.pop("U_max", 0.0)
        self.y_ij_init = kwargs.pop("y_ij", None)

        # Call parent constructor with remaining kwargs
        super().__init__(*args, **kwargs)

        # Set defaults if not provided
        if self.U_j_max is None:
            self.U_j_max = [0] * self.s_num
        if self.y_ij_init is None:
            self.y_ij_init = [[0] * self.s_num for _ in range(len(self.u_ij))]

    def initialize_random(self, mv_list: list[int]) -> list[int]:
        """Create initial MV selection ensuring coverage of all queries.

        For each query, selects the node with the highest utility.
        This ensures that each query has at least one candidate node in the initial selection.

        Args:
            mv_list: Initial list (all zeros)

        Returns:
            MV selection with at least one beneficial node per query
        """
        num_queries = len(self.u_ij)
        selected_nodes = set()
        
        # For each query, find the best node (highest utility for that query)
        for i in range(num_queries):
            best_j = None
            best_net = float('-inf')

            for j in range(len(mv_list)):
                if self.u_ij[i][j] > 0:
                    net = self.u_ij[i][j]
                    if net > best_net:
                        best_net = net
                        best_j = j

            if best_j is not None and best_net > 0:
                selected_nodes.add(best_j)

        # If no nodes selected (unlikely), fallback to nodes with positive utility
        if not selected_nodes:
            beneficial_nodes = []
            for j in range(len(mv_list)):
                total_utility = sum(self.u_ij[i][j] for i in range(num_queries))
                if total_utility > 0:
                    beneficial_nodes.append(j)

            if beneficial_nodes:
                k = min(100, len(beneficial_nodes))
                selected_nodes = set(random.sample(beneficial_nodes, k))
        
        # Set selected nodes
        for j in selected_nodes:
            mv_list[j] = 1
        
        return mv_list

    def flip_probability(
        self,
        iter_num: int,
        z_j: int,
        b_j: int,
        B_cur: float,
        U_cur: float,
        U_j_cur: float,
        U_j_max: float,
        U_max: float,
        B_max: float,
    ) -> float:
        """Calculate probability of flipping a node's materialization status.

        Args:
            iter_num: Current iteration number
            z_j: Current materialization status
            b_j: Size of node j
            B_cur: Current storage used
            U_cur: Current total utility
            U_j_cur: Current utility of node j
            U_j_max: Maximum possible utility of node j
            U_max: Maximum possible total utility
            B_max: Storage budget

        Returns:
            Flip probability between 0 and 1
        """
        p = 160  # Iteration threshold

        # Capacity component
        if B_cur < B_max:
            p_j_capacity = 1 - (B_cur / B_max)
        else:
            p_j_capacity = 1 - (B_max / B_cur)

        # Utility component
        if z_j == 1:
            # If currently materialized, consider removing
            if U_cur > 0:
                p_j_utility = 1 - (U_j_cur / U_cur)
            else:
                p_j_utility = 0
        elif iter_num <= p or B_cur <= B_max - b_j:
            # If not materialized, consider adding
            if U_max > 0 and B_max > 0:
                utility_density_j = U_j_max / b_j if b_j > 0 else 0
                avg_utility_density = U_max / B_max
                p_j_utility = (
                    utility_density_j / avg_utility_density if avg_utility_density > 0 else 0
                )
            else:
                p_j_utility = 0
        else:
            p_j_utility = 0

        return p_j_capacity * p_j_utility

    def do_flip(self, probability: float, current_z: int) -> int:
        """Decide whether to flip based on probability.

        Args:
            probability: Flip probability
            current_z: Current status (0 or 1)

        Returns:
            New status (0 or 1)
        """
        t = random.random()
        if probability > t:
            return 1 - current_z  # Flip
        else:
            return current_z  # Keep

    def local_ilp(self, u_ij_row: list[float], k: list[int]) -> list[int]:
        """Solve local ILP for a single query.

        Args:
            u_ij_row: Utility values for one query
            k: Candidate MV indices for this query

        Returns:
            Binary selection of MVs for this query
        """
        if not k:
            return [0] * len(self.b_j)

        # Build local model - only for candidate nodes k (not all nodes!)
        model = gp.Model("local_ilp")
        model.Params.OutputFlag = 0

        # Variables - only create for candidate nodes k
        y = {}
        for j in k:
            y[j] = model.addVar(vtype=gp.GRB.BINARY, name=f"y_{j}")

        model.update()

        # Objective: maximize utility only (m_cost is not included — BIGSUBS optimizes query
        # execution time without maintenance cost; update cost is evaluated separately)
        model.setObjective(
            gp.quicksum(u_ij_row[j] * y[j] for j in k), gp.GRB.MAXIMIZE
        )

        # Constraints: overlapping subexpression
        for i in k:
            k_minus = [s for s in k if s != i]
            if k_minus:
                model.addConstr(
                    y[i] + gp.quicksum(y[j] * self.X[i][j] for j in k_minus) / len(k) <= 1
                )

        model.optimize()

        # Extract solution - return full array with 0s except for k
        y_opt = [0] * len(self.b_j)
        for j in k:
            if y[j].X > 0.5:  # Binary threshold
                y_opt[j] = 1

        return y_opt

    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates (not used in BigSubs).

        BigSubs uses its own initialization through the optimize method.

        Returns:
            Empty lists (not used)
        """
        return [], []

    def optimize(self, iter_max: int = 50, **kwargs) -> OptimizationResult:
        """Execute the BigSubs optimization algorithm.

        Args:
            iter_max: Maximum number of iterations
            **kwargs: Additional arguments

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        import logging
        logger = logging.getLogger(__name__)
        
        start_time = time.time()
        num_queries = len(self.q_s_list)
        num_nodes = self.s_num

        # Initialize convergence tracking
        self._convergence_history = []

        logger.info(f"BigSubs optimization starting...")
        logger.info(f"  - Queries: {num_queries}")
        logger.info(f"  - Candidate nodes: {num_nodes}")
        logger.info(f"  - Max iterations: {iter_max}")
        logger.info(f"  - Storage budget: {self.B_max / (1024*1024):.2f} MB")

        # Initialize random MV selection
        z_j = [0] * self.s_num
        z_j = self.initialize_random(z_j)
        initial_selected = sum(z_j)
        logger.info(f"  - Initial MVs selected: {initial_selected}")

        # Calculate initial storage
        B_cur = sum(z_j[j] * self.b_j[j] for j in range(len(z_j)))

        # Iteration variables
        iter_num = 0
        U_cur = 1.0
        U_j_cur = [0.0] * len(z_j)
        best_u = 0.0
        best_b = 0.0
        best_y_ij = self.y_ij_init
        best_z_j = z_j.copy()
        no_improve_count = 0
        NO_IMPROVE_LIMIT = 10  # 10 回連続改善なしで収束とみなす

        y_ij = [list(row) for row in self.y_ij_init]

        # Iterative refinement
        while no_improve_count < NO_IMPROVE_LIMIT and iter_num < iter_max:
            iter_start = time.time()
            updated = 0

            # Vertex labeling: decide which nodes to materialize
            logger.info(f"[Iteration {iter_num + 1}/{iter_max}] Vertex labeling...")
            flips = 0
            for j in range(len(z_j)):
                p_flip = self.flip_probability(
                    iter_num,
                    z_j[j],
                    self.b_j[j],
                    B_cur,
                    U_cur,
                    U_j_cur[j],
                    self.U_j_max[j],
                    self.U_max,
                    self.B_max,
                )
                z_j_new = self.do_flip(p_flip, z_j[j])

                if z_j_new != z_j[j]:
                    flips += 1
                    if z_j_new == 0:
                        B_cur -= self.b_j[j]
                    else:
                        B_cur += self.b_j[j]

                z_j[j] = z_j_new

            current_mvs = sum(z_j)
            logger.info(f"  - Flips: {flips}, Current MVs: {current_mvs}, Storage: {B_cur / (1024*1024):.2f} MB")

            # Edge labeling: assign MVs to queries
            logger.info(f"[Iteration {iter_num + 1}/{iter_max}] Edge labeling ({num_queries} queries)...")
            U_cur = 0.0
            U_j_cur = [0.0] * len(z_j)
            z_j_new = [0] * len(z_j)

            for i in range(len(self.q_s_list)):
                # Progress every 500 queries
                if (i + 1) % 500 == 0 or i == 0:
                    logger.info(f"    Processing query {i + 1}/{num_queries}...")
                
                # Find candidates for this query
                M_i = [j for j in range(len(z_j)) if self.u_ij[i][j] > 0]
                M_i_ = [j for j in range(len(z_j)) if z_j[j] > 0]
                k = list(set(M_i) & set(M_i_))

                # Solve local ILP for this query
                y_ij[i] = self.local_ilp(self.u_ij[i], k)

                # Update utilities (only utility, not maintenance cost here)
                for j in k:
                    if y_ij[i][j] == 1:
                        U_cur += self.u_ij[i][j]
                        z_j_new[j] = 1
                    U_j_cur[j] += self.u_ij[i][j] * y_ij[i][j]

            # Update z_j (maintenance cost not deducted — BIGSUBS tracks pure utility)
            for j in range(len(z_j)):
                z_j[j] = z_j_new[j]

            # B_cur を z_j に合わせて正しく再計算する
            # Edge Labelingで使われなかったMVが削除されるため、B_curも更新が必要
            B_cur = sum(z_j[j] * self.b_j[j] for j in range(len(z_j)))

            iter_num += 1
            iter_time = time.time() - iter_start

            # Track convergence history
            storage_percent = (B_cur / self.B_max * 100) if self.B_max > 0 else 0
            mv_count = sum(z_j)
            is_best = U_cur > best_u and B_cur <= self.B_max

            self._convergence_history.append({
                'iteration': iter_num,
                'utility': U_cur,
                'storage': B_cur,
                'storage_percent': storage_percent,
                'mv_count': mv_count,
                'is_best': is_best
            })

            # Log progress (every 10 iterations or when best is updated)
            if iter_num <= 5 or iter_num % 10 == 0 or is_best:
                best_mark = "*" if is_best else ""
                logger.info(f"{iter_num:>5} | {U_cur:>12.2f} | {storage_percent:>9.2f}% | {mv_count:>6} | {best_mark:>5}")

            # Track best solution (容量制約を満たしている場合のみベストを更新)
            if U_cur > best_u and B_cur <= self.B_max:
                best_u = U_cur
                best_b = B_cur
                best_y_ij = [list(row) for row in y_ij]
                best_z_j = z_j.copy()
                no_improve_count = 0
                logger.info(f"  ★ New best! Utility: {best_u:,.2f}, Storage: {best_b / (1024*1024):.2f} MB")
            else:
                no_improve_count += 1
            
            logger.info(f"  - Iteration {iter_num} completed in {iter_time:.2f}s, Utility: {U_cur:,.2f}")

        execution_time = time.time() - start_time
        logger.info(f"BigSubs completed in {execution_time:.2f}s after {iter_num} iterations")

        # Log summary
        best_iterations = [h['iteration'] for h in self._convergence_history if h['is_best']]
        last_best_iter = max(best_iterations) if best_iterations else 0
        
        logger.info("-"*60)
        logger.info(f"{'Finished':>5} | 総イテレーション: {iter_num}, 最終ベスト更新: iter {last_best_iter}")
        logger.info(f"{'Result':>5} | Utility: {best_u:.2f}, Storage: {best_b/1024/1024:.2f}MB ({best_b/self.B_max*100:.2f}%)")
        logger.info(f"{'':>5} | 選択MV数: {sum(best_z_j)}, 実行時間: {execution_time:.2f}秒")
        logger.info("="*60)

        # Get materialized view list
        mat_list = [j for j in range(len(best_z_j)) if best_z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)
        logger.info(f"  - Final MVs selected: {len(mat_list)}")
        logger.info(f"  - Final utility: {best_u:,.2f}")
        logger.info(f"  - Final storage: {best_b / (1024*1024):.2f} MB")

        # Create result with convergence summary
        convergence_summary = {
            'total_iterations': iter_num,
            'best_iterations': best_iterations,
            'last_best_iteration': last_best_iter,
            'recommended_iter_max': last_best_iter + 20 if last_best_iter > 0 else iter_max,
        }
        
        result = self.create_result(
            y_ij=best_y_ij,
            z_j=best_z_j,
            obj_val=best_u,
            execution_time=execution_time,
            storage_used=best_b,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            iterations=iter_num,
            convergence_summary=convergence_summary,
        )

        return result
