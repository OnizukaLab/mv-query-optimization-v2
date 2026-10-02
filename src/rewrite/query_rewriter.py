"""クエリ書き換えロジック"""

import os
import re
from pathlib import Path
from typing import Any
import logging

from src.rewrite.mv_generator import MVGenerator
from src.rewrite.sql_parser import SQLParser
from src.rewrite.join_graph import JoinGraph, JoinMinimizer
from src.utils.legacy import natural_sort_key
import sqlparse
from sqlparse.sql import Where, TokenList

logger = logging.getLogger(__name__)


class QueryRewriter:
    """クエリ書き換え管理"""

    def __init__(self, query_manager: Any = None, containment_matrix: list = None, node_list: list = None, query_set: str = "job"):
        """初期化

        Args:
            query_manager: クエリ管理オブジェクトまたはSettings
            containment_matrix: X行列（包含関係）。X[i][j]=1 ならノードiがノードjを包含
            node_list: ノードIDのリスト（X行列のインデックスに対応）
            query_set: クエリセット名（未指定時はjob）
        """
        # settingsオブジェクトが渡された場合の対応
        if hasattr(query_manager, 'database'):
            # これはSettingsオブジェクト
            self.settings = query_manager
            self.qm = None
        else:
            # これはQueryManagerオブジェクト
            self.qm = query_manager
            self.settings = None
        
        # 包含行列（冗長MV除去に使用）
        self.containment_matrix = containment_matrix
        self.node_list = node_list
        self.query_set = query_set or "job"
        if containment_matrix is not None and node_list is not None:
            self._node_to_idx = {node_id: idx for idx, node_id in enumerate(node_list)}
            logger.info(f"Containment matrix enabled: {len(node_list)} nodes")
        else:
            self._node_to_idx = {}
            logger.debug("Containment matrix not provided - redundant MV filtering disabled")
        
        self.sql_parser = SQLParser()
        self.mv_generator = MVGenerator()

    def _get_query_dir(self) -> Path:
        """書き換え対象クエリのディレクトリを解決

        後方互換のため、query_set未指定時はjobを使用。
        """
        if self.settings:
            base_dir = Path(self.settings.benchmark.sql_dir)
            target_dir = base_dir / self.query_set
            if target_dir.exists():
                return target_dir
            return base_dir / "job"

        return Path("dataset/RED_SQL/job")
    
    def rewrite_queries(self, selected_views: list) -> dict[str, str]:
        """選択されたMVを使ってクエリを書き換える
        
        Args:
            selected_views: 選択されたMaterialized Viewsのリスト
                          各要素は {'view_id': str, 'node_id': str, 'create_sql': str, 
                                    'usage_positions': [[query_num, position], ...]} の辞書
            
        Returns:
            {query_id: rewritten_sql} の辞書
        """
        logger.info(f"Starting query rewriting with {len(selected_views)} selected views")
        
        # クエリごとに使用するMVをマッピング
        query_to_mvs = self._build_query_mv_mapping(selected_views)
        
        # 元のクエリファイルのパスを取得
        if self.settings:
            query_selection_mode = getattr(self.settings.benchmark, 'query_selection_mode', 'redbench')
            if query_selection_mode == 'all_ceb':
                ceb_template = getattr(self.settings.benchmark, 'ceb_template', '1a')
                ceb_limit = getattr(self.settings.benchmark, 'ceb_limit', None)
                query_dir = Path(self.settings.benchmark.sql_dir) / "ceb" / ceb_template
            else:
                query_dir = Path(self.settings.benchmark.sql_dir) / "job"
                ceb_limit = None
        else:
            query_dir = Path("dataset/RED_SQL/job")
            ceb_limit = None
        
        rewritten = {}
        
        # 各クエリを処理（optimizationフェーズと同じnatural_sort_keyでソート）
        all_query_files = sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x)))
        if ceb_limit is not None:
            all_query_files = all_query_files[:ceb_limit]
        for query_file in all_query_files:
            query_id = query_file.stem  # ファイル名から拡張子を除いた部分 (e.g., "1a")
            
            # このクエリに使用するMVがない場合は元のクエリをそのまま使用
            if query_id not in query_to_mvs or not query_to_mvs[query_id]:
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
                continue
            
            # クエリを書き換え
            try:
                rewritten_sql = self._rewrite_single_query(
                    query_file, 
                    query_to_mvs[query_id]
                )
                rewritten[query_id] = rewritten_sql
                logger.debug(f"Successfully rewrote query {query_id}")
            except Exception as e:
                logger.error(f"Error rewriting query {query_id}: {e}")
                # エラー時は元のクエリを使用
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
        
        logger.info(f"Completed query rewriting for {len(rewritten)} queries")
        return rewritten
    
    def _build_query_mv_mapping(self, selected_views: list) -> dict[str, list]:
        """selected_viewsからクエリごとに使用するMVのマッピングを作成
        
        Args:
            selected_views: 選択されたMaterialized Viewsのリスト (MaterializedViewオブジェクト)
            
        Returns:
            {query_id: [MaterializedView, ...]} の辞書
        """
        # クエリ番号（0ベース）からファイル名へのマッピングを作成
        # optimizationフェーズと同じnatural_sort_keyを使用
        if self.settings:
            query_selection_mode = getattr(self.settings.benchmark, 'query_selection_mode', 'redbench')
            if query_selection_mode == 'all_ceb':
                ceb_template = getattr(self.settings.benchmark, 'ceb_template', '1a')
                ceb_limit = getattr(self.settings.benchmark, 'ceb_limit', None)
                query_dir = Path(self.settings.benchmark.sql_dir) / "ceb" / ceb_template
            else:
                query_dir = Path(self.settings.benchmark.sql_dir) / "job"
                ceb_limit = None
        else:
            query_dir = Path("dataset/RED_SQL/job")
            ceb_limit = None
        
        # optimizationフェーズと同じソート順を使用（natural_sort_key）
        all_query_files = sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x)))
        if ceb_limit is not None:
            all_query_files = all_query_files[:ceb_limit]
        query_num_to_id = {i: f.stem for i, f in enumerate(all_query_files)}
        
        logger.debug(f"Built query number to ID mapping for {len(query_num_to_id)} queries")
        if logger.isEnabledFor(logging.DEBUG):
            # 最初の10個のマッピングをログ出力
            for i in range(min(10, len(query_num_to_id))):
                logger.debug(f"  Query {i}: {query_num_to_id[i]}")
        
        query_to_mvs = {}
        
        for mv in selected_views:
            # MaterializedViewオブジェクトの場合
            if hasattr(mv, 'usage_positions'):
                usage_positions = mv.usage_positions
            # 辞書の場合（後方互換性）
            elif isinstance(mv, dict) and 'usage_positions' in mv:
                usage_positions = mv['usage_positions']
            else:
                continue
                
            for position in usage_positions:
                query_num = position[0]  # クエリ番号 (0ベース: 0-112)
                
                # クエリ番号をクエリIDに変換
                if query_num not in query_num_to_id:
                    logger.warning(f"Query number {query_num} not found in mapping")
                    continue
                
                query_id = query_num_to_id[query_num]
                
                if query_id not in query_to_mvs:
                    query_to_mvs[query_id] = []
                
                query_to_mvs[query_id].append(mv)
        
        # 包含行列を使って冗長なMVを除去
        if self.containment_matrix is not None and self._node_to_idx:
            query_to_mvs = self._filter_redundant_mvs(query_to_mvs)
        
        return query_to_mvs
    
    def _filter_redundant_mvs(self, query_to_mvs: dict) -> dict:
        """包含行列を使って冗長なMVを除去
        
        MV Aが MV Bを包含している場合（X[A][B]=1）、MV Bは冗長なので除去する。
        
        Args:
            query_to_mvs: {query_id: [MV, ...]} のマッピング
            
        Returns:
            冗長MV除去後のマッピング
        """
        filtered = {}
        total_removed = 0
        
        for query_id, mvs in query_to_mvs.items():
            if len(mvs) <= 1:
                filtered[query_id] = mvs
                continue
            
            # 各MVのnode_idを取得
            mv_node_ids = []
            for mv in mvs:
                if hasattr(mv, 'node_id'):
                    node_id = mv.node_id
                elif isinstance(mv, dict):
                    node_id = mv.get('node_id', '')
                else:
                    node_id = ''
                mv_node_ids.append(node_id)
            
            # 冗長なMVを特定（他のMVに包含されているもの）
            redundant_indices = set()
            for i, node_i in enumerate(mv_node_ids):
                for j, node_j in enumerate(mv_node_ids):
                    if i == j:
                        continue
                    idx_i = self._node_to_idx.get(node_i)
                    idx_j = self._node_to_idx.get(node_j)
                    if idx_i is not None and idx_j is not None:
                        # X[i][j]=1 ならノードiがノードjを包含
                        if self.containment_matrix[idx_i][idx_j] == 1:
                            redundant_indices.add(j)
                            logger.debug(f"Query {query_id}: {node_i} contains {node_j} - removing {node_j}")
            
            # 冗長でないMVのみを保持
            non_redundant_mvs = [mv for k, mv in enumerate(mvs) if k not in redundant_indices]
            filtered[query_id] = non_redundant_mvs
            total_removed += len(redundant_indices)
        
        if total_removed > 0:
            logger.info(f"Removed {total_removed} redundant MVs using containment matrix")
        
        return filtered
    
    def _rewrite_single_query(self, query_file: Path, mvs: list) -> str:
        """単一のクエリをMVを使って書き換え
        
        Args:
            query_file: 元のクエリファイルのパス
            mvs: このクエリに使用するMVのリスト
            
        Returns:
            書き換えられたSQL文
        """
        # 元のクエリを読み込み
        with open(query_file, 'r') as f:
            original_sql = f.read()
        
        # SQL正規化
        sql = self._normalize_sql(original_sql)
        
        # SQLを構成要素に分解
        parts = self._parse_sql_parts(sql)
        
        # 各MVを適用
        for mv in mvs:
            parts = self._apply_mv_to_query(parts, mv)
        
        # 書き換えたSQLを再構築
        rewritten_sql = self._reconstruct_sql(parts)
        
        return rewritten_sql
    
    def _normalize_sql(self, sql: str) -> str:
        """SQLを正規化（スペース、改行、大文字小文字の統一など）
        
        Args:
            sql: 元のSQL文
            
        Returns:
            正規化されたSQL文
        """
        # ステップ1: 文字列リテラルを保護（一時的にプレースホルダーに置換）
        string_literals = []
        
        def replace_literal(match):
            """文字列リテラルをプレースホルダーに置換"""
            literal = match.group(0)
            placeholder = f"__STRING_LITERAL_{len(string_literals)}__"
            string_literals.append(literal)
            return placeholder
        
        # シングルクォートとダブルクォートの両方に対応（エスケープも考慮）
        # パターン: 'で囲まれた文字列 または "で囲まれた文字列
        sql = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", replace_literal, sql)
        
        # ステップ2: SQL正規化（文字列リテラルが保護されているので安全）
        # 改行を空白に
        sql = sql.replace('\n', ' ')
        
        # 複数の空白を1つに
        sql = re.sub(r'\s+', ' ', sql)
        
        # キーワードの大文字統一（文字列リテラルは既にプレースホルダーなので影響を受けない）
        sql = re.sub(r'\bas\b', 'AS', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\band\b', 'AND', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bor\b', 'OR', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\blike\b', 'LIKE', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bnot\b', 'NOT', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bin\b', 'IN', sql, flags=re.IGNORECASE)
        
        # 演算子の前後にスペース
        sql = re.sub(r'(?<! )=(?! )', ' = ', sql)
        sql = sql.replace('! =', '!=')
        
        # ステップ3: 文字列リテラルを復元
        for i, literal in enumerate(string_literals):
            placeholder = f"__STRING_LITERAL_{i}__"
            sql = sql.replace(placeholder, literal)
        
        return sql.strip()

    
    def _parse_sql_parts(self, sql: str) -> dict:
        """SQLを構成要素に分解
        
        Args:
            sql: SQL文
            
        Returns:
            {'select': str, 'from': str, 'where': str, 'group_by': str} の辞書
        """
        parts = {
            'select': '',
            'from': '',
            'where': '',
            'group_by': ''
        }

        def join_token_values(token_slice) -> str:
            return ' '.join(t.value.strip() for t in token_slice if t.value and t.value.strip())

        # sqlparseベースで句境界を解釈（文字列リテラル内の ; を誤認しない）
        parsed = sqlparse.parse(sql)
        if parsed:
            stmt = parsed[0]
            tokens = [t for t in stmt.tokens if not t.is_whitespace]

            def is_boundary_keyword(token) -> bool:
                if token.ttype is None:
                    return False
                if token.ttype.parent != sqlparse.tokens.Keyword and token.ttype != sqlparse.tokens.Keyword:
                    return False
                return token.normalized in {
                    'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING',
                    'LIMIT', 'UNION', 'EXCEPT', 'INTERSECT'
                }

            select_idx = None
            from_idx = None
            for i, token in enumerate(tokens):
                if token.ttype == sqlparse.tokens.DML and token.normalized == 'SELECT':
                    select_idx = i
                    break

            if select_idx is not None:
                for i in range(select_idx + 1, len(tokens)):
                    token = tokens[i]
                    if token.ttype == sqlparse.tokens.Keyword and token.normalized == 'FROM':
                        from_idx = i
                        break

            if select_idx is not None and from_idx is not None and from_idx > select_idx:
                parts['select'] = join_token_values(tokens[select_idx + 1:from_idx]).strip()
                # sqlparseトークン結合時に DISTINCT ON が DISTINCTON へ潰れる場合があるため補正
                parts['select'] = re.sub(r'\bDISTINCT\s*ON\b', 'DISTINCT ON', parts['select'], flags=re.IGNORECASE)

            if from_idx is not None:
                from_end = len(tokens)
                for i in range(from_idx + 1, len(tokens)):
                    token = tokens[i]
                    if isinstance(token, Where) or is_boundary_keyword(token) or token.value == ';':
                        from_end = i
                        break
                parts['from'] = join_token_values(tokens[from_idx + 1:from_end]).strip()

            where_token = None
            for token in tokens:
                if isinstance(token, Where):
                    where_token = token
                    break

            if where_token is not None:
                where_text = where_token.value
                parts['where'] = re.sub(r'^\s*WHERE\s+', '', where_text, flags=re.IGNORECASE).strip().rstrip(';').strip()

            group_idx = None
            for i, token in enumerate(tokens):
                if token.ttype == sqlparse.tokens.Keyword and token.normalized == 'GROUP BY':
                    group_idx = i
                    break

            if group_idx is not None:
                group_end = len(tokens)
                for i in range(group_idx + 1, len(tokens)):
                    token = tokens[i]
                    if (token.ttype == sqlparse.tokens.Keyword and token.normalized in {'ORDER BY', 'LIMIT', 'UNION', 'EXCEPT', 'INTERSECT'}) or token.value == ';':
                        group_end = i
                        break
                parts['group_by'] = join_token_values(tokens[group_idx + 1:group_end]).strip()

        # sqlparseで取得できなかった場合のフォールバック
        if not parts['select'] or not parts['from']:
            select_match = re.search(r'SELECT\s+(.+?)\s+FROM\s+', sql, re.IGNORECASE | re.DOTALL)
            if not select_match:
                select_match = re.search(r'SELECT\s+(.+?)\sFROM\s', sql, re.IGNORECASE | re.DOTALL)
            if select_match and not parts['select']:
                parts['select'] = select_match.group(1).strip()

            from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|\s+GROUP\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if from_match and not parts['from']:
                parts['from'] = from_match.group(1).strip().rstrip(';').strip()

            where_match = re.search(r'WHERE\s+(.+?)(?:\s+GROUP\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if where_match and not parts['where']:
                parts['where'] = where_match.group(1).strip().rstrip(';').strip()

            group_match = re.search(r'GROUP\s+BY\s+(.+?)(?:\s+ORDER\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if group_match and not parts['group_by']:
                parts['group_by'] = group_match.group(1).strip().rstrip(';').strip()

        # JOIN ... ON を内部処理しやすい形式に平坦化
        if re.search(r'\bJOIN\b', parts['from'], re.IGNORECASE):
            flattened_from, join_conditions = self._flatten_join_from_clause(parts['from'])
            if flattened_from:
                parts['from'] = flattened_from
            if join_conditions:
                join_where = ' AND '.join(join_conditions)
                if parts['where']:
                    parts['where'] = f"{join_where} AND {parts['where']}"
                else:
                    parts['where'] = join_where
        
        return parts

    def _normalize_identifier_token(self, token: str) -> str:
        token = token.strip()
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            return token[1:-1]
        return token

    def _parse_table_expr(self, expr: str) -> tuple[str, str]:
        """テーブル式から table_name と alias を抽出"""
        expr = expr.strip()
        match = re.match(
            r'^("?[A-Za-z_][A-Za-z0-9_]*"?)\s*(?:AS\s+)?("?[A-Za-z_][A-Za-z0-9_]*"?)?$',
            expr,
            re.IGNORECASE,
        )
        if not match:
            normalized = self._normalize_identifier_token(expr)
            return normalized, normalized

        table_name = self._normalize_identifier_token(match.group(1))
        alias_token = match.group(2)
        alias = self._normalize_identifier_token(alias_token) if alias_token else table_name
        return table_name, alias

    def _flatten_join_from_clause(self, from_clause: str) -> tuple[str, list[str]]:
        """JOIN ... ON を comma + WHERE 条件へ平坦化"""
        clause = from_clause.strip()
        join_match = re.search(r'\bJOIN\b', clause, re.IGNORECASE)
        if not join_match:
            return clause, []

        first_table_expr = clause[:join_match.start()].strip()
        table_exprs = [first_table_expr] if first_table_expr else []
        join_conditions: list[str] = []

        for match in re.finditer(
            r'\bJOIN\b\s+(.+?)\s+\bON\b\s+(.+?)(?=\s+\bJOIN\b\s+|$)',
            clause,
            re.IGNORECASE | re.DOTALL,
        ):
            table_expr = match.group(1).strip()
            condition = match.group(2).strip()
            if table_expr:
                table_exprs.append(table_expr)
            if condition:
                join_conditions.append(condition)

        normalized_table_exprs = []
        for expr in table_exprs:
            table_name, alias = self._parse_table_expr(expr)
            normalized_table_exprs.append(f'{table_name} AS {alias}')

        return ', '.join(normalized_table_exprs), join_conditions
    
    def _apply_mv_to_query(self, parts: dict, mv: dict) -> dict:
        """MVを適用してクエリの構成要素を書き換え（グラフベースの最小化）
        
        Args:
            parts: クエリの構成要素
            mv: 適用するMV (MaterializedViewオブジェクトまたは辞書)
            
        Returns:
            書き換えられた構成要素
        """
        # MaterializedViewオブジェクトまたは辞書から属性を取得
        if hasattr(mv, 'view_id'):
            view_id = mv.view_id
            create_sql = mv.create_sql
        elif isinstance(mv, dict):
            view_id = mv.get('view_id', '')
            create_sql = mv.get('create_sql', '')
        else:
            logger.warning(f"Unknown MV type: {type(mv)}")
            return parts
        
        # view_idから "mv_" プレフィックスを削除（データベースの実際のMV名に合わせる）
        if view_id.startswith('mv_'):
            view_id = view_id[3:]  # "mv_" を削除
        
        logger.info(f"Applying MV: {view_id}")
        
        # MV定義を解析
        mv_parts = self._analyze_mv_definition(create_sql)
        
        if not mv_parts:
            logger.warning(f"Could not analyze MV definition for {view_id}")
            return parts
        
        # MVのテーブルとエイリアスを取得
        mv_tables = self._extract_tables_from_from_clause(mv_parts['from'])
        mv_table_mappings = self._extract_table_mappings_from_from_clause(mv_parts['from'])
        
        logger.debug(f"MV contains tables: {mv_tables}")
        
        # クエリ側のテーブル名→エイリアスマッピング
        query_table_mappings = self._extract_table_mappings_from_from_clause(parts['from'])
        
        # MVのSELECT句からエイリアス→カラム名のマッピングを作成
        alias_to_column_mapping = self._extract_mv_column_mapping(mv_parts.get('select', ''), mv_tables)
        
        # ===== STEP 1: WHERE句を結合条件とフィルタ条件に分類 =====
        minimizer = JoinMinimizer()
        join_conditions, filter_conditions = minimizer.classify_conditions(parts['where'])
        
        logger.debug(f"Original: {len(join_conditions)} joins, {len(filter_conditions)} filters")
        
        # ===== STEP 2: MVの内部結合条件を削除 =====
        external_joins = []
        for join_cond in join_conditions:
            involved_tables = self._extract_tables_from_condition(join_cond, query_table_mappings)
            
            # 両方のテーブルがMVに含まれている → MVの内部結合なので削除
            if len(involved_tables) == 2 and all(table in mv_tables for table in involved_tables):
                logger.debug(f"Removing MV internal join: {join_cond}")
                continue
            
            external_joins.append(join_cond)
        
        logger.debug(f"After removing MV internal joins: {len(external_joins)} joins")
        
        # ===== STEP 3: FROM句を書き換え（MVのテーブルをMVに置き換え） =====
        parts['from'] = self._replace_tables_with_mv(parts['from'], mv_tables, view_id)
        
        # ===== STEP 4: SELECT句とWHERE句のエイリアス参照を更新 =====
        logger.debug(f"Updating aliases with mapping: {alias_to_column_mapping}")
        
        for old_ref, new_column in alias_to_column_mapping.items():
            alias, column = old_ref.split('.', 1)
            replacement = f"{view_id}.{new_column}"

            patterns = [
                r'\b' + re.escape(old_ref) + r'\b',
                r'"' + re.escape(alias) + r'"\."' + re.escape(column) + r'"',
            ]

            for pattern in patterns:
                # SELECT句の更新
                parts['select'] = re.sub(pattern, replacement, parts['select'])

                # WHERE句の結合条件を更新
                updated_joins = []
                for join_cond in external_joins:
                    updated_joins.append(re.sub(pattern, replacement, join_cond))
                external_joins = updated_joins

                # フィルタ条件も更新
                updated_filters = []
                for filter_cond in filter_conditions:
                    updated_filters.append(re.sub(pattern, replacement, filter_cond))
                filter_conditions = updated_filters

                # GROUP BY句の更新
                if parts['group_by']:
                    parts['group_by'] = re.sub(pattern, replacement, parts['group_by'])
        
        # ===== STEP 5: MVに含まれるフィルタ条件を削除 =====
        if mv_parts['where']:
            mv_filter_conds = self._extract_conditions(mv_parts['where'])
            normalized_mv_conds = [
                self._normalize_condition_for_comparison(c, mv_table_mappings) 
                for c in mv_filter_conds
            ]
            
            remaining_filters = []
            for cond in filter_conditions:
                normalized = self._normalize_condition_for_comparison(cond, query_table_mappings)
                if normalized not in normalized_mv_conds:
                    remaining_filters.append(cond)
                else:
                    logger.debug(f"Removing filter covered by MV: {cond}")
            
            filter_conditions = remaining_filters
        
        # ===== STEP 6: 結合グラフで冗長な結合条件を削除 =====
        minimal_joins, _ = minimizer.minimize_joins(external_joins, filter_conditions)
        
        logger.info(f"Join minimization: {len(external_joins)} → {len(minimal_joins)}")
        
        # ===== STEP 7: WHERE句を再構築 =====
        all_conditions = minimal_joins + filter_conditions
        parts['where'] = ' AND '.join(all_conditions) if all_conditions else ''
        
        logger.debug(f"Final WHERE ({len(all_conditions)} conditions): {parts['where'][:200]}...")
        
        return parts
    
    def _extract_mv_column_mapping(self, select_clause: str, mv_tables: list[str]) -> dict[str, str]:
        """MVのSELECT句からエイリアス.カラム→MVカラム名のマッピングを抽出
        
        Args:
            select_clause: MVのSELECT句
            mv_tables: MVに含まれるテーブルのエイリアスリスト
            
        Returns:
            {元のエイリアス.カラム: MVのカラム名} の辞書
            例: {'it.id': 'it_id', 'mi_idx.movie_id': 'movie_id'}
        """
        mapping = {}
        
        # SELECT句の各カラムを解析
        # 改行を削除して処理
        select_clause = select_clause.replace('\n', ' ')
        select_clause = re.sub(r'\s+', ' ', select_clause)
        
        columns = select_clause.split(',')
        for col in columns:
            col = col.strip()
            
            # エイリアス.カラム名 [AS 別名] のパターンを検出
            match = re.match(
                r'("?[A-Za-z_][A-Za-z0-9_]*"?)\.("?[A-Za-z_][A-Za-z0-9_]*"?)(?:\s+AS\s+("?[A-Za-z_][A-Za-z0-9_]*"?))?',
                col,
                re.IGNORECASE,
            )
            if match:
                alias = self._normalize_identifier_token(match.group(1))
                column = self._normalize_identifier_token(match.group(2))
                as_name = self._normalize_identifier_token(match.group(3)) if match.group(3) else column
                
                # MVに含まれるテーブルのエイリアスのみ対象
                if alias in mv_tables:
                    # 元の alias.column が MVでは as_name になる
                    mapping[f"{alias}.{column}"] = as_name
        
        return mapping
    
    def _analyze_mv_definition(self, create_sql: str) -> dict:
        """MV定義からSELECT句、FROM句、WHERE句を抽出
        
        Args:
            create_sql: CREATE MATERIALIZED VIEW文
            
        Returns:
            {'select': str, 'from': str, 'where': str} の辞書、失敗時はNone
        """
        # CREATE MATERIALIZED VIEW ... AS SELECT ... の部分を抽出
        # 形式: CREATE MATERIALIZED VIEW view_name AS\nSELECT ...\nFROM ...\nWHERE ...;
        
        try:
            # AS以降のSELECT文を抽出
            as_match = re.search(r'AS\s+(SELECT.+)', create_sql, re.IGNORECASE | re.DOTALL)
            if not as_match:
                return None
            
            select_sql = as_match.group(1).strip()
            
            # セミコロンを削除
            if select_sql.endswith(';'):
                select_sql = select_sql[:-1]
            
            # SELECT句を抽出
            select_match = re.search(r'SELECT\s+(.+?)\s+FROM', select_sql, re.IGNORECASE | re.DOTALL)
            select_clause = select_match.group(1).strip() if select_match else ''
            
            # FROM句を抽出
            from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|$)', select_sql, re.IGNORECASE | re.DOTALL)
            from_clause = from_match.group(1).strip() if from_match else ''
            
            # WHERE句を抽出
            where_match = re.search(r'WHERE\s+(.+)$', select_sql, re.IGNORECASE | re.DOTALL)
            where_clause = where_match.group(1).strip() if where_match else ''
            
            return {
                'select': select_clause,
                'from': from_clause,
                'where': where_clause
            }
        except Exception as e:
            logger.error(f"Error analyzing MV definition: {e}")
            return None
    
    def _extract_tables_from_from_clause(self, from_clause: str) -> list[str]:
        """FROM句からテーブルエイリアスのリストを抽出
        
        Args:
            from_clause: FROM句の文字列
            
        Returns:
            エイリアスのリスト
        """
        aliases = []

        for table_match in re.finditer(
            r'(?:^|\bJOIN\b|,)\s*("?[A-Za-z_][A-Za-z0-9_]*"?(?:\s+(?:AS\s+)?"?[A-Za-z_][A-Za-z0-9_]*"?)?)',
            from_clause,
            re.IGNORECASE,
        ):
            expr = table_match.group(1).strip()
            _, alias = self._parse_table_expr(expr)
            aliases.append(alias)

        return aliases
    
    def _extract_table_mappings_from_from_clause(self, from_clause: str) -> dict[str, str]:
        """FROM句からテーブル名→エイリアスのマッピングを抽出
        
        Args:
            from_clause: FROM句の文字列
            
        Returns:
            {table_name: alias} の辞書
        """
        mappings = {}

        for table_match in re.finditer(
            r'(?:^|\bJOIN\b|,)\s*("?[A-Za-z_][A-Za-z0-9_]*"?(?:\s+(?:AS\s+)?"?[A-Za-z_][A-Za-z0-9_]*"?)?)',
            from_clause,
            re.IGNORECASE,
        ):
            expr = table_match.group(1).strip()
            table_name, alias = self._parse_table_expr(expr)
            mappings[table_name] = alias

        return mappings
    
    def _replace_tables_with_mv(self, from_clause: str, mv_tables: list[str], view_id: str) -> str:
        """FROM句内のテーブルをMVに置き換え
        
        Args:
            from_clause: 元のFROM句
            mv_tables: MVに含まれるテーブルエイリアスのリスト
            view_id: MVのビューID
            
        Returns:
            書き換えられたFROM句
        """
        tables = [t.strip() for t in from_clause.split(',') if t.strip()]
        new_tables = []
        mv_added = False
        
        for table_expr in tables:
            _, alias = self._parse_table_expr(table_expr)
            if alias in mv_tables:
                # 最初のMVテーブルをMVに置き換え
                if not mv_added:
                    new_tables.append(view_id)
                    mv_added = True
                # それ以外のMVテーブルはスキップ
                continue

            # MVに含まれないテーブルはそのまま保持
            new_tables.append(table_expr)
        
        return ', '.join(new_tables)
    
    def _remove_common_conditions(
        self, 
        original_where: str, 
        mv_where: str, 
        mv_table_mappings: dict[str, str],
        query_table_mappings: dict[str, str]
    ) -> str:
        """WHERE句から、MVに含まれる条件を削除
        
        Args:
            original_where: 元のクエリのWHERE句
            mv_where: MVのWHERE句
            mv_table_mappings: MVのテーブル名→エイリアスマッピング（例: {'company_name': 'cn'}）
            query_table_mappings: クエリのテーブル名→エイリアスマッピング
            
        Returns:
            書き換えられたWHERE句
        """
        # WHERE条件を個別の条件に分割
        original_conds = self._extract_conditions(original_where)
        mv_conds = self._extract_conditions(mv_where)
        
        logger.debug(f"Original conditions: {original_conds}")
        logger.debug(f"MV conditions: {mv_conds}")
        logger.debug(f"MV table mappings: {mv_table_mappings}")
        logger.debug(f"Query table mappings: {query_table_mappings}")
        
        # MVの条件を正規化（エイリアスを除去して比較できるようにする）
        normalized_mv_conds = []
        for mv_cond in mv_conds:
            normalized_mv_conds.append(self._normalize_condition_for_comparison(mv_cond, mv_table_mappings))
        
        # 共通する条件を削除
        unique_conds = []
        for cond in original_conds:
            # 正規化して比較
            normalized_cond = self._normalize_condition_for_comparison(cond, query_table_mappings)
            
            # MVの条件と比較
            is_common = False
            for i, norm_mv_cond in enumerate(normalized_mv_conds):
                if normalized_cond == norm_mv_cond:
                    is_common = True
                    logger.debug(f"Removing common condition: '{cond}' (matches MV condition: '{mv_conds[i]}')")
                    break
            
            if not is_common:
                unique_conds.append(cond)
                logger.debug(f"Keeping unique condition: '{cond}'")
        
        # 条件を再結合
        return ' AND '.join(unique_conds) if unique_conds else ''
    
    def _normalize_condition_for_comparison(self, condition: str, table_mappings: dict[str, str]) -> str:
        """条件を正規化して比較可能な形式にする
        
        Args:
            condition: 元の条件
            table_mappings: テーブル名→エイリアスマッピング
            
        Returns:
            正規化された条件
        """
        # PostgreSQLのキャスト表記を削除 (::text, ::integer など)
        normalized = re.sub(r'::\w+(\[\])?', '', condition)
        
        # テーブルエイリアスを削除（table_mappingsに含まれるエイリアスと、MVプレフィックス付きも）
        for table_name, alias in table_mappings.items():
            # alias. を削除
            pattern = r'\b' + re.escape(alias) + r'\.'
            normalized = re.sub(pattern, '', normalized)
        
        # MVプレフィックス（mv_leaf_XX., mv_non_leaf_XX.）も削除
        normalized = re.sub(r'\bmv_\w+\.', '', normalized)

        # 識別子のダブルクォートを削除
        normalized = normalized.replace('"', '')
        
        # カラム名の周りのカッコを削除 例: (info) → info
        normalized = re.sub(r'\((\w+)\)', r'\1', normalized)
        
        # PostgreSQLの演算子を標準SQL演算子に変換
        # ~~ → LIKE
        normalized = re.sub(r'\s+~~\s+', ' like ', normalized)
        # !~~ → NOT LIKE
        normalized = re.sub(r'\s+!~~\s+', ' not like ', normalized)
        
        # PostgreSQL配列のANY構文をIN構文に変換
        # = ANY ('{val1,val2,val3}') → IN (val1,val2,val3)
        any_pattern = r'=\s*any\s*\(\s*\'\{([^}]+)\}\'\s*\)'
        def convert_any_to_in(match):
            values = match.group(1)
            # カンマで分割して個別の値に
            return f'in ({values})'
        normalized = re.sub(any_pattern, convert_any_to_in, normalized, flags=re.IGNORECASE)
        
        # 引用符を削除（値の比較のため）
        normalized = re.sub(r"'", '', normalized)
        
        # 外側の余分なカッコを削除
        while normalized.startswith('(') and normalized.endswith(')'):
            normalized = normalized[1:-1].strip()
        
        # 空白を正規化（等号周辺も統一）
        normalized = re.sub(r'\s*=\s*', '=', normalized)  # = 周辺の空白を削除
        normalized = re.sub(r'\s*>\s*', '>', normalized)  # > 周辺の空白を削除
        normalized = re.sub(r'\s*<\s*', '<', normalized)  # < 周辺の空白を削除
        normalized = re.sub(r'\s*,\s*', ',', normalized)  # , 周辺の空白を削除
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 小文字に統一（大文字小文字を無視）
        normalized = normalized.lower()
        
        return normalized
    
    def _is_join_condition(self, condition: str) -> bool:
        """条件が結合条件かどうかを判定
        
        結合条件は alias1.col1 = alias2.col2 の形式
        
        Args:
            condition: 条件文字列
            
        Returns:
            結合条件ならTrue
        """
        # alias1.col1 = alias2.col2 のパターンをチェック
        pattern = r'^\s*(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\s*$'
        return re.match(pattern, condition.strip()) is not None
    
    def _extract_tables_from_condition(self, condition: str, table_mappings: dict[str, str]) -> list[str]:
        """条件に含まれるテーブルエイリアスを抽出
        
        Args:
            condition: 条件文字列（例: "t.id = ci.movie_id"）
            table_mappings: テーブル名→エイリアスのマッピング
            
        Returns:
            テーブルエイリアスのリスト
        """
        tables = []
        # alias.column のパターンを検索
        pattern = r'"?([A-Za-z_][A-Za-z0-9_]*)"?\."?([A-Za-z_][A-Za-z0-9_]*)"?'
        matches = re.findall(pattern, condition)
        
        for alias, column in matches:
            # エイリアスがtable_mappingsの値に含まれるか、またはMVテーブル名か
            if alias in table_mappings.values() or alias.startswith(('leaf_', 'non_leaf_')):
                tables.append(alias)
        
        return list(set(tables))  # 重複を削除
    
    def _remove_redundant_join_conditions(self, where_clause: str, mv_id: str) -> str:
        """冗長な結合条件を削除
        
        例: non_leaf_475.movie_id = mc.movie_id と non_leaf_475.t_id = mc.movie_id
        は、MVの定義により同等なので、1つだけ残す
        
        Args:
            where_clause: WHERE句
            mv_id: MVのID
            
        Returns:
            クリーンアップされたWHERE句
        """
        conditions = self._extract_conditions(where_clause)
        
        # 同じMVと外部テーブルの結合条件をグループ化
        join_groups = {}  # {(mv_id, external_table): [conditions]}
        other_conditions = []
        
        for cond in conditions:
            # mv_id.col = table.col の形式かチェック
            pattern = rf'{re.escape(mv_id)}\.(\w+)\s*=\s*(\w+)\.(\w+)'
            match = re.match(pattern, cond.strip())
            if match:
                mv_col, ext_table, ext_col = match.groups()
                key = (mv_id, ext_table, ext_col)
                if key not in join_groups:
                    join_groups[key] = []
                join_groups[key].append(cond)
            else:
                # 逆パターン table.col = mv_id.col もチェック
                pattern_rev = rf'(\w+)\.(\w+)\s*=\s*{re.escape(mv_id)}\.(\w+)'
                match_rev = re.match(pattern_rev, cond.strip())
                if match_rev:
                    ext_table, ext_col, mv_col = match_rev.groups()
                    key = (mv_id, ext_table, ext_col)
                    if key not in join_groups:
                        join_groups[key] = []
                    join_groups[key].append(cond)
                else:
                    other_conditions.append(cond)
        
        # 各グループから1つだけ選択
        selected_joins = []
        for key, conds in join_groups.items():
            if len(conds) > 1:
                logger.debug(f"Removing redundant join conditions for {key}: {conds}")
                logger.debug(f"  Keeping: {conds[0]}")
            selected_joins.append(conds[0])
        
        # 再構築
        all_conditions = selected_joins + other_conditions
        return ' AND '.join(all_conditions) if all_conditions else ''
    
    def _extract_conditions(self, where_clause: str) -> list[str]:
        """WHERE句から個別の条件を抽出
        
        BETWEEN...AND構文を適切に処理するため、BETWEENを含む条件を
        一時的にプレースホルダーに置き換えてからANDで分割します。
        
        Args:
            where_clause: WHERE句の文字列
            
        Returns:
            条件のリスト
        """
        if not where_clause:
            return []
        
        # BETWEEN...AND句を保護するため、一時的にプレースホルダーに置き換え
        between_pattern = re.compile(
            r'(\w+\.?\w*\s+BETWEEN\s+[\w\d\'\"\-]+\s+AND\s+[\w\d\'\"\-]+)',
            re.IGNORECASE
        )
        
        between_clauses = {}
        placeholder_counter = 0
        
        def replace_between(match):
            nonlocal placeholder_counter
            placeholder = f'__BETWEEN_PLACEHOLDER_{placeholder_counter}__'
            between_clauses[placeholder] = match.group(1)
            placeholder_counter += 1
            return placeholder
        
        # BETWEENをプレースホルダーに置き換え
        protected_clause = between_pattern.sub(replace_between, where_clause)
        
        # ANDで分割
        conditions = [c.strip() for c in protected_clause.split(' AND ') if c.strip()]
        
        # プレースホルダーを元のBETWEEN句に戻す
        restored_conditions = []
        for cond in conditions:
            restored = cond
            for placeholder, original in between_clauses.items():
                restored = restored.replace(placeholder, original)
            if restored and restored.upper() not in ('WHERE', 'AND', 'OR'):
                restored_conditions.append(restored)
        
        logger.debug(f"Extracted {len(restored_conditions)} conditions from WHERE clause")
        if logger.isEnabledFor(logging.DEBUG):
            for i, cond in enumerate(restored_conditions):
                logger.debug(f"  Condition {i+1}: {cond}")
        
        return restored_conditions
    
    def _update_alias_references(self, clause: str, old_alias: str, view_id: str) -> str:
        """句内のエイリアス参照を更新
        
        Args:
            clause: SQL句（SELECT, WHERE, GROUP BYなど）
            old_alias: 元のエイリアス
            view_id: 新しいビューID
            
        Returns:
            更新された句
        """
        # old_alias.column を view_id.old_alias_column に置き換え
        # パターン: 単語境界の後に old_alias. が続く場合
        pattern = r'\b' + re.escape(old_alias) + r'\.'
        replacement = view_id + '.' + old_alias + '_'
        
        return re.sub(pattern, replacement, clause)
    
    def _reconstruct_sql(self, parts: dict) -> str:
        """SQL構成要素から完全なSQL文を再構築
        
        Args:
            parts: {'select': str, 'from': str, 'where': str, 'group_by': str}
            
        Returns:
            完全なSQL文
        """
        sql = f"SELECT {parts['select']}\nFROM {parts['from']}"
        
        if parts['where']:
            sql += f"\nWHERE {parts['where']}"
        
        if parts['group_by']:
            sql += f"\nGROUP BY {parts['group_by']}"
        
        sql += ";"
        
        return sql

    def rewrite_workload(
        self,
        mv_selections: dict[int, list[str]],
        output_dir: str,
        original_queries: dict[int, str] = None,
    ) -> list[str]:
        """ワークロード全体を書き換え

        Args:
            mv_selections: {query_id: [MV node IDs]}
            output_dir: 出力ディレクトリ
            original_queries: {query_id: original SQL} (optional)

        Returns:
            書き換えられたクエリファイルのパスリスト
        """
        os.makedirs(output_dir, exist_ok=True)
        rewritten_files = []

        for query_id, mv_nodes in mv_selections.items():
            if not mv_nodes or mv_nodes[0] == "NONE":
                continue

            # 元のクエリ取得
            if original_queries and query_id in original_queries:
                original_sql = original_queries[query_id]
            elif self.qm and hasattr(self.qm, "query_map") and query_id in self.qm.query_map:
                original_sql = self.qm.query_map[query_id].get("original_sql", "")
            else:
                print(f"Warning: No original SQL for query {query_id}")
                continue

            # クエリ書き換え
            rewritten_sql = self._rewrite_query(query_id, mv_nodes, original_sql)

            # ファイル保存
            filename = f"query_{query_id}.sql"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(rewritten_sql)

            rewritten_files.append(filepath)
            print(f"Rewritten query {query_id}: {filepath}")

        return rewritten_files

    def _rewrite_query(self, query_id: int, mv_nodes: list[str], original_sql: str) -> str:
        """クエリを書き換え

        Args:
            query_id: クエリID
            mv_nodes: 使用するMVノードIDリスト
            original_sql: 元のSQL

        Returns:
            書き換え後のSQL
        """
        if not mv_nodes or not original_sql:
            return original_sql

        # FROM句を解析
        from_clause = self.sql_parser.extract_from_clause(original_sql)
        where_clause = self.sql_parser.extract_where_clause(original_sql)

        # テーブルリスト取得
        tables = self.sql_parser.extract_tables(from_clause)

        # リーフノードをMVで置換
        new_from_parts = []
        replaced_tables = set()

        for table, alias in tables:
            replaced = False

            # このテーブルに対応するMVがあるか確認
            if self.qm and hasattr(self.qm, "leaf_nodes_map_r"):
                for mv_node in mv_nodes:
                    if mv_node.startswith("leaf_") and mv_node in self.qm.leaf_nodes_map_r:
                        # leaf_nodes_map_r: {node_id: (operator, table_name, alias, conditions)}
                        operator, table_name, node_alias, conditions = self.qm.leaf_nodes_map_r[mv_node]
                        if table_name == table:
                            new_from_parts.append(f"{mv_node} AS {alias}")
                            replaced_tables.add(table)
                            replaced = True
                            print(f"  Replaced {table} with {mv_node}")
                            break

            if not replaced:
                new_from_parts.append(f"{table} {alias}")

        # 新しいFROM句
        new_from = ", ".join(new_from_parts)

        # SELECT句を元のまま抽出
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", original_sql, re.IGNORECASE | re.DOTALL)
        select_clause = select_match.group(1) if select_match else "*"

        # SQLを再構築
        rewritten_sql = self.sql_parser.reconstruct_query(
            select_clause=select_clause, from_clause=new_from, where_clause=where_clause
        )

        return rewritten_sql

    def generate_mv_creation_scripts(self, mv_nodes: list[str], output_dir: Path) -> list[str]:
        """MV作成スクリプトを生成

        Args:
            mv_nodes: MVノードIDリスト
            output_dir: 出力ディレクトリ

        Returns:
            生成されたファイルパスのリスト
        """
        if not self.qm:
            print("Warning: No QueryManager available")
            return []

        return self.mv_generator.generate_mv_scripts(mv_nodes, self.qm, str(output_dir))


def load_mv_selections(mv_list_file: str) -> dict[int, list[str]]:
    """MV選択結果をCSVから読み込み

    Args:
        mv_list_file: mv_y_list.csv のパス

    Returns:
        {query_num: [MV node IDs]}
    """
    import csv

    mv_selections = {}

    if not os.path.exists(mv_list_file):
        return mv_selections

    with open(mv_list_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if row:
                mv_selections[i] = [node.strip() for node in row if node.strip()]
            else:
                mv_selections[i] = ["NONE"]

    return mv_selections
