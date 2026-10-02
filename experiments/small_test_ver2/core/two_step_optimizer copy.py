"""Two-step ILP optimizer with fixed MV support.

This module implements a 2-timestep ILP optimizer for adaptive MV selection.
It allows fixing the MVs at the first timestep and optimizing the second timestep.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Optional

import gurobipy as gp

logger = logging.getLogger(__name__)


class TwoStepOptimizer:
    """
    Two-step ILP optimization with fixed MV support.

    This optimizer is designed for adaptive/sliding window optimization:
    - Timestep 0 (prev): MVs can be fixed to current configuration
    - Timestep 1 (curr): MVs are optimized based on current workload

    Objective (minimize):
        - Workload cost: -(benefit) weighted by query frequency
        - Migration cost: Cost of creating new MVs at timestep 1
    """

    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        prev_freq: List[float],
        curr_freq: List[float],
        migration_cost: Dict[int, float],
        fixed_mvs: Optional[Set[int]] = None,
        gurobi_output: int = 0,
        migration_cost_weight: float = 1.0,
    ) -> None:
        """
        Initialize the two-step optimizer.

        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J]
            X: Inclusion matrix [J][J]
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            prev_freq: Query frequencies for previous timestep
            curr_freq: Query frequencies for current timestep
            migration_cost: Fixed migration cost for each MV {j: cost}
            fixed_mvs: Set of MV indices that must be materialized at t=0
                       If None, t=0 is also optimized
            gurobi_output: Gurobi log level (0=off, 1=on)
            migration_cost_weight: Weight for migration cost in objective
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.prev_freq = prev_freq
        self.curr_freq = curr_freq
        self.migration_cost = migration_cost
        self.fixed_mvs = fixed_mvs or set()
        self.gurobi_output = gurobi_output
        self.migration_cost_weight = migration_cost_weight

        self.I = len(self.u_ij)  # Number of queries
        self.J = len(self.node_list)  # Number of MV candidates

        # Filter candidates with positive utility
        self.cand_j = self._initialize_candidates()

        self.model: gp.Model | None = None
        self.y: Dict[tuple, gp.Var] = {}  # y[i,j,t]: query i uses MV j at time t
        self.z: Dict[tuple, gp.Var] = {}  # z[j,t]: MV j exists at time t
        self.c: Dict[tuple, gp.Var] = {}  # c[j,t]: MV j is created at time t

        logger.debug(f"TwoStepOptimizer: I={self.I}, J={self.J}, candidates={len(self.cand_j)}")
        logger.debug(f"Fixed MVs at t=0: {len(self.fixed_mvs)}")

    def _initialize_candidates(self) -> List[int]:
        """Filter candidates with positive utility."""
        candidates = []
        for j in range(self.J):
            has_utility = any(self.u_ij[i][j] > 0 for i in range(self.I))
            # Also include MVs that are fixed (even if no utility)
            if has_utility or j in self.fixed_mvs:
                candidates.append(j)
        return candidates

    def _build_model(self) -> None:
        """Build the Gurobi model."""
        self.model = gp.Model("TwoStepMV")
        self.model.setParam("OutputFlag", self.gurobi_output)
        m = self.model

        # Variables for both timesteps (t=0: prev, t=1: curr)
        for t in [0, 1]:
            for i in range(self.I):
                for j in self.cand_j:
                    self.y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")

            for j in self.cand_j:
                if t == 0 and self.fixed_mvs:
                    # Fixed at t=0: set z as constant
                    self.z[j, t] = 1 if j in self.fixed_mvs else 0
                else:
                    self.z[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}_{t}")

        # Creation variables (only for t=1)
        for j in self.cand_j:
            self.c[j, 1] = m.addVar(vtype=gp.GRB.BINARY, name=f"c_{j}_1")

        m.update()

        # --- Objective ---
        workload_cost = gp.LinExpr()
        migration_cost_expr = gp.LinExpr()

        for t, freq in [(0, self.prev_freq), (1, self.curr_freq)]:
            for i in range(self.I):
                for j in self.cand_j:
                    benefit = self.u_ij[i][j] * freq[i]
                    if isinstance(self.y[i, j, t], gp.Var):
                        workload_cost -= benefit * self.y[i, j, t]
                    elif self.y[i, j, t] == 1:
                        workload_cost -= benefit

        # Migration cost at t=1
        for j in self.cand_j:
            cost = self.migration_cost.get(j, 0.0)
            if cost > 0:
                migration_cost_expr += cost * self.c[j, 1]

        m.setObjective(
            workload_cost + self.migration_cost_weight * migration_cost_expr,
            gp.GRB.MINIMIZE
        )

        # --- Constraints ---
        for t in [0, 1]:
            for i in range(self.I):
                for j in self.cand_j:
                    # y <= z (usage implies materialization)
                    z_val = self.z[j, t]
                    if isinstance(z_val, gp.Var):
                        m.addConstr(self.y[i, j, t] <= z_val)
                    elif z_val == 0:
                        m.addConstr(self.y[i, j, t] == 0)
                    # If z_val == 1, y is free (0 or 1)

        # At most one MV per query per timestep
        for t in [0, 1]:
            for i in range(self.I):
                m.addConstr(gp.quicksum(self.y[i, j, t] for j in self.cand_j) <= 1)

        # Storage constraint (only for t=1 if t=0 is fixed)
        for t in [0, 1]:
            if t == 0 and self.fixed_mvs:
                continue  # Skip - already fixed and assumed feasible
            storage_sum = gp.quicksum(
                self.b_j[j] * self.z[j, t] 
                for j in self.cand_j 
                if isinstance(self.z[j, t], gp.Var)
            )
            # Add fixed storage if t=1
            if t == 1 and self.fixed_mvs:
                # No fixed MVs at t=1, but we need total storage
                pass
            m.addConstr(storage_sum <= self.B_max)

        # Inclusion exclusion (if MV j includes MV u, and z[j]=1, then z[u]=0)
        for t in [0, 1]:
            if t == 0 and self.fixed_mvs:
                continue  # Skip - already fixed
            for j in self.cand_j:
                for u in self.cand_j:
                    if j != u and self.X[j][u] == 1:
                        z_j = self.z[j, t]
                        z_u = self.z[u, t]
                        if isinstance(z_j, gp.Var) and isinstance(z_u, gp.Var):
                            m.addConstr(z_j + z_u <= 1)
                        elif isinstance(z_j, gp.Var) and z_u == 1:
                            m.addConstr(z_j == 0)
                        elif z_j == 1 and isinstance(z_u, gp.Var):
                            m.addConstr(z_u == 0)

        # Creation flag: c[j,1] = max(0, z[j,1] - z[j,0])
        for j in self.cand_j:
            z_0 = self.z[j, 0]
            z_1 = self.z[j, 1]
            if isinstance(z_1, gp.Var):
                if isinstance(z_0, gp.Var):
                    m.addConstr(self.c[j, 1] >= z_1 - z_0)
                elif z_0 == 0:
                    m.addConstr(self.c[j, 1] >= z_1)
                else:  # z_0 == 1
                    m.addConstr(self.c[j, 1] >= z_1 - 1)
            m.addConstr(self.c[j, 1] <= 1)

    def optimize(self) -> Dict:
        """
        Run the optimization.

        Returns:
            Dictionary with:
                - selected_mvs_t0: Set of MV indices at t=0
                - selected_mvs_t1: Set of MV indices at t=1
                - objective: Objective value
                - solve_time_sec: Solve time
        """
        start_time = time.time()
        self._build_model()
        self.model.optimize()

        solve_time = time.time() - start_time

        if self.model.Status != gp.GRB.OPTIMAL:
            logger.warning(f"Optimization status: {self.model.Status}")
            # Return fixed MVs if infeasible
            return {
                "selected_mvs_t0": self.fixed_mvs,
                "selected_mvs_t1": self.fixed_mvs,
                "objective": float('inf'),
                "solve_time_sec": solve_time,
                "status": self.model.Status,
            }

        # Extract solution
        selected_t0 = set()
        selected_t1 = set()

        for j in self.cand_j:
            z_0 = self.z[j, 0]
            z_1 = self.z[j, 1]
            if isinstance(z_0, gp.Var):
                if z_0.X > 0.5:
                    selected_t0.add(j)
            elif z_0 == 1:
                selected_t0.add(j)

            if isinstance(z_1, gp.Var):
                if z_1.X > 0.5:
                    selected_t1.add(j)
            elif z_1 == 1:
                selected_t1.add(j)

        return {
            "selected_mvs_t0": selected_t0,
            "selected_mvs_t1": selected_t1,
            "objective": self.model.ObjVal,
            "solve_time_sec": solve_time,
            "status": self.model.Status,
        }
