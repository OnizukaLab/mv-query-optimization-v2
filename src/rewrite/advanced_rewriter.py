"""Advanced query rewriting engine (Chapter 5).

This module provides sophisticated query rewriting using graph matching
and MV substitution strategies.
"""

from typing import Optional
import re
import logging

from src.rewrite.query_graph import QueryGraph, QueryGraphMatcher, MVMatch, TableNode
from src.rewrite.sql_parser import SQLParser

logger = logging.getLogger(__name__)


class QueryRewriteEngine:
    """Advanced query rewriting engine using graph matching.
    
    This engine can perform:
    - Full replacement: Replace entire query with a single MV
    - Partial replacement: Replace part of query with MV, join with remaining tables
    """
    
    def __init__(self, query_manager):
        """Initialize the rewrite engine.
        
        Args:
            query_manager: QueryManager instance
        """
        self.qm = query_manager
        self.matcher = QueryGraphMatcher(query_manager)
        self.sql_parser = SQLParser()
    
    def rewrite_query(
        self,
        original_sql: str,
        selected_mvs: list[str],
        strategy: str = "best"
    ) -> tuple[str, Optional[MVMatch]]:
        """Rewrite a query using selected MVs.
        
        Args:
            original_sql: Original SQL query
            selected_mvs: List of available MV node IDs
            strategy: Rewriting strategy - "best" (highest coverage) or "first"
            
        Returns:
            Tuple of (rewritten SQL, MVMatch used) or (original SQL, None) if no match
        """
        if not selected_mvs or not original_sql:
            logger.warning("No MVs selected or empty query")
            return original_sql, None
        
        # Build query graph from SQL
        query_graph = self._build_query_graph_from_sql(original_sql)
        
        if not query_graph:
            logger.warning("Could not build query graph from SQL")
            return original_sql, None
        
        # Find matching MVs
        mv_matches = self.matcher.find_mv_matches(query_graph, selected_mvs)
        
        if not mv_matches:
            logger.info("No MV matches found, returning original query")
            return original_sql, None
        
        # Select best match
        best_match = mv_matches[0]  # Already sorted by coverage
        logger.info(f"Selected MV: {best_match}")
        
        # Rewrite based on match type
        if best_match.replacement_type == "full":
            rewritten_sql = self._rewrite_full_replacement(
                original_sql,
                query_graph,
                best_match
            )
        else:
            rewritten_sql = self._rewrite_partial_replacement(
                original_sql,
                query_graph,
                best_match
            )
        
        return rewritten_sql, best_match
    
    def _build_query_graph_from_sql(self, sql: str) -> Optional[QueryGraph]:
        """Build a QueryGraph from SQL text.
        
        Args:
            sql: SQL query string
            
        Returns:
            QueryGraph instance or None if parsing fails
        """
        try:
            # Extract FROM clause
            from_clause = self.sql_parser.extract_from_clause(sql)
            
            # Extract WHERE clause
            where_clause = self.sql_parser.extract_where_clause(sql)
            
            # Extract tables
            tables = self.sql_parser.extract_tables(from_clause)
            
            # Build graph
            graph = QueryGraph()
            
            # Add table nodes
            for table_name, alias in tables:
                # Extract filters for this table from WHERE clause
                filters = self._extract_table_filters(alias, where_clause)
                graph.add_node(alias, table_name, filters)
            
            # Extract and add JOIN edges
            joins = self._extract_joins_from_clause(from_clause)
            for join in joins:
                graph.add_edge(
                    join['left'],
                    join['right'],
                    join['condition'],
                    join['type']
                )
            
            return graph
            
        except Exception as e:
            logger.error(f"Error building query graph: {e}")
            return None
    
    def _extract_table_filters(self, alias: str, where_clause: str) -> list[str]:
        """Extract filter conditions for a specific table alias.
        
        Args:
            alias: Table alias
            where_clause: WHERE clause text
            
        Returns:
            List of filter conditions involving this alias
        """
        if not where_clause:
            return []
        
        filters = []
        # Simple regex to find conditions with this alias
        pattern = rf'{alias}\.\w+\s*[<>=!]+\s*[^\s)]+' 
        matches = re.findall(pattern, where_clause, re.IGNORECASE)
        filters.extend(matches)
        
        return filters
    
    def _extract_joins_from_clause(self, from_clause: str) -> list[dict]:
        """Extract JOIN information from FROM clause.
        
        Args:
            from_clause: FROM clause text
            
        Returns:
            List of JOIN dictionaries with keys: left, right, condition, type
        """
        joins = []
        
        # Pattern for JOIN ... ON ...
        join_pattern = r'(INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+)?JOIN\s+(\w+)\s+(\w+)\s+ON\s+([^;]+?)(?=\s+(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+)?JOIN|\s+WHERE|$)'
        
        matches = re.finditer(join_pattern, from_clause, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            join_type = (match.group(1) or "INNER").strip()
            # table_name = match.group(2)
            right_alias = match.group(3)
            condition = match.group(4).strip()
            
            # Extract left alias from condition
            # Assumes condition like "t1.id = t2.id"
            left_match = re.match(r'(\w+)\.\w+\s*=', condition)
            left_alias = left_match.group(1) if left_match else ""
            
            if left_alias and right_alias:
                joins.append({
                    'left': left_alias,
                    'right': right_alias,
                    'condition': condition,
                    'type': join_type
                })
        
        return joins
    
    def _rewrite_full_replacement(
        self,
        original_sql: str,
        query_graph: QueryGraph,
        mv_match: MVMatch
    ) -> str:
        """Perform full replacement - replace entire query with MV.
        
        Args:
            original_sql: Original SQL
            query_graph: Query graph
            mv_match: MV match information
            
        Returns:
            Rewritten SQL
        """
        mv_id = mv_match.mv_id
        
        # Extract SELECT clause from original
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', original_sql, re.IGNORECASE | re.DOTALL)
        if not select_match:
            logger.warning("Could not extract SELECT clause")
            return original_sql
        
        select_clause = select_match.group(1).strip()
        
        # Adjust column references to use MV
        adjusted_select = self._adjust_select_for_full_mv(
            select_clause,
            mv_match.matched_tables,
            mv_id
        )
        
        # Extract WHERE clause that's not covered by MV
        where_clause = self.sql_parser.extract_where_clause(original_sql)
        remaining_where = self._filter_where_for_mv(where_clause, mv_match)
        
        # Build new SQL
        rewritten_sql = f"SELECT {adjusted_select}\nFROM {mv_id}"
        
        if remaining_where:
            rewritten_sql += f"\nWHERE {remaining_where}"
        
        rewritten_sql += ";"
        
        return rewritten_sql
    
    def _rewrite_partial_replacement(
        self,
        original_sql: str,
        query_graph: QueryGraph,
        mv_match: MVMatch
    ) -> str:
        """Perform partial replacement - replace part of query with MV.
        
        Args:
            original_sql: Original SQL
            query_graph: Query graph
            mv_match: MV match information
            
        Returns:
            Rewritten SQL
        """
        mv_id = mv_match.mv_id
        covered_tables = mv_match.matched_tables
        
        # Extract SELECT clause
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', original_sql, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return original_sql
        
        select_clause = select_match.group(1).strip()
        
        # Adjust SELECT for partial replacement
        adjusted_select = self._adjust_select_for_partial_mv(
            select_clause,
            covered_tables,
            mv_id
        )
        
        # Build FROM clause with MV and remaining tables
        from_parts = [mv_id]
        
        # Add tables not covered by MV
        for alias, node in query_graph.nodes.items():
            if alias not in covered_tables:
                from_parts.append(f"{node.table_name} {alias}")
        
        # Reconstruct JOINs
        join_clauses = []
        for edge in query_graph.edges:
            left_in_mv = edge.left_node in covered_tables
            right_in_mv = edge.right_node in covered_tables
            
            if left_in_mv and right_in_mv:
                # Both in MV - skip this JOIN
                continue
            elif left_in_mv or right_in_mv:
                # One in MV - rewrite condition
                rewritten_condition = self._rewrite_join_condition_for_mv(
                    edge.condition,
                    covered_tables,
                    mv_id
                )
                join_clauses.append(
                    f"{edge.join_type} JOIN {edge.right_node if left_in_mv else edge.left_node} "
                    f"ON {rewritten_condition}"
                )
            else:
                # Neither in MV - keep as is
                join_clauses.append(
                    f"{edge.join_type} JOIN {edge.right_node} ON {edge.condition}"
                )
        
        from_clause = " ".join(from_parts + join_clauses)
        
        # Adjust WHERE clause
        where_clause = self.sql_parser.extract_where_clause(original_sql)
        adjusted_where = self._adjust_where_for_partial_mv(
            where_clause,
            covered_tables,
            mv_id
        )
        
        # Build new SQL
        rewritten_sql = f"SELECT {adjusted_select}\nFROM {from_clause}"
        
        if adjusted_where:
            rewritten_sql += f"\nWHERE {adjusted_where}"
        
        rewritten_sql += ";"
        
        return rewritten_sql
    
    def _adjust_select_for_full_mv(
        self,
        select_clause: str,
        covered_tables: set[str],
        mv_id: str
    ) -> str:
        """Adjust SELECT clause for full MV replacement.
        
        Replaces table aliases with MV alias.
        """
        adjusted = select_clause
        
        for alias in covered_tables:
            # Replace alias.column with mv_id.column
            pattern = rf'\b{alias}\.'
            adjusted = re.sub(pattern, f'{mv_id}.', adjusted)
        
        return adjusted
    
    def _adjust_select_for_partial_mv(
        self,
        select_clause: str,
        covered_tables: set[str],
        mv_id: str
    ) -> str:
        """Adjust SELECT clause for partial MV replacement."""
        return self._adjust_select_for_full_mv(select_clause, covered_tables, mv_id)
    
    def _filter_where_for_mv(self, where_clause: str, mv_match: MVMatch) -> str:
        """Filter WHERE clause to remove conditions already in MV."""
        # For now, return the entire WHERE clause
        # A more sophisticated implementation would analyze which conditions
        # are already satisfied by the MV
        return where_clause
    
    def _adjust_where_for_partial_mv(
        self,
        where_clause: str,
        covered_tables: set[str],
        mv_id: str
    ) -> str:
        """Adjust WHERE clause for partial MV replacement."""
        if not where_clause:
            return ""
        
        adjusted = where_clause
        
        # Replace covered table aliases with MV alias
        for alias in covered_tables:
            pattern = rf'\b{alias}\.'
            adjusted = re.sub(pattern, f'{mv_id}.', adjusted)
        
        return adjusted
    
    def _rewrite_join_condition_for_mv(
        self,
        condition: str,
        covered_tables: set[str],
        mv_id: str
    ) -> str:
        """Rewrite a JOIN condition to use MV alias.
        
        Example:
            Input: "t.id = ci.movie_id" where 't' is in MV
            Output: "mv_1.id = ci.movie_id"
        """
        # Parse condition (assumes format: alias1.col1 = alias2.col2)
        parts = condition.split('=')
        if len(parts) != 2:
            return condition
        
        left = parts[0].strip()
        right = parts[1].strip()
        
        # Replace covered aliases with MV alias
        left_parts = left.split('.')
        right_parts = right.split('.')
        
        if len(left_parts) == 2 and left_parts[0] in covered_tables:
            left = f"{mv_id}.{left_parts[1]}"
        
        if len(right_parts) == 2 and right_parts[0] in covered_tables:
            right = f"{mv_id}.{right_parts[1]}"
        
        return f"{left} = {right}"
