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
        - Migration cost: Cost of creating MVs using recipes

    Constraints:
        - Usage implies materialization
        - Storage budget per timestep
        - At most one MV per query
        - Inclusion/overlap exclusion
        - Creation flags and recipe selection
        - Recipe dependencies (MVs must exist in previous timestep)
    """

    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        timesteps: List[str],
        migration_recipes: Dict[int, List[Tuple[Tuple[int, ...], float]]],
        query_frequency_by_timestep: Dict[str, List[float]],
        gurobi_output: int = 0,
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
            migration_recipes: Recipe costs for each MV
                {j: [(recipe_tuple, cost), ...]}
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
        self.recipes = migration_recipes
        self.freq = query_frequency_by_timestep

        self.I = len(self.u_ij)  # Number of queries
        self.J = len(self.node_list)  # Number of MV candidates
        self.T = len(self.timesteps)  # Number of timesteps

        # Initialize candidate filtering
        self.cand_j = self.initialize_candidates()

        self.model: gp.Model | None = None
        self.y: Dict[tuple, gp.Var] = {}  # y[i,j,t]: query i uses MV j at time t
        self.z: Dict[tuple, gp.Var] = {}  # z[j,t]: MV j exists at time t
        self.c: Dict[tuple, gp.Var] = {}  # c[j,t]: MV j is created at time t
        self.a: Dict[tuple, gp.Var] = {}  # a[j,t,k]: recipe k is used for MV j at time t

        self.gurobi_output = gurobi_output

        logger.info(f"Initialized TimeDependentOptimizer: I={self.I}, J={self.J}, T={self.T}")
        logger.info(f"Filtered to {len(self.cand_j)} candidates (from {self.J} total nodes)")

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
                self.c[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"c_{j}_{t}")

                # Recipe variables
                recs = self.recipes.get(j, [(tuple(), 0.0)])
                for k_idx, (_recipe, _cost) in enumerate(recs):
                    self.a[j, t, k_idx] = m.addVar(vtype=gp.GRB.BINARY, name=f"a_{j}_{t}_{k_idx}")

            for i in range(self.I):
                for j in self.cand_j:  # Only create variables for candidates
                    self.y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")

        m.update()
        logger.info(f"Created {len(self.y) + len(self.z) + len(self.c) + len(self.a)} variables")

    def add_usage_and_storage_constraints(self) -> None:
        """Add constraints for MV usage, storage budget, and overlap exclusion."""
        m = self.model
        assert m is not None

        logger.info("Adding usage and storage constraints...")
        constraint_count = 0

        for t in range(self.T):
            # At most one MV per query
            #for i in range(self.I): # いらない
            #    m.addConstr(
            #        gp.quicksum(self.y[i, j, t] for j in self.cand_j) <= 1,
            #        name=f"at_most_one_mv_{i}_{t}",
            #    )
            #    constraint_count += 1

            for i in range(self.I):
                for j in self.cand_j:  # Only iterate over candidates
                    # Usage implies materialization
                    m.addConstr(
                        self.y[i, j, t] <= self.z[j, t],
                        name=f"use_le_mat_{i}_{j}_{t}"
                    )
                    constraint_count += 1

                    # Inclusion/overlap exclusion
                    
                    m.addConstr(
                        self.y[i, j, t] + gp.quicksum(self.y[i, u, t] * self.X[j][u] for u in self.cand_j if u != j) <= 1,
                        # / self.J <= 1 この割り算なくてもよさそう
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
        """Add constraints for MV creation flags and recipe selection."""
        m = self.model
        assert m is not None

        logger.info("Adding creation and recipe constraints...")
        constraint_count = 0

        for t in range(self.T):
            for j in self.cand_j:  # Only iterate over candidates
                # Creation flag definition
                if t == 0:
                    # Initial timestep: c[j,0] = z[j,0]
                    m.addConstr(self.c[j, 0] == self.z[j, 0], name=f"create_init_{j}")
                    constraint_count += 1
                else:
                    # Subsequent timesteps: c[j,t] >= z[j,t] - z[j,t-1], c[j,t] <= z[j,t]
                    m.addConstr(
                        self.c[j, t] >= self.z[j, t] - self.z[j, t - 1],
                        name=f"create_lb_{j}_{t}"
                    )
                    m.addConstr(
                        self.c[j, t] <= self.z[j, t],
                        name=f"create_ub_{j}_{t}"
                    )
                    m.addConstr(
                        self.c[j, t] <= 1 - self.z[j, t-1],
                        name = f"create_not_cont_{j}_{t}"
                    ) # 追加の制約
                    constraint_count += 3

                # Recipe selection: exactly one recipe when creating
                recs = self.recipes.get(j, [(tuple(), 0.0)])
                m.addConstr(
                    gp.quicksum(self.a[j, t, k_idx] for k_idx in range(len(recs))) == self.c[j, t],
                    name=f"recipe_select_{j}_{t}",
                )
                constraint_count += 1

                # Recipe dependency constraints
                for k_idx, (recipe, _cost) in enumerate(recs):

                    # 追加の制約 a_j_t_k <= c_j_t おそらく冗長
                    #m.addConstr(
                    #    self.a[j, t, k_idx] <= self.c[j,t],
                    #    name = f"recipe_enable_{j}_{t}_{k_idx}"
                    #)
                    #constraint_count += 1

                    if t == 0:
                        # At t=0, only empty recipe is allowed (no dependencies available)
                        if len(recipe) > 0:
                            m.addConstr(
                                self.a[j, t, k_idx] == 0,
                                name=f"no_dep_at_t0_{j}_{k_idx}"
                            )
                            constraint_count += 1
                    else:
                        # At t>0, recipe dependencies must exist in previous timestep
                        for dep in recipe:
                            m.addConstr(
                                self.a[j, t, k_idx] <= self.z[dep, t - 1],
                                name=f"dep_{j}_{t}_{k_idx}_{dep}"
                            )
                            constraint_count += 1

        logger.info(f"Added {constraint_count} creation/recipe constraints")

    def build_objective(self) -> None:
        """Build the objective function (minimize workload + migration cost)."""
        m = self.model
        assert m is not None

        logger.info("Building objective function...")

        # Workload cost: -(benefit) weighted by query frequency
        workload_cost = gp.quicksum(
            -float(self.u_ij[i][j]) * float(self.freq[self.timesteps[t]][i]) * self.y[i, j, t]
            for t in range(self.T)
            for i in range(self.I)
            for j in self.cand_j  # Only sum over candidates
        )

        # Migration cost: sum of recipe costs when creating MVs
        migration_cost = gp.quicksum(
            float(self.recipes.get(j, [(tuple(), 0.0)])[k_idx][1]) * self.a[j, t, k_idx]
            for t in range(self.T)
            for j in self.cand_j  # Only sum over candidates
            for k_idx in range(len(self.recipes.get(j, [(tuple(), 0.0)])))
        )

        m.setObjective(workload_cost + migration_cost, gp.GRB.MINIMIZE)
        logger.info("Objective function built")

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
                        y_by_t[t][i][j] = int(round(self.y[i, j, t].X))
            
            obj = float(self.model.objVal)

            # Calculate objective breakdown
            workload_val = float(
                gp.quicksum(
                    -float(self.u_ij[i][j]) * float(self.freq[self.timesteps[t]][i]) * self.y[i, j, t]
                    for t in range(self.T)
                    for i in range(self.I)
                    for j in self.cand_j  # Only sum over candidates
                ).getValue()
            )
            migration_val = float(
                gp.quicksum(
                    float(self.recipes.get(j, [(tuple(), 0.0)])[k_idx][1]) * self.a[j, t, k_idx]
                    for t in range(self.T)
                    for j in self.cand_j  # Only sum over candidates
                    for k_idx in range(len(self.recipes.get(j, [(tuple(), 0.0)])))
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
