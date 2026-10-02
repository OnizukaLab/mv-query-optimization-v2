"""Unit tests for DatabaseConnection class."""

from unittest.mock import MagicMock, patch

import pytest

from config.settings import DatabaseConfig
from src.database.connection import DatabaseConnection, DatabaseConnectionPool


class TestDatabaseConnection:
    """Test suite for DatabaseConnection."""

    @pytest.fixture
    def config(self):
        """Create a test database configuration."""
        return DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            timeout=30,
        )

    @pytest.fixture
    def mock_psycopg2_connect(self):
        """Mock psycopg2.connect."""
        with patch("src.database.connection.psycopg2.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            yield mock_connect

    def test_init(self, config):
        """Test DatabaseConnection initialization."""
        db = DatabaseConnection(config)

        assert db.config == config
        assert db._conn is None

    def test_get_connection_creates_new_connection(self, config, mock_psycopg2_connect):
        """Test that get_connection creates a new connection."""
        db = DatabaseConnection(config)

        conn = db.get_connection()

        assert conn is not None
        mock_psycopg2_connect.assert_called_once_with(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=10,
            options="-c statement_timeout=30000",
        )

    def test_get_connection_reuses_existing(self, config, mock_psycopg2_connect):
        """Test that get_connection reuses existing connection."""
        db = DatabaseConnection(config)

        conn1 = db.get_connection()
        conn2 = db.get_connection()

        assert conn1 is conn2
        assert mock_psycopg2_connect.call_count == 1

    def test_get_connection_reconnects_if_closed(self, config, mock_psycopg2_connect):
        """Test that get_connection reconnects if connection is closed."""
        db = DatabaseConnection(config)

        conn1 = db.get_connection()
        conn1.closed = True  # Simulate closed connection

        db.get_connection()

        assert mock_psycopg2_connect.call_count == 2

    def test_cursor_context_manager(self, config, mock_psycopg2_connect):
        """Test cursor context manager."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with db.cursor() as cursor:
            assert cursor is mock_cursor

        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_cursor_rollback_on_error(self, config, mock_psycopg2_connect):
        """Test that cursor rolls back on error."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(ValueError):
            with db.cursor():
                raise ValueError("Test error")

        mock_conn.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_cursor_no_commit(self, config, mock_psycopg2_connect):
        """Test cursor with commit=False."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with db.cursor(commit=False):
            pass

        mock_conn.commit.assert_not_called()

    def test_execute(self, config, mock_psycopg2_connect):
        """Test execute method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db.execute("SELECT * FROM users", (1,))

        mock_cursor.execute.assert_called_once_with("SELECT * FROM users", (1,))
        mock_conn.commit.assert_called_once()

    def test_execute_many(self, config, mock_psycopg2_connect):
        """Test execute_many method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        params = [(1,), (2,), (3,)]
        db.execute_many("INSERT INTO users VALUES (%s)", params)

        mock_cursor.executemany.assert_called_once_with("INSERT INTO users VALUES (%s)", params)

    def test_fetch_one(self, config, mock_psycopg2_connect):
        """Test fetch_one method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, "Alice")
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        result = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))

        assert result == (1, "Alice")
        mock_cursor.execute.assert_called_once_with("SELECT * FROM users WHERE id = %s", (1,))
        mock_conn.commit.assert_not_called()  # Read operations don't commit

    def test_fetch_all(self, config, mock_psycopg2_connect):
        """Test fetch_all method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        results = db.fetch_all("SELECT * FROM users")

        assert len(results) == 2
        assert results[0] == (1, "Alice")

    def test_fetch_value(self, config, mock_psycopg2_connect):
        """Test fetch_value method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        result = db.fetch_value("SELECT COUNT(*) FROM users")

        assert result == 42

    def test_fetch_value_default(self, config, mock_psycopg2_connect):
        """Test fetch_value with default when no result."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        result = db.fetch_value("SELECT * FROM users WHERE id = 999", default="Not found")

        assert result == "Not found"

    def test_close(self, config, mock_psycopg2_connect):
        """Test close method."""
        db = DatabaseConnection(config)
        mock_conn = mock_psycopg2_connect.return_value

        db.get_connection()
        db.close()

        mock_conn.close.assert_called_once()
        assert db._conn is None

    def test_context_manager(self, config, mock_psycopg2_connect):
        """Test DatabaseConnection as context manager."""
        mock_conn = mock_psycopg2_connect.return_value

        with DatabaseConnection(config) as db:
            db.get_connection()

        mock_conn.close.assert_called_once()

    def test_is_connected_property(self, config, mock_psycopg2_connect):
        """Test is_connected property."""
        db = DatabaseConnection(config)

        assert not db.is_connected

        db.get_connection()
        assert db.is_connected

        db.close()
        assert not db.is_connected


class TestDatabaseConnectionPool:
    """Test suite for DatabaseConnectionPool."""

    @pytest.fixture
    def config(self):
        """Create a test database configuration."""
        return DatabaseConfig(host="localhost", port=5432, database="testdb", user="testuser")

    @pytest.fixture(autouse=True)
    def clear_pool(self):
        """Clear the connection pool before each test."""
        DatabaseConnectionPool._instances.clear()
        yield
        DatabaseConnectionPool._instances.clear()

    def test_get_connection_creates_new(self, config):
        """Test that get_connection creates new connection."""
        conn = DatabaseConnectionPool.get_connection(config)

        assert isinstance(conn, DatabaseConnection)
        assert len(DatabaseConnectionPool._instances) == 1

    def test_get_connection_reuses_existing(self, config):
        """Test that get_connection reuses existing connection."""
        conn1 = DatabaseConnectionPool.get_connection(config)
        conn2 = DatabaseConnectionPool.get_connection(config)

        assert conn1 is conn2
        assert len(DatabaseConnectionPool._instances) == 1

    def test_get_connection_different_databases(self, config):
        """Test connections to different databases are separate."""
        config2 = DatabaseConfig(host="localhost", port=5432, database="otherdb", user="testuser")

        conn1 = DatabaseConnectionPool.get_connection(config)
        conn2 = DatabaseConnectionPool.get_connection(config2)

        assert conn1 is not conn2
        assert len(DatabaseConnectionPool._instances) == 2

    @patch("src.database.connection.DatabaseConnection.close")
    def test_close_all(self, mock_close, config):
        """Test close_all method."""
        DatabaseConnectionPool.get_connection(config)

        DatabaseConnectionPool.close_all()

        assert len(DatabaseConnectionPool._instances) == 0
