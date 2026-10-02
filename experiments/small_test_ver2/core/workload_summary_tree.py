"""Workload Summary Tree for CF Pruning.

This module implements the Workload Summary Tree data structure
used in Section 4.3 of the paper for CF (MV) candidate pruning.

The tree hierarchically divides the full timestep range into smaller
sub-ranges, with each node representing 3 representative timesteps:
min (start), median (middle), and max (end).
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class TreeNode:
    """A node in the Workload Summary Tree.
    
    Each node represents a time range with three representative timesteps:
    - min_idx: Start of the range
    - median_idx: Middle of the range
    - max_idx: End of the range
    
    Attributes:
        min_idx: Index of the minimum (start) timestep
        median_idx: Index of the median (middle) timestep
        max_idx: Index of the maximum (end) timestep
        left_child: Left child node (first half of range)
        right_child: Right child node (second half of range)
        is_leaf: True if this is a leaf node (no children)
        depth: Depth of this node in the tree (root is 0)
    """
    
    def __init__(
        self,
        min_idx: int,
        median_idx: int,
        max_idx: int,
        depth: int = 0
    ):
        """Initialize a tree node.
        
        Args:
            min_idx: Index of the minimum (start) timestep
            median_idx: Index of the median (middle) timestep
            max_idx: Index of the maximum (end) timestep
            depth: Depth in the tree (root is 0)
        """
        self.min_idx = min_idx
        self.median_idx = median_idx
        self.max_idx = max_idx
        self.depth = depth
        
        self.left_child: Optional[TreeNode] = None
        self.right_child: Optional[TreeNode] = None
        self.is_leaf = True  # Will be set to False when children are added
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"TreeNode(min={self.min_idx}, med={self.median_idx}, max={self.max_idx}, depth={self.depth}, leaf={self.is_leaf})"


class WorkloadSummaryTree:
    """Workload Summary Tree for hierarchical timestep representation.
    
    This tree divides the full timestep range [0, T-1] into a binary tree
    where each node represents a sub-range with 3 representative timesteps.
    
    The tree is used for CF pruning: by solving local ILPs at each node
    with only 3 timesteps, we can identify promising MVs efficiently.
    
    Nodes are split only if:
    - The range is >= 3 (i.e., 4 or more timesteps)
    - Child nodes would have >= 3 timesteps (range >= 2)
    
    This prevents creating 2-timestep nodes that add no new information.
    
    Example:
        For T=8 timesteps [0,1,2,3,4,5,6,7]:
        
        Root: (0, 3, 7)
        ├─ Left:  (0, 1, 3)
        │  └─ Right: (1, 2, 3) [leaf]  # (0,0,1) not created (range=1)
        └─ Right: (3, 5, 7)
           ├─ Left:  (3, 4, 5) [leaf]
           └─ Right: (5, 6, 7) [leaf]
        
        Total: 5 nodes (not 7)
        
        For T=5 timesteps [0,1,2,3,4]:
        
        Root: (0, 2, 4)
        ├─ Left:  (0, 1, 2) [leaf]  # range=2, don't split
        └─ Right: (2, 3, 4) [leaf]  # range=2, don't split
        
        Total: 3 nodes
    """
    
    def __init__(self, timestep_count: int):
        """Initialize the Workload Summary Tree.
        
        Args:
            timestep_count: Total number of timesteps (T)
        
        Raises:
            ValueError: If timestep_count < 3
        """
        if timestep_count < 3:
            raise ValueError(f"Need at least 3 timesteps, got {timestep_count}")
        
        self.timestep_count = timestep_count
        self.root: Optional[TreeNode] = None
        self._build_tree()
        
        logger.info(f"Built Workload Summary Tree for {timestep_count} timesteps")
    
    def _build_tree(self) -> None:
        """Build the binary tree recursively."""
        min_idx = 0
        max_idx = self.timestep_count - 1
        median_idx = (min_idx + max_idx) // 2
        
        self.root = TreeNode(min_idx, median_idx, max_idx, depth=0)
        self._split_node(self.root)
    
    def _split_node(self, node: TreeNode) -> None:
        """Recursively split a node into left and right children.
        
        A node is NOT split if it already represents exactly 3 timesteps,
        as this is the optimal size for Local ILP optimization.
        
        Args:
            node: Node to split
        """
        # Check if we should split further
        # Stop if the range is too small (< 3 means 3 or fewer timesteps)
        if node.max_idx - node.min_idx < 3:
            # 3 or fewer timesteps - don't split further
            return
        
        # Create left child: [min, median]
        left_min = node.min_idx
        left_max = node.median_idx
        left_median = (left_min + left_max) // 2
        
        # Create right child: [median, max]
        right_min = node.median_idx
        right_max = node.max_idx
        right_median = (right_min + right_max) // 2
        
        # Only create left child if it has at least 3 distinct timesteps
        # Check: left_max - left_min >= 2 (range of at least 2 = 3 timesteps)
        if left_max - left_min >= 2:
            node.left_child = TreeNode(
                left_min, left_median, left_max,
                depth=node.depth + 1
            )
            node.is_leaf = False
            self._split_node(node.left_child)
        
        # Only create right child if it has at least 3 distinct timesteps
        if right_max - right_min >= 2:
            node.right_child = TreeNode(
                right_min, right_median, right_max,
                depth=node.depth + 1
            )
            node.is_leaf = False
            self._split_node(node.right_child)
    
    def get_all_nodes(self) -> List[TreeNode]:
        """Get all nodes in the tree in breadth-first order.
        
        Returns:
            List of all TreeNode objects (root first, then level by level)
        """
        if self.root is None:
            return []
        
        nodes = []
        queue = [self.root]
        
        while queue:
            node = queue.pop(0)
            nodes.append(node)
            
            if node.left_child:
                queue.append(node.left_child)
            if node.right_child:
                queue.append(node.right_child)
        
        return nodes
    
    def get_depth(self) -> int:
        """Get the depth of the tree (number of levels).
        
        Returns:
            Maximum depth (root is depth 0)
        """
        if self.root is None:
            return 0
        
        max_depth = 0
        for node in self.get_all_nodes():
            max_depth = max(max_depth, node.depth)
        
        return max_depth
    
    def print_tree(self) -> None:
        """Print tree structure for debugging."""
        if self.root is None:
            print("Empty tree")
            return
        
        print(f"Workload Summary Tree (T={self.timestep_count}):")
        print(f"Depth: {self.get_depth()}")
        print(f"Total nodes: {len(self.get_all_nodes())}")
        print("\nTree structure:")
        
        for node in self.get_all_nodes():
            indent = "  " * node.depth
            leaf_marker = " [LEAF]" if node.is_leaf else ""
            print(f"{indent}{node}{leaf_marker}")
