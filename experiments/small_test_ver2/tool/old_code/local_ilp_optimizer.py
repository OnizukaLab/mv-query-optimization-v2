"""Local ILP Optimizer for 3-timestep optimization with constraints.

This module implements a specialized ILP optimizer that works with exactly 3 timesteps
(min, median, max) and supports fixed MV constraints. It is used by the CF Pruner
to solve local optimization problems at each node of the Workload Summary Tree.

Based on TimeDependentOptimizer but optimized for 3 timesteps with constraint support.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Tuple

import gurobipy as gp

logger = logging.getLogger(__name__)


class LocalILPOptimizer:
    """Local ILP optimizer for 3-timestep optimization.
    
    This optimizer is similar to TimeDependentOptimizer but:
    1. Works with exactly 3 timesteps (min, median, max)
    2. Supports fixed MV constraints (force specific MVs to be selected)
    3. Used for local optimization in Workload Summary Tree nodes
    
    The optimization problem is the same as the full time-dependent problem,
    but restricted to 3 timesteps for efficiency.
    """
    
    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        timestep_indices: List[int],  # [min_idx, median_idx, max_idx]
        all_timesteps: List[str],
        migration_recipes: Dict[int, List[Tuple[Tuple[int, ...], float]]],
        query_frequency_by_timestep: Dict[str, List[float]],
        fixed_mvs_by_timestep: Dict[int, Set[int]] = None,
        candidate_indices: List[int] = None,  # ★ 新規: 事前計算された候補
        gurobi_output: int = 0,
    ) -> None:
        """Initialize the local ILP optimizer.
        
        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J] (benefit of query i using MV j)
            X: Inclusion matrix [J][J] (1 if j includes u)
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            timestep_indices: Exactly 3 timestep indices [min, median, max]
            all_timesteps: Full list of timestep names
            migration_recipes: Recipe costs for each MV
            query_frequency_by_timestep: Query frequencies for all timesteps
            fixed_mvs_by_timestep: Optional constraints {timestep_idx: set of MV indices to fix}
            candidate_indices: Optional pre-computed candidate indices (avoids redundant filtering)
            gurobi_output: Gurobi log level (0=off, 1=on)
        """
        assert len(timestep_indices) == 3, "LocalILP requires exactly 3 timesteps"
        
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        
        # Detect unique timesteps (handle duplicates for 2-timestep nodes)
        self.timestep_indices_original = timestep_indices
        unique_indices = list(dict.fromkeys(timestep_indices))  # Preserve order, remove duplicates
        
        # Map original indices to unique indices
        # Example: [4, 4, 5] -> unique=[4, 5], map={0:0, 1:0, 2:1}
        self.timestep_map = {i: unique_indices.index(timestep_indices[i]) for i in range(3)}
        
        # Use unique timesteps for optimization
        self.timestep_indices = unique_indices
        self.timesteps = [all_timesteps[idx] for idx in unique_indices]
        
        self.recipes = migration_recipes
        self.freq = query_frequency_by_timestep
        self.fixed_mvs = fixed_mvs_by_timestep or {}
        
        self.I = len(self.u_ij)  # Number of queries
        self.J = len(self.node_list)  # Number of MV candidates
        self.T = len(unique_indices)  # 2 or 3 unique timesteps
        
        # Initialize candidate filtering
        # Use pre-computed candidates if provided, otherwise compute them
        if candidate_indices is not None:
            self.cand_j = candidate_indices
            logger.debug(f"Using pre-computed candidates: {len(self.cand_j)} candidates")
        else:
            self.cand_j = self._initialize_candidates()
            logger.debug(f"Computed candidates: {len(self.cand_j)} candidates")
        
        if self.T == 2:
            logger.debug(f"Detected 2-timestep node: {timestep_indices} -> {unique_indices}")
        
        self.model: gp.Model | None = None
        self.y: Dict[tuple, gp.Var] = {}
        self.z: Dict[tuple, gp.Var] = {}
        self.c: Dict[tuple, gp.Var] = {}
        self.a: Dict[tuple, gp.Var] = {}
        
        self.gurobi_output = gurobi_output
        
        logger.debug(
            f"LocalILP: I={self.I}, J={self.J}, T={self.T}, "
            f"timesteps={self.timesteps}, candidates={len(self.cand_j)}"
        )
    
    def _initialize_candidates(self) -> List[int]:
        """Initialize MV candidates based on utility.
        
        Returns only nodes that have positive utility for at least one query.
        """
        candidates = []
        for j in range(self.J):
            has_utility = any(self.u_ij[i][j] > 0 for i in range(self.I))
            if has_utility:
                candidates.append(j)
        return candidates
    
    def _build_variables(self) -> None:
        """Create all Gurobi variables, handling fixed MVs as constants."""
        m = self.model
        assert m is not None
        
        logger.debug("Building variables for LocalILP...")
        
        # Track counts
        var_count = 0
        fixed_count = 0
        
        # Create variables in same order as TimeDependentOptimizer
        for t in range(self.T):
            # Check if this timestep is fixed
            global_t = self.timestep_indices[t]
            is_fixed_t = global_t in self.fixed_mvs
            fixed_set = self.fixed_mvs.get(global_t, set())
            
            for j in self.cand_j:
                # Determine z[j,t]
                z_val = None
                if is_fixed_t:
                    # If fixed, z is 1 if in set, else 0
                    z_val = 1 if j in fixed_set else 0
                    self.z[j, t] = z_val
                    fixed_count += 1
                else:
                    # Variable
                    self.z[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}_{t}")
                    var_count += 1
                
                # Determine c[j,t], a[j,t,k], y[i,j,t]
                # Optimization: If z[j,t] is fixed to 0, then c, a, y must be 0
                if z_val == 0:
                    self.c[j, t] = 0
                    recipes = self.recipes.get(j, [(tuple(), 0.0)])
                    for k_idx in range(len(recipes)):
                        self.a[j, t, k_idx] = 0
                    for i in range(self.I):
                        self.y[i, j, t] = 0
                else:
                    # If z is 1 or variable, we generally need variables for c, a, y
                    # (c could be fixed if z[t-1] is known, but let's keep logic simple)
                    
                    # c[j,t]
                    self.c[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"c_{j}_{t}")
                    var_count += 1
                    
                    # a[j,t,k]
                    recipes = self.recipes.get(j, [(tuple(), 0.0)])
                    for k_idx in range(len(recipes)):
                        self.a[j, t, k_idx] = m.addVar(vtype=gp.GRB.BINARY, name=f"a_{j}_{t}_{k_idx}")
                        var_count += 1
                    
                    # y[i,j,t]
                    for i in range(self.I):
                        self.y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")
                        var_count += 1
        
        m.update()
        logger.debug(f"Created {var_count} variables (skipped {fixed_count} fixed z-vars + associated y/c/a)")

    def _add_safe_constr(self, constr, name: str) -> None:
        """Add constraint to model only if it's not trivially True."""
        # If constraint evaluates to bool (e.g. 0 <= 1), it's a constant check
        if isinstance(constr, bool):
            if not constr:
                logger.error(f"Infeasible constant constraint: {name}")
            return
        
        # Otherwise it's a Gurobi TempConstr
        self.model.addConstr(constr, name=name)

    def _add_usage_and_storage_constraints(self) -> None:
        """Add constraints for MV usage, storage budget, and overlap exclusion."""
        m = self.model
        assert m is not None
        
        logger.debug("Adding usage and storage constraints...")
        constraint_count = 0
        
        for t in range(self.T):
            for i in range(self.I):
                for j in self.cand_j:
                    # Usage implies materialization (y[i,j,t] <= z[j,t])
                    # If y=0 and z=0, 0<=0 (True). If y var and z=1, y<=1.
                    self._add_safe_constr(
                        self.y[i, j, t] <= self.z[j, t],
                        name=f"use_le_mat_{i}_{j}_{t}"
                    )
                    constraint_count += 1
                    
                    # Inclusion/overlap exclusion
                    # y[i, j, t] + sum(...) <= 1
                    lhs = self.y[i, j, t] + gp.quicksum(
                        self.y[i, u, t] * self.X[j][u] 
                        for u in self.cand_j if u != j
                    )
                    self._add_safe_constr(
                        lhs <= 1,
                        name=f"inclusive_excl_{i}_{j}_{t}"
                    )
                    constraint_count += 1
            
            # Storage budget constraint
            self._add_safe_constr(
                gp.quicksum(self.b_j[j] * self.z[j, t] for j in self.cand_j) <= self.B_max,
                name=f"storage_{t}"
            )
            constraint_count += 1
        
        logger.debug(f"Added usage/storage constraints")
    
    def _add_creation_and_recipe_constraints(self) -> None:
        """Add constraints for MV creation flags and recipe selection."""
        m = self.model
        assert m is not None
        
        logger.debug("Adding creation and recipe constraints...")
        
        for t in range(self.T):
            for j in self.cand_j:
                recipes = self.recipes.get(j, [(tuple(), 0.0)])
                
                # Exactly one recipe if created
                # sum(a) == c
                self._add_safe_constr(
                    gp.quicksum(self.a[j, t, k] for k in range(len(recipes))) == self.c[j, t],
                    name=f"one_recipe_{j}_{t}"
                )
                
                # Recipe dependencies must be satisfied
                for k_idx, (deps, _) in enumerate(recipes):
                    if t > 0:
                        if deps:
                            # If deps exist, check them
                            # sum(z_dep)
                            # Note: z[dep, t-1] might be int or Var. quicksum handles both.
                            lhs = len(deps) * self.a[j, t, k_idx]
                            rhs = gp.quicksum(self.z[dep, t-1] for dep in deps if dep in self.cand_j)
                            
                            self._add_safe_constr(
                                lhs <= rhs,
                                name=f"recipe_dep_{j}_{t}_{k_idx}"
                            )
                
                # Creation logic
                if t == 0:
                    # First timestep: created if exists
                    self._add_safe_constr(
                        self.c[j, t] == self.z[j, t],
                        name=f"create_t0_{j}"
                    )
                else:
                    # Later timesteps: created if exists now but didn't exist before
                    # c >= z[t] - z[t-1]
                    self._add_safe_constr(
                        self.c[j, t] >= self.z[j, t] - self.z[j, t-1],
                        name=f"create_after_{j}_{t}"
                    )
                    
                    # c <= z[t]
                    self._add_safe_constr(
                        self.c[j, t] <= self.z[j, t],
                        name=f"create_only_if_exist_{j}_{t}"
                    )
                    
                    # c <= 1 - z[t-1]
                    self._add_safe_constr(
                        self.c[j, t] <= 1 - self.z[j, t-1],
                        name=f"create_only_if_new_{j}_{t}"
                    )
    
    def _add_fixed_mv_constraints(self) -> None:
        """Add constraints to fix specific MVs at specific timesteps.
        
        Optimized: This is now handled in _build_variables by setting variables to constants.
        No explicit constraints needed.
        """
        pass
    
    def _build_objective(self) -> None:
        """Build the objective function (minimize workload + migration cost)."""
        # Workload cost: -sum(u_ij * freq * y_ijt)
        workload = gp.quicksum(
            -float(self.u_ij[i][j]) * float(self.freq[self.timesteps[t]][i]) * self.y[i, j, t]
            for t in range(self.T)
            for i in range(self.I)
            for j in self.cand_j
        )
        
        # Migration cost: sum(recipe_cost * a_jtk)
        migration = gp.quicksum(
            float(self.recipes.get(j, [(tuple(), 0.0)])[k_idx][1]) * self.a[j, t, k_idx]
            for t in range(self.T)
            for j in self.cand_j
            for k_idx in range(len(self.recipes.get(j, [(tuple(), 0.0)])))
        )
        
        self.model.setObjective(workload + migration, gp.GRB.MINIMIZE)
    
    def optimize(self, time_limit: float = None) -> dict:
        """Run the optimization and return results.
        
        Args:
            time_limit: Time limit in seconds (default: None = no limit)
        
        Returns:
            Dictionary containing:
                - selected_mvs_by_timestep: Dict mapping timestep index to set of selected MV indices
                - objective: Objective value
                - solve_time_sec: Solve time
        """
        logger.debug(f"Starting LocalILP optimization for timesteps {self.timesteps}")
        
        self.model = gp.Model("LocalILP")
        try:
            self.model.Params.OutputFlag = self.gurobi_output
            if time_limit is not None:
                self.model.Params.TimeLimit = time_limit
            # self.model.Params.Threads = 4  # Multi-threaded for consistency
            
            # Build model
            self._build_variables()
            self._add_usage_and_storage_constraints()
            self._add_creation_and_recipe_constraints()
            self._add_fixed_mv_constraints()  # Add fixed MV constraints
            self._build_objective()
            
            # Solve
            t0 = time.time()
            self.model.optimize()
            elapsed = time.time() - t0
            
            # Check status
            if self.model.status != gp.GRB.OPTIMAL:
                logger.warning(f"LocalILP optimization not optimal: status={self.model.status}")
                if self.model.status == gp.GRB.INFEASIBLE:
                    logger.error("Model is infeasible")
                    # Return empty solution with original indices
                    return {
                        "selected_mvs_by_timestep": {idx: set() for idx in self.timestep_indices_original},
                        "objective": float("inf"),
                        "solve_time_sec": elapsed,
                    }
            
            # Extract solution from unique timesteps
            selected_mvs_unique = {}
            for t_local, t_global in enumerate(self.timestep_indices):
                selected = set()
                for j in self.cand_j:
                    z_obj = self.z[j, t_local]
                    # Handle both Gurobi Var and constant int
                    if isinstance(z_obj, gp.Var):
                        val = z_obj.X
                    else:
                        val = z_obj
                    
                    if val > 0.5:
                        selected.add(j)
                selected_mvs_unique[t_global] = selected
            
            # Map back to original 3 indices (handle duplicates)
            selected_mvs_by_timestep = {}
            for orig_idx in self.timestep_indices_original:
                selected_mvs_by_timestep[orig_idx] = selected_mvs_unique[orig_idx]
            
            obj = float(self.model.objVal) if self.model.status == gp.GRB.OPTIMAL else float("inf")
            
            logger.debug(f"LocalILP completed: T={self.T}, obj={obj:.4f}, time={elapsed:.2f}s")
            
            return {
                "selected_mvs_by_timestep": selected_mvs_by_timestep,
                "objective": obj,
                "solve_time_sec": elapsed,
            }
        finally:
            self.model.dispose()
            self.model = None
