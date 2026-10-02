"""グローバルエイリアスマッピングを使用したクエリ書き換えロジック

このモジュールは複数のMVが選択された場合に、テーブルエイリアス→MVの
グローバルマッピングを事前構築してから一括書き換えを行います。
ただし、JOIN最小化やフィルタ削除などの元の実装の機能も維持します。
"""

import re
from pathlib import Path
from typing import Any
import logging

from src.rewrite.join_graph import JoinMinimizer
from src.utils.legacy import natural_sort_key

logger = logging.getLogger(__name__)


class GlobalAliasQueryRewriter:
    """グローバルエイリアスマッピングを使用したクエリ書き換え"""

    def __init__(self, settings: Any, qm: Any):
        """初期化
        
        Args:
            settings: 設定オブジェクト
            qm: QueryManager
        """
        self.settings = settings
        self.qm = qm
    
    def rewrite_queries(self, selected_views: list) -> dict[str, str]:
        """選択されたMVを使ってクエリを書き換える"""
        logger.info(f"Starting query rewriting with {len(selected_views)} selected views")
        
        # グローバルエイリアス→MVマッピングを構築
        global_alias_mapping = self._build_global_alias_mapping(selected_views)
        logger.info(f"Built global alias mapping: {len(global_alias_mapping)} entries")
        
        # クエリごとに使用するMVをマッピング
        query_to_mvs = self._build_query_mv_mapping(selected_views)
        
        # 元のクエリファイルのパスを取得
        query_dir = Path(self.settings.benchmark.sql_dir) / "job"
        
        rewritten = {}
        
        # 各クエリを処理
        for query_file in sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x))):
            query_id = query_file.stem
            
            # このクエリに使用するMVがない場合は元のクエリをそのまま使用
            if query_id not in query_to_mvs or not query_to_mvs[query_id]:
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
                continue
            
            # クエリを書き換え
            try:
                rewritten_sql = self._rewrite_single_query(
                    query_file, 
                    query_to_mvs[query_id],
                    global_alias_mapping
                )
                rewritten[query_id] = rewritten_sql
                logger.debug(f"Successfully rewrote query {query_id}")
            except Exception as e:
                logger.error(f"Error rewriting query {query_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
        
        logger.info(f"Completed query rewriting for {len(rewritten)} queries")
        return rewritten
    
    def _build_query_mv_mapping(self, selected_views: list) -> dict[str, list]:
        """selected_viewsからクエリごとに使用するMVのマッピングを作成"""
        # query_numからquery_idへのマッピングを構築
        query_dir = Path(self.settings.benchmark.sql_dir) / "job"
        query_num_to_id = {}
        for i, query_file in enumerate(sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x)))):
            query_num_to_id[i] = query_file.stem
        
        query_to_mvs = {}
        
        for mv in selected_views:
            if hasattr(mv, 'usage_positions'):
                usage_positions = mv.usage_positions
            elif isinstance(mv, dict):
                usage_positions = mv.get('usage_positions', [])
            else:
                continue
            
            for pos in usage_positions:
                query_num = pos[0]
                query_id = query_num_to_id.get(query_num)
                if query_id:
                    if query_id not in query_to_mvs:
                        query_to_mvs[query_id] = []
                    query_to_mvs[query_id].append(mv)
        
        return query_to_mvs
    
    def _build_global_alias_mapping(self, selected_views: list) -> dict[str, str]:
        """全MVからテーブル名→MV名のマッピングを構築"""
        mapping = {}
        
        for mv in selected_views:
            # MaterializedViewオブジェクトからnode_idを取得
            if hasattr(mv, 'node_id'):
                node_id = mv.node_id
            elif isinstance(mv, dict):
                node_id = mv.get('node_id', '')
            else:
                continue
            
            # view_idから実際のMV名を取得（mv_ プレフィックスを除去）
            if hasattr(mv, 'view_id'):
                view_id = mv.view_id
                if view_id.startswith('mv_'):
                    view_id = view_id[3:]
            else:
                view_id = node_id
            
            if node_id.startswith('leaf_'):
                # leaf ノード: QueryManagerから取得
                if hasattr(self.qm, 'relation_tables') and node_id in self.qm.relation_tables:
                    table_name = self.qm.relation_tables[node_id]
                    mapping[table_name] = view_id
            else:
                # non_leaf ノード: create_sql から含まれるテーブルを抽出
                if hasattr(mv, 'create_sql') and mv.create_sql:
                    tables = self._extract_tables_from_create_sql(mv.create_sql)
                    for table in tables:
                        if table not in mapping: # 既に登録済みの場合は上書きしない（or より上位のMVを優先するか検討）
                            mapping[table] = view_id
        
        return mapping
    
    def _extract_tables_from_create_sql(self, create_sql: str) -> list[str]:
        """CREATE文からテーブル名を抽出"""
        tables = []
        # FROM句のパターン: table_name AS alias
        from_match = re.search(r'FROM\s+(.+?)(?:WHERE|$)', create_sql, re.IGNORECASE | re.DOTALL)
        if from_match:
            from_clause = from_match.group(1)
            # table_name AS alias または table_name alias
            table_pattern = re.compile(r'(\w+)\s+(?:AS\s+)?(\w+)', re.IGNORECASE)
            for match in table_pattern.finditer(from_clause):
                table_name = match.group(1).lower()
                if table_name not in ('as', 'join', 'inner', 'left', 'right', 'outer', 'cross', 'lateral'):
                    tables.append(table_name)
        return tables
    
    def _rewrite_single_query(self, query_file: Path, mvs: list, global_alias_mapping: dict) -> str:
        """単一のクエリをMVを使って書き換え"""
        with open(query_file, 'r') as f:
            original_sql = f.read()
        
        # SQL正規化（文字列リテラル保護付き）
        sql, string_literals = self._normalize_sql_with_literals(original_sql)
        
        # SQLを構成要素に分解
        parts = self._parse_sql_parts(sql)
        
        # ===== STEP 1: エイリアス置換（グローバルマッピング使用） =====
        parts, active_mvs = self._apply_global_alias_mapping(parts, mvs, global_alias_mapping)
        
        # ===== STEP 2: WHERE句の分析と最適化 =====
        # 結合条件とフィルタ条件に分類
        minimizer = JoinMinimizer()
        join_conditions, filter_conditions = minimizer.classify_conditions(parts['where'])
        
        # ===== STEP 3: MVの内部結合条件を削除 =====
        # ここでは簡易的に、"両辺が同じMVを参照している結合条件" を削除
        external_joins = []
        for join_cond in join_conditions:
            # 形式: mv1.col1 = mv2.col2
            match = re.search(r'([\w\.]+)\s*=\s*([\w\.]+)', join_cond)
            if match:
                left_op = match.group(1)
                right_op = match.group(2)
                
                left_mv = left_op.split('.')[0] if '.' in left_op else None
                right_mv = right_op.split('.')[0] if '.' in right_op else None
                
                # 両方が同じMVで、かつそのMVが有効なMVリストに含まれる場合
                if left_mv and right_mv and left_mv == right_mv and left_mv in active_mvs:
                    logger.debug(f"Removing internal join: {join_cond}")
                    continue
            
            external_joins.append(join_cond)
        
        # ===== STEP 4: 冗長なフィルタの削除 =====
        # MVに含まれるフィルタと重複するクエリのフィルタを削除
        remaining_filters = self._remove_redundant_filters(filter_conditions, mvs, active_mvs)
        
        # ===== STEP 5: 結合グラフで冗長な結合条件を削除 =====
        minimal_joins, _ = minimizer.minimize_joins(external_joins, remaining_filters)
        
        # ===== STEP 6: WHERE句を再構築 =====
        all_conditions = minimal_joins + remaining_filters
        parts['where'] = ' AND '.join(all_conditions) if all_conditions else ''
        
        # 書き換えたSQLを再構築
        rewritten_sql = self._reconstruct_sql(parts)
        
        # 文字列リテラルを復元
        for i, literal in enumerate(string_literals):
            placeholder = f"__STRING_LITERAL_{i}__"
            rewritten_sql = rewritten_sql.replace(placeholder, literal)
            
        return rewritten_sql
    
    def _normalize_sql_with_literals(self, sql: str) -> tuple[str, list]:
        """SQLを正規化し、文字列リテラルを保護"""
        string_literals = []
        
        def replace_literal(match):
            literal = match.group(0)
            placeholder = f"__STRING_LITERAL_{len(string_literals)}__"
            string_literals.append(literal)
            return placeholder
        
        # リテラル保護
        sql = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", replace_literal, sql)
        
        # 正規化
        sql = sql.replace('\n', ' ')
        sql = re.sub(r'\s+', ' ', sql)
        
        # キーワード統一
        for kw in ['AS', 'AND', 'OR', 'LIKE', 'NOT', 'IN']:
            sql = re.sub(rf'\b{kw}\b', kw, sql, flags=re.IGNORECASE)
            
        # 演算子の空白調整
        sql = re.sub(r'(?<! )=(?! )', ' = ', sql)
        sql = sql.replace('! =', '!=')
        
        return sql.strip(), string_literals
    
    def _parse_sql_parts(self, sql: str) -> dict:
        """SQLを構成要素に分解"""
        parts = {
            'select': '',
            'from': '',
            'where': '',
            'group_by': ''
        }
        
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM\s+', sql, re.IGNORECASE | re.DOTALL)
        if not select_match:
             select_match = re.search(r'SELECT\s+(.+?)\sFROM\s', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            parts['select'] = select_match.group(1).strip()
        
        from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|\s+GROUP\s+BY|;|$)', sql, re.IGNORECASE)
        if from_match:
            parts['from'] = from_match.group(1).strip()
        
        where_match = re.search(r'WHERE\s+(.+?)(?:\s+GROUP\s+BY|;|$)', sql, re.IGNORECASE)
        if where_match:
            parts['where'] = where_match.group(1).strip()
        
        group_match = re.search(r'GROUP\s+BY\s+(.+?)(?:;|$)', sql, re.IGNORECASE)
        if group_match:
            parts['group_by'] = group_match.group(1).strip()
        
        return parts
    
    def _apply_global_alias_mapping(self, parts: dict, mvs: list, global_alias_mapping: dict) -> tuple[dict, set]:
        """グローバルマッピングを使ってクエリを一括書き換え
        Returns: (updated_parts, active_mv_ids)
        """
        # このクエリで使用可能なMV ID
        available_mv_ids = set()
        for mv in mvs:
            if hasattr(mv, 'view_id'):
                view_id = mv.view_id
                if view_id.startswith('mv_'):
                    view_id = view_id[3:]
                available_mv_ids.add(view_id)
        
        # FROM句のエイリアスを抽出
        query_alias_to_table = {}
        table_pattern = re.compile(r'(\w+)\s+AS\s+(\w+)', re.IGNORECASE)
        for match in table_pattern.finditer(parts['from']):
            table_name = match.group(1).lower()
            alias = match.group(2).lower()
            query_alias_to_table[alias] = table_name
            
        # エイリアス→MVマッピング（実際にこのクエリで使えるものだけ）
        alias_to_mv = {}
        active_mvs = set()
        for alias, table_name in query_alias_to_table.items():
            if table_name in global_alias_mapping:
                mv_name = global_alias_mapping[table_name]
                if mv_name in available_mv_ids:
                    alias_to_mv[alias] = mv_name
                    active_mvs.add(mv_name)
        
        # FROM句書き換え
        new_from = parts['from']
        replaced_mvs = set()
        
        for alias, mv_name in alias_to_mv.items():
            pattern = r'(\w+)\s+AS\s+' + re.escape(alias) + r'\b'
            if mv_name not in replaced_mvs:
                new_from = re.sub(pattern, mv_name, new_from, flags=re.IGNORECASE)
                replaced_mvs.add(mv_name)
            else:
                new_from = re.sub(pattern + r'\s*,?\s*', '', new_from, flags=re.IGNORECASE)
        
        new_from = re.sub(r',\s*,', ',', new_from)
        new_from = re.sub(r',\s*$', '', new_from)
        new_from = re.sub(r'^\s*,', '', new_from)
        parts['from'] = new_from.strip()
        
        # 参照更新
        for alias, mv_name in alias_to_mv.items():
            pattern = r'\b' + re.escape(alias) + r'\.'
            replacement = f'{mv_name}.'
            parts['select'] = re.sub(pattern, replacement, parts['select'], flags=re.IGNORECASE)
            parts['where'] = re.sub(pattern, replacement, parts['where'], flags=re.IGNORECASE)
            if parts['group_by']:
                parts['group_by'] = re.sub(pattern, replacement, parts['group_by'], flags=re.IGNORECASE)
                
        return parts, active_mvs

    def _remove_redundant_filters(self, filter_conditions: list, mvs: list, active_mvs: set) -> list:
        """MVに含まれるフィルタと重複する条件を削除
        
        MVのWHERE句（ソーステーブルのカラムを使用）を、MVの出力カラム名に変換してから比較を行う。
        """
        remaining_filters = []
        
        # 適用されているMVごとのフィルタ条件（正規化済み）のセット
        mv_filters = set()
        
        for mv in mvs:
            view_id = mv.view_id
            if view_id.startswith('mv_'):
                view_id = view_id[3:]
            
            if view_id in active_mvs and hasattr(mv, 'create_sql'):
                # 1. SELECT句からソースカラム→MVカラムのマッピングを作成
                # 例: t.production_year -> production_year, it.info -> it_info
                col_mapping = self._build_source_to_mv_col_mapping(mv.create_sql)
                
                # 2. WHERE句を抽出
                try:
                    where_match = re.search(r'WHERE\s+(.+?)(?:;|$)', mv.create_sql, re.IGNORECASE | re.DOTALL)
                    if where_match:
                        mv_where = where_match.group(1).strip()
                        conds = self._extract_conditions(mv_where)
                        
                        for c in conds:
                            # 3. 条件内のソースカラムをMVカラムに置換
                            translated_cond = self._translate_condition(c, col_mapping)
                            
                            # 4. 正規化して登録
                            normalized = self._normalize_condition_string(translated_cond)
                            # 値のキャスト(::textなど)を除去するので、両辺のキャストを除去する正規化が必要
                            mv_filters.add(normalized)
                            logger.debug(f"MV Filter ({view_id}): {c} => {translated_cond} => {normalized}")
                except Exception as e:
                    logger.warning(f"Error processing filters for {view_id}: {e}")
        
        for cond in filter_conditions:
            # クエリ条件の正規化
            # クエリは既に書き換え済みで、mv_name.col という形式になっている
            
            # テーブル/MVプレフィックスを除去
            simple_cond = re.sub(r'\b\w+\.', '', cond)
            normalized = self._normalize_condition_string(simple_cond)
            
            logger.debug(f"Query Filter: {cond} => {simple_cond} => {normalized}")
            
            if normalized in mv_filters:
                logger.debug(f"Removing redundant filter: {cond}")
            else:
                remaining_filters.append(cond)
                
        return remaining_filters

    def _build_source_to_mv_col_mapping(self, create_sql: str) -> dict[str, str]:
        """MVのCREATE SQLから ソースカラム(alias.col) -> MVカラム(mv_col) のマッピングを作成"""
        mapping = {}
        # SELECT句の抽出 (AS SELECT ... FROM)
        match = re.search(r'AS\s+SELECT\s+(.+?)\s+FROM', create_sql, re.IGNORECASE | re.DOTALL)
        if not match:
            # Maybe CREATE MATERIALIZED VIEW x AS SELECT ...
            match = re.search(r'SELECT\s+(.+?)\s+FROM', create_sql, re.IGNORECASE | re.DOTALL)
            
        if not match:
            return mapping
            
        select_clause = match.group(1)
        # カンマ分割（括弧内のカンマは無視したいが、単純化のためsplitで試行）
        # 関数などがある場合は複雑だが、JOBクエリなら単純なカラムリストが多い
        cols = [c.strip() for c in select_clause.split(',')]
        
        for col in cols:
            # パターン: src_table.col AS mv_col
            # または: src_table.col (この場合は mv_col = col)
            m = re.search(r'(\w+\.\w+)(?:\s+AS\s+(\w+))?', col, re.IGNORECASE)
            if m:
                src_col = m.group(1)
                mv_col = m.group(2) if m.group(2) else src_col.split('.')[1]
                mapping[src_col.lower()] = mv_col.lower()
        return mapping

    def _translate_condition(self, condition: str, mapping: dict) -> str:
        """条件文字列内のソースカラムをMVカラムに置換"""
        # 単純な文字列置換だと部分一致（例: id と kind_id）で誤爆するので、単語境界を考慮
        
        # 長いカラム名から順に適用することで、部分一致のリスクを軽減
        sorted_src_cols = sorted(mapping.keys(), key=len, reverse=True)
        
        translated = condition.lower()
        for src_col in sorted_src_cols:
            mv_col = mapping[src_col]
            # ソースカラム(t.production_year)をMVカラム(production_year)に置換
            
            # 正規表現で単語境界チェックして置換
            # t.production_year -> production_year
            pattern = r'\b' + re.escape(src_col) + r'\b'
            translated = re.sub(pattern, mv_col, translated)
            
        return translated

    def _normalize_condition_string(self, cond: str) -> str:
        """条件文字列を比較用に強力に正規化"""
        cond = cond.strip()
        
        # 1. 外部の括弧を再帰的に削除 ((a) = (b)) -> a = b
        while True:
            if cond.startswith('(') and cond.endswith(')'):
                # バランスチェック
                depth = 0
                is_wrapper = True
                for i, c in enumerate(cond[:-1]):
                    if c == '(': depth += 1
                    elif c == ')': depth -= 1
                    if depth == 0: 
                        is_wrapper = False
                        break
                if is_wrapper:
                    cond = cond[1:-1]
                    continue
            break
            
        # 2. キャスト削除 (::text, ::integer, etc)
        cond = re.sub(r'::\w+', '', cond)
        
        # 3. カラム単体の括弧削除 (col) = val -> col = val
        # 左辺
        cond = re.sub(r'\(\s*(\w+)\s*\)\s*(=|>|<|!|LIKE)', r'\1 \2', cond, flags=re.IGNORECASE)
        # 右辺は文字列リテラルなどが含まれるので慎重に
        
        # 4. 演算子正規化
        cond = cond.replace('!~~', 'NOT LIKE')
        cond = cond.replace('~~', 'LIKE')
        cond = re.sub(r'\s*(!=|<>)\s*', ' != ', cond)
        cond = re.sub(r'\s*=\s*', ' = ', cond)
        cond = re.sub(r'\s*(>=)\s*', ' >= ', cond)
        cond = re.sub(r'\s*(<=)\s*', ' <= ', cond)
        cond = re.sub(r'\s*(>)\s*', ' > ', cond)
        cond = re.sub(r'\s*(<)\s*', ' < ', cond)
        cond = re.sub(r'\s+LIKE\s+', ' LIKE ', cond, flags=re.IGNORECASE)
        cond = re.sub(r'\s+NOT LIKE\s+', ' NOT LIKE ', cond, flags=re.IGNORECASE)
        
        # 5. 空白正規化
        cond = re.sub(r'\s+', ' ', cond).strip().lower()
        
        return cond

    def _extract_conditions(self, where_clause: str) -> list[str]:
        """WHERE句をANDで分割（括弧を考慮）"""
        conditions = []
        paren_depth = 0
        
        # AND で分割するが、括弧内の AND は無視する
        tokens = re.split(r'(\s+AND\s+)', where_clause, flags=re.IGNORECASE)
        
        buffer = ""
        for token in tokens:
            if re.match(r'\s+AND\s+', token, re.IGNORECASE):
                if paren_depth == 0:
                    if buffer.strip():
                        conditions.append(buffer.strip())
                    buffer = ""
                else:
                    buffer += token
            else:
                buffer += token
                paren_depth += token.count('(') - token.count(')')
        
        if buffer.strip():
            conditions.append(buffer.strip())
            
        return conditions

    def _reconstruct_sql(self, parts: dict) -> str:
        """構成要素からSQLを再構築"""
        sql = f"SELECT {parts['select']}\nFROM {parts['from']}"
        if parts['where']:
            sql += f"\nWHERE {parts['where']}"
        if parts['group_by']:
            sql += f"\nGROUP BY {parts['group_by']}"
        return sql + ";"
