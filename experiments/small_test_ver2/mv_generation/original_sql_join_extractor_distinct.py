"""元のSQLファイルからJOIN条件とテーブルエイリアスを抽出するユーティリティ.

PostgreSQLの定数プッシュダウン最適化により、実行プランからJOIN条件が
消失するケースに対応するため、元のSQLクエリから正確なJOIN条件を抽出する。

使用例:
    sql = open("01_queries/cluster_53/5a9.sql").read()
    aliases = extract_aliases_from_sql(sql)
    # => {'t': 'title', 'mi1': 'movie_info', 'it3': 'info_type', ...}
    conditions = extract_equijoin_conditions(sql)
    # => [('mi1', 'info_type_id', 'it3', 'id'), ...]
"""

import re
from typing import Optional


def _normalize_identifier(token: str) -> str:
    """識別子を正規化（ダブルクォート除去 + 小文字化）."""
    token = token.strip()
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1]
    return token.lower()


def _extract_main_clause(sql: str, clause: str) -> str:
    """指定句の本体を抽出（次の主要句まで）."""
    match = re.search(
        rf'\b{clause}\s+(.*?)(?:\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|;|$)',
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _extract_equijoins_from_expression(expr: str) -> list[tuple[str, str, str, str]]:
    """式文字列から alias.column = alias.column を抽出."""
    if not expr:
        return []

    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    pattern = re.compile(
        rf'({ident})\s*\.\s*({ident})\s*=\s*({ident})\s*\.\s*({ident})',
        flags=re.IGNORECASE,
    )

    result = []
    for match in pattern.finditer(expr):
        left_alias = _normalize_identifier(match.group(1))
        left_column = _normalize_identifier(match.group(2))
        right_alias = _normalize_identifier(match.group(3))
        right_column = _normalize_identifier(match.group(4))

        if left_alias == right_alias:
            continue

        result.append((left_alias, left_column, right_alias, right_column))

    return result


def extract_aliases_from_sql(sql: str) -> dict[str, str]:
    """FROM句からテーブルエイリアスマッピングを抽出.

    サポートする形式:
      - table AS alias
      - table alias (ASなし)

    Args:
        sql: SQLクエリ文字列

    Returns:
        {alias: table_name} の辞書
    """
    # FROM句を抽出（WHERE/GROUP BY/ORDER BY/LIMIT/HAVING まで）
    from_clause = _extract_main_clause(sql, 'FROM')
    if not from_clause:
        return {}

    # FROM/JOIN で参照されるテーブルとエイリアスを抽出
    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    table_pattern = re.compile(
        rf'(?:^|,|\bJOIN\b)\s*({ident})\s+(?:AS\s+)?({ident})\b',
        re.IGNORECASE,
    )

    aliases = {}
    for match in table_pattern.finditer(from_clause):
        table_name = _normalize_identifier(match.group(1))
        alias = _normalize_identifier(match.group(2))
        if alias.upper() == 'AS':
            continue
        aliases[alias] = table_name

    # エイリアスなし（単独テーブル）のフォールバック
    if not aliases:
        single = re.match(rf'^\s*({ident})\s*$', from_clause, re.IGNORECASE)
        if single:
            table_name = _normalize_identifier(single.group(1))
            aliases[table_name] = table_name

    return aliases


def extract_equijoin_conditions(sql: str) -> list[tuple[str, str, str, str]]:
    """WHERE句からalias.column = alias.column形式の等価結合条件を抽出.

    定数条件（alias.column = 'value' や alias.column = 123）は除外し、
    テーブル間結合のみを返す。

    Args:
        sql: SQLクエリ文字列

    Returns:
        [(left_alias, left_column, right_alias, right_column), ...] のリスト
    """
    conditions = []
    dedupe_keys = set()

    # 1) WHERE句由来の等価結合
    where_clause = _extract_main_clause(sql, 'WHERE')
    for cond in _extract_equijoins_from_expression(where_clause):
        key = tuple(sorted([(cond[0], cond[1]), (cond[2], cond[3])]))
        if key in dedupe_keys:
            continue
        dedupe_keys.add(key)
        conditions.append(cond)

    # 2) JOIN ... ON 由来の等価結合
    on_pattern = re.compile(
        r'\bON\b\s+(.*?)(?=\b(?:INNER|LEFT|RIGHT|FULL|CROSS)\s+JOIN\b|\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|;|$)',
        re.IGNORECASE | re.DOTALL,
    )
    for on_match in on_pattern.finditer(sql):
        on_expr = on_match.group(1).strip()
        for cond in _extract_equijoins_from_expression(on_expr):
            key = tuple(sorted([(cond[0], cond[1]), (cond[2], cond[3])]))
            if key in dedupe_keys:
                continue
            dedupe_keys.add(key)
            conditions.append(cond)

    return conditions


def extract_select_column_refs(sql: str) -> list[tuple[str, str]]:
    """SELECT句（DISTINCT ON含む）から alias.column 参照を抽出.

    Args:
        sql: SQLクエリ文字列

    Returns:
        [(alias, column), ...] のリスト（重複除去済み）
    """
    select_clause = _extract_main_clause(sql, 'SELECT')
    if not select_clause:
        return []

    # DISTINCT ON (...) と DISTINCT を除去して式本体を解析
    body = re.sub(r'^\s*DISTINCT\s+ON\s*\([^)]*\)\s*', '', select_clause, flags=re.IGNORECASE)
    body = re.sub(r'^\s*DISTINCT\s+', '', body, flags=re.IGNORECASE)

    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    pattern = re.compile(
        rf'({ident})\s*\.\s*({ident})',
        flags=re.IGNORECASE,
    )

    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(body):
        alias = _normalize_identifier(match.group(1))
        column = _normalize_identifier(match.group(2))
        key = (alias, column)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)

    return result


def extract_distinct_on_columns(sql: str) -> list[tuple[str, str]]:
    """SELECT句のDISTINCT ON(...) から alias.column 参照を抽出.

    Args:
        sql: SQLクエリ文字列

    Returns:
        [(alias, column), ...] のリスト
    """
    select_clause = _extract_main_clause(sql, 'SELECT')
    if not select_clause:
        return []

    # DISTINCT ON (...) を抽出
    match = re.search(r'DISTINCT\s+ON\s*\((.*?)\)', select_clause, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    body = match.group(1)
    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    pattern = re.compile(
        rf'({ident})\s*\.\s*({ident})',
        flags=re.IGNORECASE,
    )

    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in pattern.finditer(body):
        alias = _normalize_identifier(m.group(1))
        column = _normalize_identifier(m.group(2))
        key = (alias, column)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)

    return result


def extract_where_column_refs(sql: str) -> list[tuple[str, str]]:
    """WHERE句から alias.column 参照を抽出.

    Args:
        sql: SQLクエリ文字列

    Returns:
        [(alias, column), ...] のリスト（重複除去済み）
    """
    where_clause = _extract_main_clause(sql, 'WHERE')
    if not where_clause:
        return []

    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    pattern = re.compile(
        rf'({ident})\s*\.\s*({ident})',
        flags=re.IGNORECASE,
    )

    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(where_clause):
        alias = _normalize_identifier(match.group(1))
        column = _normalize_identifier(match.group(2))
        key = (alias, column)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)

    return result


def get_join_conditions_for_aliases(
    sql: str,
    target_aliases: set[str]
) -> list[tuple[str, str, str, str]]:
    """指定されたエイリアスセットに関連するJOIN条件のみを返す.

    サブツリー内のテーブルのみに関連するJOIN条件をフィルタリングする。

    Args:
        sql: SQLクエリ文字列
        target_aliases: 対象エイリアスのセット（小文字）

    Returns:
        [(left_alias, left_column, right_alias, right_column), ...] のリスト
        ※両辺のエイリアスがtarget_aliasesに含まれるもののみ
    """
    all_conditions = extract_equijoin_conditions(sql)
    return [
        (la, lc, ra, rc)
        for la, lc, ra, rc in all_conditions
        if la in target_aliases and ra in target_aliases
    ]


def find_sql_file_for_query(
    json_file_path: str,
    sql_dir: Optional[str] = None
) -> Optional[str]:
    """JSONファイルパスから対応するSQLファイルパスを導出.

    Args:
        json_file_path: JSONファイルの絶対パス
            例: .../02_json/cluster_53/5a9.json
        sql_dir: SQLファイルが格納されているディレクトリ
            例: .../01_queries/cluster_53
            None の場合、JSONパスから推測する

    Returns:
        SQLファイルのパス。見つからない場合はNone
    """
    from pathlib import Path

    json_path = Path(json_file_path)
    stem = json_path.stem  # e.g., "5a9"

    if sql_dir:
        sql_path = Path(sql_dir) / f"{stem}.sql"
        return str(sql_path) if sql_path.exists() else None

    # JSONパスから推測: 02_json → 01_queries に置換
    json_dir = str(json_path.parent)
    possible_sql_dir = json_dir.replace("02_json", "01_queries")
    sql_path = Path(possible_sql_dir) / f"{stem}.sql"
    return str(sql_path) if sql_path.exists() else None
