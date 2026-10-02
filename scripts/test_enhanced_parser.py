#!/usr/bin/env python
"""Test script to verify enhanced parser functionality with real queries.

This script loads a sample query from the dataset and verifies that
JOIN conditions are properly extracted and stored.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.query_parser import QueryParser
from config.settings import Settings


def test_enhanced_parser():
    """Test enhanced parser with a real query."""
    print("=" * 80)
    print("Testing Enhanced Parser with Real Query")
    print("=" * 80)
    
    # Load a sample query
    query_file = Path("dataset/RED_JSON/job/1a.json")
    
    if not query_file.exists():
        print(f"❌ Query file not found: {query_file}")
        return False
    
    print(f"\n📂 Loading query: {query_file}")
    
    with open(query_file) as f:
        query_data = json.load(f)
    
    # Create parser
    parser = QueryParser(Settings())
    
    # Convert the query
    print("\n🔄 Converting query plan...")
    subquery_list, deep_list, order_list = parser.convert_json(query_data, freq=1)
    
    print(f"\n✅ Converted {len(subquery_list)} nodes")
    print(f"   - Depth list: {len(deep_list)} items")
    print(f"   - Order list: {len(order_list)} items")
    
    # Count nodes with enhanced information
    enhanced_nodes = 0
    legacy_nodes = 0
    total_join_conditions = 0
    
    for node in subquery_list:
        if node["type"] == "non_leaf":
            if "join_conditions" in node and "join_type" in node:
                enhanced_nodes += 1
                total_join_conditions += len(node["join_conditions"])
                
                # Print details for first few enhanced nodes
                if enhanced_nodes <= 3:
                    print(f"\n📊 Enhanced Node #{enhanced_nodes}:")
                    print(f"   - Operator: {node['operator']}")
                    print(f"   - JOIN Type: {node['join_type']}")
                    print(f"   - JOIN Conditions: {len(node['join_conditions'])}")
                    
                    for i, jc in enumerate(node['join_conditions'], 1):
                        print(f"      {i}. {jc.left_table}.{jc.left_column} "
                              f"{jc.operator} {jc.right_table}.{jc.right_column}")
                        print(f"         Type: {jc.condition_type}")
                        print(f"         Original: {jc.original_text}")
            else:
                legacy_nodes += 1
    
    print(f"\n📈 Statistics:")
    print(f"   - Enhanced non-leaf nodes: {enhanced_nodes}")
    print(f"   - Legacy non-leaf nodes: {legacy_nodes}")
    print(f"   - Total JOIN conditions extracted: {total_join_conditions}")
    
    # Process with QueryManager
    print("\n🔧 Processing with QueryManager...")
    
    for j, subquery in zip(order_list, subquery_list):
        result = parser.qm.depth_first_search(subquery, [0, j])
    
    # Check enhanced data in QueryManager
    enhanced_in_qm = len(parser.qm.non_leaf_nodes_info)
    join_conds_in_qm = len(parser.qm.join_conditions)
    
    print(f"\n✅ QueryManager Statistics:")
    print(f"   - Leaf nodes: {len(parser.qm.leaf_nodes_map)}")
    print(f"   - Non-leaf nodes: {len(parser.qm.non_leaf_nodes_map)}")
    print(f"   - Enhanced node info stored: {enhanced_in_qm}")
    print(f"   - JOIN conditions stored: {join_conds_in_qm}")
    
    # Show sample enhanced node info
    if parser.qm.non_leaf_nodes_info:
        print("\n🔍 Sample Enhanced Node Info:")
        sample_id = list(parser.qm.non_leaf_nodes_info.keys())[0]
        sample_info = parser.qm.non_leaf_nodes_info[sample_id]
        
        print(f"   Node ID: {sample_id}")
        print(f"   Operator: {sample_info.operator}")
        print(f"   JOIN Type: {sample_info.join_type}")
        print(f"   Children: {sample_info.children}")
        print(f"   JOIN Conditions: {len(sample_info.join_conditions)}")
        
        for i, jc in enumerate(sample_info.join_conditions, 1):
            print(f"      {i}. {jc.left_table}.{jc.left_column} "
                  f"{jc.operator} {jc.right_table}.{jc.right_column}")
    
    # Verify backward compatibility
    print("\n✅ Backward Compatibility Check:")
    print(f"   - Old-style non_leaf_nodes_map: {len(parser.qm.non_leaf_nodes_map)} entries")
    print(f"   - Old-style non_leaf_nodes_map_r: {len(parser.qm.non_leaf_nodes_map_r)} entries")
    
    success = (
        enhanced_nodes > 0 and
        total_join_conditions > 0 and
        enhanced_in_qm > 0
    )
    
    if success:
        print("\n" + "=" * 80)
        print("✅ SUCCESS: Enhanced parser is working correctly!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("⚠️  WARNING: Some features may not be working as expected")
        print("=" * 80)
    
    return success


if __name__ == "__main__":
    success = test_enhanced_parser()
    sys.exit(0 if success else 1)
