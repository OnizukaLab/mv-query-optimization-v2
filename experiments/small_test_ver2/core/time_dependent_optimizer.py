"""Time-dependent ILP optimizer with migration costs.

This module implements the time-dependent materialized view selection
algorithm that considers migration costs between timesteps.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Tuple

import gurobipy as gp

logger = logging.getLogger(__name__)


class TimeDependentOptimizer:
    """
    Time-dependent ILP optimization with migration costs.

    This optimizer handles workload changes over time and considers
    the cost of creating/migrating materialized views between timesteps.

    Objective (minimize):
        - Workload cost: -(benefit) weighted by query frequency
        - Migration cost: Cost of creating MVs (fixed full-build cost)

    Constraints:
        - Usage implies materialization
        - Storage budget per timestep
        - At most one MV per query
        - Inclusion/overlap exclusion
        - Creation flags (c[j,t] = 1 if MV is created at t)
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
        gurobi_output: int = 0,
        migration_cost_weight: float = 1.0,  # マイグレーションコストの重み係数（0.1 = 1/10に削減）
    ) -> None:
        """
        Initialize the time-dependent optimizer.

        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J] (benefit of query i using MV j)
            X: Inclusion matrix [J][J] (1 if j includes u)
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            timesteps: List of timestep names (e.g., ["morning", "evening"])
            migration_cost: Fixed migration cost for each MV {j: cost}
            query_frequency_by_timestep: Query frequencies for each timestep
                {timestep_name: [freq_i, ...]}
            gurobi_output: Gurobi log level (0=off, 1=on)
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.timesteps = timesteps
        self.migration_cost = migration_cost
        self.freq = query_frequency_by_timestep

        self.I = len(self.u_ij)  # Number of queries
        self.J = len(self.node_list)  # Number of MV candidates
        self.T = len(self.timesteps)  # Number of timesteps

        # Initialize candidate filtering
        self.cand_j = self.initialize_candidates()

        # Sparse utility index on candidates:
        # y[i,j,t] is created only when u_ij[i][j] > 0 and j in cand_j.
        self.pos_js_by_i: Dict[int, List[int]] = {}
        self.pos_is_by_j: Dict[int, List[int]] = {}
        self._build_sparse_utility_index()

        self.model: gp.Model | None = None
        self.y: Dict[tuple, gp.Var] = {}  # y[i,j,t]: query i uses MV j at time t
        self.z: Dict[tuple, gp.Var] = {}  # z[j,t]: MV j exists at time t
        self.c: Dict[tuple, gp.Var] = {}  # c[j,t]: MV j is created at time t
        # self.a removed (no recipe selection)

        self.gurobi_output = gurobi_output
        self.migration_cost_weight = migration_cost_weight

        logger.info(f"Initialized TimeDependentOptimizer: I={self.I}, J={self.J}, T={self.T}")
        logger.info(f"Filtered to {len(self.cand_j)} candidates (from {self.J} total nodes)")
        logger.info(f"Migration cost weight: {self.migration_cost_weight}")

    def _build_sparse_utility_index(self) -> None:
        """Build sparse index for positive-utility (i, j) pairs on candidates."""
        self.pos_js_by_i = {i: [] for i in range(self.I)}
        self.pos_is_by_j = {j: [] for j in self.cand_j}

        for i in range(self.I):
            for j in self.cand_j:
                if self.u_ij[i][j] > 0:
                    self.pos_js_by_i[i].append(j)
                    self.pos_is_by_j[j].append(i)

    def set_candidates(self, candidates: List[int]) -> None:
        """Replace candidate set and rebuild sparse utility indexes.

        This must be called whenever cand_j is changed after initialization.
        """
        unique_sorted = sorted(set(candidates))
        self.cand_j = [j for j in unique_sorted if 0 <= j < self.J]
        self._build_sparse_utility_index()

    def _get_y(self, i: int, j: int, t: int):
        """Return y variable if exists, otherwise 0 (sparse y)."""
        return self.y.get((i, j, t), 0)

    def initialize_candidates(self) -> list[int]:
        """Initialize MV candidates based on utility.
        
        Returns only nodes that have positive utility (u_ij > 0) for at least
        one query. This reduces the ILP problem size by excluding nodes that
        cannot provide any benefit.
        
        Returns:
            List of candidate node indices (nodes with u_ij > 0 for some query i)
        """
        candidates = set()
        for i in range(self.I):
            for j in range(self.J):
                if self.u_ij[i][j] > 0:
                    candidates.add(j)
        return sorted(list(candidates))

    def build_variables(self) -> None:
        """Create all Gurobi variables."""
        m = self.model
        assert m is not None

        logger.info("Building variables...")

        for t in range(self.T):
            for j in self.cand_j:  # Only create variables for candidates
                self.z[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}_{t}")
                # c is a derived creation flag; relaxation to continuous is exact under current constraints.
                self.c[j, t] = m.addVar(vtype=gp.GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"c_{j}_{t}")

            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):  # Sparse y: only positive-utility pairs
                    self.y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")

        m.update()
        logger.info(f"Created {len(self.y) + len(self.z) + len(self.c)} variables")

    def add_usage_and_storage_constraints(self) -> None:
        """Add constraints for MV usage, storage budget, and overlap exclusion."""
        m = self.model
        assert m is not None

        logger.info("Adding usage and storage constraints...")
        constraint_count = 0

        for t in range(self.T):
            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):
                    # Usage implies materialization
                    m.addConstr(
                        self._get_y(i, j, t) <= self.z[j, t],
                        name=f"use_le_mat_{i}_{j}_{t}"
                    )
                    constraint_count += 1

                    # Inclusion/overlap exclusion
                    # Note: Normalization by len(cand_j) matches NormalOptimizer behavior
                    m.addConstr(
                        self._get_y(i, j, t)
                        + gp.quicksum(
                            self._get_y(i, u, t) * self.X[j][u]
                            for u in self.pos_js_by_i.get(i, [])
                            if u != j and self.X[j][u] != 0
                        )
                        / max(1, len(self.cand_j))
                        <= 1,
                        name=f"inclusive_excl_{i}_{j}_{t}",
                    )
                    constraint_count += 1

            # Storage budget constraint
            m.addConstr(
                gp.quicksum(self.b_j[j] * self.z[j, t] for j in self.cand_j) <= self.B_max,
                name=f"storage_{t}",
            )
            constraint_count += 1

        logger.info(f"Added {constraint_count} usage/storage constraints")

    def add_creation_and_recipe_constraints(self) -> None:
        """Add constraints for MV creation flags."""
        m = self.model
        assert m is not None

        logger.info("Adding creation constraints...")
        constraint_count = 0

        for t in range(self.T):
            for j in self.cand_j:  # Only iterate over candidates
                # Creation flag definition
                if t == 0:
                    # Initial timestep: c[j,0] = z[j,0]
                    m.addConstr(self.c[j, 0] == self.z[j, 0], name=f"create_init_{j}")
                    constraint_count += 1
                else:
                    # Subsequent timesteps: c[j,t] >= z[j,t] - z[j,t-1]
                    m.addConstr(
                        self.c[j, t] >= self.z[j, t] - self.z[j, t - 1],
                        name=f"create_lb_{j}_{t}"
                    )
                    # c[j,t] <= z[j,t]
                    m.addConstr(
                        self.c[j, t] <= self.z[j, t],
                        name=f"create_ub_{j}_{t}"
                    )
                    # c[j,t] <= 1 - z[j,t-1] (if it existed before, not created now)
                    m.addConstr(
                        self.c[j, t] <= 1 - self.z[j, t-1],
                        name=f"create_not_cont_{j}_{t}"
                    )
                    constraint_count += 3

        logger.info(f"Added {constraint_count} creation constraints")

    def build_objective(self) -> None:
        """Build the objective function (minimize workload + migration cost)."""
        m = self.model
        assert m is not None

        logger.info("Building objective function...")

        # Workload cost: -(benefit) weighted by query frequency
        workload_cost = gp.quicksum(
            -float(self.u_ij[i][j]) * float(self.freq[self.timesteps[t]][i]) * self._get_y(i, j, t)
            for t in range(self.T)
            for i in range(self.I)
            for j in self.pos_js_by_i.get(i, [])
        )

        # Migration cost: sum of fixed costs when creating MVs
        # Apply weight to reduce the impact of migration cost (default 0.1 = 1/10)
        migration_cost = gp.quicksum(
            float(self.migration_cost.get(j, 0.0)) * self.migration_cost_weight * self.c[j, t]
            for t in range(self.T)
            for j in self.cand_j  # Only sum over candidates
        )

        m.setObjective(workload_cost + migration_cost, gp.GRB.MINIMIZE)
        logger.info(f"Objective function built (migration_cost_weight={self.migration_cost_weight})")

    def optimize(self, time_limit: float | None = None) -> dict:
        """
        Run the optimization and return results.

        Args:
            time_limit: Optional time limit in seconds for Gurobi

        Returns:
            Dictionary containing:
                - timesteps: List of timestep names
                - node_list: List of node IDs
                - z_by_timestep: List of z values for each timestep
                - y_by_timestep: List of y values for each timestep
                - objective: Total objective value
                - workload_cost: Workload component of objective
                - migration_cost: Migration component of objective
                - solve_time_sec: Time taken to solve
        """
        logger.info("Starting optimization...")

        self.model = gp.Model("TD-MV")
        try:
            self.model.Params.OutputFlag = self.gurobi_output
            if time_limit is not None:
                self.model.Params.TimeLimit = time_limit

            # Build model
            self.build_variables()
            self.add_usage_and_storage_constraints()
            self.add_creation_and_recipe_constraints()
            self.build_objective()

            # Solve
            t0 = time.time()
            self.model.optimize()
            elapsed = time.time() - t0

            logger.info(f"Optimization completed in {elapsed:.2f} seconds")

            # Check status
            if self.model.status != gp.GRB.OPTIMAL:
                logger.error(f"Optimization failed with status {self.model.status}")
                if self.model.status == gp.GRB.INFEASIBLE:
                    logger.error("Model is infeasible, computing IIS...")
                    self.model.computeIIS()
                    iis_file = "model_infeasible.ilp"
                    self.model.write(iis_file)
                    logger.error(f"IIS written to {iis_file}")
                raise RuntimeError(f"Gurobi optimization failed with status: {self.model.status}")

            # Extract solution
            # Initialize full arrays with zeros for all nodes
            z_by_t = [[0] * self.J for _ in range(self.T)]
            y_by_t = [[[0] * self.J for _ in range(self.I)] for _ in range(self.T)]
            
            # Fill in candidate values
            for t in range(self.T):
                for j in self.cand_j:
                    z_by_t[t][j] = int(round(self.z[j, t].X))
                for i in range(self.I):
                    for j in self.pos_js_by_i.get(i, []):
                        y_by_t[t][i][j] = int(round(self.y[i, j, t].X))
            
            obj = float(self.model.objVal)

            # Calculate objective breakdown
            workload_val = float(
                gp.quicksum(
                    -float(self.u_ij[i][j]) * float(self.freq[self.timesteps[t]][i]) * self._get_y(i, j, t)
                    for t in range(self.T)
                    for i in range(self.I)
                    for j in self.pos_js_by_i.get(i, [])
                ).getValue()
            )
            migration_val = float(
                gp.quicksum(
                    float(self.migration_cost.get(j, 0.0)) * self.c[j, t]
                    for t in range(self.T)
                    for j in self.cand_j  # Only sum over candidates
                ).getValue()
            )

            logger.info(f"Objective: {obj:.4f} (Workload: {workload_val:.4f}, Migration: {migration_val:.4f})")

            # Log selected MVs per timestep
            for t, ts_name in enumerate(self.timesteps):
                selected = [self.node_list[j] for j in range(self.J) if z_by_t[t][j] == 1]
                logger.info(f"Timestep {ts_name}: {len(selected)} MVs selected: {selected}")

            return {
                "timesteps": self.timesteps,
                "node_list": self.node_list,
                "z_by_timestep": z_by_t,
                "y_by_timestep": y_by_t,
                "objective": obj,
                "workload_cost": workload_val,
                "migration_cost": migration_val,
                "solve_time_sec": elapsed,
            }
        finally:
            self.model.dispose()
            self.model = None
