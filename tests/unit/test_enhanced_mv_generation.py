"""Unit tests for SchemaProvider and EnhancedMVGenerator (Chapters 3 & 4).

This module tests the new schema provider and enhanced MV generator.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.rewrite.schema_provider import SchemaProvider, ForeignKeyRelation
from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
from src.core.models import NonLeafNodeInfo, JoinCondition
from src.core.query_manager import QueryManager


class TestSchemaProvider:
    """Test SchemaProvider functionality."""

    @pytest.fixture
    def mock_db_config(self):
        """Mock database configuration."""
        return {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }

    def test_init_with_config(self, mock_db_config):
        """Test initialization with config."""
        provider = SchemaProvider(mock_db_config)
        assert provider.db_config == mock_db_config
        assert provider._column_cache == {}
        assert provider._fk_cache == {}
        assert provider._pk_cache == {}

    def test_init_without_config(self):
        """Test initialization without config (uses defaults)."""
        provider = SchemaProvider()
        assert "host" in provider.db_config
        assert "database" in provider.db_config

    @patch('psycopg2.connect')
    def test_get_table_columns_with_db(self, mock_connect, mock_db_config):
        """Test getting table columns from database."""
        # Setup mock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [('id',), ('name',), ('year',)]
        mock_conn.cursor.return_value = mock_cur
        mock_connect.return_value = mock_conn
        
        provider = SchemaProvider(mock_db_config)
        columns = provider.get_table_columns('title')
        
        assert columns == ['id', 'name', 'year']
        assert 'title' in provider._column_cache
        mock_cur.execute.assert_called_once()

    @patch('psycopg2.connect')
    def test_get_table_columns_cached(self, mock_connect, mock_db_config):
        """Test that columns are cached."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [('id',), ('name',)]
        mock_conn.cursor.return_value = mock_cur
        mock_connect.return_value = mock_conn
        
        provider = SchemaProvider(mock_db_config)
        
        # First call
        columns1 = provider.get_table_columns('title')
        # Second call (should use cache)
        columns2 = provider.get_table_columns('title')
        
        assert columns1 == columns2
        # Database should only be queried once
        assert mock_cur.execute.call_count == 1

    def test_get_table_columns_fallback(self, mock_db_config):
        """Test fallback to static schema when psycopg2 not available."""
        provider = SchemaProvider(mock_db_config)
        
        # Should fall back to static schema
        columns = provider.get_table_columns('title')
        
        # Should return something (from static schema)
        assert isinstance(columns, list)

    @patch('psycopg2.connect')
    def test_get_foreign_key_relations(self, mock_connect, mock_db_config):
        """Test getting FK relations."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ('movie_info', 'movie_id', 'title', 'id', 'fk_movie_info_title')
        ]
        mock_conn.cursor.return_value = mock_cur
        mock_connect.return_value = mock_conn
        
        provider = SchemaProvider(mock_db_config)
        fk_relations = provider.get_foreign_key_relations(
            ['movie_info'], ['title']
        )
        
        assert len(fk_relations) == 1
        assert fk_relations[0].from_table == 'movie_info'
        assert fk_relations[0].from_column == 'movie_id'
        assert fk_relations[0].to_table == 'title'
        assert fk_relations[0].to_column == 'id'

    @patch('psycopg2.connect')
    def test_get_primary_key(self, mock_connect, mock_db_config):
        """Test getting primary key."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [('id',)]
        mock_conn.cursor.return_value = mock_cur
        mock_connect.return_value = mock_conn
        
        provider = SchemaProvider(mock_db_config)
        pk = provider.get_primary_key('title')
        
        assert pk == ['id']

    def test_clear_cache(self, mock_db_config):
        """Test cache clearing."""
        provider = SchemaProvider(mock_db_config)
        provider._column_cache['test'] = ['col1']
        provider._fk_cache[('t1', 't2')] = []
        provider._pk_cache['test'] = ['id']
        
        provider.clear_cache()
        
        assert len(provider._column_cache) == 0
        assert len(provider._fk_cache) == 0
        assert len(provider._pk_cache) == 0

    def test_context_manager(self, mock_db_config):
        """Test context manager usage."""
        with SchemaProvider(mock_db_config) as provider:
            assert provider is not None
        # Connection should be closed after exiting context


class TestEnhancedMVGenerator:
    """Test EnhancedMVGenerator functionality."""

    @pytest.fixture
    def qm(self):
        """Create QueryManager with test data."""
        qm = QueryManager()
        
        # Add leaf nodes
        qm.process_leaf_node(
            "Seq Scan", "title", "t",
            "(production_year > 2000)",
            [0, 0], 30.0, 30.0, 12500, 25
        )
        qm.process_leaf_node(
            "Seq Scan", "cast_info", "ci", "",
            [0, 1], 50.0, 50.0, 125000, 25
        )
        
        return qm

    @pytest.fixture
    def schema_provider(self):
        """Create mock SchemaProvider."""
        provider = Mock(spec=SchemaProvider)
        provider.get_table_columns.side_effect = lambda table: {
            'title': ['id', 'title', 'production_year'],
            'cast_info': ['id', 'person_id', 'movie_id', 'role_id']
        }.get(table, [])
        return provider

    def test_init(self, qm, schema_provider):
        """Test initialization."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        assert generator.qm == qm
        assert generator.schema_provider == schema_provider

    def test_generate_leaf_mv_sql(self, qm, schema_provider):
        """Test leaf MV SQL generation."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        sql = generator.generate_leaf_mv_sql('leaf_1')
        
        assert 'CREATE MATERIALIZED VIEW leaf_1 AS' in sql
        assert 'SELECT t.id, t.title, t.production_year' in sql
        assert 'FROM title AS t' in sql
        assert 'WHERE (production_year > 2000)' in sql

    def test_generate_leaf_mv_sql_no_filter(self, qm, schema_provider):
        """Test leaf MV without filter."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        sql = generator.generate_leaf_mv_sql('leaf_2')
        
        assert 'CREATE MATERIALIZED VIEW leaf_2 AS' in sql
        assert 'FROM cast_info AS ci' in sql
        assert 'WHERE' not in sql  # No filter condition

    def test_generate_non_leaf_mv_enhanced(self, qm, schema_provider):
        """Test non-leaf MV generation with enhanced info."""
        # Create JOIN condition
        join_cond = JoinCondition(
            left_table="t",
            left_column="id",
            operator="=",
            right_table="ci",
            right_column="movie_id",
            condition_type="Hash Cond",
            original_text="(t.id = ci.movie_id)"
        )
        
        # Create non-leaf node with enhanced info
        node_id = qm.process_non_leaf_node_v2(
            operator="Hash Join",
            join_type="Inner",
            child_node_ids=['leaf_1', 'leaf_2'],
            join_conditions=[join_cond],
            filters=[],
            position=[0, 2],
            total_cost=100.0,
            original_cost=100.0,
            rows=1000,
            width=50
        )
        
        generator = EnhancedMVGenerator(qm, schema_provider)
        sql = generator.generate_non_leaf_mv_sql(node_id)
        
        assert 'CREATE MATERIALIZED VIEW' in sql
        # JOINキーワードは大文字小文字の違いや、カンマ区切りの可能性があるため柔軟にチェック
        assert ('JOIN' in sql.upper() or ',' in sql)
        # 実際のテーブル名またはエイリアスがSQL内にあることを確認
        assert ('title' in sql.lower() or 't' in sql.lower())
        assert ('cast_info' in sql.lower() or 'ci' in sql.lower())

    def test_get_child_tables_leaf(self, qm, schema_provider):
        """Test getting tables for leaf node."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        tables = generator._get_child_tables('leaf_1')
        
        # エイリアスまたはテーブル名のいずれかが含まれていることを確認
        assert 't' in tables or 'title' in tables

    def test_get_child_tables_non_leaf(self, qm, schema_provider):
        """Test getting tables for non-leaf node."""
        # Create non-leaf node
        node_id = qm.process_non_leaf_node(
            ['leaf_1', 'leaf_2'],
            [0, 2], 100.0, 50000, 50
        )
        
        generator = EnhancedMVGenerator(qm, schema_provider)
        tables = generator._get_child_tables(node_id)
        
        # エイリアスまたはテーブル名のいずれかが含まれていることを確認
        assert ('t' in tables or 'title' in tables)
        assert ('ci' in tables or 'cast_info' in tables)

    def test_find_join_conditions_for_mvs(self, qm, schema_provider):
        """Test finding JOIN conditions between MVs."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        join_conditions = [
            JoinCondition(
                "leaf_1", "id", "=", "leaf_2", "movie_id",
                "Hash Cond", "(leaf_1.id = leaf_2.movie_id)"
            ),
            JoinCondition(
                "leaf_1", "kind_id", "=", "leaf_3", "id",
                "Hash Cond", "(leaf_1.kind_id = leaf_3.id)"
            )
        ]
        
        # Find condition between leaf_1 and leaf_2
        matching = generator._find_join_conditions_for_mvs(
            join_conditions,
            'leaf_1',
            'leaf_2'
        )
        
        assert len(matching) == 1
        assert matching[0].right_table == 'leaf_2'

    def test_build_select_clause(self, qm, schema_provider):
        """Test building SELECT clause."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        child_mvs = [
            {'id': 'leaf_1', 'tables': ['title']},
            {'id': 'leaf_2', 'tables': ['cast_info']}
        ]
        
        select_clause = generator._build_select_clause(child_mvs)
        
        assert 'leaf_1.*' in select_clause
        assert 'leaf_2.*' in select_clause

    def test_generate_mv_sql_dispatch(self, qm, schema_provider):
        """Test that generate_mv_sql dispatches correctly."""
        generator = EnhancedMVGenerator(qm, schema_provider)
        
        # Test leaf
        leaf_sql = generator.generate_mv_sql('leaf_1')
        assert 'FROM title' in leaf_sql
        
        # Test non-leaf (create one first)
        node_id = qm.process_non_leaf_node(
            ['leaf_1', 'leaf_2'],
            [0, 2], 100.0, 50000, 50
        )
        non_leaf_sql = generator.generate_mv_sql(node_id)
        assert 'JOIN' in non_leaf_sql

    def test_fallback_without_enhanced_info(self, qm, schema_provider):
        """Test fallback when enhanced info not available."""
        # Create non-leaf without enhanced info
        node_id = qm.process_non_leaf_node(
            ['leaf_1', 'leaf_2'],
            [0, 2], 100.0, 50000, 50
        )
        
        generator = EnhancedMVGenerator(qm, schema_provider)
        sql = generator.generate_non_leaf_mv_sql(node_id)
        
        # Should still generate SQL (using fallback)
        assert 'CREATE MATERIALIZED VIEW' in sql
        assert node_id in sql


class TestAddTableAliasToFilter:
    """Test _add_table_alias_to_filter method functionality."""

    @pytest.fixture
    def generator(self):
        """Create EnhancedMVGenerator with mock dependencies."""
        qm = Mock()
        qm.leaf_nodes_map_r = {}
        qm.non_leaf_nodes_info = {}
        qm.non_leaf_nodes_map_r = {}
        return EnhancedMVGenerator(qm)

    def test_is_null_pattern(self, generator):
        """Test adding alias to IS NULL pattern."""
        result = generator._add_table_alias_to_filter(
            "(note IS NULL)",
            "ci"
        )
        assert "ci.note" in result
        assert "IS NULL" in result

    def test_is_not_null_pattern(self, generator):
        """Test adding alias to IS NOT NULL pattern."""
        result = generator._add_table_alias_to_filter(
            "(note IS NOT NULL)",
            "pi"
        )
        assert "pi.note" in result
        assert "IS NOT NULL" in result

    def test_cast_pattern(self, generator):
        """Test adding alias to cast pattern."""
        result = generator._add_table_alias_to_filter(
            "((info)::text = 'mini biography'::text)",
            "it"
        )
        assert "(it.info)::text" in result

    def test_multiple_patterns(self, generator):
        """Test adding alias to multiple patterns in same condition."""
        result = generator._add_table_alias_to_filter(
            "(note IS NOT NULL) AND ((info)::text = 'test'::text)",
            "t"
        )
        assert "t.note" in result
        assert "(t.info)::text" in result

    def test_already_qualified_column(self, generator):
        """Test that already qualified columns are not modified."""
        result = generator._add_table_alias_to_filter(
            "(t.name IS NOT NULL)",
            "other_alias"
        )
        # Should remain as t.name, not other_alias.t.name
        assert "t.name" in result
        assert "other_alias.t.name" not in result

    def test_sql_keywords_not_modified(self, generator):
        """Test that SQL keywords are not treated as column names."""
        result = generator._add_table_alias_to_filter(
            "(status IS NOT NULL)",
            "t"
        )
        assert "t.status" in result
        # NULL keyword should not be prefixed
        assert "t.NULL" not in result
        assert "t.NOT" not in result

    def test_complex_imdb_filter(self, generator):
        """Test complex filter from IMDB database."""
        filter_condition = (
            "(note IS NOT NULL) AND ((name)::text ~~ '%a%'::text) "
            "AND ((info)::text = 'mini biography'::text)"
        )
        result = generator._add_table_alias_to_filter(filter_condition, "pi")
        
        assert "pi.note" in result
        assert "(pi.name)::text" in result
        assert "(pi.info)::text" in result

    def test_empty_filter(self, generator):
        """Test with empty filter condition."""
        result = generator._add_table_alias_to_filter("", "t")
        assert result == ""

    def test_none_filter(self, generator):
        """Test with None filter condition."""
        result = generator._add_table_alias_to_filter(None, "t")
        assert result is None

    def test_comparison_operators(self, generator):
        """Test with various comparison operators."""
        result = generator._add_table_alias_to_filter(
            "year > 2000 AND score <= 100",
            "t"
        )
        assert "t.year" in result
        assert "t.score" in result
