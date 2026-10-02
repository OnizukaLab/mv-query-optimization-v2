#!/usr/bin/env python3
"""
simple_migration_plansからSQLクエリを抽出し、NeuroCard用のCSV形式に変換する

入力: simple_migration_plans.json
出力: queries_for_neurocard.csv
"""

import json
import re
import os
from pathlib import Path
from typing import List, Tuple, Dict

# NeuroCard job-mスキーマで許可されているテーブル (job-lightより広範囲)
JOB_M_TABLES = {
    'title', 'aka_title', 'cast_info', 'complete_cast', 'movie_companies',
    'movie_info', 'movie_info_idx', 'movie_keyword', 'movie_link',
    'kind_type', 'comp_cast_type', 'company_name', 'company_type',
    'info_type', 'keyword', 'link_type'
}

# job-lightの6テーブル（デフォルト）
JOB_LIGHT_TABLES = {
    'cast_info',
    'movie_companies', 
    'movie_info',
    'movie_keyword',
    'title',
    'movie_info_idx'
}

# 使用するスキーマを選択（job-mを使用）
ALLOWED_TABLES = JOB_M_TABLES


def extract_table_aliases(from_clause: str) -> Dict[str, str]:
    """FROM句からテーブル名とエイリアスを抽出
    
    カンマ区切りと明示的JOINの両方に対応
    """
    alias_to_table = {}
    
    # カンマで分割（カンマ区切りJOIN対応）
    table_parts = from_clause.split(',')
    
    for part in table_parts:
        part = part.strip()
        
        # JOINキーワードを含む場合はさらに分割
        if 'JOIN' in part.upper():
            # JOIN table AS alias の形式
            join_parts = re.split(r'\s+JOIN\s+', part, flags=re.IGNORECASE)
            for jp in join_parts:
                jp = jp.strip()
                # ON句を除去
                jp = re.sub(r'\s+ON\s+.+$', '', jp, flags=re.IGNORECASE)
                match = re.match(r'(\w+)\s+(?:AS\s+)?(\w+)', jp, re.IGNORECASE)
                if match:
                    table, alias = match.groups()
                    alias_to_table[alias] = table
        else:
            # カンマ区切りの場合: table AS alias
            match = re.match(r'(\w+)\s+(?:AS\s+)?(\w+)', part, re.IGNORECASE)
            if match:
                table, alias = match.groups()
                alias_to_table[alias] = table
    
    return alias_to_table


def extract_joins(from_clause: str, where_clause: str) -> List[str]:
    """JOIN条件を抽出（WHERE句の等価結合条件から）"""
    joins = []
    
    # WHERE句から = で結ばれた条件を抽出
    if where_clause:
        # パターン: alias1.col1 = alias2.col2
        join_pattern = r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)'
        matches = re.findall(join_pattern, where_clause)
        
        for alias1, col1, alias2, col2 in matches:
            joins.append(f"{alias1}.{col1}={alias2}.{col2}")
    
    return joins


def normalize_sql_operators(sql: str) -> str:
    """
    PostgreSQL特有の演算子を標準的な形式に正規化
    - 型キャスト (::型名, ::型名[]) を削除
    - PostgreSQL特有のLIKE演算子を変換
    """
    # 型キャスト除去: ::text, ::integer, ::text[] など
    # 配列型（::text[]）にも対応
    sql = re.sub(r'::\w+(\[\])?', '', sql)
    
    # PostgreSQL特有のLIKE演算子を標準形式に変換
    sql = re.sub(r'~~', 'LIKE', sql)
    sql = re.sub(r'!~~', '!LIKE', sql)
    sql = re.sub(r'~~\*', 'ILIKE', sql)
    sql = re.sub(r'!~~\*', '!ILIKE', sql)
    
    return sql


def convert_or_to_in(where_clause: str) -> Tuple[str, bool]:
    """OR条件をIN演算子に変換可能な場合は変換（改善版）
    
    Args:
        where_clause: WHERE句の内容
    
    Returns:
        (変換後のWHERE句, 変換成功したか)
    """
    # ステップ1: ORで分割
    or_parts = re.split(r'\s+OR\s+', where_clause, flags=re.IGNORECASE)
    
    if len(or_parts) <= 1:
        return where_clause, False
    
    # ステップ2: 各パーツを解析
    # パターン: (*)column)* = 'value'(*)
    # 括弧、カラム名、値を個別にキャプチャ
    parsed_parts = []
    for part in or_parts:
        part = part.strip()
        # 柔軟なパターン: 複数の括弧に対応
        match = re.match(r'^(\(*)\s*(\w+(?:\.\w+)?)\s*\)?\s*=\s*\'([^\']+)\'\s*(\)*)$', part)
        if match:
            open_parens, column, value, close_parens = match.groups()
            parsed_parts.append({
                'type': 'equality',
                'column': column,
                'value': value,
                'open_parens': open_parens,
                'close_parens': close_parens,
                'original': part
            })
        else:
            parsed_parts.append({
                'type': 'other',
                'original': part
            })
    
    # ステップ3: 同じカラムの等価条件をグループ化
    column_groups = {}
    other_conditions = []
    
    for part in parsed_parts:
        if part['type'] == 'equality':
            col = part['column']
            if col not in column_groups:
                column_groups[col] = []
            column_groups[col].append(part)
        else:
            other_conditions.append(part['original'])
    
    # ステップ4: IN変換
    converted = False
    in_conditions = []
    
    for column, parts in column_groups.items():
        if len(parts) > 1:
            # 複数の値 -> IN変換
            values = [f"'{p['value']}'" for p in parts]
            
            # 括弧数: すべての開き括弧の最小値、すべての閉じ括弧の最大値を使用
            min_open = min(len(p['open_parens']) for p in parts)
            max_close = max(len(p['close_parens']) for p in parts)
            
            in_cond = '(' * min_open + f"{column} IN ({', '.join(values)})" + ')' * max_close
            in_conditions.append(in_cond)
            converted = True
        else:
            # 単一の値 -> 元のまま
            in_conditions.append(parts[0]['original'])
    
    # ステップ5: 結果を再構築
    if converted:
        all_conditions = in_conditions + other_conditions
        result = ' OR '.join(all_conditions)
        return result, True
    else:
        return where_clause, False


def get_query_conditions(sql: str) -> Tuple[Dict[str, str], List[Tuple[str, str, any]]]:
    """
    SQLからNeuroCard推定用の条件リストを抽出する
    
    Args:
        sql: 解析対象のSQL
        
    Returns:
        (table_aliases, conditions)
        table_aliases: {alias: table_name}
        conditions: [(column, operator, value), ...]
    """
    # 1. SQLの正規化
    sql_normalized = normalize_sql_operators(sql)
    
    # 2. テーブルエイリアスの抽出
    from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|;|$)', sql_normalized, re.IGNORECASE | re.DOTALL)
    if not from_match:
        return {}, []
    
    from_clause = from_match.group(1)
    table_aliases = extract_table_aliases(from_clause)
    
    # job-mで許可されていないテーブルが含まれる場合はスキップ
    for table in table_aliases.values():
        if table not in JOB_M_TABLES:
            return {}, []
            
    # デフォルトエイリアスの決定（単一テーブルの場合）
    default_alias = None
    if len(table_aliases) == 1:
        default_alias = list(table_aliases.keys())[0]
        
    # 3. WHERE句の抽出
    where_match = re.search(r'WHERE\s+(.+?)(?:;|$)', sql_normalized, re.IGNORECASE | re.DOTALL)
    if not where_match:
        # WHERE句がない場合はテーブル情報のみ返す
        return table_aliases, []
        
    where_clause = where_match.group(1)
    
    # 4. 条件の抽出（extract_filtersのロジックを再利用・調整）
    # OR条件をIN演算子に変換を試行
    where_clause_normalized, converted = convert_or_to_in(where_clause)
    
    # 変換できなかったOR条件が残っている場合はスキップ
    if ' OR ' in where_clause_normalized.upper():
        return {}, []
    
    # WHERE句全体の外側括弧を除去
    where_stripped = where_clause_normalized.strip()
    while where_stripped.startswith('((') and where_stripped.endswith('))'):
        inner = where_stripped[1:-1]
        if inner.count('(') == inner.count(')'):
            where_stripped = inner.strip()
        else:
            break
            
    # ANDで分割
    # 以前の正規表現 r'\)\s+AND\s+\(|\s+AND\s+' は括弧を消費してしまうため問題があった
    # 単純に AND で分割し、個々の条件の括弧は後で除去する
    conditions = re.split(r'\s+AND\s+', where_stripped, flags=re.IGNORECASE)
    
    # ANY構文の変換
    converted_conditions = []
    for cond in conditions:
        # ANY構文: column = ANY ('{val1,val2,...}')
        any_pattern = r"\(?(\w+(?:\.\w+)?)\)?\s*=\s*ANY\s*\(\s*'\{([^}]+)\}'(?:::\w+\[\])?\s*\)"
        any_match = re.search(any_pattern, cond, re.IGNORECASE)
        if any_match:
            column = any_match.group(1)
            values = any_match.group(2)
            # 値リストを作成
            value_list = []
            for v in values.split(','):
                v = v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1] # ダブルクォート除去
                elif v.startswith("'") and v.endswith("'"):
                    v = v[1:-1] # シングルクォート除去
                value_list.append(v)
            
            # IN句として処理するため、再構築せずに直接リストとして保持したいが、
            # 下流の処理を共通化するため一旦IN句の文字列形式にする
            # ただし、ここでは値をクォートで囲んでカンマ区切りにする
            values_str = ", ".join([f"'{v}'" for v in value_list])
            in_clause = f"{column} IN ({values_str})"
            converted_conditions.append(in_clause)
        else:
            converted_conditions.append(cond)
            
    conditions = converted_conditions
    
    result_conditions = []
    
    for condition in conditions:
        condition = condition.strip()
        while condition.startswith('(') and condition.endswith(')'):
            condition = condition[1:-1].strip()
            
        # JOIN条件スキップ
        if re.match(r'\w+\.\w+\s*=\s*\w+\.\w+', condition):
            continue
            
        # IS NULL / IS NOT NULL
        is_null_pattern = r'(\w+(?:\.\w+)?)\s+(IS\s+NOT\s+NULL|IS\s+NULL)'
        is_null_match = re.match(is_null_pattern, condition, re.IGNORECASE)
        if is_null_match:
            column = is_null_match.group(1)
            operator = is_null_match.group(2).upper().replace(' ', '_')
            
            # エイリアス解決: alias.col -> table.col
            if '.' in column:
                alias, col = column.split('.')
                if alias in table_aliases:
                    column = f"{table_aliases[alias]}.{col}"
            elif default_alias:
                column = f"{table_aliases[default_alias]}.{column}"
                
            result_conditions.append((column, operator, 'NULL'))
            continue
            
        # IN演算子
        in_pattern = r'(\w+(?:\.\w+)?)\s+IN\s+\((.+?)\)'
        in_match = re.match(in_pattern, condition, re.IGNORECASE)
        if in_match:
            column = in_match.group(1)
            values_str = in_match.group(2)
            
            # エイリアス解決
            if '.' in column:
                alias, col = column.split('.')
                if alias in table_aliases:
                    column = f"{table_aliases[alias]}.{col}"
            elif default_alias:
                column = f"{table_aliases[default_alias]}.{column}"
                
            # 値リストをパース
            values = [v.strip().strip("'\"") for v in values_str.split(',')]
            
            result_conditions.append((column, 'IN', values))
            continue
            
        # 通常の比較演算子
        filter_pattern = r'\(?(\w+)\.(\w+)\)?\s*(>=|<=|!=|<>|NOT LIKE|!LIKE|LIKE|=|>|<)\s*(.+)'
        match = re.search(filter_pattern, condition)
        
        # エイリアスなしパターン
        no_alias_pattern = r'\(?(\w+)\)?\s*(>=|<=|!=|<>|NOT LIKE|!LIKE|LIKE|=|>|<)\s*(.+)'
        match_no_alias = re.search(no_alias_pattern, condition)
        
        column = None
        operator = None
        value = None
        
        if match:
            alias = match.group(1)
            col = match.group(2)
            operator = match.group(3)
            value = match.group(4)
            
            # エイリアス解決
            if alias in table_aliases:
                column = f"{table_aliases[alias]}.{col}"
            else:
                column = f"{alias}.{col}" # フォールバック
                
        elif match_no_alias and default_alias:
            col = match_no_alias.group(1)
            operator = match_no_alias.group(2)
            value = match_no_alias.group(3)
            column = f"{table_aliases[default_alias]}.{col}"
            
        if column:
            # 値のクォート除去
            value = value.strip()
            if (value.startswith("'") and value.endswith("'")) or \
               (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
                
            # 演算子の正規化
            op_map = {
                '<>': '!=',
                '!LIKE': 'NOT_LIKE',
                'NOT LIKE': 'NOT_LIKE',
                'LIKE': 'LIKE',
                '=': '=',
                '>': '>',
                '<': '<',
                '>=': '>=',
                '<=': '<=',
                '!=': '!='
            }
            if operator in op_map:
                operator = op_map[operator]
                
            result_conditions.append((column, operator, value))
            
    return table_aliases, result_conditions


def extract_filters(where_clause: str, join_conditions: List[str], default_alias: str = None, 
                   table_aliases: Dict[str, str] = None) -> List[str]:
    """WHERE句からフィルタ条件を抽出（JOIN条件を除く）
    
    Args:
        where_clause: WHERE句の内容
        join_conditions: JOIN条件のリスト
        default_alias: 単一テーブルの場合のデフォルトエイリアス
        table_aliases: エイリアス→テーブル名のマッピング（job-lightフィルタリング用）
    
    Returns:
        フィルタ条件のリスト（NeuroCard形式: ["col", "op", "val", ...]）
        OR条件を含む場合、または補助テーブルのフィルタの場合は空リストを返す
    """
    if not where_clause:
        return []
    
    # OR条件をIN演算子に変換を試行
    where_clause_normalized, converted = convert_or_to_in(where_clause)
    
    # 変換できなかったOR条件が残っている場合はスキップ
    if ' OR ' in where_clause_normalized.upper():
        return []
    
    # WHERE句全体の外側括弧を除去（AND分割を正しく行うため）
    where_stripped = where_clause_normalized.strip()
    while where_stripped.startswith('((') and where_stripped.endswith('))'):
        # バランスチェック: 最外層の括弧ペアのみ除去
        inner = where_stripped[1:-1]
        if inner.count('(') == inner.count(')'):
            where_stripped = inner.strip()
        else:
            break
    
    # 不正な括弧のバランスをチェック
    open_count = where_stripped.count('(')
    close_count = where_stripped.count(')')
    if open_count != close_count:
        return []
    
    filter_triplets = []  # ["col", "op", "val"] の形式で格納
    
    # WHERE句を AND で分割（括弧とORを考慮）
    conditions = re.split(r'\)\s+AND\s+\(|\s+AND\s+', where_stripped, flags=re.IGNORECASE)
    
    # PostgreSQLのANY構文をIN句に変換（前処理）
    # 例: info = ANY ('{Sweden,Norway}') → info IN ('Sweden', 'Norway')
    # 型キャスト付きにも対応: info = ANY ('{...}'::text[])
    converted_conditions = []
    for cond in conditions:
        # ANY構文のパターン（型キャスト付きも対応）
        # column = ANY ('{val1,val2,...}') または column = ANY ('{val1,val2,...}'::type[])
        # カラム名が括弧で囲まれている場合も対応: (column) = ANY (...)
        any_pattern = r"\(?(\w+(?:\.\w+)?)\)?\s*=\s*ANY\s*\(\s*'\{([^}]+)\}'(?:::\w+\[\])?\s*\)"
        any_match = re.search(any_pattern, cond, re.IGNORECASE)
        if any_match:
            column = any_match.group(1)
            values = any_match.group(2)
            # カンマで分割してIN句に変換
            # 値に引用符が含まれる場合も考慮
            value_list = []
            for v in values.split(','):
                v = v.strip()
                # 既に引用符で囲まれている場合はそのまま、そうでない場合は追加
                if v.startswith('"') and v.endswith('"'):
                    # ダブルクォートをシングルクォートに変換
                    v = f"'{v[1:-1]}'"
                elif not v.startswith("'"):
                    v = f"'{v}'"
                value_list.append(v)
            in_clause = f"{column} IN ({', '.join(value_list)})"
            converted_conditions.append(in_clause)
        else:
            converted_conditions.append(cond)
    
    conditions = converted_conditions
    
    for condition in conditions:
        condition = condition.strip()
        # すべての先頭と末尾の括弧を除去
        while condition.startswith('(') and condition.endswith(')'):
            condition = condition[1:-1].strip()
        
        # JOIN条件（=で2つのテーブル列を結ぶもの）をスキップ
        if re.match(r'\w+\.\w+\s*=\s*\w+\.\w+', condition):
            continue
        
        # IS NULL / IS NOT NULL を処理
        is_null_pattern = r'(\w+(?:\.\w+)?)\s+(IS\s+NOT\s+NULL|IS\s+NULL)'
        is_null_match = re.match(is_null_pattern, condition, re.IGNORECASE)
        if is_null_match:
            column = is_null_match.group(1)
            operator = is_null_match.group(2).upper().replace(' ', '_')  # IS_NULL or IS_NOT_NULL
            
            # エイリアスがない場合はdefault_aliasを追加
            if '.' not in column and default_alias:
                column = f"{default_alias}.{column}"
            
            # テーブルエイリアスチェック
            if table_aliases and '.' in column:
                alias = column.split('.')[0]
                if alias in table_aliases:
                    if table_aliases[alias] not in ALLOWED_TABLES:
                        continue
            
            # IS NULL/IS NOT NULLは値として'NULL'を設定
            filter_triplets.extend([column, operator, "'NULL'"])
            continue
        
        # IN演算子を処理
        # 括弧内の内容全体を取得: ('val1', 'val2', 'val3')
        in_pattern = r'(\w+(?:\.\w+)?)\s+IN\s+\((.+?)\)'
        in_match = re.match(in_pattern, condition, re.IGNORECASE)
        if in_match:
            column = in_match.group(1)
            values_str = in_match.group(2)  # 'val1', 'val2', 'val3'
            
            # エイリアスがない場合はdefault_aliasを追加
            if '.' not in column and default_alias:
                column = f"{default_alias}.{column}"
            
            # IN値をCSV形式に変換
            # NeuroCard公式形式: IN,"('val1','val2','val3')"
            # values_strを括弧で囲んでダブルクォートで囲む
            in_value = f'"({values_str})"'
            
            filter_triplets.extend([column, "IN", in_value])
            continue
        
        # 比較演算子を検出（型キャストは既にnormalize_sql_operatorsで除去済み）
        condition_cleaned = condition
        
        # フィルタパターン: (alias.column) op value または alias.column op value
        # 括弧付きカラム名に対応
        # 演算子の順序: 長いものを先に（>=, <=を>, <より先に）
        # !LIKE も追加（PostgreSQLの!~~から変換される）
        filter_pattern = r'\(?(\w+)\.(\w+)\)?\s*(>=|<=|!=|<>|NOT LIKE|!LIKE|LIKE|=|>|<)\s*(.+)'
        match = re.match(filter_pattern, condition_cleaned, re.IGNORECASE)
        
        if match:
            alias, column, operator, value = match.groups()
        else:
            # エイリアスなしパターン: (column) op value または column op value
            # 演算子の順序: 長いものを先に（>=, <=を>, <より先に）
            # !LIKE も追加（PostgreSQLの!~~から変換される）
            no_alias_pattern = r'\(?(\w+)\)?\s*(>=|<=|!=|<>|NOT LIKE|!LIKE|LIKE|=|>|<)\s*(.+)'
            match = re.match(no_alias_pattern, condition_cleaned, re.IGNORECASE)
            if match:
                column, operator, value = match.groups()
                alias = default_alias if default_alias else "UNKNOWN"
            else:
                # パースできない条件はスキップ
                continue
        
        # job-m外のテーブルのフィルタをスキップ
        if table_aliases and alias in table_aliases:
            if table_aliases[alias] not in ALLOWED_TABLES:
                continue
        
        # 値のクリーニング
        value = value.strip()
        
        # AND分割時に括弧が不均衡になる場合があるため、両端の余分な括弧を除去
        # 例: "2010)" → "2010"
        while value and value.startswith('('):
            value = value[1:].strip()
        while value and value.endswith(')'):
            value = value[:-1].strip()
        
        # 再度引用符を除去（括弧除去後に残っている可能性）
        value = re.sub(r"^['\"]|['\"]$", '', value)
        
        # 不正な値をチェック
        if ')' in value and value.count(')') > value.count('('):
            continue
        if re.match(r'^(=|>|<|>=|<=|!=|<>)', value):
            continue
        if ',' in value:
            continue
        
        # 演算子の正規化（LIKE/NOT LIKEは既に正規化済み）
        op_map = {
            '<>': '!=',
            'NOT LIKE': 'NOT_LIKE',
            '!LIKE': 'NOT_LIKE'  # !LIKEもNOT_LIKEに正規化
        }
        operator = op_map.get(operator.upper(), operator)
        
        # 値をシングルクォートで囲む
        if not value.startswith("'"):
            value = f"'{value}'"
        
        filter_triplets.extend([f"{alias}.{column}", operator, value])
    
    return filter_triplets


def parse_create_view_sql(sql: str) -> Tuple[str, str, str]:
    """
    CREATE MATERIALIZED VIEW文を解析
    
    Returns:
        (テーブル定義, JOIN条件, フィルタ条件)
        job-lightスキーマに含まれないテーブルを使用する場合は ("", "", "")
    """
    # PostgreSQL特有の演算子を正規化
    sql = normalize_sql_operators(sql)
    
    # SELECT ... FROM ... WHERE ... のパターンを抽出
    select_pattern = r'SELECT\s+.+?\s+FROM\s+(.+?)(?:\s+WHERE\s+(.+?))?(?:;|$)'
    match = re.search(select_pattern, sql, re.IGNORECASE | re.DOTALL)
    
    if not match:
        return "", "", ""
    
    from_clause = match.group(1).strip()
    where_clause = match.group(2).strip() if match.group(2) else ""
    
    # テーブルとエイリアスを抽出
    table_aliases = extract_table_aliases(from_clause)
    
    # job-mスキーマに含まれないテーブルをチェック
    invalid_tables = []
    for alias, table in table_aliases.items():
        if table not in ALLOWED_TABLES:
            invalid_tables.append(table)
    
    # job-mスキーマ外のテーブルが含まれる場合はスキップ
    if invalid_tables:
        return "", "", ""
    
    # job-lightテーブルのみを使用する場合は処理を続行
    # エイリアスが1つしかない場合、カラム名のみの条件をそのエイリアスで補完
    single_alias = list(table_aliases.keys())[0] if len(table_aliases) == 1 else None
    
    # テーブル定義を構築 (format: "table alias,table alias,...")
    tables = [f"{table} {alias}" for alias, table in table_aliases.items()]
    table_def = ",".join(tables)
    
    # JOIN条件を抽出（補助テーブルへの参照は除外）
    joins = extract_joins(from_clause, where_clause)
    # JOIN条件から補助テーブルへの参照を除外
    filtered_joins = []
    for join in joins:
        # join形式: alias1.col1=alias2.col2
        parts = join.split('=')
        if len(parts) == 2:
            alias1 = parts[0].split('.')[0]
            alias2 = parts[1].split('.')[0]
            # 両方のエイリアスがjob-lightテーブルに対応している場合のみ保持
            if alias1 in table_aliases and alias2 in table_aliases:
                filtered_joins.append(join)
    
    join_def = ",".join(filtered_joins)
    
    # フィルタ条件を抽出（エイリアスが1つだけの場合はそれを渡す）
    filters = extract_filters(where_clause, joins, single_alias, table_aliases)
    
    # フィルタ抽出で問題があった場合（OR条件、不正な値など）
    # extract_filtersは空リストを返す。この場合、WHERE句があるのにフィルタが
    # 空になるのはパース失敗なので、全体を無効にする
    if where_clause and not filters:
        return "", "", ""
    
    filter_def = ",".join(filters)
    
    return table_def, join_def, filter_def


def convert_to_neurocard_format(sql: str, view_name: str = None, dummy_cardinality: int = 1000) -> str:
    """
    SQLをNeuroCard CSV形式に変換
    
    Args:
        sql: 変換するSQL文
        view_name: ビュー名（マッピング用）
        dummy_cardinality: ダミーの基数値
    
    Returns:
        NeuroCard CSV形式の文字列、またはパース失敗時は空文字列
    
    フォーマット: テーブル定義#JOIN条件#フィルタ条件#正解基数#ビュー名
    Note: dummy_cardinalityはNeuroCardの内部計算で使用される可能性があるため、
          0ではなく妥当な正の値（デフォルト1000）を設定
    """
    table_def, join_def, filter_def = parse_create_view_sql(sql)
    
    if not table_def:
        # パースできない場合は空行を返す
        return ""
    
    # NeuroCardは単一テーブルクエリにも対応可能
    # （カラム間相関の学習が得意）
    # 結合条件がない場合は空文字列のまま進める
    
    # NeuroCard CSVフォーマットに整形（最後にビュー名を追加）
    csv_line = f"{table_def}#{join_def}#{filter_def}#{dummy_cardinality}"
    if view_name:
        csv_line += f"#{view_name}"
    return csv_line


def main():
    """メイン処理"""
    # 入力ファイルパス
    input_file = Path(__file__).parent.parent.parent / "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json"
    
    # 出力ファイルパス
    output_file = Path(__file__).parent / "queries_for_neurocard.csv"
    
    print(f"入力ファイル: {input_file}")
    print(f"出力ファイル: {output_file}")
    print(f"job-m許可テーブル: {', '.join(sorted(ALLOWED_TABLES))}")
    print()
    
    # JSONファイル読み込み
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # CSVデータを生成
    csv_lines = []
    view_name_mapping = []  # CSVの行番号 -> ビュー名のマッピング
    processed_count = 0
    skipped_count = 0
    skipped_reasons = {
        'non_job_m_tables': 0,
        'single_table': 0,
        'or_condition': 0,
        'or_converted_to_in': 0,  # OR→IN変換成功
        'parse_error': 0,
        'other': 0
    }
    
    for view_name, view_data in data.items():
        # "[]"キーからSQLを取得
        if "[]" not in view_data:
            continue
        
        sql = view_data["[]"]
        original_sql = sql  # 統計用に元のSQLを保持
        was_or_converted = False
        
        # OR→IN変換を試行
        if 'OR' in sql.upper():
            # WHERE句を抽出してOR→IN変換を試行
            where_match = re.search(r'WHERE\s+(.+?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
            if where_match:
                where_clause = where_match.group(1)
                where_converted, converted = convert_or_to_in(where_clause)
                if converted:
                    # 変換されたWHERE句でSQLを更新
                    sql = sql[:where_match.start(1)] + where_converted + sql[where_match.end(1):]
                    was_or_converted = True
        
        # NeuroCard形式に変換（ビュー名を渡す）
        csv_line = convert_to_neurocard_format(sql, view_name=view_name)
        
        if csv_line:
            csv_lines.append(csv_line)
            view_name_mapping.append(view_name)
            processed_count += 1
            if was_or_converted:
                skipped_reasons['or_converted_to_in'] += 1
        else:
            skipped_count += 1
            # スキップの理由を判定（シンプルなロジックに変更）
            
            # OR条件チェック
            if ' OR ' in sql.upper():
                skipped_reasons['or_condition'] += 1
                continue
            
            # 非job-mテーブルチェック
            non_job_m_tables = ['name', 'person_info', 'char_name', 'comp_cast', 'role_type', 'aka_name']
            if any(table in sql.lower() for table in non_job_m_tables):
                skipped_reasons['non_job_m_tables'] += 1
                continue
            
            # テーブル数チェック
            from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|;|$)', sql, re.IGNORECASE | re.DOTALL)
            if from_match:
                from_clause = from_match.group(1)
                is_single = ',' not in from_clause and 'JOIN' not in from_clause.upper()
                if is_single:
                    skipped_reasons['single_table'] += 1
                    continue
            
            # それ以外はパースエラー
            skipped_reasons['parse_error'] += 1
    
    # CSVファイルに書き込み
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(csv_lines))
    
    # マッピングファイルも出力（デバッグ・検証用）
    mapping_file = output_file.parent / "queries_for_neurocard_mapping.json"
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(view_name_mapping, f, indent=2)
    
    print(f"\n完了!")
    print(f"- 処理成功: {processed_count} クエリ")
    if skipped_reasons['or_converted_to_in'] > 0:
        print(f"  - うち OR→IN 変換: {skipped_reasons['or_converted_to_in']} クエリ")
    print(f"- スキップ: {skipped_count} クエリ")
    print(f"  - job-m外テーブル使用: {skipped_reasons['non_job_m_tables']}")
    print(f"  - 単一テーブル: {skipped_reasons['single_table']}")
    print(f"  - OR条件あり(変換不可): {skipped_reasons['or_condition']}")
    print(f"  - パースエラー: {skipped_reasons['parse_error']}")
    print(f"  - その他: {skipped_reasons['other']}")
    print(f"- 出力先: {output_file}")
    print(f"- マッピング: {mapping_file}")


if __name__ == "__main__":
    main()
