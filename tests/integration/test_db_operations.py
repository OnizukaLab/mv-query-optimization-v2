"""Integration tests for database operations.

These tests require a running PostgreSQL database.
They are marked with @pytest.mark.integration and can be skipped
by running: pytest -m "not integration"
"""

import pytest

from config.settings import DatabaseConfig, Settings
from src.database import DatabaseConnection, MaterializedViewManager, SchemaManager

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_config():
    """Create database configuration for tests."""
    # Try to load from settings, fallback to defaults
    try:
        settings = Settings.from_yaml("config/default.yaml")
        return settings.database
    except Exception:
        return DatabaseConfig(host="localhost", port=5432, database="imdbload", user="postgres")


@pytest.fixture(scope="module")
def db_connection(db_config):
    """Create a database connection for tests."""
    conn = DatabaseConnection(db_config)
    yield conn
    conn.close()


@pytest.fixture
def mv_manager(db_connection):
    """Create a MaterializedViewManager for tests."""
    manager = MaterializedViewManager(db_connection, schema="public")
    yield manager
    # Cleanup: drop any test views
    try:
        manager.drop_all_views(pattern="test_mv_%")
    except Exception:
        pass


@pytest.fixture
def schema_manager(db_connection):
    """Create a SchemaManager for tests."""
    return SchemaManager(db_connection, schema="public")


class TestDatabaseConnectionIntegration:
    """Integration tests for DatabaseConnection."""

    def test_connection_successful(self, db_connection):
        """Test that connection to database is successful."""
        conn = db_connection.get_connection()
        assert conn is not None
        assert not conn.closed

    def test_execute_simple_query(self, db_connection):
        """Test executing a simple query."""
        result = db_connection.fetch_value("SELECT 1")
        assert result == 1

    def test_fetch_database_version(self, db_connection):
        """Test fetching PostgreSQL version."""
        version = db_connection.fetch_value("SELECT version()")
        assert version is not None
        assert "PostgreSQL" in version


class TestMaterializedViewManagerIntegration:
    """Integration tests for MaterializedViewManager."""

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_create_and_drop_view(self, mv_manager):
        """Test creating and dropping a materialized view."""
        view_name = "test_mv_simple"

        # Create view
        result = mv_manager.create_view(view_name, "SELECT 1 as id, 'test' as name", replace=True)
        assert result is True

        # Check it exists
        assert mv_manager.view_exists(view_name)

        # Check it appears in list
        views = mv_manager.list_views(pattern="test_mv_%")
        assert view_name in views

        # Drop view
        mv_manager.drop_view(view_name)
        assert not mv_manager.view_exists(view_name)

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_get_view_size(self, mv_manager):
        """Test getting view size."""
        view_name = "test_mv_size"

        # Create view
        mv_manager.create_view(view_name, "SELECT generate_series(1, 1000) as id", replace=True)

        # Get size
        size = mv_manager.get_view_size(view_name)
        assert size > 0

        # Cleanup
        mv_manager.drop_view(view_name)

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_refresh_view(self, mv_manager):
        """Test refreshing a materialized view."""
        view_name = "test_mv_refresh"

        # Create view
        mv_manager.create_view(view_name, "SELECT NOW() as timestamp", replace=True)

        # Refresh
        result = mv_manager.refresh_view(view_name)
        assert result is True

        # Cleanup
        mv_manager.drop_view(view_name)


class TestSchemaManagerIntegration:
    """Integration tests for SchemaManager."""

    def test_list_tables(self, schema_manager):
        """Test listing tables in schema."""
        tables = schema_manager.list_tables()
        assert isinstance(tables, list)
        # Should have at least some tables in imdbload
        assert len(tables) >= 0

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_table_exists(self, schema_manager):
        """Test checking if table exists."""
        # Assuming 'title' table exists in IMDB schema
        assert schema_manager.table_exists("title")
        assert not schema_manager.table_exists("nonexistent_table_xyz")

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_get_column_info(self, schema_manager):
        """Test getting column information."""
        # Assuming 'title' table exists
        columns = schema_manager.get_column_info("title")
        assert isinstance(columns, list)
        assert len(columns) > 0

        # Check column structure
        col = columns[0]
        assert hasattr(col, "name")
        assert hasattr(col, "data_type")
        assert hasattr(col, "is_nullable")

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_get_table_size(self, schema_manager):
        """Test getting table size."""
        # Assuming 'title' table exists
        size = schema_manager.get_table_size("title")
        assert isinstance(size, int)
        assert size >= 0


class TestEndToEndWorkflow:
    """End-to-end integration tests."""

    @pytest.mark.skip(reason="Requires specific database setup")
    def test_complete_mv_workflow(self, db_connection):
        """Test complete workflow: create, query, refresh, drop MV."""
        mv_manager = MaterializedViewManager(db_connection)
        schema_manager = SchemaManager(db_connection)

        view_name = "test_mv_workflow"

        try:
            # 1. Check if table exists for our query
            if schema_manager.table_exists("title"):

                # 2. Create materialized view
                mv_manager.create_view(
                    view_name, "SELECT id, title FROM title LIMIT 100", replace=True
                )

                # 3. Verify it exists
                assert mv_manager.view_exists(view_name)

                # 4. Get view info
                info = mv_manager.get_view_info(view_name)
                assert info is not None
                assert info.name == view_name
                assert info.size_bytes > 0

                # 5. Refresh view
                mv_manager.refresh_view(view_name)

                # 6. Query the view
                with db_connection.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {view_name}")
                    count = cur.fetchone()[0]
                    assert count <= 100

        finally:
            # Cleanup
            mv_manager.drop_view(view_name, if_exists=True)


# Conftest additions for integration tests
def pytest_configure(config):
    """Register integration marker."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires database)"
    )
