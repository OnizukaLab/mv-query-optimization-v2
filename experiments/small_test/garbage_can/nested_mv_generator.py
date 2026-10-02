"""Nested MV Generator - クエリプラン対応版

クエリプランから元のSQL構造を保持したままMVを生成します。
"""

from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)


class NestedMVGenerator:
    """サブツリー復元方式のMVジェネレータ（クエリプラン対応）
    
    - クエリプランがある場合: プランから元のSQL構造を復元
    - ない場合: QueryManagerから再構築
    """
    
    def __init__(
        self, 
        query_manager: Any, 
        schema_provider: Optional[Any] = None,
        query_plan: Optional[Dict] = None,
        node_plan_mapping: Optional[Dict[str, Dict]] = None
    ):
        """Initialize NestedMVGenerator.
        
        Args:
            query_manager: QueryManager instance
            schema_provider: Optional SchemaProvider
            query_plan: オプション: クエリプラン全体（EXPLAIN JSON）
            node_plan_mapping: オプション: ノードID → プランノードのマッピング
        """
        self.qm = query_manager
        self.schema_provider = schema_provider
        self.query_plan = query_plan
        self.node_plan_mapping = node_plan_mapping or {}
    
    def generate_mv_sql(self, node_id: str) -> str:
        """Generate CREATE MATERIALIZED VIEW SQL.
        
        クエリプランがある場合は、そこからサブツリーを復元。
        ない場合は従来の方式で生成。
        
        Args:
            node_id: Node ID (leaf_X or non_leaf_X)
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        try:
            # クエリプランから復元する場合
            if self.query_plan and node_id in self.node_plan_mapping:
                logger.info(f"Generating SQL from query plan for {node_id}")
                query = self._build_query_from_plan(node_id)
            else:
                # 従来の方式（QueryManagerから）
                logger.info(f"Generating SQL from QueryManager for {node_id}")
                query = self._build_query_from_qm(node_id)
            
            if not query:
                logger.error(f"Failed to build query for {node_id}")
                return ""
            
            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{query};"
            
            return create_sql
            
        except Exception as e:
            logger.error(f"Error generating SQL for {node_id}: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _build_query_from_plan(self, node_id: str) -> Optional[str]:
        """クエリプランからサブツリーのSQLを復元
        
        Args:
            node_id: ノードID
            
        Returns:
            復元されたSQL
        """
        if node_id not in self.node_plan_mapping:
            logger.error(f"Node {node_id} not in plan mapping")
            return None
        
        target_node = self.node_plan_mapping[node_id]
        
        from experiments.small_test.query_plan_to_sql import QueryPlanToSQLConverter
        
        converter = QueryPlanToSQLConverter(self.query_plan)
        
        return converter.convert_subtree_to_sql(
            node=target_node,
            include_select=True,
            include_group_by=False,  # MVのサブツリーには含まない
            include_order_by=False   # MVのサブツリーには含まない
        )
    
    def _build_query_from_qm(self, node_id: str) -> Optional[str]:
        """QueryManagerから従来方式でSQLを構築
        
        Args:
            node_id: ノードID
            
        Returns:
            構築されたSQL
        """
        # leaf_nodeの場合
        if node_id in self.qm.leaf_nodes_map_r:
            return self._build_leaf_query(node_id)
        
        # non_leaf_nodeの場合
        elif node_id in self.qm.non_leaf_nodes_info:
            return self._build_non_leaf_query(node_id)
        
        else:
            logger.error(f"Unknown node: {node_id}")
            return None
    
    def _build_leaf_query(self, node_id: str) -> str:
        """leaf_nodeのクエリを構築"""
        operator, table_name, alias, filter_cond = self.qm.leaf_nodes_map_r[node_id]
        
        select_clause = "SELECT *"
        from_clause = f"FROM {table_name} AS {alias}"
        where_clause = ""
        if filter_cond:
            where_clause = f"\nWHERE {filter_cond}"
        
        query = f"{select_clause}\n{from_clause}{where_clause}"
        return query
    
    def _build_non_leaf_query(self, node_id: str) -> str:
        """non_leaf_nodeのクエリを構築（サブクエリとして子ノードを復元）"""
        node_info = self.qm.non_leaf_nodes_info[node_id]
        
        if not node_info.children:
            logger.error(f"No children for {node_id}")
            return ""
        
        select_clause = "SELECT *"
        
        # FROM句: 子ノードをサブクエリとして復元
        from_parts = []
        for child_id in node_info.children:
            child_query = self._build_query_from_qm(child_id)
            if not child_query:
                continue
            from_parts.append(f"({child_query}) AS {child_id}")
        
        if not from_parts:
            logger.error(f"No valid children for {node_id}")
            return ""
        
        from_clause = f"FROM {',\n     '.join(from_parts)}"
        
        # WHERE句: JOIN条件
        where_conditions = []
        if node_info.join_conditions:
            for jc in node_info.join_conditions:
                jc_str = f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
                where_conditions.append(jc_str)
        
        if node_info.filters:
            where_conditions.extend(node_info.filters)
        
        where_clause = ""
        if where_conditions:
            where_clause = f"\nWHERE {' AND '.join(where_conditions)}"
        
        query = f"{select_clause}\n{from_clause}{where_clause}"
        return query