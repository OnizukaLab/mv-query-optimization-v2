#!/usr/bin/env python3
"""Generate parse statistics from existing query parser cache.

This script loads a saved QueryParser cache and generates/regenerates
parse statistics without re-running the full query parsing process.
"""
import argparse
import json
import pickle
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def compute_parse_statistics(qp) -> dict:
    """Compute statistics about parsed queries and utilities.
    
    Args:
        qp: QueryParser instance
        
    Returns:
        Dictionary containing various parsing statistics
    """
    stats = {}
    
    # Basic counts
    num_queries = len(qp.u_ij)
    num_nodes = len(qp.node_list)
    num_leaf_nodes = len(qp.qm.leaf_nodes_map)
    num_non_leaf_nodes = len(qp.qm.non_leaf_nodes_map)
    
    stats['num_queries'] = num_queries
    stats['num_nodes'] = num_nodes
    stats['num_leaf_nodes'] = num_leaf_nodes
    stats['num_non_leaf_nodes'] = num_non_leaf_nodes
    
    # Utility statistics
    total_utility_entries = 0
    positive_utility_entries = 0
    zero_utility_entries = 0
    negative_utility_entries = 0
    
    utility_values = []
    positive_utilities = []
    
    for i, row in enumerate(qp.u_ij):
        for j, u in enumerate(row):
            total_utility_entries += 1
            utility_values.append(u)
            if u > 0:
                positive_utility_entries += 1
                positive_utilities.append(u)
            elif u == 0:
                zero_utility_entries += 1
            else:
                negative_utility_entries += 1
    
    stats['total_utility_entries'] = total_utility_entries
    stats['positive_utility_entries'] = positive_utility_entries
    stats['zero_utility_entries'] = zero_utility_entries
    stats['negative_utility_entries'] = negative_utility_entries
    stats['positive_utility_percentage'] = (
        positive_utility_entries / total_utility_entries * 100
        if total_utility_entries > 0 else 0
    )
    stats['non_zero_utility_percentage'] = (
        (positive_utility_entries + negative_utility_entries) / total_utility_entries * 100
        if total_utility_entries > 0 else 0
    )
    
    # Utility value statistics
    if utility_values:
        stats['utility_min'] = min(utility_values)
        stats['utility_max'] = max(utility_values)
        stats['utility_mean'] = sum(utility_values) / len(utility_values)
        sorted_values = sorted(utility_values)
        mid = len(sorted_values) // 2
        stats['utility_median'] = (
            sorted_values[mid] if len(sorted_values) % 2 == 1
            else (sorted_values[mid - 1] + sorted_values[mid]) / 2
        )
    else:
        stats['utility_min'] = 0
        stats['utility_max'] = 0
        stats['utility_mean'] = 0
        stats['utility_median'] = 0
    
    if positive_utilities:
        stats['positive_utility_mean'] = sum(positive_utilities) / len(positive_utilities)
        stats['positive_utility_max'] = max(positive_utilities)
    else:
        stats['positive_utility_mean'] = 0
        stats['positive_utility_max'] = 0
    
    # Maintenance cost statistics
    if qp.m_cost:
        stats['maintenance_cost_min'] = min(qp.m_cost)
        stats['maintenance_cost_max'] = max(qp.m_cost)
        stats['maintenance_cost_mean'] = sum(qp.m_cost) / len(qp.m_cost)
        stats['maintenance_cost_total'] = sum(qp.m_cost)
    else:
        stats['maintenance_cost_min'] = 0
        stats['maintenance_cost_max'] = 0
        stats['maintenance_cost_mean'] = 0
        stats['maintenance_cost_total'] = 0
    
    # Storage size statistics
    if qp.b_j:
        stats['storage_size_min'] = min(qp.b_j)
        stats['storage_size_max'] = max(qp.b_j)
        stats['storage_size_mean'] = sum(qp.b_j) / len(qp.b_j)
        stats['storage_size_total'] = sum(qp.b_j)
    else:
        stats['storage_size_min'] = 0
        stats['storage_size_max'] = 0
        stats['storage_size_mean'] = 0
        stats['storage_size_total'] = 0
    
    # Per-query statistics
    queries_with_positive_utility = 0
    for row in qp.u_ij:
        if any(u > 0 for u in row):
            queries_with_positive_utility += 1
    
    stats['queries_with_positive_utility'] = queries_with_positive_utility
    stats['queries_with_positive_utility_percentage'] = (
        queries_with_positive_utility / num_queries * 100
        if num_queries > 0 else 0
    )
    
    # Per-node statistics (how many nodes have positive utility from at least one query)
    nodes_with_positive_utility = 0
    for j in range(num_nodes):
        if any(qp.u_ij[i][j] > 0 for i in range(num_queries)):
            nodes_with_positive_utility += 1
    
    stats['nodes_with_positive_utility'] = nodes_with_positive_utility
    stats['nodes_with_positive_utility_percentage'] = (
        nodes_with_positive_utility / num_nodes * 100
        if num_nodes > 0 else 0
    )
    
    # Net benefit analysis (utility - maintenance_cost)
    net_benefits = []
    positive_net_benefits = 0
    for j in range(num_nodes):
        max_utility_for_node = max(qp.u_ij[i][j] for i in range(num_queries)) if num_queries > 0 else 0
        net_benefit = max_utility_for_node - qp.m_cost[j] if j < len(qp.m_cost) else max_utility_for_node
        net_benefits.append(net_benefit)
        if net_benefit > 0:
            positive_net_benefits += 1
    
    stats['nodes_with_positive_net_benefit'] = positive_net_benefits
    stats['nodes_with_positive_net_benefit_percentage'] = (
        positive_net_benefits / num_nodes * 100
        if num_nodes > 0 else 0
    )
    
    if net_benefits:
        stats['net_benefit_min'] = min(net_benefits)
        stats['net_benefit_max'] = max(net_benefits)
        stats['net_benefit_mean'] = sum(net_benefits) / len(net_benefits)
    else:
        stats['net_benefit_min'] = 0
        stats['net_benefit_max'] = 0
        stats['net_benefit_mean'] = 0
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate parse statistics from cache")
    parser.add_argument(
        "--output",
        type=str,
        default="Output",
        help="Output directory containing qp_class.pkl"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing statistics file"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    pickle_path = output_dir / "qp_class.pkl"
    stats_path = output_dir / "parse_statistics.json"
    
    if not pickle_path.exists():
        print(f"Error: Query parser cache not found: {pickle_path}")
        print("Run an experiment with query_parsing phase first.")
        sys.exit(1)
    
    if stats_path.exists() and not args.force:
        print(f"Statistics file already exists: {stats_path}")
        print("Use --force to overwrite.")
        sys.exit(0)
    
    print(f"Loading query parser from {pickle_path}...")
    with open(pickle_path, 'rb') as f:
        qp = pickle.load(f)
    
    print("Computing statistics...")
    stats = compute_parse_statistics(qp)
    
    print(f"Saving statistics to {stats_path}...")
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print("\n" + "=" * 60)
    print("📊 Parse Statistics Summary")
    print("=" * 60)
    print(f"  Queries: {stats['num_queries']}")
    print(f"  Nodes: {stats['num_nodes']} (leaf: {stats['num_leaf_nodes']}, non-leaf: {stats['num_non_leaf_nodes']})")
    print()
    print(f"  Total utility entries: {stats['total_utility_entries']:,}")
    print(f"  Positive utility entries: {stats['positive_utility_entries']:,} ({stats['positive_utility_percentage']:.2f}%)")
    print()
    print(f"  Nodes with positive utility: {stats['nodes_with_positive_utility']} ({stats['nodes_with_positive_utility_percentage']:.2f}%)")
    print(f"  Nodes with positive net benefit: {stats['nodes_with_positive_net_benefit']} ({stats['nodes_with_positive_net_benefit_percentage']:.2f}%)")
    print()
    print(f"  Utility range: [{stats['utility_min']:.2f}, {stats['utility_max']:.2f}]")
    print(f"  Utility mean: {stats['utility_mean']:.2f}")
    print()
    print(f"  Maintenance cost range: [{stats['maintenance_cost_min']:.4f}, {stats['maintenance_cost_max']:.4f}]")
    print(f"  Maintenance cost total: {stats['maintenance_cost_total']:.2f}")
    print("=" * 60)
    print(f"\n✅ Statistics saved to {stats_path}")


if __name__ == "__main__":
    main()
