"""Enhanced MV Generator with accurate JOIN condition handling.

This module provides EnhancedMVGenerator class that generates accurate
materialized view creation SQL using the enhanced JOIN information from
QueryParser and QueryManager.
"""

import logging
from typing import Any, Optional

from src.core.models import NonLeafNodeInfo, JoinCondition
from src.rewrite.schema_provider import SchemaProvider

logger = logging.getLogger(__name__)


class EnhancedMVGenerator:
    """Enhanced materialized view SQL generator (Chapter 4).
    
    This class generates accurate MV creation SQL by utilizing:
    - Complete JOIN condition information from NonLeafNodeInfo
    - Dynamic schema information from SchemaProvider
    - Proper child node ordering preservation
    
    Attributes:
        schema_provider: SchemaProvider for dynamic schema info
        qm: QueryManager instance
    """

    def __init__(self, query_manager: Any, schema_provider: Optional[SchemaProvider] = None, selected_mvs: Optional[set] = None):
        """Initialize EnhancedMVGenerator.
        
        Args:
            query_manager: QueryManager instance with enhanced node info
            schema_provider: Optional SchemaProvider for dynamic schema.
                           If None, will use fallback static schema.
            selected_mvs: Optional set of selected MV node IDs. If a child node
                         is not in this set, it will be expanded as a subquery.
        """
        self.qm = query_manager
        self.schema_provider = schema_provider
        self.selected_mvs = selected_mvs if selected_mvs is not None else set()
        
    def generate_mv_sql(self, node_id: str) -> str:
        """Generate MV creation SQL for a node.
        
        Args:
            node_id: Node ID (leaf_X or non_leaf_X)
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id.startswith("leaf_"):
            return self.generate_leaf_mv_sql(node_id)
        elif node_id.startswith("non_leaf_"):
            return self.generate_non_leaf_mv_sql(node_id)
        else:
            logger.warning(f"Unknown node type: {node_id}")
            return ""
    
    def generate_index_sql(self, node_id: str) -> str | None:
        """Generate CREATE INDEX SQL for a node if it requires an index.
        
        For leaf nodes that use Index Scan, generates a CREATE INDEX statement
        for the MV based on the columns used in the original Index Cond.
        
        Args:
            node_id: Node ID (leaf_X or non_leaf_X)
            
        Returns:
            CREATE INDEX statement if index is needed, None otherwise
        """
        # Check if requires_index_build attribute exists (for backward compatibility with old cache)
        if not hasattr(self.qm, 'requires_index_build'):
            return None
        
        # Check if this node requires an index
        if not self.qm.requires_index_build.get(node_id, False):
            return None
        
        # Check if index_columns attribute exists (for backward compatibility with old cache)
        if not hasattr(self.qm, 'index_columns'):
            return None
        
        # Get the index columns
        index_columns = self.qm.index_columns.get(node_id, [])
        if not index_columns:
            logger.warning(f"Node {node_id} requires index but no columns found")
            return None
        
        # Generate index name: idx_<mv_name>_<column1>_<column2>...
        column_suffix = "_".join(index_columns[:3])  # Limit to avoid too long names
        index_name = f"idx_{node_id}_{column_suffix}"
        
        # Generate CREATE INDEX statement
        columns_str = ", ".join(index_columns)
        sql = f"CREATE INDEX {index_name} ON {node_id} ({columns_str});"
        
        return sql
    
    def generate_mv_and_index_sql(self, node_id: str) -> tuple[str, str | None]:
        """Generate both MV creation SQL and INDEX creation SQL for a node.
        
        Args:
            node_id: Node ID (leaf_X or non_leaf_X)
            
        Returns:
            Tuple of (CREATE MATERIALIZED VIEW statement, CREATE INDEX statement or None)
        """
        mv_sql = self.generate_mv_sql(node_id)
        index_sql = self.generate_index_sql(node_id)
        return mv_sql, index_sql

    def generate_leaf_mv_sql(self, node_id: str) -> str:
        """Generate leaf MV creation SQL (Chapter 4).
        
        Args:
            node_id: Leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id not in self.qm.leaf_nodes_map_r:
            logger.error(f"Leaf node {node_id} not found")
            return ""
        
        operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
        
        if not table:
            logger.error(f"No table name for {node_id}")
            return ""
        
        # Get columns dynamically from schema
        columns = self._get_table_columns(table)
        
        # Build SELECT clause
        if columns:
            select_items = [f"{alias}.{col}" for col in columns]
            select_clause = ", ".join(select_items)
        else:
            select_clause = f"{alias}.*"
            logger.warning(f"No columns found for {table}, using *")
        
        # Build SQL
        sql_parts = [
            f"CREATE MATERIALIZED VIEW {node_id} AS",
            f"SELECT {select_clause}",
            f"FROM {table} AS {alias}"
        ]
        
        if filter_condition:
            sql_parts.append(f"WHERE {filter_condition}")
        
        sql_parts.append(";")
        
        return "\n".join(sql_parts)

    def generate_non_leaf_mv_sql(self, node_id: str) -> str:
        """Generate non-leaf MV creation SQL with accurate JOIN conditions (Chapter 4).
        
        This is the core improvement: we use the stored JOIN condition information
        to generate accurate JOIN clauses instead of guessing.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        # Check if enhanced info is available
        if node_id in self.qm.non_leaf_nodes_info:
            return self._generate_non_leaf_mv_enhanced(node_id)
        else:
            # Fallback to legacy method
            logger.warning(f"No enhanced info for {node_id}, using fallback")
            return self._generate_non_leaf_mv_fallback(node_id)

    def _generate_non_leaf_mv_enhanced(self, node_id: str) -> str:
        """Generate non-leaf MV using enhanced information.
        
        フラット展開: 子ノードを再帰的にテーブルレベルまで展開し、
        ネストしたサブクエリではなく、すべてのJOINをフラットに並べる。
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        try:
            node_info = self.qm.non_leaf_nodes_info[node_id]
            
            if not node_info.children:
                logger.error(f"No children for {node_id}")
                return ""
            
            # すべての子ノードをフラットに展開（テーブルまたは選択済みMV）
            flat_components = []
            all_join_conditions_set = set()  # 重複除去のためsetを使用
            all_filters = list(node_info.filters) if node_info.filters else []
            
            # 各子ノードをフラット化
            for child_id in node_info.children:
                child_flat = self._flatten_node(child_id)
                flat_components.append(child_flat)
                # 子ノードのJOIN条件とフィルタも収集（重複除去）
                for jc in child_flat.get('join_conditions', []):
                    all_join_conditions_set.add(jc)
                all_filters.extend(child_flat.get('filters', []))
            
            # 現在のノードのJOIN条件を追加（重複除去）
            if node_info.join_conditions:
                for jc in node_info.join_conditions:
                    if not jc.left_table or not jc.right_table:
                        continue
                    jc_str = f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
                    all_join_conditions_set.add(jc_str)
            
            # setをlistに変換
            all_join_conditions = list(all_join_conditions_set)
            
            # FROM句を構築：最初のコンポーネント
            from_parts = []
            first_comp = flat_components[0]
            
            # 最初のテーブル/MV
            first_table_added = False
            for table_info in first_comp['tables']:
                if not first_table_added:
                    from_parts.append(f"{table_info['source']} AS {table_info['alias']}")
                    first_table_added = True
                    break
            
            # エイリアスマップを作成（テーブル名→エイリアス変換用）
            table_to_alias = {}  # table_name -> alias
            
            for comp in flat_components:
                for table_info in comp['tables']:
                    source_name = table_info['source']
                    alias = table_info['alias']
                    if not source_name.startswith('mv_'):
                        # 通常のテーブル
                        table_to_alias[source_name] = alias
            
            # サブツリー全体から全てのJOIN条件を収集（既存の条件に追加）
            subtree_join_conditions = self._collect_all_join_conditions(node_info, self.qm)
            for jc in subtree_join_conditions:
                if not jc.left_table or not jc.right_table:
                    logger.debug(f"Skipping join condition with empty table: .{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
                    continue
                jc_str = f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
                all_join_conditions_set.add(jc_str)
            
            # JOIN条件のテーブル名をエイリアスに変換
            converted_join_conditions = []
            for jc_str in all_join_conditions_set:
                # テーブル名をエイリアスに置換（まだ置換されていない場合）
                converted_jc = jc_str
                for table_name, alias in table_to_alias.items():
                    converted_jc = converted_jc.replace(f"{table_name}.", f"{alias}.")
                
                converted_join_conditions.append(converted_jc)
            
            # 残りをカンマ結合で追加（JOIN条件は全てWHERE句で指定）
            for comp in flat_components:
                for i, table_info in enumerate(comp['tables']):
                    if comp == flat_components[0] and i == 0:
                        continue  # 最初のテーブルはスキップ済み
                    
                    # カンマ結合を使用し、全てのJOIN条件をWHERE句に移動
                    # これによりPostgreSQLのクエリプランナーが最適なJOIN順序を決定できる
                    from_parts.append(f", {table_info['source']} AS {table_info['alias']}")
            
            from_clause = " ".join(from_parts)  # カンマ結合なので改行は不要
            
            # SELECT句を構築：カラム重複を避けるため、各テーブルのカラムを明示的に指定
            select_parts = []
            seen_columns = set()  # 重複カラム名を追跡
            
            for comp in flat_components:
                for table_info in comp['tables']:
                    table_name = table_info['source']
                    alias = table_info['alias']
                    
                    # テーブルのカラムを取得
                    columns = self._get_table_columns(table_name)
                    
                    if columns:
                        for col in columns:
                            # カラム名が重複している場合は、エイリアス付きで選択
                            if col in seen_columns:
                                # 重複カラムはエイリアスを付けて区別
                                select_parts.append(f"{alias}.{col} AS {alias}_{col}")
                            else:
                                select_parts.append(f"{alias}.{col}")
                                seen_columns.add(col)
                    else:
                        # スキーマ情報がない場合は、テーブル全体を選択（エイリアス付き）
                        logger.warning(f"No schema info for {table_name}, using {alias}.*")
                        select_parts.append(f"{alias}.*")
            
            select_clause = ",\n    ".join(select_parts) if select_parts else "*"
            
            # WHERE句構築: すべてのJOIN条件とフィルタを含める
            where_clause = ""
            where_conditions = converted_join_conditions + all_filters
            if where_conditions:
                where_clause = f"\nWHERE {' AND '.join(where_conditions)}"
            
            # Build final SQL
            sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT {select_clause}
FROM {from_clause}{where_clause};"""
            
            return sql
        except Exception as e:
            logger.error(f"Error in _generate_non_leaf_mv_enhanced for {node_id}: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to old method
            return self._generate_non_leaf_mv_fallback(node_id)
    
    def _flatten_node(self, node_id: str) -> dict:
        """ノードを再帰的にフラット化してテーブル/選択済みMVのリストに変換
        
        Args:
            node_id: ノードID
            
        Returns:
            {
                'tables': [{'source': テーブル名またはMV名, 'alias': エイリアス}, ...],
                'join_conditions': [JOIN条件の文字列, ...],
                'filters': [フィルタ条件の文字列, ...]
            }
        """
        # leafノードの場合
        if node_id in self.qm.leaf_nodes_map_r:
            operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
            
            # フィルタ条件にテーブルエイリアスを追加
            fixed_filter = self._add_table_alias_to_filter(filter_condition, alias) if filter_condition else None
            
            result = {
                'tables': [{'source': table, 'alias': alias}],
                'join_conditions': [],
                'filters': [fixed_filter] if fixed_filter else []
            }
            return result
        
        # non-leafノードの場合
        elif node_id in self.qm.non_leaf_nodes_info:
            # 選択済みMVなら、それ自体を1つのテーブルとして扱う
            if node_id in self.selected_mvs:
                return {
                    'tables': [{'source': node_id, 'alias': node_id}],
                    'join_conditions': [],
                    'filters': []
                }
            
            # 選択されていない場合は、さらに展開
            node_info = self.qm.non_leaf_nodes_info[node_id]
            result = {
                'tables': [],
                'join_conditions': [],
                'filters': list(node_info.filters) if node_info.filters else []
            }
            
            # 子ノードを再帰的に展開
            for child_id in node_info.children:
                child_flat = self._flatten_node(child_id)
                result['tables'].extend(child_flat['tables'])
                result['join_conditions'].extend(child_flat['join_conditions'])
                result['filters'].extend(child_flat['filters'])
            
            # このノードのJOIN条件を追加（重複除去）
            if node_info.join_conditions:
                for jc in node_info.join_conditions:
                    if not jc.left_table or not jc.right_table:
                        continue
                    jc_str = f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
                    if jc_str not in result['join_conditions']:
                        result['join_conditions'].append(jc_str)
            
            return result
        
        else:
            logger.error(f"Node {node_id} not found")
            return {'tables': [], 'join_conditions': [], 'filters': []}
    
    def _add_table_alias_to_filter(self, filter_condition: str, table_alias: str) -> str:
        """フィルタ条件内のカラム参照にテーブルエイリアスを追加
        
        Args:
            filter_condition: 元のフィルタ条件（例: "((info)::text = 'top 250 rank'::text)"）
            table_alias: テーブルエイリアス（例: "it"）
            
        Returns:
            エイリアスを追加したフィルタ条件（例: "((it.info)::text = 'top 250 rank'::text)"）
        """
        if not filter_condition or not table_alias:
            return filter_condition
        
        import re
        
        # SQLキーワードとリテラルパターン（除外対象）
        sql_keywords = {
            'AND', 'OR', 'NOT', 'IN', 'ANY', 'ALL', 'IS', 'NULL', 'TRUE', 'FALSE',
            'LIKE', 'ILIKE', 'BETWEEN', 'EXISTS', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
            'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST', 'AS', 'CAST', 'text', 'integer',
            'varchar', 'boolean', 'date', 'timestamp', 'numeric', 'float', 'double'
        }
        
        # カラム参照のパターンを検出: (カラム名):: の形式
        # 既にエイリアスが付いている場合はスキップ（alias.column の形式）
        def replace_column_cast(match):
            full_match = match.group(0)
            column_name = match.group(1)
            # 既にエイリアスが付いているかチェック
            if '.' in column_name:
                return full_match  # そのまま返す
            # SQLキーワードはスキップ
            if column_name.upper() in sql_keywords:
                return full_match
            # エイリアスを追加: (カラム名):: → (alias.カラム名)::
            return f"({table_alias}.{column_name})::"
        
        # パターン1: (カラム名):: → (alias.カラム名)::
        result = re.sub(r'\((\w+)\)::', replace_column_cast, filter_condition)
        
        # パターン2: (カラム名 IS NOT NULL) または (カラム名 IS NULL) の形式
        # 例: "(note IS NOT NULL)" → "(alias.note IS NOT NULL)"
        def replace_is_null_pattern(match):
            prefix = match.group(1)  # 前の括弧やスペース
            column_name = match.group(2)
            rest = match.group(3)  # "IS NOT NULL" または "IS NULL" など
            
            # 既にエイリアスが付いている場合はスキップ
            if '.' in column_name:
                return match.group(0)
            # SQLキーワードはスキップ
            if column_name.upper() in sql_keywords:
                return match.group(0)
            
            return f"{prefix}{table_alias}.{column_name}{rest}"
        
        # (column IS NULL) / (column IS NOT NULL) パターン
        result = re.sub(
            r'(\(|\s)(\w+)(\s+IS\s+(?:NOT\s+)?NULL)',
            replace_is_null_pattern,
            result,
            flags=re.IGNORECASE
        )
        
        # パターン3: WHERE句などで単独で使われるカラム名
        # 例: "note = 'something'" → "alias.note = 'something'"
        # ただし、関数名や既にエイリアスが付いているものは除外
        def replace_bare_column(match):
            prefix = match.group(1)  # 前の文字（スペースや括弧）
            column_name = match.group(2)
            suffix = match.group(3)  # 後ろの文字（演算子など）
            
            # 既にエイリアスが付いている場合はスキップ
            if '.' in column_name:
                return match.group(0)
            # SQLキーワードはスキップ
            if column_name.upper() in sql_keywords:
                return match.group(0)
            # 数値はカラム名ではないのでスキップ（1950, 100 などの定数）
            if column_name.isdigit():
                return match.group(0)
            
            return f"{prefix}{table_alias}.{column_name}{suffix}"
        
        # 単語境界で囲まれたカラム名を検出（演算子の前など）
        result = re.sub(
            r'(\s|\(|^)(\w+)(?![.(])(\s*(?:=|!=|<|>|<=|>=|~|!~|LIKE|ILIKE|IN|ANY))',
            replace_bare_column,
            result,
            flags=re.IGNORECASE
        )
        
        return result
    
    def _get_child_source(self, child_id: str) -> dict:
        """Get source SQL for a child node (table or subquery).
        
        For MV creation, we reference already-created MVs if they are selected.
        If a child MV is not selected, we expand it as a subquery.
        
        Args:
            child_id: Child node ID
            
        Returns:
            Dict with 'type' ('table', 'mv', or 'subquery'), and relevant info
        """
        # Check if leaf node
        if child_id in self.qm.leaf_nodes_map_r:
            operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[child_id]
            return {
                'type': 'table',
                'table': table,
                'alias': alias,
                'filter': filter_condition
            }
        # Check if non-leaf node
        elif child_id in self.qm.non_leaf_nodes_info:
            # Check if this MV is selected
            if child_id in self.selected_mvs:
                # Reference the MV that should already be created (topological order)
                return {
                    'type': 'mv',
                    'mv_name': child_id,
                    'alias': child_id
                }
            else:
                # MV not selected: expand as subquery
                logger.debug(f"Expanding {child_id} as subquery (not selected as MV)")
                child_sql = self._generate_child_subquery(child_id)
                return {
                    'type': 'subquery',
                    'sql': child_sql,
                    'alias': child_id
                }
        else:
            logger.error(f"Child {child_id} not found in leaf or non-leaf maps")
            return {
                'type': 'table',
                'table': 'UNKNOWN',
                'alias': child_id,
                'filter': ''
            }
    
    def _generate_child_subquery(self, node_id: str) -> str:
        """Generate subquery SQL for a non-leaf child (without CREATE statement).
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            SELECT statement (without CREATE MATERIALIZED VIEW)
        """
        # This is similar to _generate_non_leaf_mv_enhanced but returns SELECT only
        full_sql = self._generate_non_leaf_mv_enhanced(node_id)
        
        # Extract SELECT ... FROM ... WHERE part (remove CREATE MATERIALIZED VIEW)
        if "SELECT" in full_sql:
            select_part = full_sql.split("AS\n", 1)[1].rsplit(";", 1)[0].strip()
            return select_part
        else:
            return "SELECT * FROM dual"  # Fallback
    
    def _build_join_clause_for_sources(
        self,
        left_alias: str,
        right_part: str,
        right_alias: str,
        join_type: str,
        join_conditions: list[JoinCondition],
        left_tables: list[str],
        right_tables: list[str]
    ) -> str:
        """Build JOIN clause for table/subquery sources.
        
        Args:
            left_alias: Alias of left source
            right_part: Right source (table or subquery with alias)
            right_alias: Alias of right source
            join_type: JOIN type
            join_conditions: List of JOIN conditions
            left_tables: Original table aliases in left source
            right_tables: Original table aliases in right source
            
        Returns:
            JOIN clause string
        """
        # Find conditions that connect these two sources
        matching_conditions = self._find_join_conditions_for_mvs(
            join_conditions, left_tables, right_tables
        )
        
        if matching_conditions:
            # Build condition string using original table aliases
            condition_parts = []
            for jc in matching_conditions:
                # Use the original table aliases from the condition
                condition_parts.append(f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
            
            condition_str = " AND ".join(condition_parts) if condition_parts else "TRUE"
        else:
            # No specific join conditions found, use TRUE (cross join)
            logger.warning(f"No join conditions found between {left_tables} and {right_tables}, using cross join")
            condition_str = "TRUE"
        
        return f"{join_type} JOIN {right_part} ON {condition_str}"

    def _build_join_clause(
        self,
        left_mv: str,
        right_mv: str,
        join_type: str,
        join_conditions: list[JoinCondition],
        left_tables: list[str],
        right_tables: list[str]
    ) -> str:
        """Build JOIN clause for two child MVs.
        
        Args:
            left_mv: Left MV node ID
            right_mv: Right MV node ID
            join_type: JOIN type (Inner, Left, Right, etc.)
            join_conditions: List of JOIN conditions
            left_tables: Table aliases covered by left MV
            right_tables: Table aliases covered by right MV
            
        Returns:
            JOIN clause string (e.g., "INNER JOIN mv_2 ON mv_1.id = mv_2.ref_id")
        """
        # Find conditions that connect these two MVs
        matching_conditions = self._find_join_conditions_for_mvs(
            join_conditions, left_tables, right_tables
        )
        
        if matching_conditions:
            # Build condition string
            condition_parts = []
            for jc in matching_conditions:
                # Determine which alias is in which MV and rewrite to use MV names
                if jc.left_table in left_tables and jc.right_table in right_tables:
                    condition_parts.append(
                        f"{left_mv}.{jc.left_column} {jc.operator} {right_mv}.{jc.right_column}"
                    )
                elif jc.right_table in left_tables and jc.left_table in right_tables:
                    condition_parts.append(
                        f"{left_mv}.{jc.right_column} {jc.operator} {right_mv}.{jc.left_column}"
                    )
                else:
                    # Condition might reference tables in the same MV
                    logger.warning(f"Join condition references tables not in MVs: {jc}")
            
            if condition_parts:
                condition_str = " AND ".join(condition_parts)
            else:
                condition_str = "TRUE  -- WARNING: Could not map join conditions to MVs"
        else:
            # Try to infer from foreign keys
            condition_str = self._infer_join_condition(
                left_mv, right_mv, left_tables, right_tables
            )
        
        return f"{join_type} JOIN {right_mv} ON {condition_str}"

    def _find_join_conditions_for_mvs(
        self,
        join_conditions: list[JoinCondition],
        left_tables: list[str],
        right_tables: list[str]
    ) -> list[JoinCondition]:
        """Find JOIN conditions that connect two sets of tables.
        
        Args:
            join_conditions: All JOIN conditions
            left_tables: Tables in left MV
            right_tables: Tables in right MV
            
        Returns:
            List of matching JoinCondition objects
        """
        matching = []
        
        for jc in join_conditions:
            # Check if this condition connects the two MVs
            if (jc.left_table in left_tables and jc.right_table in right_tables) or \
               (jc.right_table in left_tables and jc.left_table in right_tables):
                matching.append(jc)
        
        return matching

    def _infer_join_condition(
        self,
        left_mv: str,
        right_mv: str,
        left_tables: list[str],
        right_tables: list[str]
    ) -> str:
        """Infer JOIN condition from foreign key relationships.
        
        Args:
            left_mv: Left MV node ID
            right_mv: Right MV node ID
            left_tables: Tables in left MV
            right_tables: Tables in right MV
            
        Returns:
            JOIN condition string
        """
        if not self.schema_provider:
            logger.warning(f"No schema provider, cannot infer JOIN between {left_mv} and {right_mv}")
            return "TRUE  -- WARNING: Join condition could not be inferred"
        
        try:
            # Try to find FK relationship
            fk_relations = self.schema_provider.get_foreign_key_relations(
                left_tables, right_tables
            )
            
            if fk_relations:
                # Use first FK relationship
                fk = fk_relations[0]
                logger.info(
                    f"Inferred JOIN: {left_mv}.{fk.from_column} = {right_mv}.{fk.to_column}"
                )
                return f"{left_mv}.{fk.from_column} = {right_mv}.{fk.to_column}"
            else:
                logger.warning(f"No FK found between {left_tables} and {right_tables}")
                return "TRUE  -- WARNING: No FK relationship found"
                
        except Exception as e:
            logger.error(f"Error inferring JOIN condition: {e}")
            return "TRUE  -- WARNING: Error inferring join condition"

    def _build_select_clause(self, child_mvs: list[dict]) -> str:
        """Build SELECT clause for non-leaf MV.
        
        Args:
            child_mvs: List of child MV info dicts
            
        Returns:
            SELECT clause string
        """
        # Simple approach: select all from all child MVs
        select_parts = [f"{mv['id']}.*" for mv in child_mvs]
        return ", ".join(select_parts)

    def _rewrite_filter_for_mvs(
        self,
        filter_str: str,
        child_mvs: list[dict]
    ) -> Optional[str]:
        """Rewrite filter condition to use MV names instead of table aliases.
        
        Args:
            filter_str: Original filter string (e.g., "t.year > 2000")
            child_mvs: List of child MV info
            
        Returns:
            Rewritten filter string or None if cannot rewrite
        """
        # This is a simplified implementation
        # In practice, you'd need more sophisticated parsing
        # For now, just return the filter as-is
        # TODO: Implement proper alias rewriting
        logger.debug(f"Filter rewriting not fully implemented: {filter_str}")
        return filter_str

    def _get_child_tables(self, node_id: str) -> list[str]:
        """Get all table aliases covered by a node.
        
        This returns aliases (not table names) because JOIN conditions
        use aliases from the original query.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of table aliases
        """
        aliases = set()
        
        if node_id.startswith("leaf_"):
            # Get alias from leaf node
            if node_id in self.qm.leaf_nodes_map_r:
                operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
                if alias:
                    aliases.add(alias)
        elif node_id.startswith("non_leaf_"):
            # Recursively get aliases from children
            if node_id in self.qm.non_leaf_nodes_map_r:
                for child_id in self.qm.non_leaf_nodes_map_r[node_id]:
                    aliases.update(self._get_child_tables(child_id))
        
        return list(aliases)

    def _collect_all_join_conditions(self, node_info: NonLeafNodeInfo, qm: Any) -> list[JoinCondition]:
        """サブツリー全体から全てのJOIN条件を再帰的に収集.
        
        Args:
            node_info: 現在のノードの情報
            qm: QueryManager インスタンス
            
        Returns:
            サブツリー内の全てのJOIN条件のリスト
        """
        all_conditions = []
        
        # 現在のノードのJOIN条件を追加
        if node_info.join_conditions:
            all_conditions.extend(node_info.join_conditions)
        
        # 子ノードがnon_leafなら再帰的に収集
        for child in node_info.children:
            # 子ノードIDを取得
            child_node_id = None
            
            # childが文字列の場合
            if isinstance(child, str):
                child_node_id = child
            # childがオブジェクトの場合
            elif hasattr(child, 'node_id'):
                child_node_id = child.node_id
            elif hasattr(child, 'id'):
                child_node_id = child.id
            
            # non_leaf子ノードの場合のみ再帰処理
            if child_node_id and child_node_id.startswith('non_leaf_'):
                if child_node_id in qm.non_leaf_nodes_info:
                    child_node = qm.non_leaf_nodes_info[child_node_id]
                    # 再帰的に子ノードのJOIN条件を収集
                    all_conditions.extend(
                        self._collect_all_join_conditions(child_node, qm)
                    )
        
        return all_conditions
    
    def _get_table_columns(self, table_name: str) -> list[str]:
        """Get columns for a table.
        
        Args:
            table_name: Table name
            
        Returns:
            List of column names
        """
        if self.schema_provider:
            try:
                return self.schema_provider.get_table_columns(table_name)
            except Exception as e:
                logger.warning(f"Error getting columns for {table_name}: {e}")
        
        # Fallback to static schema
        try:
            from .schema import get_table_columns
            return get_table_columns(table_name)
        except KeyError:
            logger.warning(f"Table {table_name} not in schema")
            return []

    def _generate_non_leaf_mv_fallback(self, node_id: str) -> str:
        """Fallback method for generating non-leaf MV without enhanced info.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id not in self.qm.non_leaf_nodes_map_r:
            return ""
        
        child_ids = list(self.qm.non_leaf_nodes_map_r[node_id])
        
        if len(child_ids) < 2:
            logger.warning(f"Insufficient children for {node_id}")
            return ""
        
        # Simple fallback: assume simple equality JOIN on 'id'
        from_clause = child_ids[0]
        for child in child_ids[1:]:
            from_clause += f"\nJOIN {child} ON {child_ids[0]}.id = {child}.id"
        
        sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT *
FROM {from_clause};"""
        
        logger.warning(f"Used fallback generation for {node_id}")
        return sql
