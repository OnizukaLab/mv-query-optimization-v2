"""Data models for query optimization.

This module defines the core data structures used throughout the application,
including query nodes, materialized views, and optimization results.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class QueryNode:
    """Base class for query plan nodes.

    Attributes:
        node_id: Unique identifier for the node
        total_cost: Total cost of executing this node
        size: Size of the result set (rows * width)
        width: Width of the result tuples in bytes
    """

    node_id: str
    total_cost: float
    size: int
    width: int


@dataclass
class LeafNode(QueryNode):
    """Leaf node representing a table scan.

    Attributes:
        operator: Operator type (e.g., 'Seq Scan', 'Index Scan')
        table_name: Name of the table being scanned
        alias: Alias used in the query
        filter_condition: Filter condition applied to the scan
    """

    operator: str
    table_name: str
    alias: str
    filter_condition: str


@dataclass
class NonLeafNode(QueryNode):
    """Non-leaf node representing a join or other operation.

    Attributes:
        child_ids: Tuple of child node IDs
        operator: Operator type (e.g., 'Hash Join', 'Merge Join')
        filter_condition: Filter condition applied after the operation
    """

    child_ids: tuple[str, ...]
    operator: str
    filter_condition: str = ""


@dataclass
class MaterializedView:
    """Represents a materialized view candidate.

    Attributes:
        view_id: Unique identifier for the view
        node_id: ID of the query node this view corresponds to
        create_sql: SQL statement to create the materialized view
        size: Storage size of the view in bytes
        maintenance_cost: Cost of maintaining the view during updates
        usage_positions: List of [query_id, position] where this view is used
        index_sql: SQL statement to create index on the MV (if needed)
    """

    view_id: str
    node_id: str
    create_sql: str
    size: int
    maintenance_cost: float
    usage_positions: list[list[int]] = field(default_factory=list)
    index_sql: str | None = None  # CREATE INDEX statement if needed


@dataclass
class OptimizationResult:
    """Result of an optimization algorithm run.

    Attributes:
        algorithm: Name of the algorithm used
        selected_views: List of selected materialized views
        total_utility: Total utility achieved
        total_storage: Total storage used in bytes
        execution_time: Time taken for optimization in seconds
        metadata: Additional algorithm-specific metadata
    """

    algorithm: str
    selected_views: list[MaterializedView]
    total_utility: float
    total_storage: int
    execution_time: float
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert optimization result to dictionary.
        
        Note: Large arrays like y_ij and z_j are excluded from metadata
        to keep JSON file size manageable. Use usage_positions in selected_views
        instead for query-MV mapping.
        
        Returns:
            Dictionary representation of the result
        """
        # Filter out large arrays from metadata to reduce file size
        # y_ij can be millions of elements (queries x nodes), which would make JSON GB-sized
        filtered_metadata = {
            k: v for k, v in self.metadata.items() 
            if k not in ('y_ij', 'z_j', 'node_list')
        }
        
        return {
            "algorithm": self.algorithm,
            "total_utility": self.total_utility,
            "total_storage": self.total_storage,
            "total_storage_mb": round(self.total_storage / (1024 * 1024), 2),
            "execution_time": self.execution_time,
            "num_selected_views": len(self.selected_views),
            "selected_views": [
                {
                    "view_id": mv.view_id,
                    "node_id": mv.node_id,
                    "create_sql": mv.create_sql,  # ← SQLを保存
                    "index_sql": mv.index_sql,  # ← インデックスSQLを保存
                    "size": mv.size,
                    "size_mb": round(mv.size / (1024 * 1024), 2),
                    "maintenance_cost": mv.maintenance_cost,
                    "usage_count": len(mv.usage_positions),
                    "usage_positions": mv.usage_positions,  # ← 使用位置も保存
                }
                for mv in self.selected_views
            ],
            "metadata": filtered_metadata,
        }
    
    def save_to_json(self, output_path: str) -> None:
        """Save optimization result to JSON file.
        
        Args:
            output_path: Path to output JSON file
        """
        import json
        from pathlib import Path
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_json(cls, json_path: str) -> "OptimizationResult":
        """Load optimization result from JSON file.
        
        Args:
            json_path: Path to JSON file
            
        Returns:
            OptimizationResult object
        """
        import json
        from pathlib import Path
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct MaterializedView objects
        selected_views = [
            MaterializedView(
                view_id=mv_data["view_id"],
                node_id=mv_data["node_id"],
                create_sql=mv_data["create_sql"],
                size=mv_data["size"],
                maintenance_cost=mv_data["maintenance_cost"],
                usage_positions=mv_data.get("usage_positions", []),
            )
            for mv_data in data["selected_views"]
        ]
        
        return cls(
            algorithm=data["algorithm"],
            selected_views=selected_views,
            total_utility=data["total_utility"],
            total_storage=data["total_storage"],
            execution_time=data["execution_time"],
            metadata=data.get("metadata", {}),
        )
    
    def save_to_csv(self, output_path: str) -> None:
        """Save selected MVs to CSV file (legacy format).
        
        This maps each query to the MVs that are ACTUALLY USED by that query.
        Primary method uses usage_positions from selected MVs.
        Fallback uses y_ij if usage_positions is not available.
        
        Args:
            output_path: Path to output CSV file
        """
        from pathlib import Path
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create a mapping of query_id -> list of node_ids
        query_mv_map: dict[int, list[str]] = {}
        
        # Primary method: use usage_positions from selected_views
        # This is more reliable as it directly maps MVs to queries
        has_usage_positions = any(mv.usage_positions for mv in self.selected_views)
        
        if has_usage_positions:
            # Use usage_positions - each MV knows which queries use it
            for mv in self.selected_views:
                for query_id, _ in mv.usage_positions:
                    if query_id not in query_mv_map:
                        query_mv_map[query_id] = []
                    query_mv_map[query_id].append(mv.node_id)
        else:
            # Fallback: use y_ij from metadata
            y_ij = self.metadata.get('y_ij')
            node_list = self.metadata.get('node_list')
            
            if y_ij is not None and node_list is not None:
                # Build a set of selected node indices from selected_views
                selected_node_ids = {mv.node_id for mv in self.selected_views}
                
                # For each query, collect the node_ids where y_ij[i][j] == 1
                for i, query_row in enumerate(y_ij):
                    for j, used in enumerate(query_row):
                        if used == 1:
                            node_id = node_list[j]
                            # Only include if this node is in our selected MVs
                            if node_id in selected_node_ids:
                                if i not in query_mv_map:
                                    query_mv_map[i] = []
                                query_mv_map[i].append(node_id)
        
        # Write CSV file
        with open(output_path, 'w', encoding='utf-8') as f:
            # Find max query_id to determine number of rows
            max_query_id = max(query_mv_map.keys()) if query_mv_map else 0
            
            for query_id in range(max_query_id + 1):
                if query_id in query_mv_map:
                    f.write(','.join(query_mv_map[query_id]) + '\n')
                else:
                    f.write('NONE\n')


@dataclass
class QueryPlan:
    """Represents a complete query plan.

    Attributes:
        query_id: Unique identifier for the query
        root_node_id: ID of the root node in the plan tree
        frequency: Frequency of query execution
        original_cost: Original cost without materialized views
        subquery_list: List of subquery nodes in execution order
        depth_list: List of depths for each node
    """

    query_id: int
    root_node_id: str
    frequency: int
    original_cost: float
    subquery_list: list[dict[str, Any]] = field(default_factory=list)
    depth_list: list[int] = field(default_factory=list)


# ============================================================================
# Enhanced Data Structures for JOIN Condition Tracking (Chapter 1)
# ============================================================================


@dataclass
class ColumnRef:
    """Column reference information.
    
    Attributes:
        table: Table name or alias
        column: Column name
        alias: Optional column alias in SELECT clause
    """
    table: str
    column: str
    alias: Optional[str] = None


@dataclass
class JoinCondition:
    """JOIN condition details.
    
    This class stores complete information about a JOIN condition extracted
    from PostgreSQL EXPLAIN JSON output.
    
    Attributes:
        left_table: Left table name or alias
        left_column: Left column name
        operator: Comparison operator (=, <, >, <=, >=, !=)
        right_table: Right table name or alias
        right_column: Right column name
        condition_type: Type of condition (Hash Cond, Merge Cond, Join Filter, Index Cond)
        original_text: Original condition text from EXPLAIN JSON (e.g., "(t.id = ci.movie_id)")
    """
    left_table: str
    left_column: str
    operator: str
    right_table: str
    right_column: str
    condition_type: str
    original_text: str


@dataclass
class NonLeafNodeInfo:
    """Detailed information for non-leaf nodes.
    
    This class stores comprehensive information about JOIN operations,
    including the exact JOIN conditions, operator type, and filters.
    This is an enhanced version that preserves much more information
    than the simple tuple-based representation.
    
    Attributes:
        node_id: Unique identifier for this node
        operator: Operator type (Hash Join, Merge Join, Nested Loop, etc.)
        join_type: JOIN type (Inner, Left, Right, Full, Semi, Anti)
        children: List of child node IDs (order preserved, NOT sorted)
        join_conditions: List of JOIN conditions with full details
        filters: Additional WHERE clause filters applied after JOIN
        output_columns: Optional list of output columns
        cost: Total cost of this operation
        rows: Estimated number of rows produced
        width: Width of result tuples in bytes
    """
    node_id: str
    operator: str
    join_type: str
    children: list[str]
    join_conditions: list[JoinCondition] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    output_columns: Optional[list[ColumnRef]] = None
    cost: float = 0.0
    rows: int = 0
    width: int = 1

