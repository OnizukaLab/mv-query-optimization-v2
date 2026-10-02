"""Query parser for processing PostgreSQL query plans.

This module provides the QueryParser class which parses JSON query plans
from PostgreSQL EXPLAIN output and processes them for optimization.
"""

import json
import random
import re
from pathlib import Path
from typing import Any

from config.settings import Settings

from ..utils.legacy import get_red_queries, get_all_job_queries, natural_sort_key
from .query_manager import QueryManager
from .models import JoinCondition


class QueryParser:
    """Parses and processes query plans for materialized view optimization.

    This class handles:
    - Loading and parsing JSON query plans from PostgreSQL EXPLAIN
    - Converting query plans into internal representation
    - Computing utility and cost metrics
    - Building dependency relationships between subqueries

    Attributes:
        qm: QueryManager instance for managing query nodes
        s_num: Total number of subquery nodes
        m_cost: Maintenance cost for each node
        node_list: List of all node IDs
        position_node_id: Maps (query_id, position) to node_id
        deeplist: List of depth lists for each query
        U_j_max: Maximum utility for each node
        b_j: Storage size for each node
        q_s_list: Binary matrix of query-to-subquery relationships
        q_s_order_list: Execution order of subqueries in each query
        u_ij: Utility matrix [query_id][node_id]
        us_ij: Shared utility matrix
        y_ij: Decision variables (for ILP)
        X: Inclusive dependency matrix
        U_max: Maximum total utility
        query: List of processed query plans
        subqlist: Reverse mapping of non-leaf nodes to children
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the QueryParser.

        Args:
            settings: Configuration settings (optional, loads default if None)
        """
        self.settings = settings or Settings()
        self.qm = QueryManager()

        # Initialize result attributes
        self.s_num: int = 0
        self.m_cost: list[float] = []
        self.node_list: list[str] = []
        self.position_node_id: dict[tuple[int, int], str] = {}
        self.deeplist: list[list[int]] = []
        self.U_j_max: list[float] = []
        self.b_j: list[int] = []
        self.q_s_list: list[list[int]] = []
        self.q_s_order_list: list[list[int]] = []
        self.u_ij: list[list[float]] = []
        self.us_ij: list[list[float]] = []
        self.y_ij: list[list[int]] = []
        self.X: list[list[int]] = []
        self.U_max: float = 0.0
        self.query: list[list[dict[str, Any]]] = []
        self.subqlist: dict[tuple[str, ...], str] = {}
        
        # Store original subquery costs (from EXPLAIN JSON Total Cost)
        self.original_subquery_costs: dict[str, float] = {}
        
        # Store processed query files
        self.query_files: list[str] = []
        
        # Index build costs for Index Scan nodes (used in optimization phase)
        self.index_build_costs: list[float] = []

    def natural_sort_key(self, s: str) -> list:
        """Generate a key for natural sorting of strings with numbers.

        Args:
            s: String to generate sort key for

        Returns:
            List of strings and integers for sorting
        """
        return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", s)]

    def extract_join_conditions(self, node):
        """Extract JOIN conditions from Hash/Merge Cond and Index Cond in descendant nodes."""
        condition_texts = []
        
        # Extract from current node
        if "Hash Cond" in node:
            condition_texts.append(("Hash Cond", node["Hash Cond"], None))
        if "Merge Cond" in node:
            condition_texts.append(("Merge Cond", node["Merge Cond"], None))
        
        # Nested Loop: Extract Index Cond from both Outer and Inner sides
        if node.get("Node Type") == "Nested Loop":
            if "Plans" in node and len(node["Plans"]) >= 2:
                # Extract from Outer side (Plans[0])
                outer_plan = node["Plans"][0]
                outer_conds = self._extract_index_cond_recursive(outer_plan)
                for cond_text, table_alias in outer_conds:
                    condition_texts.append(("Index Cond", cond_text, table_alias))
                
                # Extract from Inner side (Plans[1])
                inner_plan = node["Plans"][1]
                inner_conds = self._extract_index_cond_from_inner(inner_plan)
                for cond_text, table_alias in inner_conds:
                    condition_texts.append(("Index Cond", cond_text, table_alias))
            
            # Also check for Join Filter (explicit join condition)
            if "Join Filter" in node:
                condition_texts.append(("Join Filter", node["Join Filter"], None))
        
        # Parse all condition texts into JoinCondition objects
        join_conditions = []
        for condition_type, condition_text, table_alias in condition_texts:
            parsed = self.parse_join_condition(condition_text, condition_type, table_alias)
            join_conditions.extend(parsed)
        
        return join_conditions
    
    def _extract_index_cond_from_inner(self, inner_plan):
        """Extract Index Cond from Nested Loop's inner side.
        
        Handles cases where inner side is:
        - Direct Index Scan: Use its Index Cond
        - Memoize/Materialize: Search inside for Index Scan
        
        Args:
            inner_plan: Inner side plan (typically Plans[1] of Nested Loop)
            
        Returns:
            List of tuples: (condition_text, table_alias)
        """
        conditions = []
        
        # Case 1: Inner side is directly an Index Scan
        if "Index Cond" in inner_plan:
            table_alias = inner_plan.get("Alias", "")
            conditions.append((inner_plan["Index Cond"], table_alias))
            return conditions
        
        # Case 2: Inner side is Memoize/Materialize/similar intermediate node
        node_type = inner_plan.get("Node Type", "")
        if node_type in ["Memoize", "Materialize", "CTE Scan", "Subquery Scan"]:
            # Look one level deeper
            if "Plans" in inner_plan and len(inner_plan["Plans"]) > 0:
                child = inner_plan["Plans"][0]
                if "Index Cond" in child:
                    table_alias = child.get("Alias", "")
                    conditions.append((child["Index Cond"], table_alias))
        
        return conditions

    def _extract_index_cond_recursive(self, node):
        """Recursively extract Index Cond from current node and all descendant nodes.
        
        Returns:
            List of tuples: (condition_text, table_alias)
        """
        conditions = []
        
        # Extract from current node
        if "Index Cond" in node:
            # Index Scanノードの場合、テーブルエイリアスも取得
            table_alias = node.get("Alias", "")
            conditions.append((node["Index Cond"], table_alias))
        
        # Recursively process child nodes
        if "Plans" in node:
            for child in node["Plans"]:
                child_conds = self._extract_index_cond_recursive(child)
                conditions.extend(child_conds)
        
        return conditions

    def parse_join_condition(self, condition_text: str, condition_type: str, table_alias: str = None) -> list[JoinCondition]:
        """Parse JOIN condition text into structured format (Chapter 2).

        Extracts table.column comparisons from condition strings.
        
        Examples:
            "(t.id = ci.movie_id)" -> JoinCondition(...)
            "(mc.company_type_id = ct.id)" -> JoinCondition(...)
            "(movie_id = mc.movie_id)" -> JoinCondition(...) # Index Cond format

        Args:
            condition_text: Raw condition text from EXPLAIN
            condition_type: Type of condition (Hash Cond, Merge Cond, etc.)
            table_alias: Table alias for Index Cond (when left table is missing)

        Returns:
            List of JoinCondition objects
        """
        conditions = []
        
        # Pattern 1: (alias1.column1 operator alias2.column2) - standard format
        pattern1 = r'\((\w+)\.(\w+)\s*(=|<|>|<=|>=|!=|<>)\s*(\w+)\.(\w+)\)'
        matches1 = re.finditer(pattern1, condition_text)
        
        for match in matches1:
            left_table = match.group(1)
            left_column = match.group(2)
            operator = match.group(3)
            right_table = match.group(4)
            right_column = match.group(5)
            
            # Normalize <> to !=
            if operator == "<>":
                operator = "!="
            
            conditions.append(JoinCondition(
                left_table=left_table,
                left_column=left_column,
                operator=operator,
                right_table=right_table,
                right_column=right_column,
                condition_type=condition_type,
                original_text=match.group(0)
            ))
        
        # Pattern 2: (column operator alias.column) - Index Cond format without left table
        # This pattern is used when Index Scan references the indexed table's column
        if not conditions:
            pattern2 = r'\((\w+)\s*(=|<|>|<=|>=|!=|<>)\s*(\w+)\.(\w+)\)'
            matches2 = re.finditer(pattern2, condition_text)
            
            for match in matches2:
                left_column = match.group(1)
                operator = match.group(2)
                right_table = match.group(3)
                right_column = match.group(4)
                
                # Normalize <> to !=
                if operator == "<>":
                    operator = "!="
                
                # Use the provided table_alias for left table (from Index Scan node)
                left_table = table_alias if table_alias else ""
                
                conditions.append(JoinCondition(
                    left_table=left_table,
                    left_column=left_column,
                    operator=operator,
                    right_table=right_table,
                    right_column=right_column,
                    condition_type=condition_type,
                    original_text=match.group(0)
                ))
        
        return conditions
        
        return conditions

    def _extract_columns_from_condition(
        self, condition: str, alias: str
    ) -> list[str]:
        """Extract column names from an Index Cond expression.
        
        Parses expressions like:
        - "(movie_id = mc.movie_id)" -> ["movie_id"]
        - "(id = 1)" -> ["id"]
        - "((status_id = 1) AND (type_id = 2))" -> ["status_id", "type_id"]
        
        Args:
            condition: Index Cond expression string
            alias: Table alias for the current node
            
        Returns:
            List of column names that should be indexed
        """
        import re
        
        columns = []
        
        # Pattern to match column = value or column = alias.column
        # Left side column (without alias prefix or with our alias)
        patterns = [
            # (column = value) or (column = alias.column)
            rf'\(({alias}\.)?([\w_]+)\s*=',
            # = alias.column (for right side of join)
            rf'=\s*{alias}\.([\w_]+)\)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, condition)
            for match in matches:
                if isinstance(match, tuple):
                    # Get the column name (last non-empty group)
                    col = [m for m in match if m and not m.endswith('.')]
                    if col:
                        columns.append(col[-1])
                else:
                    columns.append(match)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_columns = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                unique_columns.append(col)
        
        return unique_columns

    def convert_node(
        self,
        node: dict[str, Any],
        subquery_list: list[dict[str, Any]],
        deep_list: list[int],
        order_list: list[int],
        order: int,
        depth: int = 0,
        table_info: list[str] = None,
        frequency: int = 1,
    ) -> tuple[dict[str, Any], int]:
        """Convert a PostgreSQL plan node to internal representation.

        Args:
            node: PostgreSQL EXPLAIN plan node
            subquery_list: Accumulated list of converted subqueries
            deep_list: Accumulated list of node depths
            order_list: Accumulated list of execution orders
            order: Current execution order
            depth: Current depth in the plan tree
            table_info: Table info for Bitmap Heap Scan [table_name, alias]
            frequency: Query execution frequency

        Returns:
            Tuple of (converted node dict, next order number)
        """
        if table_info is None:
            table_info = []

        deep_list.append(depth)

        if "Plans" in node:  # Non-leaf node
            children = []
            new_order = order

            # Special handling for Bitmap Heap Scan
            if node["Node Type"] == "Bitmap Heap Scan":
                table_info = [node["Relation Name"], node["Alias"]]

            # Recursively process children
            for child in node["Plans"]:
                converted_child, order_1 = self.convert_node(
                    child,
                    subquery_list,
                    deep_list,
                    order_list,
                    new_order + 1,
                    depth + 1,
                    table_info,
                    frequency,
                )
                children.append(converted_child)
                new_order = order_1

            # Extract JOIN conditions (Chapter 2 enhancement)
            join_conditions = self.extract_join_conditions(node)
            
            # Get JOIN type (default to Inner)
            join_type = node.get("Join Type", "Inner")

            # Determine filter condition key based on operator type
            if node["Node Type"] == "Hash Join":
                filter_name = "Hash Cond"
            elif node["Node Type"] == "Merge Join":
                filter_name = "Merge Cond"
            elif node["Node Type"] == "Nested Loop":
                if "Join Filter" in node:
                    filter_name = "Join Filter"
                else:
                    # Check if any child has Index Cond
                    filter_name = "Filter"  # Default
                    for child in node["Plans"]:
                        if "Index Cond" in child:
                            filter_name = "Index Cond"
                            break
            else:
                filter_name = "Filter"

            filter_condition = node.get(filter_name, "")
            
            # Collect additional filters (not JOIN conditions)
            additional_filters = []
            for filter_key in ["Filter", "Join Filter"]:
                if filter_key in node and filter_key != filter_name:
                    additional_filters.append(node[filter_key])

            # Cost calculation logic
            # まず、EXPLAIN JSONからの生のコストを取得（original_subquery_costs用）
            original_cost = node.get("Total Cost", 0.0)
            
            # 次に、MV選択用の調整されたコストを計算
            # Prevent MVs with no filter condition
            if "Seq Scan" in node["Node Type"] and filter_condition == "":
                cost = 0.0
            # Edge case: Hash node with no filter in child
            elif (
                node["Node Type"] == "Hash" and "Plans" in node and "Filter" not in node["Plans"][0]
            ):
                cost = 0.0
            else:
                cost = original_cost
            
            # Ensure non-zero width
            width = node.get("Plan Width", 0)
            if width == 0:
                width = 1

            # Enhanced subquery structure (Chapter 2)
            subquery_list.append(
                {
                    "type": "non_leaf",
                    "operator": node["Node Type"],
                    "join_type": join_type,  # New field
                    "join_conditions": join_conditions,  # New field
                    "additional_filters": additional_filters,  # New field
                    "filter": filter_condition,
                    "cost": cost * frequency,
                    "original_cost": original_cost * frequency,  # EXPLAIN JSONの生のコスト
                    "size": node.get("Plan Rows", 0) * width,
                    "rows": node.get("Plan Rows", 0),  # New field
                    "width": width,
                    "children": children,
                }
            )
            order_list.append(order)
            return subquery_list[-1], new_order

        else:  # Leaf node
            # Determine filter condition
            # Note: Index Condは結合条件なのでリーフMV生成時は使わない
            # 親ノードのextract_join_conditions()で抽出される
            
            # まず、EXPLAIN JSONからの生のコストを取得（original_subquery_costs用）
            original_cost = node.get("Total Cost", 0.0)
            
            if "Filter" in node:
                # Filterのみを使用（Index Condは除外）
                filter_condition = node["Filter"]
                cost = node["Total Cost"]
            else:
                filter_condition = ""
                cost = 0.0

            # Zero cost for scan without filter
            if "Scan" in node["Node Type"] and "Filter" not in node:
                cost = 0.0

            # Ensure non-zero width
            width = node.get("Plan Width", 0)
            if width == 0:
                width = 1

            # Handle Bitmap Index Scan
            if node["Node Type"] == "Bitmap Index Scan":
                table = table_info[0] if len(table_info) > 0 else ""
                alias = table_info[1] if len(table_info) > 1 else ""
            else:
                table = node.get("Relation Name", "")
                alias = node.get("Alias", "")
            
            # Extract index columns for Index Scan nodes
            index_columns = []
            if "Index" in node["Node Type"] and "Scan" in node["Node Type"]:
                # Get Index Cond and extract column names
                if "Index Cond" in node:
                    index_columns = self._extract_columns_from_condition(
                        node["Index Cond"], alias
                    )

            subquery_list.append(
                {
                    "type": "leaf",
                    "operator": node["Node Type"],
                    "table": table,
                    "alias": alias,
                    "filter": filter_condition,
                    "cost": cost * frequency,
                    "original_cost": original_cost * frequency,  # EXPLAIN JSONの生のコスト
                    "size": node.get("Plan Rows", 0) * width,
                    "width": width,
                    "index_columns": index_columns,  # インデックス対象カラム
                }
            )
            order_list.append(order)
            return subquery_list[-1], order

    def convert_json(
        self, json_data: list[dict[str, Any]], freq: int
    ) -> tuple[list[dict[str, Any]], list[int], list[int]]:
        """Convert JSON query plan data to internal representation.

        Args:
            json_data: List of PostgreSQL EXPLAIN output plans
            freq: Query execution frequency

        Returns:
            Tuple of (subquery_list, depth_list, order_list)
        """
        subquery_list = []
        deep_list = []
        order_list = []
        order = 0

        for plan in json_data:
            self.convert_node(
                plan["Plan"], subquery_list, deep_list, order_list, order, frequency=freq
            )

        return subquery_list, deep_list, order_list

    def make_reverse_dict(self, d: dict[str, list[list[int]]]) -> dict[tuple[int, int], str]:
        """Create reverse dictionary from position lists.

        Args:
            d: Dictionary mapping node_id to list of [query_id, position] pairs

        Returns:
            Dictionary mapping (query_id, position) to node_id
        """
        reverse_dict = {}
        for key, value in d.items():
            if len(value) == 1:
                v_tuple = tuple(value[0])
                reverse_dict[v_tuple] = key
            else:
                for v in value:
                    v_tuple = tuple(v)
                    reverse_dict[v_tuple] = key
        return reverse_dict

    def make_reverse_dict2(self, d: dict[tuple[str, ...], str]) -> dict[str, tuple[str, ...]]:
        """Create reverse dictionary.

        Args:
            d: Dictionary mapping children tuple to node_id

        Returns:
            Dictionary mapping node_id to children tuple
        """
        reverse_dict = {}
        for key, value in d.items():
            reverse_dict[value] = key
        return reverse_dict

    def search_leaf_node(self, node_id: str) -> list[str]:
        """Find all leaf table names in a subtree.

        Recursively searches the subtree rooted at node_id and returns
        a list of all table names referenced by leaf nodes.

        Args:
            node_id: Root node ID to start search from

        Returns:
            List of unique table names
        """
        leaf_tables = set()

        def _find_leaf_tables_recursive(current_node_id: str) -> None:
            if current_node_id.startswith("leaf_"):
                table_name = self.qm.relation_tables.get(current_node_id)
                if table_name:
                    leaf_tables.add(table_name)
            elif current_node_id.startswith("non_leaf_"):
                child_node_ids = self.qm.non_leaf_nodes_map_r.get(current_node_id, [])
                for child_id in child_node_ids:
                    _find_leaf_tables_recursive(child_id)

        _find_leaf_tables_recursive(node_id)
        return list(leaf_tables)

    def check_m_cost(
        self,
        m_cost: list[float],
        table_list: list[str],
        update_table: list[list[str]],
        record_list: list[int],
        search_cost: list[float],
        insert_cost: float,
        table_width: list[int],
        insert_times: float,
    ) -> list[float]:
        """Calculate maintenance cost for materialized views.

        Args:
            m_cost: Initial maintenance cost list (will be updated)
            table_list: List of table names
            update_table: List of tables being updated
            record_list: Number of records in each table
            search_cost: Search cost for each table
            insert_cost: Cost per insert operation (alpha)
            table_width: Width of each table in bytes
            insert_times: Number of insert operations

        Returns:
            Updated maintenance cost list
        """
        len_leaf = len(self.qm.leaf_nodes_map)

        # Calculate maintenance cost for leaf nodes
        for i in range(len(self.qm.leaf_nodes_map)):
            node_id = f"leaf_{i + 1}"
            for item in update_table:
                item2 = self.qm.relation_tables[node_id]
                if item[0] == item2:
                    m_cost[i] += (
                        self.qm.subquery_costs[node_id] / record_list[table_list.index(item2)]
                    )
                    m_cost[i] += (
                        insert_cost
                        * self.qm.subquery_widths[node_id]
                        / table_width[table_list.index(item2)]
                    )
            m_cost[i] *= insert_times

        # Calculate maintenance cost for non-leaf nodes
        for i in range(len(self.qm.non_leaf_nodes_map)):
            node_id = f"non_leaf_{i + 1}"
            node_id_table_list = self.search_leaf_node(node_id)
            for item in update_table:
                if item[0] in node_id_table_list:
                    m_cost[i + len_leaf] += (
                        self.qm.subquery_costs[node_id] / record_list[table_list.index(item[0])]
                    )
                    m_cost[i + len_leaf] += (
                        insert_cost
                        * self.qm.subquery_widths[node_id]
                        / table_width[table_list.index(item[0])]
                    )
            m_cost[i + len_leaf] *= insert_times

        return m_cost

    def calculate_maintenance_cost_v2(
        self,
        table_stats: dict[str, Any],
        update_frequency: dict[str, float] | None = None,
        random_page_cost: float = 4.0,
        seq_page_cost: float = 1.0,
        write_cost_per_row: float = 1.0,
    ) -> list[float]:
        """Calculate maintenance cost using the three-component model from the paper.

        This implements the IVM (Incremental View Maintenance) cost model:
        1. Computing changes (差分計算コスト): cost(A ⋈ ΔB) ≈ cost_read(A ⋈ B) × |ΔB|/|B|
        2. Identifying records (特定コスト): cost(σ_ΔV(V)) ≈ cost_read(σ_ΔB(B)) × fanout
        3. Applying changes (適用コスト): cost(V - ΔV) ≈ cost_write(-ΔB) × fanout

        The model assumes |ΔB| = 1 (single row update) and multiplies by update_frequency.

        Args:
            table_stats: Pre-fetched table statistics from SchemaManager.get_all_table_statistics()
            update_frequency: Dict mapping table names to normalized update frequency
                              (from SchemaManager.get_normalized_update_frequencies())
            random_page_cost: PostgreSQL random_page_cost (default: 4.0)
            seq_page_cost: PostgreSQL seq_page_cost (default: 1.0)
            write_cost_per_row: Cost to write one row (default: 1.0)

        Returns:
            List of maintenance costs for each node (leaf nodes first, then non-leaf)
        """
        import math

        len_leaf = len(self.qm.leaf_nodes_map)
        len_non_leaf = len(self.qm.non_leaf_nodes_map)
        m_cost = [0.0] * (len_leaf + len_non_leaf)

        # Get all table names
        all_tables = set()
        for node_id in self.qm.relation_tables:
            all_tables.add(self.qm.relation_tables[node_id])
        
        # Default: uniform update frequency
        if update_frequency is None:
            update_frequency = {t: 1.0 for t in all_tables}

        # Calculate cost for leaf nodes
        for i in range(len_leaf):
            node_id = f"leaf_{i + 1}"
            table_name = self.qm.relation_tables.get(node_id)
            
            if not table_name or table_name not in table_stats:
                continue

            stats = table_stats[table_name]
            freq = update_frequency.get(table_name, 1.0)
            
            if freq == 0:
                continue

            # For leaf nodes (single table), fanout = 1
            base_rows = max(1, stats.row_count)
            
            # |ΔB| = 1 (single row update per the paper's model)
            delta_rows = 1

            # 1. Computing changes: cost_read(query) × |ΔB|/|B|
            full_cost = self.qm.subquery_costs.get(node_id, 1.0)
            compute_cost = full_cost * (delta_rows / base_rows)

            # 2. Identifying records: cost to find the row to update
            # For leaf nodes, this is just the point query cost (no fanout needed)
            if stats.has_unique_index:
                tree_depth = math.log2(base_rows) if base_rows > 1 else 1
                identify_cost = tree_depth * random_page_cost + 1.0
            else:
                identify_cost = stats.page_count * seq_page_cost

            # 3. Applying changes: write cost for 1 row
            apply_cost = write_cost_per_row

            # Total = single update cost × update frequency
            single_update_cost = compute_cost + identify_cost + apply_cost
            m_cost[i] = single_update_cost * freq

        # Calculate cost for non-leaf nodes (joins)
        for i in range(len_non_leaf):
            node_id = f"non_leaf_{i + 1}"
            involved_tables = self.search_leaf_node(node_id)
            
            if not involved_tables:
                continue

            total_cost = 0.0
            
            # For each base table that could be updated
            for table_name in involved_tables:
                if table_name not in table_stats:
                    continue

                stats = table_stats[table_name]
                freq = update_frequency.get(table_name, 1.0)
                
                if freq == 0:
                    continue

                base_rows = max(1, stats.row_count)
                
                # |ΔB| = 1 (single row update)
                delta_rows = 1

                # Calculate fanout: |V| / |B|
                # How many view rows are affected by updating 1 row in base table
                view_rows = self.qm.subquery_rows.get(node_id, base_rows)
                fanout = max(1.0, view_rows / base_rows)

                # 1. Computing changes: cost(A ⋈ ΔB) ≈ cost_read(A ⋈ B) × |ΔB|/|B|
                full_join_cost = self.qm.subquery_costs.get(node_id, 1.0)
                compute_cost = full_join_cost * (delta_rows / base_rows)

                # 2. Identifying records: cost_read(σ_ΔB(B)) × fanout
                # Point query cost on base table, multiplied by fanout
                if stats.has_unique_index:
                    tree_depth = math.log2(base_rows) if base_rows > 1 else 1
                    base_identify_cost = tree_depth * random_page_cost + 1.0
                else:
                    base_identify_cost = stats.page_count * seq_page_cost
                
                identify_cost = base_identify_cost * fanout

                # 3. Applying changes: cost_write(-ΔB) × fanout
                # Write cost for fanout rows (1 base row affects fanout view rows)
                apply_cost = write_cost_per_row * fanout

                # Single update cost for this table
                single_update_cost = compute_cost + identify_cost + apply_cost
                
                # Multiply by update frequency for this table
                total_cost += single_update_cost * freq

            m_cost[i + len_leaf] = total_cost

        return m_cost

    def get_maintenance_cost_breakdown(
        self,
        node_id: str,
        table_stats: dict[str, Any],
        update_frequency: dict[str, float] | None = None,
        random_page_cost: float = 4.0,
        seq_page_cost: float = 1.0,
        write_cost_per_row: float = 1.0,
    ) -> dict[str, dict[str, float]]:
        """Get detailed breakdown of maintenance cost for a specific node.

        This follows the paper's model with |ΔB| = 1 (single row update).

        Args:
            node_id: Node ID (e.g., 'leaf_1', 'non_leaf_3')
            table_stats: Pre-fetched table statistics
            update_frequency: Dict mapping table names to update frequency
            random_page_cost: PostgreSQL random_page_cost
            seq_page_cost: PostgreSQL seq_page_cost
            write_cost_per_row: Cost per row write

        Returns:
            Dictionary with breakdown per table:
            {
                'table_name': {
                    'compute_cost': float,
                    'identify_cost': float,
                    'apply_cost': float,
                    'fanout': float,
                    'update_frequency': float,
                    'single_update_cost': float,
                    'total': float  (single_update_cost × update_frequency)
                }
            }
        """
        import math

        result = {}
        
        # Default frequency
        if update_frequency is None:
            update_frequency = {}
        
        if node_id.startswith('leaf_'):
            table_name = self.qm.relation_tables.get(node_id)
            if table_name and table_name in table_stats:
                stats = table_stats[table_name]
                base_rows = max(1, stats.row_count)
                freq = update_frequency.get(table_name, 1.0)

                # |ΔB| = 1
                full_cost = self.qm.subquery_costs.get(node_id, 1.0)
                compute_cost = full_cost * (1 / base_rows)

                if stats.has_unique_index:
                    tree_depth = math.log2(base_rows) if base_rows > 1 else 1
                    identify_cost = tree_depth * random_page_cost + 1.0
                else:
                    identify_cost = stats.page_count * seq_page_cost

                apply_cost = write_cost_per_row
                single_update_cost = compute_cost + identify_cost + apply_cost

                result[table_name] = {
                    'compute_cost': compute_cost,
                    'identify_cost': identify_cost,
                    'apply_cost': apply_cost,
                    'fanout': 1.0,
                    'update_frequency': freq,
                    'single_update_cost': single_update_cost,
                    'total': single_update_cost * freq
                }
        else:
            involved_tables = self.search_leaf_node(node_id)
            view_rows = self.qm.subquery_rows.get(node_id, 1)
            
            for table_name in involved_tables:
                if table_name not in table_stats:
                    continue

                stats = table_stats[table_name]
                base_rows = max(1, stats.row_count)
                fanout = max(1.0, view_rows / base_rows)
                freq = update_frequency.get(table_name, 1.0)

                # |ΔB| = 1
                full_join_cost = self.qm.subquery_costs.get(node_id, 1.0)
                compute_cost = full_join_cost * (1 / base_rows)

                if stats.has_unique_index:
                    tree_depth = math.log2(base_rows) if base_rows > 1 else 1
                    base_identify = tree_depth * random_page_cost + 1.0
                else:
                    base_identify = stats.page_count * seq_page_cost

                identify_cost = base_identify * fanout
                apply_cost = write_cost_per_row * fanout
                single_update_cost = compute_cost + identify_cost + apply_cost

                result[table_name] = {
                    'compute_cost': compute_cost,
                    'identify_cost': identify_cost,
                    'apply_cost': apply_cost,
                    'fanout': fanout,
                    'update_frequency': freq,
                    'single_update_cost': single_update_cost,
                    'total': single_update_cost * freq
                }

        return result

    def set_inclusive_dependency(
        self, X: list[list[int]] | None, j: int, parent: str | None = None
    ) -> list[list[int]]:
        """Build inclusive dependency matrix recursively.

        The dependency matrix X indicates which nodes must be materialized
        together (if node i is materialized, all its descendants must be too).

        Args:
            X: Dependency matrix (None for initial call)
            j: Current row index
            parent: Parent node ID

        Returns:
            Updated dependency matrix
        """
        if parent is None:
            # Initialize matrix
            X = [[0] * len(self.node_list) for _ in range(len(self.node_list))]
            for j in range(len(self.node_list)):
                parent = self.node_list[j]
                if parent in self.subqlist.keys():
                    for child in self.subqlist[parent]:
                        X[j][self.node_list.index(child)] = 1
                        X = self.set_inclusive_dependency(X, j, child)
        else:
            if parent not in self.subqlist.keys():
                return X
            for child in self.subqlist[parent]:
                X[j][self.node_list.index(child)] = 1
                X = self.set_inclusive_dependency(X, j, child)

        return X

    def _load_original_sql_conditions(self, json_files: list[str], sql_dir: str) -> None:
        """元のSQLファイルからJOIN条件を抽出してQueryManagerに保存.

        PostgreSQLの定数プッシュダウン最適化により、実行プランから消失する
        JOIN条件を元のSQLから補完するために使用する。

        Args:
            json_files: 処理されたJSONファイルのパスリスト（順序はクエリインデックスに対応）
            sql_dir: 元のSQLファイルが格納されているディレクトリのパス
        """
        from experiments.small_test_ver2.mv_generation.original_sql_join_extractor import (
            extract_aliases_from_sql,
            extract_equijoin_conditions,
            extract_select_column_refs,
            extract_where_column_refs,
            extract_distinct_on_columns,
            find_sql_file_for_query,
        )

        loaded_count = 0
        for i, json_file in enumerate(json_files):
            sql_path = find_sql_file_for_query(json_file, sql_dir)
            if sql_path is None:
                continue

            try:
                with open(sql_path, 'r', encoding='utf-8') as f:
                    sql_text = f.read()

                aliases = extract_aliases_from_sql(sql_text)
                conditions = extract_equijoin_conditions(sql_text)
                select_columns = extract_select_column_refs(sql_text)
                where_columns = extract_where_column_refs(sql_text)
                distinct_on = extract_distinct_on_columns(sql_text)

                if aliases:
                    self.qm.original_query_aliases[i] = aliases
                if distinct_on:
                    self.qm.original_query_distinct_on[i] = distinct_on
                if conditions:
                    self.qm.original_query_join_conditions[i] = conditions
                    loaded_count += 1
                if select_columns:
                    self.qm.original_query_select_columns[i] = select_columns
                if where_columns:
                    self.qm.original_query_where_columns[i] = where_columns
            except Exception as e:
                print(f"  [WARN] 元SQL読み込み失敗 ({sql_path}): {e}")

        if loaded_count > 0:
            print(f"  [INFO] {loaded_count}個のクエリから元SQL JOIN条件を読み込み完了")

    def query_parse(self, q_num: int, path: str, insert_query: int, sql_dir: str | None = None) -> None:
        """Parse workload and compute optimization parameters.

        This is the main entry point for parsing a query workload.
        It processes all queries, builds node relationships, and computes
        utility and cost metrics needed for optimization.

        Args:
            q_num: Number of queries (currently not used, determined from files)
            path: Path to directory containing JSON query plans
            insert_query: Number of insert queries for maintenance cost
            sql_dir: Path to directory containing original SQL files.
                     Used to extract JOIN conditions that may be lost in
                     execution plans due to PostgreSQL constant pushdown.
                     If None, original SQL conditions are not loaded.

        Raises:
            json.JSONDecodeError: If JSON parsing fails
        """
        workloads_dir = self.settings.benchmark.workloads_dir
        get_ceb = self.settings.benchmark.type == "ceb"
        query_selection_mode = self.settings.benchmark.query_selection_mode

        # Get query files with frequencies based on selection mode
        if query_selection_mode == "all_job":
            # Use all JOB queries from the directory
            print(f"Query selection mode: all_job (using all JOB queries)")
            files, file_freq = get_all_job_queries(path)
        else:
            # Use RedBench workload-based selection (default)
            print(f"Query selection mode: redbench (using workload-based queries)")
            files, file_freq = get_red_queries(path, workloads_dir, get_ceb)
        
        files = sorted(files, key=natural_sort_key)
        self.query_files = [Path(f).stem for f in files]  # Store filenames without extension as query IDs

        q_num_len = len(files)
        print(f"q_num_len= {q_num_len}")

        try:
            query = []
            deeplist = []
            orderlist = []
            result = None  # Initialize result to handle empty query case

            # Process each query file
            for i in range(q_num_len):
                with open(files[i]) as f:
                    data = json.load(f)
                    frequency = file_freq[files[i]]
                    converted_data, deep_list, order_list = self.convert_json(data, frequency)
                    deeplist.append(deep_list)
                    orderlist.append(order_list)

                    # Process nodes with DFS
                    for j, subquery in zip(order_list, converted_data):
                        result = self.qm.depth_first_search(subquery, [i, j])

                    query.append(converted_data)

            # 元のSQLファイルからJOIN条件を抽出して保存
            if sql_dir:
                self._load_original_sql_conditions(files, sql_dir)

            # Build child-to-parent relationships
            child_to_parent = {}
            for key, value in self.qm.non_leaf_nodes_map.items():
                for item in key:
                    if item not in child_to_parent:
                        child_to_parent[item] = []
                    child_to_parent[item].append(value)

            if result is not None:
                print(f"Root node ID: {result}")
            else:
                print("Warning: No queries were processed")

            # Build node lists and mappings
            node_list = list(self.qm.leaf_nodes_map.values()) + list(
                self.qm.non_leaf_nodes_map.values()
            )
            position_node_id = self.make_reverse_dict(self.qm.subquery_positions)

            len_leaf = len(self.qm.leaf_nodes_map)
            len_non_leaf = len(self.qm.non_leaf_nodes_map)
            s_num = len_leaf + len_non_leaf

            # Count node usage
            s_counter = [0] * s_num
            s_counter2 = [0] * s_num

            for j in range(s_num):
                s_counter2[j] = len(self.qm.subquery_positions[node_list[j]])
                if len(self.qm.subquery_positions[node_list[j]]) > 1:
                    s_counter[j] = 1

            # Build query-to-subquery matrices
            q_s_list = []
            q_s_order_list = []
            u_ij = []
            us_ij = []
            y_ij = []

            for i in range(q_num_len):
                q_by_s = [0] * s_num
                q_s_order = []
                u_ij_seed = [0.0] * s_num
                y_ij_seed = [0] * s_num
                us_ij_seed = [0.0] * s_num

                for j in range(s_num):
                    for item in self.qm.subquery_positions[node_list[j]]:
                        if item[0] == i:
                            q_s_order.append(item[1])
                            q_by_s[j] = 1
                            u_ij_seed[j] = self.qm.subquery_costs[node_list[j]]
                            us_ij_seed[j] = self.qm.subquery_costs[node_list[j]] * s_counter[j]

                q_s_list.append(q_by_s)
                q_s_order_list.append(q_s_order)
                u_ij.append(u_ij_seed)
                us_ij.append(us_ij_seed)
                y_ij.append(y_ij_seed)

            # Calculate storage sizes
            b_j = [0] * s_num
            for j, item in enumerate(node_list):
                b_j[j] = self.qm.subquery_sizes[item]
                if b_j[j] == 0:
                    b_j[j] = 1

            # Calculate max budget and utility
            maxb = 0
            maxu = 0.0

            for i in range(len(u_ij)):
                p_0 = (i, 0)
                p_1 = (i, 1)
                node_0 = position_node_id[p_0]
                node_1 = position_node_id.get(p_1)

                maxb += self.qm.subquery_sizes[node_0]

                if len(orderlist[i]) > 1 and node_1:
                    if self.qm.subquery_costs[node_0] < self.qm.subquery_costs[node_1]:
                        maxu += self.qm.subquery_costs[node_1]
                    else:
                        maxu += self.qm.subquery_costs[node_0]
                else:
                    maxu += self.qm.subquery_costs[node_0]

            print("total_cost", "total_budget")
            print(maxu, maxb)

            # Calculate max utility per node
            U_max = sum(sum(u_row) for u_row in u_ij)
            U_j_max = [0.0] * s_num
            for i in range(len(u_ij)):
                for j in range(len(u_ij[i])):
                    U_j_max[j] += u_ij[i][j]

            # Build dependency matrix
            self.subqlist = self.make_reverse_dict2(self.qm.non_leaf_nodes_map)
            self.node_list = node_list
            X = self.set_inclusive_dependency(None, 0)

            # Calculate maintenance costs
            # IMDB schema hardcoded values (should be externalized to config)
            table_list = [
                "aka_name",
                "aka_title",
                "cast_info",
                "char_name",
                "comp_cast_type",
                "company_name",
                "company_type",
                "complete_cast",
                "info_type",
                "keyword",
                "kind_type",
                "link_type",
                "movie_companies",
                "movie_info",
                "movie_info_idx",
                "movie_keyword",
                "movie_link",
                "name",
                "person_info",
                "role_type",
                "title",
            ]
            record_list = [
                901343,
                361472,
                36244344,
                3140339,
                4,
                234997,
                4,
                135086,
                113,
                134170,
                7,
                18,
                2609129,
                14835720,
                1380035,
                4523930,
                29997,
                4167491,
                2963664,
                12,
                2528312,
            ]
            insert_cost_alpha = 0.01
            search_cost = [
                8.44,
                8.44,
                8.46,
                8.45,
                8.17,
                8.44,
                8.17,
                8.31,
                8.17,
                8.44,
                8.17,
                8.17,
                8.45,
                8.45,
                8.44,
                8.45,
                8.30,
                8.45,
                8.45,
                8.17,
                8.16,
            ]
            table_width = [
                324,
                348,
                56,
                182,
                86,
                198,
                86,
                16,
                86,
                60,
                52,
                86,
                48,
                76,
                52,
                12,
                16,
                238,
                76,
                86,
                306,
            ]

            m_cost = [0.0] * (len_leaf + len_non_leaf)
            insert_times = insert_query / 1000

            # Generate random update tables
            update_table = [[""] for _ in range(1000)]
            for i in range(len(update_table)):
                x = random.randint(0, 20)
                update_table[i][0] = table_list[x]

            m_cost = self.check_m_cost(
                m_cost,
                table_list,
                update_table,
                record_list,
                search_cost,
                insert_cost_alpha,
                table_width,
                insert_times,
            )

            # Store results as instance attributes
            self.qm = self.qm
            self.s_num = s_num
            self.m_cost = m_cost
            self.node_list = node_list
            self.position_node_id = position_node_id
            self.deeplist = deeplist
            self.U_j_max = U_j_max
            self.b_j = b_j
            self.q_s_list = q_s_list
            self.q_s_order_list = q_s_order_list
            self.u_ij = u_ij
            self.us_ij = us_ij
            self.y_ij = y_ij
            self.X = X
            self.U_max = U_max
            self.query = query
            
            # Store original subquery costs (from EXPLAIN JSON Total Cost)
            # These are already preserved in qm.original_subquery_costs during processing
            self.original_subquery_costs = self.qm.original_subquery_costs
            
            # Store index build costs for each node (same order as node_list)
            # This is used in optimization phase to consider index creation cost
            self.index_build_costs = [
                self.qm.index_build_costs.get(node_id, 0.0) for node_id in node_list
            ]
            
            # Compute and store parsing statistics
            self.parse_statistics = self._compute_parse_statistics()

        except json.JSONDecodeError as e:
            print(f"Error reading {files[i] if i < len(files) else 'unknown file'}: {e}")
            raise

    def _compute_parse_statistics(self) -> dict:
        """Compute statistics about parsed queries and utilities.
        
        Returns:
            Dictionary containing various parsing statistics
        """
        stats = {}
        
        # Basic counts
        num_queries = len(self.u_ij)
        num_nodes = len(self.node_list)
        num_leaf_nodes = len(self.qm.leaf_nodes_map)
        num_non_leaf_nodes = len(self.qm.non_leaf_nodes_map)
        
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
        
        for i, row in enumerate(self.u_ij):
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
        if self.m_cost:
            stats['maintenance_cost_min'] = min(self.m_cost)
            stats['maintenance_cost_max'] = max(self.m_cost)
            stats['maintenance_cost_mean'] = sum(self.m_cost) / len(self.m_cost)
            stats['maintenance_cost_total'] = sum(self.m_cost)
        else:
            stats['maintenance_cost_min'] = 0
            stats['maintenance_cost_max'] = 0
            stats['maintenance_cost_mean'] = 0
            stats['maintenance_cost_total'] = 0
        
        # Storage size statistics
        if self.b_j:
            stats['storage_size_min'] = min(self.b_j)
            stats['storage_size_max'] = max(self.b_j)
            stats['storage_size_mean'] = sum(self.b_j) / len(self.b_j)
            stats['storage_size_total'] = sum(self.b_j)
        else:
            stats['storage_size_min'] = 0
            stats['storage_size_max'] = 0
            stats['storage_size_mean'] = 0
            stats['storage_size_total'] = 0
        
        # Per-query statistics
        queries_with_positive_utility = 0
        for row in self.u_ij:
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
            if any(self.u_ij[i][j] > 0 for i in range(num_queries)):
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
            max_utility_for_node = max(self.u_ij[i][j] for i in range(num_queries)) if num_queries > 0 else 0
            net_benefit = max_utility_for_node - self.m_cost[j] if j < len(self.m_cost) else max_utility_for_node
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
    
    def get_parse_statistics(self) -> dict:
        """Get parsing statistics.
        
        Returns:
            Dictionary containing parsing statistics, or empty dict if not computed
        """
        return getattr(self, 'parse_statistics', {})
