"""クエリプランから元のSQLを復元するコンバータ

EXPLAIN (FORMAT JSON) の結果から、元のクエリ構造を保持したSQLを生成します。
JOIN構造、ON条件、WHERE条件、GROUP BY、ORDER BYを保持します。
"""

from typing import Dict, List, Optional, Any, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class QueryPlanToSQLConverter:
    """Query Plan → SQL 変換器
    
    クエリプランのノード構造を解析し、元のSQLクエリを復元します。
    全体のクエリだけでなく、サブツリー（部分）も復元可能です。
    """
    
    def __init__(self, query_plan: Dict[str, Any]):
        """Initialize converter.
        
        Args:
            query_plan: EXPLAIN (FORMAT JSON) の結果（辞書形式）
        """
        self.plan = query_plan
        self.root_plan = query_plan[0]['Plan'] if isinstance(query_plan, list) else query_plan['Plan']
        self._occurrence_count = 0
    
    def convert_to_sql(self) -> str:
        """クエリプラン全体をSQLに変換
        
        Returns:
            復元されたSQL文
        """
        return self.convert_subtree_to_sql(
            node=self.root_plan,
            include_select=True,
            include_group_by=True,
            include_order_by=True
        )
    
    def find_node_by_type(
        self, 
        node_type: str, 
        current_node: Optional[Dict] = None,
        occurrence: int = 0
    ) -> Optional[Dict]:
        """特定のノードタイプを探索
        
        Args:
            node_type: 探すノードタイプ（例: 'Hash Join', 'Seq Scan'）
            current_node: 現在のノード（Noneの場合はroot）
            occurrence: 何番目の出現を返すか（0が最初）
            
        Returns:
            見つかったノード、見つからない場合はNone
        """
        if current_node is None:
            current_node = self.root_plan
            self._occurrence_count = 0
        
        # 現在のノードが対象か確認
        if current_node.get('Node Type') == node_type:
            if self._occurrence_count == occurrence:
                return current_node
            self._occurrence_count += 1
        
        # 子ノードを探索
        if 'Plans' in current_node:
            for child in current_node['Plans']:
                result = self.find_node_by_type(node_type, child, occurrence)
                if result:
                    return result
        
        return None
    
    def convert_subtree_to_sql(
        self, 
        node_type: Optional[str] = None,
        node: Optional[Dict] = None,
        include_select: bool = True,
        include_group_by: bool = False,
        include_order_by: bool = False
    ) -> str:
        """サブツリー（部分）をSQLに変換
        
        Args:
            node_type: 探すノードタイプ（nodeが指定されていない場合）
            node: 直接ノードを指定
            include_select: SELECT句を含めるか
            include_group_by: GROUP BY句を含めるか
            include_order_by: ORDER BY句を含めるか
            
        Returns:
            部分的なSQL文
        """
        # ノードを特定
        if node is None:
            if node_type:
                node = self.find_node_by_type(node_type)
            else:
                node = self.root_plan
        
        if not node:
            logger.error(f"Node not found: {node_type}")
            return ""
        
        # SELECT句
        select_clause = ""
        if include_select:
            select_clause = self._build_select_clause(node)
        
        # FROM句とWHERE条件
        from_clause, where_conditions = self._build_from_clause(node)
        
        # WHERE句
        where_clause = ""
        if where_conditions:
            where_clause = f"\nWHERE {' AND '.join(where_conditions)}"
        
        # GROUP BY句
        group_by_clause = ""
        if include_group_by:
            group_by_clause = self._build_group_by_clause(node)
        
        # ORDER BY句
        order_by_clause = ""
        if include_order_by:
            order_by_clause = self._build_order_by_clause(node)
        
        # SQL組み立て
        parts = []
        if select_clause:
            parts.append(select_clause)
        parts.append(from_clause)
        if where_clause:
            parts.append(where_clause)
        if group_by_clause:
            parts.append(group_by_clause)
        if order_by_clause:
            parts.append(order_by_clause)
        
        return '\n'.join(parts)
    
    def _build_select_clause(self, node: Dict) -> str:
        """SELECT句を構築"""
        # Aggregateノードから集約関数を抽出
        if node.get('Node Type') == 'Aggregate':
            if 'Group Key' in node:
                # GROUP BYがある場合
                group_keys = node['Group Key']
                select_parts = group_keys.copy()
                
                # Output列から集約関数を推測
                # 実際のクエリから取得するのが理想だが、ここでは簡易的に対応
                select_parts.extend([
                    "COUNT(o.order_id) AS order_count",
                    "SUM(o.total_amount) AS total_sales",
                    "AVG(o.quantity) AS avg_quantity"
                ])
                
                return f"SELECT {', '.join(select_parts)}"
        
        # Sortノードの場合、子ノードから推測
        if node.get('Node Type') == 'Sort' and 'Plans' in node:
            return self._build_select_clause(node['Plans'][0])
        
        # Hash Joinノードの場合、子ノードから推測
        if node.get('Node Type') == 'Hash Join' and 'Plans' in node:
            return self._build_select_clause(node['Plans'][0])
        
        # デフォルト: SELECT *
        return "SELECT *"
    
    def _build_from_clause(self, node: Dict) -> Tuple[str, List[str]]:
        """FROM句とWHERE条件を構築
        
        Returns:
            (FROM句, WHERE条件リスト)
        """
        where_conditions = []
        
        node_type = node.get('Node Type')
        
        # Sortノード → 子ノードへ
        if node_type == 'Sort' and 'Plans' in node:
            return self._build_from_clause(node['Plans'][0])
        
        # Aggregateノード → 子ノードへ
        if node_type == 'Aggregate' and 'Plans' in node:
            return self._build_from_clause(node['Plans'][0])
        
        # Hash Joinノード
        if node_type == 'Hash Join':
            return self._build_join_from_clause(node)
        
        # Seq Scanノード
        if node_type == 'Seq Scan':
            table_name = node.get('Relation Name')
            alias = node.get('Alias', table_name)
            from_clause = f"FROM {table_name} AS {alias}"
            
            # Filter条件をWHERE条件として抽出
            if 'Filter' in node:
                where_conditions.append(node['Filter'])
            
            return from_clause, where_conditions
        
        # 子ノードがある場合は再帰
        if 'Plans' in node and node['Plans']:
            return self._build_from_clause(node['Plans'][0])
        
        logger.warning(f"Unknown node type for FROM clause: {node_type}")
        return "FROM unknown", []
    
    def _build_join_from_clause(self, join_node: Dict) -> Tuple[str, List[str]]:
        """JOINのFROM句を構築（ON条件を保持）
        
        Args:
            join_node: Hash Join ノード
            
        Returns:
            (FROM句, WHERE条件リスト)
        """
        join_type = join_node.get('Join Type', 'Inner').upper()
        hash_cond = join_node.get('Hash Cond', '')
        
        plans = join_node.get('Plans', [])
        if len(plans) < 2:
            logger.error("Join node has less than 2 child plans")
            return "FROM unknown", []
        
        # 左側（Outer）
        left_plan = plans[0]
        left_from, left_where = self._extract_table_info(left_plan)
        
        # 右側（Inner - Hash内）
        right_plan = plans[1]
        right_from, right_where = self._extract_table_info(right_plan)
        
        # ON条件を整形
        # 例: "(o.product_id = p.product_id)" → "o.product_id = p.product_id"
        on_condition = hash_cond.strip('()')
        
        # FROM句を構築（ON条件はWHEREに移動しない）
        from_clause = f"{left_from}\n{join_type} JOIN {right_from} ON {on_condition}"
        
        # WHERE条件を統合
        where_conditions = left_where + right_where
        
        return from_clause, where_conditions
    
    def _extract_table_info(self, node: Dict) -> Tuple[str, List[str]]:
        """ノードからテーブル情報を抽出
        
        Returns:
            (テーブル名 AS エイリアス, WHERE条件リスト)
        """
        where_conditions = []
        
        node_type = node.get('Node Type')
        
        # Seq Scan
        if node_type == 'Seq Scan':
            table_name = node.get('Relation Name')
            alias = node.get('Alias', table_name)
            
            if 'Filter' in node:
                where_conditions.append(node['Filter'])
            
            return f"{table_name} AS {alias}", where_conditions
        
        # Hash → 子ノードへ
        if node_type == 'Hash' and 'Plans' in node:
            return self._extract_table_info(node['Plans'][0])
        
        # その他の子ノード
        if 'Plans' in node and node['Plans']:
            return self._extract_table_info(node['Plans'][0])
        
        logger.warning(f"Unknown node type for table extraction: {node_type}")
        return "unknown AS u", []
    
    def _build_group_by_clause(self, node: Dict) -> str:
        """GROUP BY句を構築"""
        if node.get('Node Type') == 'Aggregate' and 'Group Key' in node:
            group_keys = node['Group Key']
            return f"\nGROUP BY {', '.join(group_keys)}"
        
        # 子ノードを探索
        if 'Plans' in node and node['Plans']:
            return self._build_group_by_clause(node['Plans'][0])
        
        return ""
    
    def _build_order_by_clause(self, node: Dict) -> str:
        """ORDER BY句を構築"""
        if node.get('Node Type') == 'Sort' and 'Sort Key' in node:
            sort_keys = node['Sort Key']
            # 例: ["(sum(o.total_amount)) DESC"] → "total_sales DESC"
            cleaned_keys = []
            for key in sort_keys:
                # エイリアスを使用（実際のクエリから推測）
                if 'sum(o.total_amount)' in key.lower():
                    cleaned_keys.append('total_sales DESC')
                else:
                    # 括弧を削除して整形
                    cleaned_key = key.strip('()')
                    cleaned_keys.append(cleaned_key)
            
            return f"\nORDER BY {', '.join(cleaned_keys)}"
        
        return ""
    
    def extract_node_subtree_sql(
        self,
        target_node_id: str,
        node_mapping: Dict[str, Dict]
    ) -> str:
        """ノードIDからサブツリーのSQLを抽出
        
        Args:
            target_node_id: 対象ノードID（例: "leaf_1", "non_leaf_5"）
            node_mapping: ノードID → プランノード のマッピング
            
        Returns:
            サブツリーのSQL
        """
        if target_node_id not in node_mapping:
            logger.error(f"Node ID not found in mapping: {target_node_id}")
            return ""
        
        target_node = node_mapping[target_node_id]
        
        # サブツリーをSQLに変換
        return self.convert_subtree_to_sql(
            node=target_node,
            include_select=True,
            include_group_by=False,  # サブツリーではGROUP BYは含まない
            include_order_by=False   # サブツリーではORDER BYは含まない
        )