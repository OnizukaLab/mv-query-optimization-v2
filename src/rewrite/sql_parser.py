"""SQL解析ユーティリティ"""

import re


class SQLParser:
    """SQLクエリの解析を行うヘルパークラス"""

    def __init__(self):
        """初期化"""
        pass

    def extract_from_clause(self, sql: str) -> str:
        """FROM句を抽出

        Args:
            sql: SQL文字列

        Returns:
            FROM句の文字列
        """
        pattern = r"FROM\s+(.+?)(?:WHERE|GROUP BY|ORDER BY|LIMIT|$)"
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def extract_where_clause(self, sql: str) -> str:
        """WHERE句を抽出

        Args:
            sql: SQL文字列

        Returns:
            WHERE句の文字列
        """
        pattern = r"WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)"
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def extract_tables(self, from_clause: str) -> list[tuple[str, str]]:
        """FROM句からテーブルとエイリアスを抽出

        Args:
            from_clause: FROM句の文字列

        Returns:
            (テーブル名, エイリアス) のリスト
        """
        tables = []
        # カンマで分割
        parts = from_clause.split(",")

        for part in parts:
            part = part.strip()
            # JOIN句を含む場合
            if "JOIN" in part.upper():
                # 複数のJOINを処理
                join_parts = re.split(
                    r"\s+(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\s+", part, flags=re.IGNORECASE
                )
                for jp in join_parts:
                    table_alias = self._extract_table_alias(jp)
                    if table_alias:
                        tables.append(table_alias)
            else:
                table_alias = self._extract_table_alias(part)
                if table_alias:
                    tables.append(table_alias)

        return tables

    def _extract_table_alias(self, part: str) -> tuple[str, str] | None:
        """テーブル名とエイリアスを抽出

        Args:
            part: SQL断片

        Returns:
            (テーブル名, エイリアス) または None
        """
        # ON句を削除
        part = re.sub(r"\s+ON\s+.+$", "", part, flags=re.IGNORECASE)
        part = part.strip()

        # "table AS alias" または "table alias" の形式
        match = re.match(r"(\w+)(?:\s+(?:AS\s+)?(\w+))?", part, re.IGNORECASE)
        if match:
            table = match.group(1)
            alias = match.group(2) if match.group(2) else table
            return (table, alias)
        return None

    def parse_condition(self, condition: str) -> dict[str, list[str]]:
        """条件式を解析してカラムごとに分類

        Args:
            condition: WHERE句の条件式

        Returns:
            {alias.column: [条件1, 条件2, ...]}
        """
        conditions = {}

        # AND/ORで分割
        parts = re.split(r"\s+(?:AND|OR)\s+", condition, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            # alias.column を抽出
            match = re.match(r"(\w+)\.(\w+)\s*([<>=!]+|LIKE|IN)\s*(.+)", part, re.IGNORECASE)
            if match:
                alias = match.group(1)
                column = match.group(2)
                operator = match.group(3)
                value = match.group(4)

                key = f"{alias}.{column}"
                if key not in conditions:
                    conditions[key] = []
                conditions[key].append(f"{column} {operator} {value}")

        return conditions

    def reconstruct_query(
        self,
        select_clause: str,
        from_clause: str,
        where_clause: str = "",
        group_by: str = "",
        order_by: str = "",
        limit: str = "",
    ) -> str:
        """クエリを再構築

        Args:
            select_clause: SELECT句
            from_clause: FROM句
            where_clause: WHERE句
            group_by: GROUP BY句
            order_by: ORDER BY句
            limit: LIMIT句

        Returns:
            再構築されたSQL
        """
        sql = f"SELECT {select_clause}\nFROM {from_clause}"

        if where_clause:
            sql += f"\nWHERE {where_clause}"
        if group_by:
            sql += f"\nGROUP BY {group_by}"
        if order_by:
            sql += f"\nORDER BY {order_by}"
        if limit:
            sql += f"\nLIMIT {limit}"

        return sql
