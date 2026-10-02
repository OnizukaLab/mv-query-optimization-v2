"""Query graph structures for advanced query rewriting (Chapter 5).

This module provides graph-based query representation and matching
for sophisticated MV-based query rewriting.
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TableNode:
    """Represents a table in the query graph.
    
    Attributes:
        alias: Table alias in the query
        table_name: Actual table name
        filters: List of filter conditions applied to this table
    """
    alias: str
    table_name: str
    filters: list[str] = field(default_factory=list)
    
    def __hash__(self):
        return hash(self.alias)
    
    def __eq__(self, other):
        if not isinstance(other, TableNode):
            return False
        return self.alias == other.alias


@dataclass
class JoinEdge:
    """Represents a JOIN between two tables.
    
    Attributes:
        left_node: Left table node
        right_node: Right table node
        condition: JOIN condition (e.g., "t.id = ci.movie_id")
        join_type: Type of JOIN (Inner, Left, Right, etc.)
    """
    left_node: str  # alias
    right_node: str  # alias
    condition: str
    join_type: str = "Inner"
    
    def __hash__(self):
        # Order-independent hash
        return hash(frozenset([self.left_node, self.right_node, self.condition]))
    
    def __eq__(self, other):
        if not isinstance(other, JoinEdge):
            return False
        return (
            (self.left_node == other.left_node and self.right_node == other.right_node) or
            (self.left_node == other.right_node and self.right_node == other.left_node)
        ) and self.condition == other.condition


class QueryGraph:
    """Graph representation of a SQL query.
    
    Nodes represent tables, edges represent JOINs.
    """
    
    def __init__(self):
        """Initialize empty query graph."""
        self.nodes: dict[str, TableNode] = {}  # alias -> TableNode
        self.edges: list[JoinEdge] = []
        
    def add_node(self, alias: str, table_name: str, filters: list[str] = None):
        """Add a table node to the graph.
        
        Args:
            alias: Table alias
            table_name: Actual table name
            filters: Optional list of filter conditions
        """
        self.nodes[alias] = TableNode(
            alias=alias,
            table_name=table_name,
            filters=filters or []
        )
        logger.debug(f"Added node: {alias} ({table_name})")
    
    def add_edge(self, left_alias: str, right_alias: str, condition: str, join_type: str = "Inner"):
        """Add a JOIN edge to the graph.
        
        Args:
            left_alias: Left table alias
            right_alias: Right table alias
            condition: JOIN condition
            join_type: Type of JOIN
        """
        edge = JoinEdge(
            left_node=left_alias,
            right_node=right_alias,
            condition=condition,
            join_type=join_type
        )
        self.edges.append(edge)
        logger.debug(f"Added edge: {left_alias} -{join_type}-> {right_alias}")
    
    def node_count(self) -> int:
        """Get number of nodes in the graph."""
        return len(self.nodes)
    
    def edge_count(self) -> int:
        """Get number of edges in the graph."""
        return len(self.edges)
    
    def get_all_tables(self) -> set[str]:
        """Get all table aliases in the graph."""
        return set(self.nodes.keys())
    
    def get_all_joins(self) -> list[JoinEdge]:
        """Get all JOIN edges in the graph."""
        return self.edges.copy()
    
    def is_subgraph_of(self, other: 'QueryGraph') -> bool:
        """Check if this graph is a subgraph of another.
        
        Args:
            other: The supergraph to check against
            
        Returns:
            True if this graph is a subgraph of other
        """
        # All our nodes must be in other
        for alias in self.nodes:
            if alias not in other.nodes:
                return False
        
        # All our edges must be in other
        for edge in self.edges:
            if not self._edge_exists_in(edge, other.edges):
                return False
        
        return True
    
    def _edge_exists_in(self, edge: JoinEdge, edge_list: list[JoinEdge]) -> bool:
        """Check if an edge exists in a list of edges."""
        for other_edge in edge_list:
            if edge == other_edge:
                return True
        return False
    
    def __repr__(self):
        return f"QueryGraph(nodes={len(self.nodes)}, edges={len(self.edges)})"


@dataclass
class MVMatch:
    """Represents a match between a query and an MV.
    
    Attributes:
        mv_id: MV node ID
        matched_tables: Set of table aliases covered by this MV
        matched_joins: List of JOIN edges covered by this MV
        coverage_score: Fraction of query covered (0.0 to 1.0)
        replacement_type: "full" or "partial"
    """
    mv_id: str
    matched_tables: set[str]
    matched_joins: list[JoinEdge]
    coverage_score: float
    replacement_type: str  # "full" or "partial"
    
    def __repr__(self):
        return (
            f"MVMatch(mv={self.mv_id}, tables={len(self.matched_tables)}, "
            f"coverage={self.coverage_score:.2%}, type={self.replacement_type})"
        )


@dataclass
class MatchInfo:
    """Information about a graph matching result."""
    tables: set[str]
    joins: list[JoinEdge]
    coverage: float
    type: str  # "full" or "partial"


class QueryGraphMatcher:
    """Matches query graphs with MV graphs for rewriting.
    
    This class implements subgraph matching to find applicable MVs
    for a given query.
    """
    
    def __init__(self, query_manager):
        """Initialize the matcher.
        
        Args:
            query_manager: QueryManager instance with MV information
        """
        self.qm = query_manager
    
    def find_mv_matches(
        self,
        query_graph: QueryGraph,
        available_mvs: list[str]
    ) -> list[MVMatch]:
        """Find MVs that can be used to rewrite the query.
        
        Args:
            query_graph: The query represented as a graph
            available_mvs: List of available MV node IDs
            
        Returns:
            List of MV matches, sorted by coverage score (descending)
        """
        matches = []
        
        for mv_id in available_mvs:
            # Build graph for this MV
            mv_graph = self._build_mv_graph(mv_id)
            
            if not mv_graph:
                continue
            
            # Check if MV graph is a subgraph of query graph
            match_info = self._match_graphs(query_graph, mv_graph)
            
            if match_info:
                matches.append(MVMatch(
                    mv_id=mv_id,
                    matched_tables=match_info.tables,
                    matched_joins=match_info.joins,
                    coverage_score=match_info.coverage,
                    replacement_type=match_info.type
                ))
        
        # Sort by coverage (highest first)
        matches.sort(key=lambda m: m.coverage_score, reverse=True)
        
        logger.info(f"Found {len(matches)} MV matches for query")
        return matches
    
    def _build_mv_graph(self, mv_id: str) -> Optional[QueryGraph]:
        """Build a graph representation of an MV.
        
        Args:
            mv_id: MV node ID
            
        Returns:
            QueryGraph representing the MV, or None if not found
        """
        # Check if it's a leaf node
        if mv_id in self.qm.leaf_nodes_map_r:
            leaf_info = self.qm.leaf_nodes_map_r[mv_id]
            # leaf_info is a tuple: (operator, table_name, alias, filter)
            graph = QueryGraph()
            graph.add_node(
                alias=leaf_info[2],  # alias
                table_name=leaf_info[1],  # table_name
                filters=[leaf_info[3]] if leaf_info[3] else []  # filter
            )
            return graph
        
        # Check if it's a non-leaf node with enhanced info
        if mv_id in self.qm.non_leaf_nodes_info:
            node_info = self.qm.non_leaf_nodes_info[mv_id]
            graph = QueryGraph()
            
            # Recursively build graph from children
            for child_id in node_info.children:
                child_graph = self._build_mv_graph(child_id)
                if child_graph:
                    # Merge child graph into this graph
                    for alias, node in child_graph.nodes.items():
                        graph.add_node(alias, node.table_name, node.filters)
            
            # Add JOIN edges from stored conditions
            if mv_id in self.qm.join_conditions:
                for jc in self.qm.join_conditions[mv_id]:
                    graph.add_edge(
                        jc.left_table,
                        jc.right_table,
                        jc.original_text,
                        node_info.join_type
                    )
            
            return graph
        
        # Fallback: check legacy non-leaf nodes
        if mv_id in self.qm.non_leaf_nodes_map:
            child_ids = self.qm.non_leaf_nodes_map[mv_id]
            graph = QueryGraph()
            
            for child_id in child_ids:
                child_graph = self._build_mv_graph(child_id)
                if child_graph:
                    for alias, node in child_graph.nodes.items():
                        graph.add_node(alias, node.table_name, node.filters)
            
            return graph
        
        logger.warning(f"Could not build graph for MV: {mv_id}")
        return None
    
    def _match_graphs(
        self,
        query_graph: QueryGraph,
        mv_graph: QueryGraph
    ) -> Optional[MatchInfo]:
        """Check if MV graph matches (is subgraph of) query graph.
        
        Args:
            query_graph: The query graph
            mv_graph: The MV graph
            
        Returns:
            MatchInfo if match found, None otherwise
        """
        # Check if MV graph is subgraph of query graph
        if not mv_graph.is_subgraph_of(query_graph):
            return None
        
        # Calculate coverage
        coverage = mv_graph.node_count() / query_graph.node_count()
        
        # Determine type
        match_type = "full" if coverage >= 0.99 else "partial"
        
        return MatchInfo(
            tables=mv_graph.get_all_tables(),
            joins=mv_graph.get_all_joins(),
            coverage=coverage,
            type=match_type
        )
