"""ノード情報からサブツリーを復元するモジュール

QueryManagerのノード情報（leaf_nodes_map_r, non_leaf_nodes_info）から
元のクエリ構造（JOIN、ON条件、WHERE）を復元します。

☆☆SQLのネストが深くなりrewriteで書き換えが上手くいかない

"""

from typing import Optional, Any, List, Dict
import logging

logger = logging.getLogger(__name__)

class SubtreeRestorer:
    """
    サブツリーを復元

    QueryManagerが保持する情報から、元のSQL構造を再構築します。
    JOIN構造とON条件を保持したまま復元します。
    """

    def __init__(self, query_manager: Any, schema_provider: Any):
        """Initialize SbtreeRestorer

        Args:
            query_manager: QueryManager instance
            schema_provider: SchemaProvider instance for column inference
        """

        self.qm = query_manager
        self.schema_provider = schema_provider

    def  restore_subtree_sql(
            self,
            node_id: str,
            preserve_join_structure: bool = True
    ) -> Optional[str]:
        """ノードIDからサブツリーのSQLを復元
        
        Args:
            node_id: 対象ノードID（例: "leaf_1", "non_leaf_5"）
            preserve_join_structure: JOIN構造を保持するか（Trueの場合はINNER JOIN ... ON、Falseの場合はカンマJOIN + WHERE）
            
        Returns:
            復元されたSQL（SELECT句含む）
        """

        try:
            if node_id in self.qm.leaf_nodes_map_r:
                return self._restore_leaf_sql(node_id)
            elif node_id in self.qm.non_leaf_nodes_info:
                return self._restore_non_leaf_sql(node_id, preserve_join_structure)
            else:
                logger.error(f"Unknown node: {node_id}")
                return None
        except Exception as e:
            logger.error(f"Error restoring subtree for {node_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def _restore_leaf_sql(self, node_id: str) -> str:
        """leaf_nodeのSQLを復元
        
        Args:
            node_id: leaf node ID
            
        Returns:
            SELECT columns FROM table AS alias WHERE filter
        """

        operator, table_name, alias, filter_cond = self.qm.leaf_nodes_map_r[node_id]

        # カラムを推論
        columns = self._get_node_columns(node_id)
        select_clause = f"SELECT {', '.join(columns)}"
        
        from_clause = f"FROM {table_name} AS {alias}"
        where_clause = ""

        if filter_cond:
            where_clause = f"\nWHERE {filter_cond}"

        return f"{select_clause}\n{from_clause}{where_clause}"
    
    def _restore_non_leaf_sql(
            self,
            node_id: str,
            preserve_join_structure: bool
    ) -> str:
        """non_leaf_nodeのSQLを復元
        
        Args:
            node_id: non_leaf node ID
            preserve_join_structure:JOIN構造を保持するか
            
        Returns:
            JOIN構造を保持したSQL
        """

        node_info = self.qm.non_leaf_nodes_info[node_id]

        if not node_info.children:
            logger.error(f"No children for {node_id}")

        # カラムを推論
        columns = self._get_node_columns(node_id)
        select_clause = f"SELECT {', '.join(columns)}"

        # JOIN構造を保持する場合
        if preserve_join_structure:
            return self._build_join_preserved_sql(
                node_info,
                select_clause
            )
        else:
            return self._build_comma_join_sql(
                node_info,
                select_clause
            )
        

    def _build_join_preserved_sql(
            self,
            node_info,
            select_clause: str
    ) -> str:
        """JOIN構造を保持してSQLを構築
        
        例: FROM t1 INNER JOIN t2 ON t1.id = t2.id
        """
        children = node_info.children

        if len(children) == 0:
            return ""
        
        # 最初の子ノードをベースに
        base_child_id = children[0]
        base_child_sql = self.restore_subtree_sql(base_child_id)

        if not base_child_sql:
            return ""
        
        # サブクエリとして包む
        from_parts = [f"({base_child_sql}) AS {base_child_id}"]

        # 残りの子ノードをJOINで追加
        for i, child_id in enumerate(children[1:], start=1):
            child_sql = self.restore_subtree_sql(child_id)

            if not child_id:
                continue

             # JOIN条件を探す
            on_conditions = self._find_join_conditions(
                base_child_id,
                child_id,
                node_info.join_conditions
            )

            if on_conditions:
                #INNER JOIN ... ON構造
                from_parts.append(
                    f"INNER JOIN ({child_sql}) AS {child_id} ON {on_conditions}"
                )
            else:
                 # ON条件が見つからない場合はカンマJOIN
                logger.warning(f"No JOIN condition found between {base_child_id} and {child_id}")
                from_parts.append(f", ({child_sql}) AS {child_id}")

        from_clause = "FROM " + "\n".join(from_parts)

        # WHERE句: フィルタのみ
        where_conditions = []
        if node_info.filters:
            where_conditions.extend(node_info.filters)

        where_clause =""
        if where_conditions:
            where_clause = f"\nWHERE {' AND '.join(where_conditions)}"

        return f"{select_clause}\n{from_clause}{where_clause}"
    
    def _build_comma_join_sql(
            self,
            node_info,
            select_clause: str
    ) -> str:
        
        """カンマJOIN + WHERE方式でSQLを構築
        
        例: FROM t1, t2 WHERE t1.id = t2.id
        """
        children = node_info.children
        
        # 子ノードをサブクエリとして列挙
        from_parts = []
        for child_id in children:
            child_sql = self.restore_subtree_sql(child_id)
            
            if not child_sql:
                continue
            
            from_parts.append(f"({child_sql}) AS {child_id}")
        
        if not from_parts:
            return ""
        
        from_clause = f"FROM {',\n     '.join(from_parts)}"

        # WHERE句: JOIN句+フィルタ
        where_conditions = []

        if node_info.join_conditions:
            for jc in node_info.join_conditions:
                jc_str = f"{jc.left_table}.{jc.left_column} {jc.right_table}.{jc.right_column}"
                where_conditions.append(jc_str)

        # フィルタを追加
        if node_info.filters:
            where_conditions.extend(node_info.filters)

        where_clause = ""
        if where_conditions:
            where_clause = f"\nWHERE {' AND '.join(where_conditions)}"

        return f"{select_clause}\n{from_clause}{where_clause}"
    
    def _get_node_columns(self, node_id: str) -> List[str]:
        """ノードのカラムを推論
        
        優先順位:
        1. node_info.output_columns
        2. node_info.projection
        3. SchemaProvider.get_table_columns (leaf nodeの場合)
        4. 子ノードから再帰的に推論 (non-leaf nodeの場合)
        
        Args:
            node_id: ノードID
            
        Returns:
            カラムのリスト
        """
        # Leaf nodeの場合
        if node_id in self.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = self.qm.leaf_nodes_map_r[node_id]
            
            # SchemaProviderからテーブルのカラムを取得
            try:
                columns = self.schema_provider.get_table_columns(table_name)
                if columns:
                    # aliasを付けてカラムを返す
                    return [f"{alias}.{col}" for col in columns]
            except Exception as e:
                logger.warning(f"Failed to get columns for table {table_name}: {e}")
            
            # SchemaProviderが使えない場合はエラー
            raise ValueError(f"Cannot infer columns for leaf node {node_id} (table: {table_name})")
        
        # Non-leaf nodeの場合
        if node_id in self.qm.non_leaf_nodes_info:
            node_info = self.qm.non_leaf_nodes_info[node_id]
            
            # 1. output_columns属性をチェック
            if hasattr(node_info, 'output_columns') and node_info.output_columns:
                return node_info.output_columns
            
            # 2. projection属性をチェック
            if hasattr(node_info, 'projection') and node_info.projection:
                return node_info.projection
            
            # 3. 子ノードから再帰的に推論
            if node_info.children:
                all_columns = []
                for child_id in node_info.children:
                    try:
                        child_columns = self._get_node_columns(child_id)
                        all_columns.extend(child_columns)
                    except Exception as e:
                        logger.warning(f"Failed to get columns from child {child_id}: {e}")
                
                if all_columns:
                    return all_columns
            
            # どの方法でも取得できない場合はエラー
            raise ValueError(f"Cannot infer columns for non-leaf node {node_id}")
        
        # 未知のノード
        raise ValueError(f"Unknown node: {node_id}")
    
    def _find_join_conditions(
            self,
            left_child: str,
            right_child: str,
            join_conditions: List
    ) -> Optional[str]:
        """2つの子ノード間のJOIN条件を探す
        
        Args:
            left_child: 左側の子ノードID
            right_child: 右側の子ノードID
            join_conditions: JOIN条件のリスト
            
        Returns:
            JOIN条件文字列（例: "t1.id = t2.id"）
        """
        for jc in join_conditions:
            if ((jc.left_table ==left_child and jc.right_table == right_child) or
                (jc.left_table == right_child and jc.right_table == left_child)):
                return f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
            
        return None
        
            
    
            
    
