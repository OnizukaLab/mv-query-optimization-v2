"""SQLParserのテスト"""

import pytest

from src.rewrite.sql_parser import SQLParser


class TestSQLParser:
    """SQLParserクラスのテスト"""

    @pytest.fixture
    def parser(self):
        """パーサーのフィクスチャ"""
        return SQLParser()

    def test_extract_from_clause(self, parser):
        """FROM句の抽出"""
        sql = "SELECT * FROM users u WHERE u.age > 20"
        from_clause = parser.extract_from_clause(sql)
        assert "users u" in from_clause

    def test_extract_where_clause(self, parser):
        """WHERE句の抽出"""
        sql = "SELECT * FROM users WHERE age > 20 AND name = 'test'"
        where = parser.extract_where_clause(sql)
        assert "age > 20" in where
        assert "name = 'test'" in where

    def test_extract_tables_simple(self, parser):
        """単純なFROM句からテーブル抽出"""
        from_clause = "users u, orders o"
        tables = parser.extract_tables(from_clause)
        assert len(tables) == 2
        assert ("users", "u") in tables
        assert ("orders", "o") in tables

    def test_extract_tables_with_join(self, parser):
        """JOIN句を含むFROM句"""
        from_clause = "users u INNER JOIN orders o ON u.id = o.user_id"
        tables = parser.extract_tables(from_clause)
        assert len(tables) == 2

    def test_parse_condition(self, parser):
        """条件式の解析"""
        condition = "u.age > 20 AND u.name = 'test' AND o.total > 1000"
        conditions = parser.parse_condition(condition)
        assert "u.age" in conditions
        assert "u.name" in conditions
        assert "o.total" in conditions

    def test_reconstruct_query(self, parser):
        """クエリの再構築"""
        sql = parser.reconstruct_query(
            select_clause="u.name, COUNT(*)",
            from_clause="users u",
            where_clause="u.age > 20",
            group_by="u.name",
        )
        assert "SELECT u.name, COUNT(*)" in sql
        assert "FROM users u" in sql
        assert "WHERE u.age > 20" in sql
        assert "GROUP BY u.name" in sql
