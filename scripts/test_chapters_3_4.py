"""Test script for Chapters 3 & 4 implementation.

This script demonstrates:
- SchemaProvider: Dynamic schema retrieval from PostgreSQL
- EnhancedMVGenerator: Accurate MV SQL generation with proper JOINs
"""

import json
import logging
from pathlib import Path

from src.core.query_parser import QueryParser
from src.core.query_manager import QueryManager
from src.rewrite.schema_provider import SchemaProvider
from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_schema_provider():
    """Test SchemaProvider functionality."""
    print("\n" + "="*80)
    print("Testing SchemaProvider (Chapter 3)")
    print("="*80)
    
    # Initialize SchemaProvider (will use fallback if psycopg2 not available)
    provider = SchemaProvider()
    
    # Test 1: Get table columns
    print("\n[Test 1] Getting columns for 'title' table:")
    try:
        columns = provider.get_table_columns('title')
        print(f"  Found {len(columns)} columns: {columns[:5]}..." if len(columns) > 5 else f"  Found {len(columns)} columns: {columns}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 2: Get foreign key relations
    print("\n[Test 2] Getting FK relations between 'cast_info' and 'title':")
    try:
        fk_relations = provider.get_foreign_key_relations(['cast_info'], ['title'])
        if fk_relations:
            for fk in fk_relations:
                print(f"  {fk.from_table}.{fk.from_column} -> {fk.to_table}.{fk.to_column}")
        else:
            print("  No FK relations found (using fallback schema)")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 3: Get primary key
    print("\n[Test 3] Getting primary key for 'title' table:")
    try:
        pk = provider.get_primary_key('title')
        print(f"  Primary key: {pk}")
    except Exception as e:
        print(f"  Error: {e}")
    
    return provider


def test_enhanced_mv_generator_with_query():
    """Test EnhancedMVGenerator with a synthetic query."""
    print("\n" + "="*80)
    print("Testing EnhancedMVGenerator with Synthetic Query (Chapter 4)")
    print("="*80)
    
    test_synthetic_query()


def test_synthetic_query():
    """Test with a synthetic query that has JOIN conditions."""
    print("\n[Using Synthetic Query with JOINs]")
    
    # Create QueryManager
    qm = QueryManager()
    
    # Add leaf nodes
    qm.process_leaf_node(
        "Seq Scan", "title", "t",
        "(production_year > 2000)",
        [0, 0], 30.0, 12500, 25
    )
    qm.process_leaf_node(
        "Seq Scan", "cast_info", "ci", "",
        [0, 1], 50.0, 125000, 25
    )
    
    # Add non-leaf node with enhanced info using v2 method
    from src.core.models import JoinCondition
    join_cond = JoinCondition(
        left_table="t",
        left_column="id",
        operator="=",
        right_table="ci",
        right_column="movie_id",
        condition_type="Hash Cond",
        original_text="(t.id = ci.movie_id)"
    )
    
    node_id = qm.process_non_leaf_node_v2(
        operator="Hash Join",
        join_type="Inner",
        child_node_ids=['leaf_1', 'leaf_2'],
        join_conditions=[join_cond],
        filters=[],
        position=[0, 2],
        total_cost=100.0,
        rows=1000,
        width=50
    )
    
    print(f"\nQuery Statistics:")
    print(f"  Leaf nodes: {len(qm.leaf_nodes_map_r)}")
    print(f"  Non-leaf nodes: {len(qm.non_leaf_nodes_map)}")
    print(f"  Enhanced info: {len(qm.non_leaf_nodes_info)}")
    print(f"  JOIN conditions: {len(qm.join_conditions)}")
    
    # Generate SQL
    schema_provider = SchemaProvider()
    generator = EnhancedMVGenerator(qm, schema_provider)
    
    print(f"\n[Non-Leaf Node with Enhanced Info: {node_id}]")
    try:
        sql = generator.generate_non_leaf_mv_sql(node_id)
        print("Generated SQL:")
        print(sql)
    except Exception as e:
        print(f"Error: {e}")


def test_backward_compatibility():
    """Test backward compatibility with nodes without enhanced info."""
    print("\n" + "="*80)
    print("Testing Backward Compatibility")
    print("="*80)
    
    # Create a QueryManager with legacy nodes (no enhanced info)
    qm = QueryManager()
    
    # Add some leaf nodes
    qm.process_leaf_node(
        "Seq Scan", "title", "t",
        "(production_year > 2000)",
        [0, 0], 30.0, 12500, 25
    )
    qm.process_leaf_node(
        "Seq Scan", "cast_info", "ci", "",
        [0, 1], 50.0, 125000, 25
    )
    
    # Add non-leaf node using old method (no enhanced info)
    node_id = qm.process_non_leaf_node(
        ['leaf_1', 'leaf_2'],
        [0, 2], 100.0, 50000, 50
    )
    
    print(f"\nCreated nodes:")
    print(f"  Leaf nodes: 2")
    print(f"  Non-leaf nodes (legacy): 1")
    print(f"  Enhanced info available: {len(qm.non_leaf_nodes_info)}")
    
    # Try to generate SQL with EnhancedMVGenerator
    schema_provider = SchemaProvider()
    generator = EnhancedMVGenerator(qm, schema_provider)
    
    print(f"\n[Testing with legacy non-leaf node: {node_id}]")
    try:
        sql = generator.generate_non_leaf_mv_sql(node_id)
        print("  ✓ Successfully generated SQL (using fallback)")
        print("  " + sql[:200] + "..." if len(sql) > 200 else "  " + sql)
    except Exception as e:
        print(f"  ✗ Error: {e}")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("Testing Chapters 3 & 4 Implementation")
    print("="*80)
    
    # Test SchemaProvider
    schema_provider = test_schema_provider()
    
    # Test EnhancedMVGenerator with real query
    test_enhanced_mv_generator_with_query()
    
    # Test backward compatibility
    test_backward_compatibility()
    
    print("\n" + "="*80)
    print("All tests completed!")
    print("="*80)


if __name__ == "__main__":
    main()
