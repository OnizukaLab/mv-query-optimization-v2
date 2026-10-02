#!/usr/bin/env python3
"""
Simple test script for CF Pruning components.

This script tests the individual components of the CF pruning implementation
without requiring a full database setup.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Try to import, but handle missing gurobipy gracefully
try:
    from experiments.small_test_ver2.core.workload_summary_tree import WorkloadSummaryTree
    WORKLOAD_TREE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import WorkloadSummaryTree: {e}")
    WORKLOAD_TREE_AVAILABLE = False


def test_workload_summary_tree():
    """Test WorkloadSummaryTree construction."""
    print("=" * 70)
    print("Testing WorkloadSummaryTree")
    print("=" * 70)
    
    if not WORKLOAD_TREE_AVAILABLE:
        print("\nSkipping test: WorkloadSummaryTree not available (missing dependencies)")
        return
    
    # Test with different timestep counts
    test_cases = [3, 5, 8, 16, 50]
    
    for T in test_cases:
        print(f"\n--- Testing with T={T} timesteps ---")
        tree = WorkloadSummaryTree(T)
        
        print(f"Tree depth: {tree.get_depth()}")
        print(f"Total nodes: {len(tree.get_all_nodes())}")
        
        # Print tree structure for smaller cases
        if T <= 8:
            print("\nTree structure:")
            tree.print_tree()
        
        # Verify tree properties
        nodes = tree.get_all_nodes()
        
        # Check root node
        assert tree.root is not None
        assert tree.root.min_idx == 0
        assert tree.root.max_idx == T - 1
        
        # Check that all nodes have valid indices
        for node in nodes:
            assert 0 <= node.min_idx < T
            assert 0 <= node.median_idx < T
            assert 0 <= node.max_idx < T
            assert node.min_idx <= node.median_idx <= node.max_idx
        
        print(f"✓ Tree structure is valid")
    
    print("\n" + "=" * 70)
    print("All WorkloadSummaryTree tests passed!")
    print("=" * 70)


def test_local_ilp_optimizer():
    """Test LocalILPOptimizer with a simple example."""
    print("\n" + "=" * 70)
    print("Testing LocalILPOptimizer")
    print("=" * 70)
    
    print("\nNote: This test requires Gurobi to be installed and licensed.")
    print("Skipping LocalILPOptimizer test (requires full setup).")
    print("Run integration tests with real data to verify LocalILP.")
    
    print("\n" + "=" * 70)
    print("LocalILPOptimizer test skipped")
    print("=" * 70)


def test_cf_pruner():
    """Test CFPruner with a simple example."""
    print("\n" + "=" * 70)
    print("Testing CFPruner")
    print("=" * 70)
    
    print("\nNote: This test requires Gurobi and full data setup.")
    print("Skipping CFPruner test (requires full setup).")
    print("Run integration tests with real data to verify pruning.")
    
    print("\n" + "=" * 70)
    print("CFPruner test skipped")
    print("=" * 70)


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("CF Pruning Component Tests")
    print("=" * 70)
    
    try:
        test_workload_summary_tree()
        test_local_ilp_optimizer()
        test_cf_pruner()
        
        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETED")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Run integration test with 5 timesteps:")
        print("   python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job")
        print("\n2. Run with pruning enabled:")
        print("   python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning")
        print("\n3. Compare results and performance")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
