"""Run time-dependent optimization with migration costs.

This script loads data from:
- qp_class.pkl: Query parser data (u_ij, X, b_j, etc.)
- frequency_time_dependent.json: Timesteps and query frequencies
- migration_costs.json: Migration costs for each MV

And performs ILP optimization considering time-varying workloads
and migration costs between timesteps.
python experiments/small_test_ver2/scripts/run_time_dependent_with_migration.py --query-set job
python experiments/small_test_ver2/scripts/run_time_dependent_with_migration.py --query-set job --migration-file simple_migration_costs.json
"""

import json
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from experiments.small_test_ver2.core.io_loaders import (
    load_qp_inputs,
    load_timesteps_and_frequencies,
    parse_migration_costs,
)
from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def analyze_migration_transitions(
    result: dict, 
    node_list: list, 
    b_j: list, 
    recipes: dict,
    B_max: float
) -> dict:
    """
    Analyze migration transitions between timesteps and enhance the result.
    
    Args:
        result: Optimization result dictionary
        node_list: List of node IDs
        b_j: Storage sizes
        recipes: Migration recipes
        B_max: Storage budget
    
    Returns:
        Enhanced result with migration analysis
    """
    timesteps = result["timesteps"]
    z_by_timestep = result["z_by_timestep"]
    
    # Build migration analysis
    migration_analysis = []
    
    for t in range(len(timesteps)):
        timestep_name = timesteps[t]
        current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)
        
        # Calculate per-timestep info
        selected_nodes = [node_list[j] for j in sorted(current_mvs)]
        total_size = sum(b_j[j] for j in current_mvs)
        utilization = (total_size / B_max * 100) if B_max > 0 else 0
        
        timestep_info = {
            "timestep": timestep_name,
            "selected_mvs": selected_nodes,
            "mv_count": len(current_mvs),
            "total_size": round(total_size, 2),
            "storage_budget": round(B_max, 2),
            "utilization_percent": round(utilization, 2)
        }
        
        # Migration info (only for t > 0)
        if t > 0:
            prev_mvs = set(j for j, v in enumerate(z_by_timestep[t-1]) if v == 1)
            
            # Calculate transitions
            maintained = current_mvs & prev_mvs
            created = current_mvs - prev_mvs
            deleted = prev_mvs - current_mvs
            
            # Detailed migration info
            migration_details = {
                "from_timestep": timesteps[t-1],
                "to_timestep": timestep_name,
                "maintained": {
                    "count": len(maintained),
                    "mvs": [node_list[j] for j in sorted(maintained)],
                    "total_size": round(sum(b_j[j] for j in maintained), 2)
                },
                "created": {
                    "count": len(created),
                    "mvs": [node_list[j] for j in sorted(created)],
                    "total_size": round(sum(b_j[j] for j in created), 2)
                },
                "deleted": {
                    "count": len(deleted),
                    "mvs": [node_list[j] for j in sorted(deleted)],
                    "total_size": round(sum(b_j[j] for j in deleted), 2)
                }
            }
            
            # Calculate creation costs (find cheapest recipe for each created MV)
            creation_cost = 0.0
            creation_details = []
            
            for j in sorted(created):
                mv_recipes = recipes.get(j, [(tuple(), float("inf"))])
                # Find applicable recipes (dependencies exist in previous timestep)
                applicable_recipes = []
                for recipe, cost in mv_recipes:
                    if all(dep in prev_mvs for dep in recipe):
                        applicable_recipes.append((recipe, cost))
                
                if applicable_recipes:
                    best_recipe, best_cost = min(applicable_recipes, key=lambda x: x[1])
                    creation_cost += best_cost
                    creation_details.append({
                        "mv": node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(best_cost, 2),
                        "dependencies": [node_list[dep] for dep in best_recipe] if best_recipe else []
                    })
            
            migration_details["creation_cost"] = round(creation_cost, 2)
            migration_details["creation_details"] = creation_details
            
            timestep_info["migration"] = migration_details
        else:
            # Initial timestep: all MVs are created
            initial_cost = 0.0
            creation_details = []
            
            for j in sorted(current_mvs):
                mv_recipes = recipes.get(j, [(tuple(), 0.0)])
                # For t=0, only empty recipe is allowed
                empty_recipes = [(recipe, cost) for recipe, cost in mv_recipes if len(recipe) == 0]
                if empty_recipes:
                    _, cost = min(empty_recipes, key=lambda x: x[1])
                    initial_cost += cost
                    creation_details.append({
                        "mv": node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": []
                    })
            
            timestep_info["initial_creation"] = {
                "total_cost": round(initial_cost, 2),
                "creation_details": creation_details
            }
        
        migration_analysis.append(timestep_info)
    
    # Create enhanced result
    enhanced = result.copy()
    enhanced["migration_analysis"] = migration_analysis
    
    # Add summary statistics
    total_created = sum(
        len(ma.get("migration", {}).get("created", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )
    total_deleted = sum(
        len(ma.get("migration", {}).get("deleted", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )
    total_maintained = sum(
        len(ma.get("migration", {}).get("maintained", {}).get("mvs", []))
        for ma in migration_analysis if "migration" in ma
    )
    
    enhanced["summary"] = {
        "total_timesteps": len(timesteps),
        "total_mvs_created": total_created + len(migration_analysis[0].get("initial_creation", {}).get("creation_details", [])),
        "total_mvs_deleted": total_deleted,
        "total_transitions_maintained": total_maintained,
        "avg_mvs_per_timestep": round(sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2),
        "avg_storage_utilization": round(sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2)
    }
    
    return enhanced


def main():
    """Main execution function."""
    # Paths
    # Get the small_test_ver2 directory (parent of scripts/)
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    # コマンドライン引数の処理
    import argparse
    parser = argparse.ArgumentParser(description="Time-dependent MV optimization with migration costs")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="Query set name (e.g., job_like, explicit_join)"
    )
    parser.add_argument(
        "--migration-file",
        type=str,
        default="migration_costs.json",
        help="Migration cost file name (e.g., migration_costs.json, simple_migration_costs.json)"
    )
    args = parser.parse_args()
    query_set = args.query_set
    migration_file = args.migration_file
    
    output_dir = os.path.join(base_dir, "time_dependent_output", query_set)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("="*80)
    logger.info("Time-Dependent MV Optimization with Migration Costs")
    logger.info("="*80)

    # 1. Load query parser data from qp_class.pkl
    logger.info("\n[1/4] Loading query parser data from qp_class.pkl...")
    qp = load_qp_inputs(base_dir, query_set)
    node_list = qp["node_list"]
    u_ij = qp["u_ij"]
    X = qp["X"]
    b_j = qp["b_j"]
    
    # Calculate storage budget (30% of total storage)
    B_max = float(10240)

    logger.info(f"  - Queries: {len(u_ij)}")
    logger.info(f"  - MV candidates: {len(node_list)}")
    logger.info(f"  - Total storage: {sum(b_j):.2f}")
    logger.info(f"  - Storage budget (30%): {B_max:.2f}")

    # 2. Load timesteps and frequencies from frequency_time_dependent.json
    logger.info("\n[2/4] Loading timesteps and frequencies from frequency_time_dependent.json...")
    timesteps, frequencies = load_timesteps_and_frequencies(base_dir, query_set)
    
    logger.info(f"  - Timesteps: {timesteps}")
    for ts in timesteps:
        total_freq = sum(frequencies[ts])
        logger.info(f"  - {ts}: total frequency = {total_freq:.0f}")

    # Validate frequency dimensions
    query_count = len(u_ij)
    for ts in timesteps:
        if len(frequencies[ts]) != query_count:
            logger.warning(
                f"Frequency count mismatch for {ts}: "
                f"expected {query_count}, got {len(frequencies[ts])}"
            )
            # Pad or truncate
            if len(frequencies[ts]) < query_count:
                frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
            else:
                frequencies[ts] = frequencies[ts][:query_count]

    # 3. Load migration costs from migration cost file
    logger.info(f"\n[3/4] Loading migration costs from {migration_file}...")
    recipes = parse_migration_costs(base_dir, node_list, query_set, migration_file)
    logger.info(f"  - Loaded recipes for {len(recipes)} MVs")

    # Log sample recipes
    sample_count = min(3, len(recipes))
    for j_idx in list(recipes.keys())[:sample_count]:
        node_id = node_list[j_idx]
        recipe_list = recipes[j_idx]
        logger.info(f"  - {node_id}: {len(recipe_list)} recipes")
        for recipe, cost in recipe_list[:2]:  # Show first 2 recipes
            dep_names = [node_list[dep] for dep in recipe] if recipe else ["[]"]
            logger.info(f"      {dep_names} -> cost={cost:.2f}")

    # 4. Run optimization
    logger.info("\n[4/4] Running time-dependent ILP optimization...")
    optimizer = TimeDependentOptimizer(
        node_list=node_list,
        u_ij=u_ij,
        X=X,
        b_j=b_j,
        B_max=B_max,
        timesteps=timesteps,
        migration_recipes=recipes,
        query_frequency_by_timestep=frequencies,
        gurobi_output=1,  # Show Gurobi log
    )

    result = optimizer.optimize(time_limit=300)  # 5 minute time limit

    # 5. Analyze and enhance results
    logger.info("\n[5/6] Analyzing migration transitions...")
    enhanced_result = analyze_migration_transitions(result, node_list, b_j, recipes, B_max)
    
    # Add input data to result
    enhanced_result["input_data"] = {
        "storage_budget": round(B_max, 2),
        "total_storage": round(sum(b_j), 2),
        "mv_storage_sizes": {
            node_list[j]: round(b_j[j], 2) 
            for j in range(len(node_list))
        },
        "query_frequencies": {
            ts: {
                f"query_{i}": round(frequencies[ts][i], 2)
                for i in range(len(frequencies[ts]))
            }
            for ts in timesteps
        },
        "utility_matrix": {
            f"query_{i}": {
                node_list[j]: round(u_ij[i][j], 2)
                for j in range(len(node_list))
            }
            for i in range(len(u_ij))
        },
        "inclusion_matrix_details": {
            node_list[j]: {
                node_list[u]: X[j][u]
                for u in range(len(node_list)) if X[j][u] == 1
            }
            for j in range(len(node_list))
        },
        "inclusive_matrix":X,
    }
    
    # 6. Save results
    logger.info("\n[6/6] Saving results...")
    result_path = os.path.join(output_dir, "td_mv_optimization_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(enhanced_result, f, ensure_ascii=False, indent=2)
    logger.info(f"  - Saved to: {result_path}")

    # Print summary
    logger.info("\n" + "="*80)
    logger.info("OPTIMIZATION SUMMARY")
    logger.info("="*80)
    logger.info(f"Total objective: {enhanced_result['objective']:.4f}")
    logger.info(f"  - Workload cost: {enhanced_result['workload_cost']:.4f}")
    logger.info(f"  - Migration cost: {enhanced_result['migration_cost']:.4f}")
    logger.info(f"Solve time: {enhanced_result['solve_time_sec']:.2f} seconds")
    logger.info("")
    
    # Print detailed migration analysis
    logger.info("MIGRATION ANALYSIS")
    logger.info("="*80)
    
    for ma in enhanced_result["migration_analysis"]:
        ts_name = ma["timestep"]
        logger.info(f"\nTimestep '{ts_name}':")
        logger.info(f"  Selected MVs: {ma['mv_count']}")
        logger.info(f"  Storage: {ma['total_size']:.2f} / {ma['storage_budget']:.2f} ({ma['utilization_percent']:.1f}%)")
        logger.info(f"  MVs: {', '.join(ma['selected_mvs'])}")
        
        if "migration" in ma:
            mig = ma["migration"]
            logger.info(f"\n  Migration from '{mig['from_timestep']}':")
            logger.info(f"    ✓ Maintained: {mig['maintained']['count']} MVs ({mig['maintained']['total_size']:.2f} GB)")
            if mig['maintained']['mvs']:
                logger.info(f"      → {', '.join(mig['maintained']['mvs'])}")
            
            logger.info(f"    + Created: {mig['created']['count']} MVs ({mig['created']['total_size']:.2f} GB, cost: {mig['creation_cost']:.2f})")
            if mig['creation_details']:
                for detail in mig['creation_details']:
                    deps = f" from [{', '.join(detail['dependencies'])}]" if detail['dependencies'] else " (full build)"
                    logger.info(f"      → {detail['mv']} ({detail['size']:.2f} GB, cost: {detail['cost']:.2f}){deps}")
            
            logger.info(f"    - Deleted: {mig['deleted']['count']} MVs ({mig['deleted']['total_size']:.2f} GB)")
            if mig['deleted']['mvs']:
                logger.info(f"      → {', '.join(mig['deleted']['mvs'])}")
        
        elif "initial_creation" in ma:
            init = ma["initial_creation"]
            logger.info(f"\n  Initial Creation (cost: {init['total_cost']:.2f}):")
            for detail in init['creation_details']:
                logger.info(f"    → {detail['mv']} ({detail['size']:.2f} GB, cost: {detail['cost']:.2f})")
    
    logger.info("\n" + "="*80)
    logger.info("OVERALL STATISTICS")
    logger.info("="*80)
    summary = enhanced_result["summary"]
    logger.info(f"Total timesteps: {summary['total_timesteps']}")
    logger.info(f"Total MVs created: {summary['total_mvs_created']}")
    logger.info(f"Total MVs deleted: {summary['total_mvs_deleted']}")
    logger.info(f"Total transitions maintained: {summary['total_transitions_maintained']}")
    logger.info(f"Average MVs per timestep: {summary['avg_mvs_per_timestep']}")
    logger.info(f"Average storage utilization: {summary['avg_storage_utilization']:.1f}%")
    logger.info("="*80)
    logger.info("Optimization completed successfully!")
    logger.info("="*80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
