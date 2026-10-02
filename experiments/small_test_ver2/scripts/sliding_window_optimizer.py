"""Sliding Window Adaptive Optimizer.

This module implements a sliding window approach for adaptive materialized
view selection. It uses past workload history to make MV decisions for
the next timestep.

Approach:
    At each timestep t, we use a 2-timestep ILP:
    - t=0: Current MVs (FIXED) with previous frequency
    - t=1: Next MVs (VARIABLE) with current frequency
    
    This correctly accounts for migration costs from current state to next state.

Usage:
    python experiments/small_test_ver2/scripts/sliding_window_optimizer.py \\
        --query-set job
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)


class SlidingWindowOptimizer:
    """Sliding Window Adaptive Optimizer for time-varying workloads.
    
    This optimizer uses a 2-timestep ILP approach:
    1. Fix the first timestep to current MV configuration
    2. Optimize the second timestep with current frequency
    3. Use the second timestep's solution as the next MV configuration
    
    This ensures migration costs are correctly calculated.
    
    Key features:
    - Average frequency initialization: Uses average frequency across all
      timesteps to compute initial MV configuration for t=0
    - Migration cost aware: Correctly considers transition costs by fixing
      the current state in the ILP
    """
    
    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        all_timesteps: List[str],
        all_frequencies: Dict[str, List[float]],
        migration_cost: Dict[int, float],
        migration_cost_weight: float = 1.0,
        gurobi_output: int = 0,
    ) -> None:
        """Initialize the Sliding Window Optimizer.
        
        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J] (benefit of query i using MV j)
            X: Inclusion matrix [J][J] (1 if j includes u)
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            all_timesteps: List of all timestep names
            all_frequencies: Query frequencies for all timesteps {timestep: [freqs]}
            migration_cost: Migration cost for each MV {j: cost}
            migration_cost_weight: Weight for migration costs (default: 1.0)
            gurobi_output: Gurobi log level (0=off, 1=on)
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.all_timesteps = all_timesteps
        self.all_frequencies = all_frequencies
        self.migration_cost = migration_cost
        self.migration_cost_weight = migration_cost_weight
        self.gurobi_output = gurobi_output
        
        self.I = len(u_ij)  # Number of queries
        self.J = len(node_list)  # Number of MV candidates
        self.T = len(all_timesteps)  # Total timesteps
        
        # State tracking
        self.current_mvs: Set[int] = set()  # Current MV configuration
        
        # Results storage
        self.results_by_timestep: Dict[str, Dict] = {}
        
        logger.info(f"Initialized SlidingWindowOptimizer:")
        logger.info(f"  - Queries: {self.I}, MV candidates: {self.J}")
        logger.info(f"  - Total timesteps: {self.T}")
        logger.info(f"  - Storage budget: {B_max:.2f}")
    
    def _compute_average_frequency(self) -> List[float]:
        """Compute average frequency across all timesteps.
        
        Returns:
            List of average frequencies for each query
        """
        avg_freq = [0.0] * self.I
        
        for ts in self.all_timesteps:
            freqs = self.all_frequencies.get(ts, [0.0] * self.I)
            for i in range(min(len(freqs), self.I)):
                avg_freq[i] += freqs[i]
        
        for i in range(self.I):
            avg_freq[i] /= self.T
        
        return avg_freq
    
    def _solve_static_ilp(self, frequencies: List[float]) -> Set[int]:
        """Solve static ILP for a single frequency vector.
        
        This is used for initial MV configuration using average frequency.
        
        Args:
            frequencies: Frequency for each query
        
        Returns:
            Set of selected MV indices
        """
        from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
        
        # Create single-timestep problem
        timesteps = ["static"]
        freq_dict = {"static": frequencies}
        
        optimizer = TimeDependentOptimizer(
            node_list=self.node_list,
            u_ij=self.u_ij,
            X=self.X,
            b_j=self.b_j,
            B_max=self.B_max,
            timesteps=timesteps,
            migration_cost=self.migration_cost,
            query_frequency_by_timestep=freq_dict,
            gurobi_output=self.gurobi_output,
            migration_cost_weight=self.migration_cost_weight,
        )
        
        result = optimizer.optimize()
        z_values = result["z_by_timestep"][0]
        return set(j for j, v in enumerate(z_values) if v == 1)
    
    def _solve_step_ilp(
        self,
        prev_freq: List[float],
        curr_freq: List[float],
        current_mvs: Set[int],
    ) -> Set[int]:
        """Solve 2-timestep ILP with first timestep fixed.
        
        This correctly accounts for migration cost from current state.
        
        Args:
            prev_freq: Previous timestep's frequency
            curr_freq: Current timestep's frequency
            current_mvs: Current MV configuration (to be fixed at t=0)
        
        Returns:
            Set of selected MV indices for the next timestep
        """
        from experiments.small_test_ver2.core.local_ilp_optimizer import LocalILPOptimizer
        
        # Create 2-timestep problem
        timestep_indices = [0, 1]  # Two timesteps
        all_timesteps = ["prev", "curr"]
        freq_dict = {"prev": prev_freq, "curr": curr_freq}
        
        # Fix the first timestep to current MVs
        fixed_mvs = {0: current_mvs}
        
        optimizer = LocalILPOptimizer(
            node_list=self.node_list,
            u_ij=self.u_ij,
            X=self.X,
            b_j=self.b_j,
            B_max=self.B_max,
            timestep_indices=timestep_indices,
            all_timesteps=all_timesteps,
            migration_cost=self.migration_cost,
            query_frequency_by_timestep=freq_dict,
            fixed_mvs_by_timestep=fixed_mvs,
            gurobi_output=self.gurobi_output,
        )
        
        result = optimizer.optimize()
        
        # Return the solution for the second timestep (t=1)
        return result["selected_mvs_by_timestep"][1]
    
    def compute_initial_mvs(self) -> Set[int]:
        """Compute initial MV configuration using average frequency.
        
        This is used for t=0 where no history is available.
        
        Returns:
            Set of MV indices to use at t=0
        """
        logger.info("Computing initial MV configuration using average frequency...")
        
        avg_freq = self._compute_average_frequency()
        logger.info(f"  Average frequency computed (sum: {sum(avg_freq):.2f})")
        
        initial_mvs = self._solve_static_ilp(avg_freq)
        logger.info(f"  Initial MVs: {len(initial_mvs)} selected")
        
        return initial_mvs
    
    def optimize_all(self) -> Dict:
        """Run sliding window optimization for all timesteps.
        
        Returns:
            Dictionary containing:
                - timesteps: List of timestep names
                - z_by_timestep: List of z values for each timestep
                - mv_changes: List of (created, deleted) MV sets per timestep
                - solve_times: List of solve times per timestep
                - total_solve_time: Total optimization time
        """
        logger.info("=" * 70)
        logger.info("Starting Sliding Window Adaptive Optimization")
        logger.info("=" * 70)
        
        total_start = time.time()
        
        # Initialize with average frequency for t=0
        self.current_mvs = self.compute_initial_mvs()
        
        z_by_timestep = []
        mv_changes = []
        solve_times = []
        
        # Track previous frequency for 2-timestep ILP
        prev_freq = self._compute_average_frequency()
        
        for t, ts_name in enumerate(self.all_timesteps):
            logger.info(f"\n--- Timestep {t}: {ts_name} ---")
            
            t_start = time.time()
            
            # Record current MVs for this timestep
            z_t = [1 if j in self.current_mvs else 0 for j in range(self.J)]
            z_by_timestep.append(z_t)
            
            # Get current frequency
            curr_freq = self.all_frequencies.get(ts_name, [1.0] * self.I)
            
            logger.info(f"  Using MV set: {len(self.current_mvs)} MVs")
            
            # Solve 2-timestep ILP with current MVs fixed at t=0
            next_mvs = self._solve_step_ilp(prev_freq, curr_freq, self.current_mvs)
            
            # Calculate changes
            created = next_mvs - self.current_mvs
            deleted = self.current_mvs - next_mvs
            
            logger.info(f"  Next MVs: {len(next_mvs)} (created: {len(created)}, deleted: {len(deleted)})")
            
            t_elapsed = time.time() - t_start
            solve_times.append(t_elapsed)
            
            # Record changes
            mv_changes.append({
                "created": [self.node_list[j] for j in sorted(created)],
                "deleted": [self.node_list[j] for j in sorted(deleted)],
                "created_count": len(created),
                "deleted_count": len(deleted),
            })
            
            # Store detailed results
            self.results_by_timestep[ts_name] = {
                "selected_mvs": [self.node_list[j] for j in sorted(self.current_mvs)],
                "mv_count": len(self.current_mvs),
                "solve_time": t_elapsed,
            }
            
            # Update state for next iteration
            prev_freq = curr_freq
            self.current_mvs = next_mvs
        
        total_time = time.time() - total_start
        
        logger.info("\n" + "=" * 70)
        logger.info("Sliding Window Optimization Complete")
        logger.info(f"Total time: {total_time:.2f}s")
        logger.info("=" * 70)
        
        return {
            "timesteps": self.all_timesteps,
            "node_list": self.node_list,
            "z_by_timestep": z_by_timestep,
            "mv_changes": mv_changes,
            "solve_times": solve_times,
            "total_solve_time": total_time,
            "results_by_timestep": self.results_by_timestep,
        }


def main():
    """Main function for testing."""
    import argparse
    import json
    import os
    import sys
    
    # Add project root to path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    sys.path.insert(0, project_root)
    
    from experiments.small_test_ver2.core.io_loaders import (
        load_qp_inputs,
        load_timesteps_and_frequencies,
        load_full_build_costs_and_sizes,
    )
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Sliding Window Adaptive MV Optimization")
    parser.add_argument("--query-set", type=str, default="job", help="Query set name")
    parser.add_argument("--freq-suffix", type=str, default="", help="Frequency file suffix (e.g., _16_3)")
    parser.add_argument("--storage-budget", type=float, default=float(100*1024*1024), help="Storage budget")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    args = parser.parse_args()
    
    # Paths
    base_dir = os.path.dirname(script_dir)  # experiments/small_test_ver2
    
    logger.info("=" * 80)
    logger.info("Sliding Window Adaptive MV Optimization")
    logger.info("=" * 80)
    
    # Load data
    logger.info("\n[1/3] Loading data...")
    qp = load_qp_inputs(base_dir, args.query_set)
    node_list = qp["node_list"]
    u_ij = qp["u_ij"]
    X = qp["X"]
    b_j = qp["b_j"]
    
    timesteps, frequencies = load_timesteps_and_frequencies(
        base_dir, args.query_set, args.freq_suffix
    )
    
    migration_cost, utilities, sizes = load_full_build_costs_and_sizes(
        base_dir, node_list, args.query_set
    )
    
    logger.info(f"  - Queries: {len(u_ij)}")
    logger.info(f"  - MV candidates: {len(node_list)}")
    logger.info(f"  - Timesteps: {len(timesteps)}")
    logger.info(f"  - Storage budget: {args.storage_budget} MB")
    
    # Run optimization
    logger.info("\n[2/3] Running sliding window optimization...")
    optimizer = SlidingWindowOptimizer(
        node_list=node_list,
        u_ij=u_ij,
        X=X,
        b_j=sizes,  # Use calculated sizes
        B_max=args.storage_budget,
        all_timesteps=timesteps,
        all_frequencies=frequencies,
        migration_cost=migration_cost,
        gurobi_output=0,
    )
    
    result = optimizer.optimize_all()
    
    # Save results
    logger.info("\n[3/3] Saving results...")
    output_dir = os.path.join(base_dir, "time_dependent_output", args.query_set)
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = args.output or os.path.join(
        output_dir, f"sliding_window_result{args.freq_suffix}.json"
    )
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"  - Results saved to: {output_file}")
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total timesteps: {len(timesteps)}")
    logger.info(f"Total solve time: {result['total_solve_time']:.2f}s")
    
    total_created = sum(c["created_count"] for c in result["mv_changes"])
    total_deleted = sum(c["deleted_count"] for c in result["mv_changes"])
    logger.info(f"Total MVs created: {total_created}")
    logger.info(f"Total MVs deleted: {total_deleted}")
    
    avg_mvs = sum(sum(z) for z in result["z_by_timestep"]) / len(timesteps)
    logger.info(f"Average MVs per timestep: {avg_mvs:.1f}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
