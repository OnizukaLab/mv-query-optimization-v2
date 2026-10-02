"""Unit tests for MaterializedViewManager class."""

from unittest.mock import Mock, patch

import pytest

from src.core.models import MaterializedView
from src.database.connection import DatabaseConnection
from src.database.mv_manager import MaterializedViewManager, ViewInfo


class TestMaterializedViewManager:
    """Test suite for MaterializedViewManager."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        return Mock(spec=DatabaseConnection)

    @pytest.fixture
    def mv_manager(self, mock_db):
        """Create MaterializedViewManager instance."""
        return MaterializedViewManager(mock_db, schema="public")

    def test_init(self, mock_db):
        """Test MaterializedViewManager initialization."""
        manager = MaterializedViewManager(mock_db, schema="test_schema")

        assert manager.db is mock_db
        assert manager.schema == "test_schema"

    def test_create_view(self, mv_manager, mock_db):
        """Test creating a materialized view."""
        mock_db.execute = Mock()
        mock_db.fetch_value = Mock(return_value=False)  # view doesn't exist

        result = mv_manager.create_view("test_view", "SELECT * FROM users", replace=False)

        assert result is True
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args[0][0]
        assert "CREATE MATERIALIZED VIEW" in call_args
        assert "test_view" in call_args

    def test_create_view_with_replace(self, mv_manager, mock_db):
        """Test creating a view with replace=True."""
        mock_db.execute = Mock()
        mock_db.fetch_value = Mock(return_value=True)  # view exists

        with patch.object(mv_manager, "drop_view") as mock_drop:
            mv_manager.create_view("test_view", "SELECT * FROM users", replace=True)

        mock_drop.assert_called_once_with("test_view", cascade=True)
        mock_db.execute.assert_called_once()

    def test_create_view_without_data(self, mv_manager, mock_db):
        """Test creating a view with WITH NO DATA."""
        mock_db.execute = Mock()
        mock_db.fetch_value = Mock(return_value=False)

        mv_manager.create_view("test_view", "SELECT * FROM users", with_data=False)

        call_args = mock_db.execute.call_args[0][0]
        assert "WITH NO DATA" in call_args

    def test_create_view_from_model(self, mv_manager, mock_db):
        """Test creating a view from MaterializedView model."""
        mock_db.execute = Mock()
        mock_db.fetch_value = Mock(return_value=False)

        view = MaterializedView(
            view_id="mv_test",
            node_id="node_1",
            create_sql="SELECT id, name FROM users",
            size=1024,
            maintenance_cost=0.5,
        )

        result = mv_manager.create_view_from_model(view)

        assert result is True
        call_args = mock_db.execute.call_args[0][0]
        assert "mv_test" in call_args
        assert "SELECT id, name FROM users" in call_args

    def test_drop_view(self, mv_manager, mock_db):
        """Test dropping a materialized view."""
        mock_db.execute = Mock()

        result = mv_manager.drop_view("test_view")

        assert result is True
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args[0][0]
        assert "DROP MATERIALIZED VIEW" in call_args
        assert "test_view" in call_args

    def test_drop_view_cascade(self, mv_manager, mock_db):
        """Test dropping a view with CASCADE."""
        mock_db.execute = Mock()

        mv_manager.drop_view("test_view", cascade=True)

        call_args = mock_db.execute.call_args[0][0]
        assert "CASCADE" in call_args

    def test_drop_all_views(self, mv_manager, mock_db):
        """Test dropping all views."""
        mock_db.fetch_all = Mock(return_value=[("mv_1",), ("mv_2",), ("mv_3",)])
        mock_db.execute = Mock()

        count = mv_manager.drop_all_views()

        assert count == 3
        assert mock_db.execute.call_count == 3

    def test_drop_all_views_with_pattern(self, mv_manager, mock_db):
        """Test dropping views matching a pattern."""
        mock_db.fetch_all = Mock(return_value=[("mv_temp_1",), ("mv_temp_2",)])
        mock_db.execute = Mock()

        count = mv_manager.drop_all_views(pattern="mv_temp_%")

        assert count == 2

    def test_refresh_view(self, mv_manager, mock_db):
        """Test refreshing a materialized view."""
        mock_db.execute = Mock()

        result = mv_manager.refresh_view("test_view")

        assert result is True
        call_args = mock_db.execute.call_args[0][0]
        assert "REFRESH MATERIALIZED VIEW" in call_args
        assert "test_view" in call_args

    def test_refresh_view_concurrently(self, mv_manager, mock_db):
        """Test refreshing a view concurrently."""
        mock_db.execute = Mock()

        mv_manager.refresh_view("test_view", concurrently=True)

        call_args = mock_db.execute.call_args[0][0]
        assert "CONCURRENTLY" in call_args

    def test_view_exists_true(self, mv_manager, mock_db):
        """Test view_exists when view exists."""
        mock_db.fetch_value = Mock(return_value=True)

        result = mv_manager.view_exists("test_view")

        assert result is True

    def test_view_exists_false(self, mv_manager, mock_db):
        """Test view_exists when view doesn't exist."""
        mock_db.fetch_value = Mock(return_value=False)

        result = mv_manager.view_exists("test_view")

        assert result is False

    def test_list_views(self, mv_manager, mock_db):
        """Test listing all views."""
        mock_db.fetch_all = Mock(return_value=[("mv_users",), ("mv_orders",), ("mv_products",)])

        views = mv_manager.list_views()

        assert len(views) == 3
        assert "mv_users" in views
        assert "mv_orders" in views

    def test_list_views_with_pattern(self, mv_manager, mock_db):
        """Test listing views with pattern."""
        mock_db.fetch_all = Mock(return_value=[("mv_temp_1",), ("mv_temp_2",)])

        views = mv_manager.list_views(pattern="mv_temp_%")

        assert len(views) == 2
        # Verify the pattern was passed to the SQL
        call_args = mock_db.fetch_all.call_args[0]
        assert "mv_temp_%" in call_args[1]

    def test_get_view_size(self, mv_manager, mock_db):
        """Test getting view size."""
        mock_db.fetch_value = Mock(return_value=1048576)  # 1 MB

        size = mv_manager.get_view_size("test_view")

        assert size == 1048576

    def test_get_total_size(self, mv_manager, mock_db):
        """Test getting total size of all views."""
        mock_db.fetch_all = Mock(return_value=[("mv_1",), ("mv_2",)])
        mock_db.fetch_value = Mock(side_effect=[1024, 2048])  # Sizes for each view

        total = mv_manager.get_total_size()

        assert total == 3072

    def test_get_view_definition(self, mv_manager, mock_db):
        """Test getting view definition."""
        expected_def = "SELECT * FROM users WHERE active = true"
        mock_db.fetch_value = Mock(return_value=expected_def)

        definition = mv_manager.get_view_definition("test_view")

        assert definition == expected_def

    def test_get_view_info_when_exists(self, mv_manager, mock_db):
        """Test getting view info when view exists."""
        mock_db.fetch_value = Mock(
            side_effect=[True, 1024, 100]  # view_exists  # size  # row count
        )
        mock_db.fetch_one = Mock(
            return_value=("public", "test_view", "SELECT * FROM users", True)  # ispopulated
        )

        info = mv_manager.get_view_info("test_view")

        assert info is not None
        assert info.name == "test_view"
        assert info.definition == "SELECT * FROM users"
        assert info.size_bytes == 1024
        assert info.row_count == 100
        assert info.has_data is True

    def test_get_view_info_when_not_exists(self, mv_manager, mock_db):
        """Test getting view info when view doesn't exist."""
        mock_db.fetch_value = Mock(return_value=False)

        info = mv_manager.get_view_info("nonexistent_view")

        assert info is None

    def test_sanitize_identifier_valid(self, mv_manager):
        """Test sanitizing valid identifiers."""
        assert mv_manager._sanitize_identifier("test_view") == "test_view"
        assert mv_manager._sanitize_identifier("Test_View_123") == "Test_View_123"
        assert mv_manager._sanitize_identifier('"quoted_view"') == "quoted_view"

    def test_sanitize_identifier_invalid(self, mv_manager):
        """Test sanitizing invalid identifiers raises error."""
        with pytest.raises(ValueError):
            mv_manager._sanitize_identifier("test-view")  # hyphen not allowed

        with pytest.raises(ValueError):
            mv_manager._sanitize_identifier("123_view")  # can't start with number

        with pytest.raises(ValueError):
            mv_manager._sanitize_identifier("test; DROP TABLE")  # SQL injection attempt

    def test_create_index(self, mv_manager, mock_db):
        """Test creating an index on a view."""
        mock_db.execute = Mock()

        result = mv_manager.create_index("test_view", ["user_id"], unique=True)

        assert result is True
        call_args = mock_db.execute.call_args[0][0]
        assert "CREATE UNIQUE INDEX" in call_args
        assert "test_view" in call_args
        assert "user_id" in call_args

    def test_create_index_multiple_columns(self, mv_manager, mock_db):
        """Test creating an index on multiple columns."""
        mock_db.execute = Mock()

        mv_manager.create_index("test_view", ["user_id", "order_date"], index_name="custom_idx")

        call_args = mock_db.execute.call_args[0][0]
        assert "user_id, order_date" in call_args
        assert "custom_idx" in call_args


class TestViewInfo:
    """Test suite for ViewInfo dataclass."""

    def test_view_info_creation(self):
        """Test creating a ViewInfo instance."""
        info = ViewInfo(
            name="test_view",
            definition="SELECT * FROM users",
            size_bytes=1024,
            row_count=100,
            has_data=True,
        )

        assert info.name == "test_view"
        assert info.definition == "SELECT * FROM users"
        assert info.size_bytes == 1024
        assert info.row_count == 100
        assert info.has_data is True

    def test_view_info_defaults(self):
        """Test ViewInfo with default values."""
        info = ViewInfo(name="test_view")

        assert info.name == "test_view"
        assert info.definition is None
        assert info.size_bytes is None
        assert info.row_count is None
        assert info.has_data is True
