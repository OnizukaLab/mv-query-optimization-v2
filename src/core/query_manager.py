"""Query manager for handling query nodes and their relationships.

This module provides the QueryManager class which manages the mapping
between query nodes (leaf and non-leaf) and their properties.
"""

from typing import Any

from .models import NonLeafNodeInfo, JoinCondition


class QueryManager:
    """Manages query nodes and their relationships.

    This class maintains mappings between query node properties and their IDs,
    handles node creation with deduplication, and tracks node positions,
    costs, and sizes.

    Attributes:
        leaf_nodes_map: Maps (operator, table, alias, filter) to leaf node ID
        leaf_nodes_map_r: Reverse map from leaf node ID to properties tuple
        non_leaf_nodes_map: Maps sorted child IDs tuple to non-leaf node ID
        non_leaf_nodes_map_r: Reverse map from non-leaf node ID to child IDs
        non_leaf_nodes_filter: Maps non-leaf node ID to filter condition
        leaf_id_counter: Counter for generating unique leaf node IDs
        non_leaf_id_counter: Counter for generating unique non-leaf node IDs
        subquery_positions: Maps node ID to list of [query_id, position] pairs
        subquery_costs: Maps node ID to total cost
        subquery_sizes: Maps node ID to size (rows * width)
        relation_tables: Maps leaf node ID to table name
        subquery_widths: Maps node ID to width in bytes
    """

    def __init__(self) -> None:
        """Initialize the QueryManager with empty mappings."""
        # Leaf node mappings
        self.leaf_nodes_map: dict[tuple[str, str, str, str], str] = {}
        self.leaf_nodes_map_r: dict[str, tuple[str, str, str, str]] = {}

        # Non-leaf node mappings
        self.non_leaf_nodes_map: dict[tuple[str, ...], str] = {}
        self.non_leaf_nodes_map_r: dict[str, tuple[str, ...]] = {}
        self.non_leaf_nodes_filter: dict[str, str] = {}

        # Enhanced: Non-leaf node detailed information (Chapter 1)
        self.non_leaf_nodes_info: dict[str, NonLeafNodeInfo] = {}
        
        # Enhanced: JOIN conditions mapping (Chapter 1)
        self.join_conditions: dict[str, list[JoinCondition]] = {}
        
        # Enhanced: Operator information (Chapter 1)
        self.node_operators: dict[str, str] = {}

        # ID counters
        self.leaf_id_counter: int = 0
        self.non_leaf_id_counter: int = 0

        # Node properties
        self.subquery_positions: dict[str, list[list[int]]] = {}
        self.subquery_costs: dict[str, float] = {}
        self.original_subquery_costs: dict[str, float] = {}  # EXPLAIN JSONから取得した元のコスト
        self.subquery_sizes: dict[str, int] = {}
        self.relation_tables: dict[str, str] = {}
        self.subquery_widths: dict[str, int] = {}
        self.subquery_rows: dict[str, int] = {}  # ノードの推定行数
        
        # Index build cost for Index Scan nodes
        # This is used for optimization phase to consider index creation cost
        self.index_build_costs: dict[str, float] = {}  # node_id -> index build cost
        self.requires_index_build: dict[str, bool] = {}  # node_id -> whether index is needed
        
        # Index information for CREATE INDEX generation
        # Stores the columns that should be indexed for each node
        self.index_columns: dict[str, list[str]] = {}  # node_id -> list of column names

        # 元SQLから抽出したJOIN条件（クエリインデックス → 条件リスト）
        # 各条件は (left_alias, left_column, right_alias, right_column) のタプル
        self.original_query_join_conditions: dict[int, list[tuple[str, str, str, str]]] = {}
        # 元SQLから抽出したエイリアスマッピング（クエリインデックス → {alias: table_name}）
        self.original_query_aliases: dict[int, dict[str, str]] = {}

    def _generate_unique_id(self, prefix: str) -> str:
        """Generate a unique ID for a query node.

        Args:
            prefix: Type of node ('leaf' or 'non_leaf')

        Returns:
            Unique node ID string

        Raises:
            ValueError: If prefix is not 'leaf' or 'non_leaf'
        """
        if prefix == "leaf":
            self.leaf_id_counter += 1
            return f"leaf_{self.leaf_id_counter}"
        elif prefix == "non_leaf":
            self.non_leaf_id_counter += 1
            return f"non_leaf_{self.non_leaf_id_counter}"
        else:
            raise ValueError(f"Invalid prefix: {prefix}. Must be 'leaf' or 'non_leaf'")

    def process_leaf_node(
        self,
        operator_name: str,
        table_name: str,
        alias: str,
        filter_condition: str,
        position: list[int],
        total_cost: float,
        original_cost: float,  # EXPLAIN JSONの生のコスト
        size: int,
        width: int,
        rows: int = 0,  # 推定行数（index build cost計算用）
        index_build_cost_per_row: float = 1.0,  # 1行あたりのインデックス構築コスト
        index_columns: list[str] | None = None,  # インデックス対象のカラム名リスト
    ) -> str:
        """Process a leaf node (table scan).

        If a leaf node with the same properties already exists, returns its ID.
        Otherwise, creates a new leaf node and returns the new ID.

        For Index Scan nodes, calculates and stores the index build cost
        which is used in optimization phase.

        Args:
            operator_name: Operator type (e.g., 'Seq Scan', 'Index Scan')
            table_name: Name of the table being scanned
            alias: Alias used in the query
            filter_condition: Filter condition applied
            position: [query_id, position] in the query plan
            total_cost: Cost of executing this node (adjusted for MV selection)
            original_cost: Original cost from EXPLAIN JSON Total Cost
            size: Size of result set (rows * width)
            width: Width of result tuples in bytes
            rows: Estimated number of rows (for index build cost calculation)
            index_build_cost_per_row: Cost to insert one row into index (default: 1.0)
            index_columns: List of column names to index (for Index Scan nodes)

        Returns:
            Node ID for this leaf node
        """
        key = (operator_name, table_name, alias, filter_condition)

        # Check if this leaf node already exists
        if key in self.leaf_nodes_map:
            node_id = self.leaf_nodes_map[key]
        else:
            # Create new leaf node
            node_id = self._generate_unique_id("leaf")
            self.leaf_nodes_map[key] = node_id
            self.leaf_nodes_map_r[node_id] = key

        # Update position if valid
        if position[0] != -1:
            if node_id in self.subquery_positions:
                self.subquery_positions[node_id].append(position)
            else:
                self.subquery_positions[node_id] = [position]

        # Update cost (keep minimum cost)
        if node_id in self.subquery_costs:
            if self.subquery_costs[node_id] >= total_cost:
                self.subquery_costs[node_id] = total_cost
        else:
            self.subquery_costs[node_id] = total_cost
        
        # original_subquery_costsは常にEXPLAIN JSONの生の値を保存
        # 初回設定時のみ保存（後で最小値に更新しない）
        if node_id not in self.original_subquery_costs:
            self.original_subquery_costs[node_id] = original_cost

        # Update other properties
        self.subquery_sizes[node_id] = size
        self.relation_tables[node_id] = table_name
        self.subquery_widths[node_id] = width
        
        # Store row count
        if rows > 0:
            self.subquery_rows[node_id] = rows
        elif width > 0:
            self.subquery_rows[node_id] = size // width
        else:
            self.subquery_rows[node_id] = size
        
        # Calculate index build cost for Index Scan nodes
        # Index Scan means the original query uses an index, so the MV should also have an index
        is_index_scan = "Index" in operator_name and "Scan" in operator_name
        self.requires_index_build[node_id] = is_index_scan
        
        if is_index_scan:
            # Index build cost = insert_cost_per_row × number_of_rows
            # This models building an index as inserting all rows
            node_rows = self.subquery_rows[node_id]
            self.index_build_costs[node_id] = index_build_cost_per_row * node_rows
            
            # Store index columns for CREATE INDEX generation
            if index_columns:
                self.index_columns[node_id] = index_columns
        else:
            self.index_build_costs[node_id] = 0.0

        return node_id

    def process_non_leaf_node(
        self,
        child_node_ids: list[str],
        position: list[int],
        total_cost: float,
        size: int,
        width: int,
        filter_condition: str = "",
    ) -> str:
        """Process a non-leaf node (join, aggregation, etc.).

        If a non-leaf node with the same children already exists, returns its ID.
        Otherwise, creates a new non-leaf node and returns the new ID.

        Args:
            child_node_ids: List of child node IDs
            position: [query_id, position] in the query plan
            total_cost: Cost of executing this node
            size: Size of result set (rows * width)
            width: Width of result tuples in bytes
            filter_condition: Filter condition applied after operation

        Returns:
            Node ID for this non-leaf node
        """
        # Create key from sorted child IDs for deduplication
        key = tuple(sorted(child_node_ids))

        # Check if this non-leaf node already exists
        if key in self.non_leaf_nodes_map:
            node_id = self.non_leaf_nodes_map[key]
        else:
            # Create new non-leaf node
            node_id = self._generate_unique_id("non_leaf")
            self.non_leaf_nodes_map[key] = node_id
            self.non_leaf_nodes_map_r[node_id] = key

        # Update position if valid
        if position[0] != -1:
            if node_id in self.subquery_positions:
                self.subquery_positions[node_id].append(position)
            else:
                self.subquery_positions[node_id] = [position]

        # Update properties
        self.non_leaf_nodes_filter[node_id] = filter_condition
        self.subquery_costs[node_id] = total_cost
        # 初回設定時のみoriginal_subquery_costsにも保存
        if node_id not in self.original_subquery_costs:
            self.original_subquery_costs[node_id] = total_cost
        self.subquery_sizes[node_id] = size
        self.subquery_widths[node_id] = width

        return node_id

    def process_non_leaf_node_v2(
        self,
        operator: str,
        join_type: str,
        child_node_ids: list[str],
        join_conditions: list[JoinCondition],
        filters: list[str],
        position: list[int],
        total_cost: float,
        original_cost: float,  # EXPLAIN JSONの生のコスト
        rows: int,
        width: int,
        output_columns: list | None = None,
    ) -> str:
        """Process a non-leaf node with enhanced information (Chapter 1 & 2).

        This is an enhanced version of process_non_leaf_node that preserves
        detailed JOIN condition information instead of losing it.

        Args:
            operator: Operator type (e.g., 'Hash Join', 'Merge Join')
            join_type: JOIN type (e.g., 'Inner', 'Left', 'Right')
            child_node_ids: List of child node IDs (order preserved)
            join_conditions: List of JOIN conditions with full details
            filters: Additional WHERE clause filters
            position: [query_id, position] in the query plan
            total_cost: Cost of executing this node (adjusted for MV selection)
            original_cost: Original cost from EXPLAIN JSON Total Cost
            rows: Estimated number of rows
            width: Width of result tuples in bytes
            output_columns: Optional list of output columns

        Returns:
            Node ID for this non-leaf node
        """
        # Create key that includes JOIN conditions to distinguish different JOINs
        # of the same tables
        join_cond_hash = hash(
            tuple(sorted([jc.original_text for jc in join_conditions]))
        ) if join_conditions else 0
        
        # Key includes: children (order preserved) + join condition hash
        key = tuple(child_node_ids)  # Don't sort - preserve order
        
        # For backward compatibility with existing code, we also maintain
        # the old sorted key mapping
        sorted_key = tuple(sorted(child_node_ids))

        # Check if this non-leaf node already exists (using sorted key for compatibility)
        if sorted_key in self.non_leaf_nodes_map:
            node_id = self.non_leaf_nodes_map[sorted_key]
        else:
            # Create new non-leaf node
            node_id = self._generate_unique_id("non_leaf")
            self.non_leaf_nodes_map[sorted_key] = node_id
            self.non_leaf_nodes_map_r[node_id] = sorted_key
            
            # Store detailed information (enhanced)
            self.non_leaf_nodes_info[node_id] = NonLeafNodeInfo(
                node_id=node_id,
                operator=operator,
                join_type=join_type,
                children=child_node_ids,  # Order preserved
                join_conditions=join_conditions,
                filters=filters,
                output_columns=output_columns,
                cost=total_cost,
                rows=rows,
                width=width,
            )
            
            # Store JOIN conditions separately for easy access
            self.join_conditions[node_id] = join_conditions
            
            # Store operator type
            self.node_operators[node_id] = operator

        # Update position if valid
        if position[0] != -1:
            if node_id in self.subquery_positions:
                self.subquery_positions[node_id].append(position)
            else:
                self.subquery_positions[node_id] = [position]

        # Update properties
        self.non_leaf_nodes_filter[node_id] = " AND ".join(filters) if filters else ""
        self.subquery_costs[node_id] = total_cost
        # original_subquery_costsは常にEXPLAIN JSONの生の値を保存
        # 初回設定時のみ保存（後で更新しない）
        if node_id not in self.original_subquery_costs:
            self.original_subquery_costs[node_id] = original_cost
        self.subquery_sizes[node_id] = rows * width
        self.subquery_widths[node_id] = width

        return node_id

    def depth_first_search(self, node: dict[str, Any], position: list[int]) -> str:
        """Perform depth-first search on a query plan tree.

        Recursively processes nodes in the query plan, creating or finding
        corresponding node IDs in the manager.

        Args:
            node: Query plan node dictionary with keys:
                - type: 'leaf' or 'non_leaf'
                - operator: Operator type
                - For leaf: table, alias, filter, cost, size, width
                - For non-leaf: children, filter, cost, size, width
                  (Enhanced: also join_type, join_conditions, additional_filters, rows)
            position: [query_id, position] in the query plan

        Returns:
            Node ID for the processed node

        Raises:
            ValueError: If node type is invalid
        """
        if node["type"] == "leaf":
            # Calculate rows from size/width if not provided
            rows = node.get("rows", 0)
            if rows == 0 and node["width"] > 0:
                rows = node["size"] // node["width"]
            
            # Get index columns for Index Scan nodes
            index_columns = node.get("index_columns", None)
            
            return self.process_leaf_node(
                node["operator"],
                node["table"],
                node["alias"],
                node["filter"],
                position,
                node["cost"],
                node.get("original_cost", node["cost"]),  # EXPLAIN JSONの生のコスト
                node["size"],
                node["width"],
                rows=rows,
                index_columns=index_columns,
            )
        elif node["type"] == "non_leaf":
            # Recursively process children
            child_ids = [self.depth_first_search(child, [-1, -1]) for child in node["children"]]
            
            # Check if enhanced information is available (Chapter 2)
            if "join_conditions" in node and "join_type" in node:
                # Use enhanced processing
                join_conditions = node.get("join_conditions", [])
                join_type = node.get("join_type", "Inner")
                additional_filters = node.get("additional_filters", [])
                rows = node.get("rows", 0)
                
                node_id = self.process_non_leaf_node_v2(
                    operator=node["operator"],
                    join_type=join_type,
                    child_node_ids=child_ids,
                    join_conditions=join_conditions,
                    filters=additional_filters,
                    position=position,
                    total_cost=node["cost"],
                    original_cost=node.get("original_cost", node["cost"]),  # EXPLAIN JSONの生のコスト
                    rows=rows,
                    width=node["width"],
                )
                
                # Store row count for non-leaf nodes
                self.subquery_rows[node_id] = rows
                
                return node_id
            else:
                # Fallback to legacy processing for backward compatibility
                node_id = self.process_non_leaf_node(
                    child_ids,
                    position,
                    node["cost"],
                    node["size"],
                    node["width"],
                    node.get("filter", ""),
                )
                
                # Store row count for non-leaf nodes
                rows = node.get("rows", 0)
                if rows == 0 and node["width"] > 0:
                    rows = node["size"] // node["width"]
                self.subquery_rows[node_id] = rows
                
                return node_id
        else:
            raise ValueError(f"Invalid node type: {node.get('type')}")

    def depth_child_to_parent_search(
        self, node: dict[str, Any], child_to_parent: dict[str, list[str]], parent_id: str
    ) -> dict[str, list[str]]:
        """Build child-to-parent mapping via depth-first search.

        This method is used to construct dependency relationships between nodes.

        Args:
            node: Query plan node dictionary
            child_to_parent: Dictionary mapping child node ID to parent IDs
            parent_id: ID of the parent node

        Returns:
            Updated child_to_parent dictionary
        """
        if node["type"] == "non_leaf":
            # Recursively process children
            child_ids = [
                self.depth_child_to_parent_search(child, child_to_parent, parent_id)
                for child in node["children"]
            ]

            # Create the current node
            current_node = self.process_non_leaf_node(
                child_ids,
                [-1, -1],
                node["cost"],
                node["size"],
                node["width"],
                node.get("filter", ""),
            )

            # Record parent relationship
            child_to_parent[current_node] = [parent_id]

            # Debug output (consider using logging in production)
            print(f"child_ids= {child_ids}")
            print(f"current_node= {current_node}")
            print(f"parent_id= {parent_id}")

        return child_to_parent

    def get_node_info(self, node_id: str) -> dict[str, Any] | None:
        """Get information about a node.

        Args:
            node_id: ID of the node to query

        Returns:
            Dictionary with node information or None if not found
        """
        info = {}

        # Check if it's a leaf node
        if node_id in self.leaf_nodes_map_r:
            operator, table, alias, filter_cond = self.leaf_nodes_map_r[node_id]
            info = {
                "type": "leaf",
                "node_id": node_id,
                "operator": operator,
                "table": table,
                "alias": alias,
                "filter": filter_cond,
            }
        # Check if it's a non-leaf node
        elif node_id in self.non_leaf_nodes_map_r:
            children = self.non_leaf_nodes_map_r[node_id]
            info = {
                "type": "non_leaf",
                "node_id": node_id,
                "children": list(children),
                "filter": self.non_leaf_nodes_filter.get(node_id, ""),
            }
        else:
            return None

        # Add common properties
        info.update(
            {
                "cost": self.subquery_costs.get(node_id),
                "size": self.subquery_sizes.get(node_id),
                "width": self.subquery_widths.get(node_id),
                "positions": self.subquery_positions.get(node_id, []),
            }
        )

        return info

    def reset(self) -> None:
        """Reset all mappings and counters.

        Useful for processing a new workload from scratch.
        """
        self.leaf_nodes_map.clear()
        self.leaf_nodes_map_r.clear()
        self.non_leaf_nodes_map.clear()
        self.non_leaf_nodes_map_r.clear()
        self.non_leaf_nodes_filter.clear()
        
        # Enhanced: Clear new mappings (Chapter 1)
        self.non_leaf_nodes_info.clear()
        self.join_conditions.clear()
        self.node_operators.clear()
        
        self.leaf_id_counter = 0
        self.non_leaf_id_counter = 0
        self.subquery_positions.clear()
        self.subquery_costs.clear()
        self.subquery_sizes.clear()
        self.relation_tables.clear()
        self.subquery_widths.clear()
        self.original_query_join_conditions.clear()
        self.original_query_aliases.clear()
