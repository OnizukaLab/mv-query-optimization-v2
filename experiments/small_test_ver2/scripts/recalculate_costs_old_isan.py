#!/usr/bin/env python3
"""Recalculate MV creation costs using pickle-based node relationships.

This script uses the node structure from the parsed query plan (pickle file)
combined with sampled row counts from simple_migration_costs.json to calculate
accurate costs that account for JOIN complexity (especially Nested Loop Joins).

Usage (from project root: /home/masuda/projects/mv-query-optimization):
    # Basic usage (outputs to simple_migration_costs_recalc.json)
    python3 experiments/small_test_ver2/scripts/recalculate_costs.py --query-set job
    
    # Overwrite original file
    python3 experiments/small_test_ver2/scripts/recalculate_costs.py --query-set job --overwrite
"""

import json
import math
import pickle
import argparse
import sys
from pathlib import Path

# Add project root to path for pickle deserialization (pickle contains references to src.*)
PROJECT_ROOT = Path("/home/masuda/projects/mv-query-optimization")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# PostgreSQL Cost Constants (should match postgresql.conf)
BLOCK_SIZE = 8192
SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 1.1  # SSD環境向け（デフォルト4.0はHDD前提）
CPU_TUPLE_COST = 0.01
CPU_INDEX_TUPLE_COST = 0.005
CPU_OPERATOR_COST = 0.0025

# Large table penalty for Index Scan (non-clustered index causes random I/O)
# Tables larger than this threshold get a penalty on Index Scan cost
LARGE_TABLE_THRESHOLD = 100 * 1024 * 1024  # 100MB
LARGE_TABLE_INDEX_PENALTY = 1.0  # 2x penalty for unclustered random I/O

# Table information from database (rows and size in bytes)
# Used for calculating actual scan costs for leaf nodes
TABLE_INFO = {
    "cast_info": {"rows": 36244344, "size": 2070282240},
    "movie_info": {"rows": 14835720, "size": 1324220416},
    "movie_keyword": {"rows": 4523930, "size": 200540160},
    "name": {"rows": 4167491, "size": 455933952},
    "char_name": {"rows": 3140423, "size": 298582016},
    "person_info": {"rows": 2963664, "size": 418447360},
    "movie_companies": {"rows": 2609129, "size": 154206208},
    "title": {"rows": 2528312, "size": 294977536},
    "movie_info_idx": {"rows": 1380035, "size": 65273856},
    "aka_name": {"rows": 901343, "size": 93519872},
    "aka_title": {"rows": 361472, "size": 51052544},
    "company_name": {"rows": 234997, "size": 24903680},
    "complete_cast": {"rows": 135086, "size": 6029312},
    "keyword": {"rows": 134170, "size": 8257536},
    "movie_link": {"rows": 29997, "size": 1335296},
    "info_type": {"rows": 113, "size": 8192},
    "link_type": {"rows": 18, "size": 8192},
    "role_type": {"rows": 12, "size": 8192},
    "kind_type": {"rows": 7, "size": 8192},
    "company_type": {"rows": 4, "size": 8192},
    "comp_cast_type": {"rows": 4, "size": 8192},
}


def load_pickle(pickle_path: Path):
    """Load QueryParser object from pickle file."""
    with open(pickle_path, 'rb') as f:
        return pickle.load(f)


def load_migration_costs(json_path: Path) -> dict:
    """Load migration costs from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_children(qm, node_id: str) -> list:
    """Get children of a node from QueryManager."""
    if node_id in qm.non_leaf_nodes_map_r:
        return list(qm.non_leaf_nodes_map_r[node_id])
    return []


def get_operator(qm, node_id: str) -> str:
    """Get operator type of a node from QueryManager."""
    # First, check if it's a leaf node
    if node_id in qm.leaf_nodes_map_r:
        operator, table, alias, filter_cond = qm.leaf_nodes_map_r[node_id]
        return operator
    
    # For non-leaf nodes, check node_operators mapping
    if node_id in qm.node_operators:
        return qm.node_operators[node_id]
    
    # Fallback to non_leaf_nodes_info
    if hasattr(qm, 'non_leaf_nodes_info') and node_id in qm.non_leaf_nodes_info:
        return qm.non_leaf_nodes_info[node_id].operator
    
    return "Unknown"


def get_rows_from_migration_costs(migration_costs: dict, node_id: str) -> int:
    """Get scaled rows for a node from migration_costs.json."""
    if node_id in migration_costs:
        # Get the "[]" plan key which represents the MV creation cost
        node_data = migration_costs[node_id]
        if "[]" in node_data:
            return node_data["[]"].get("rows", 0)
    return 0


def get_width_from_migration_costs(migration_costs: dict, node_id: str) -> int:
    """Get width for a node from migration_costs.json."""
    if node_id in migration_costs:
        node_data = migration_costs[node_id]
        if "[]" in node_data:
            return node_data["[]"].get("width", 0)
    return 0


def calculate_node_cost(qm, node_id: str, migration_costs: dict, memo: dict) -> tuple:
    """
    Recursively calculate cost for a node using C-Store style model.
    
    Returns:
        Tuple of (exec_cost, creation_cost, utility, output_rows)
        - exec_cost: 実行コスト（このサブクエリを実行するのにかかるコスト）
        - creation_cost: MV作成コスト（実行コスト + 書き込みコスト）
        - utility: 純利得（実行コスト - MV読み取りコスト）
        - output_rows: 出力行数
    """
    # Memoization: avoid recalculating the same node
    if node_id in memo:
        return memo[node_id]
    
    # Get node properties
    operator = get_operator(qm, node_id)
    output_rows = get_rows_from_migration_costs(migration_costs, node_id)
    width = get_width_from_migration_costs(migration_costs, node_id)
    
    # Fallback to pickle data if not in migration_costs
    if output_rows == 0 and hasattr(qm, 'subquery_rows') and node_id in qm.subquery_rows:
        output_rows = qm.subquery_rows[node_id]
    if width == 0 and hasattr(qm, 'subquery_widths') and node_id in qm.subquery_widths:
        width = qm.subquery_widths[node_id]
    
    children = get_children(qm, node_id)
    
    # --- Leaf Node ---
    if not children:
        # Get table name for this leaf node
        table_name = None
        if node_id in qm.leaf_nodes_map_r:
            _, table_name, _, _ = qm.leaf_nodes_map_r[node_id]
        
        # Get table size from TABLE_INFO (input size for scan)
        if table_name and table_name in TABLE_INFO:
            input_rows = TABLE_INFO[table_name]["rows"]
            input_size = TABLE_INFO[table_name]["size"]
            input_pages = math.ceil(input_size / BLOCK_SIZE) if input_size > 0 else 0
        else:
            # Fallback: use output rows as input (no filter case)
            input_rows = output_rows
            input_size = output_rows * width
            input_pages = math.ceil(input_size / BLOCK_SIZE) if input_size > 0 else 0
        
        # Execution cost = cost to scan the TABLE (not output)
        if 'Index' in operator and 'Scan' in operator:
            # Index Scan: random I/O for matching rows only
            # Apply penalty for large tables (non-clustered index causes cache misses)
            penalty = LARGE_TABLE_INDEX_PENALTY if input_size > LARGE_TABLE_THRESHOLD else 1.0
            exec_cost = (output_rows * RANDOM_PAGE_COST * penalty) + (output_rows * CPU_INDEX_TUPLE_COST)
        else:
            # Seq Scan: scan full table + filter
            exec_cost = (input_pages * SEQ_PAGE_COST) + (input_rows * CPU_TUPLE_COST)
        
        # Output size (for MV)
        output_size = output_rows * width
        output_pages = math.ceil(output_size / BLOCK_SIZE) if output_size > 0 else 0
        
        # Write cost for MV creation
        write_cost = (output_pages * SEQ_PAGE_COST) + (output_rows * CPU_TUPLE_COST)
        creation_cost = exec_cost + write_cost
        
        # MV read cost (cost to read the MV)
        mv_read_cost = (output_pages * SEQ_PAGE_COST) + (output_rows * CPU_TUPLE_COST)
        
        # Net utility = execution cost - MV read cost
        utility = max(0, exec_cost - mv_read_cost)
        
        memo[node_id] = (exec_cost, creation_cost, utility, output_rows)
        return exec_cost, creation_cost, utility, output_rows
    
    # --- Non-Leaf Node ---
    # Recursively calculate children costs
    children_exec_costs = []  # execution costs (for cost propagation)
    children_rows = []
    
    for child_id in children:
        c_exec, c_creation, c_utility, c_rows = calculate_node_cost(qm, child_id, migration_costs, memo)
        children_exec_costs.append(c_exec)
        children_rows.append(c_rows)
    
    input_rows_sum = sum(children_rows)
    exec_cost = 0.0
    
    # Cost calculation based on operator type
    # 単純加算方式：すべてのJOIN操作で統一
    # exec_cost = sum(children_costs) + self_cost
    # これにより、サンプリングで得られた正確な行数が親ノードのコストに反映される
    if operator in ('Nested Loop', 'Hash Join', 'Merge Join'):
        # すべてのJOIN: 子ノードのコストを累積 + 自ノードの処理コスト
        my_cost = input_rows_sum * CPU_OPERATOR_COST
        exec_cost = sum(children_exec_costs) + my_cost
    
    elif operator == 'Sort':
        # Sort: N log N
        if input_rows_sum > 1:
            my_cost = input_rows_sum * math.log(input_rows_sum, 2) * CPU_OPERATOR_COST
        else:
            my_cost = input_rows_sum * CPU_OPERATOR_COST
        exec_cost = sum(children_exec_costs) + my_cost
    
    elif operator == 'Aggregate':
        my_cost = input_rows_sum * CPU_OPERATOR_COST
        exec_cost = sum(children_exec_costs) + my_cost
    
    else:
        # Default: sum children costs + pass-through cost
        my_cost = input_rows_sum * CPU_TUPLE_COST
        exec_cost = sum(children_exec_costs) + my_cost
    
    # Calculate write cost for MV creation
    output_size = output_rows * width
    output_pages = math.ceil(output_size / BLOCK_SIZE) if output_size > 0 else 0
    write_cost = (output_pages * SEQ_PAGE_COST) + (output_rows * CPU_TUPLE_COST)
    creation_cost = exec_cost + write_cost
    
    # MV read cost
    mv_read_cost = (output_pages * SEQ_PAGE_COST) + (output_rows * CPU_TUPLE_COST)
    
    # Net utility = execution cost - MV read cost
    utility = max(0, exec_cost - mv_read_cost)
    
    memo[node_id] = (exec_cost, creation_cost, utility, output_rows)
    return exec_cost, creation_cost, utility, output_rows


def recalculate_costs(pickle_path: Path, json_input_path: Path, json_output_path: Path):
    """
    Main function to recalculate costs.
    
    Args:
        pickle_path: Path to the pickle file containing QueryParser
        json_input_path: Path to simple_migration_costs.json
        json_output_path: Path to save recalculated costs
    """
    print(f"Loading pickle from: {pickle_path}")
    qp = load_pickle(pickle_path)
    qm = qp.qm  # QueryManager
    
    print(f"Loading migration costs from: {json_input_path}")
    migration_costs = load_migration_costs(json_input_path)
    
    # Memoization dictionary for recursive calculation
    memo = {}
    
    updated_count = 0
    
    # Process all nodes
    all_nodes = list(qm.leaf_nodes_map_r.keys()) + list(qm.non_leaf_nodes_map_r.keys())
    print(f"Processing {len(all_nodes)} nodes...")
    
    for node_id in all_nodes:
        if node_id not in migration_costs:
            continue
        
        # Calculate cost using recursive method (now returns 4 values)
        exec_cost, creation_cost, utility, output_rows = calculate_node_cost(qm, node_id, migration_costs, memo)
        
        # Update the JSON data
        if "[]" in migration_costs[node_id]:
            migration_costs[node_id]["[]"]["cost"] = round(creation_cost, 2)  # 作成コスト
            migration_costs[node_id]["[]"]["utility"] = round(utility, 2)  # 利得
            migration_costs[node_id]["[]"]["exec_cost"] = round(exec_cost, 2)  # 実行コスト（デバッグ用）
            migration_costs[node_id]["[]"]["recalculated"] = True
            migration_costs[node_id]["[]"]["calc_method"] = "pickle_recursive_v2"
            updated_count += 1
    
    print(f"Updated {updated_count} nodes.")
    
    # Save to output file
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(migration_costs, f, indent=2, ensure_ascii=False)
    
    print(f"Saved recalculated costs to: {json_output_path}")


def main():
    parser = argparse.ArgumentParser(description="Recalculate MV costs using pickle-based node relationships")
    parser.add_argument(
        '--query-set',
        type=str,
        default='job',
        help='Query set to process (default: job)'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite input file instead of creating new output file'
    )
    args = parser.parse_args()
    
    # Paths
    base_dir = Path("/home/masuda/projects/mv-query-optimization/experiments/small_test_ver2")
    pickle_path = base_dir / "03_parsed" / args.query_set / "qp_class.pkl"
    json_input_path = base_dir / "04_migration" / args.query_set / "simple_migration_costs.json"
    
    if args.overwrite:
        json_output_path = json_input_path
    else:
        json_output_path = base_dir / "04_migration" / args.query_set / "simple_migration_costs_recalc.json"
    
    # Validate paths
    if not pickle_path.exists():
        print(f"Error: Pickle file not found at {pickle_path}")
        print("Please run Phase 2 (query parsing) first.")
        return 1
    
    if not json_input_path.exists():
        print(f"Error: Migration costs file not found at {json_input_path}")
        print("Please run Phase 5 (migration cost calculation) first.")
        return 1
    
    recalculate_costs(pickle_path, json_input_path, json_output_path)
    return 0


if __name__ == "__main__":
    exit(main())
