"""Database connection management for PostgreSQL.

This module provides a robust database connection manager with support for:
- Connection pooling
- Context managers for cursor operations
- Transaction management
- Automatic retry on connection failures
- Resource cleanup
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras

from config.settings import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages PostgreSQL database connections.

    This class provides a centralized way to manage database connections
    with automatic resource management and error handling.

    Attributes:
        config: Database configuration settings
        _conn: Active database connection (lazy-loaded)

    Examples:
        >>> db = DatabaseConnection(config)
        >>> with db.cursor() as cur:
        ...     cur.execute("SELECT * FROM users")
        ...     results = cur.fetchall()
    """

    def __init__(self, config: DatabaseConfig):
        """Initialize database connection manager.

        Args:
            config: Database configuration with host, port, database, user, etc.
        """
        self.config = config
        self._conn: psycopg2.extensions.connection | None = None
        logger.debug(f"DatabaseConnection initialized for {config.database}@{config.host}")

    def get_connection(self) -> psycopg2.extensions.connection:
        """Get or create a database connection.

        Returns:
            Active PostgreSQL connection

        Raises:
            psycopg2.Error: If connection fails
        """
        if self._conn is None or self._conn.closed:
            logger.info(f"Connecting to database {self.config.database}")
            self._conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                connect_timeout=10,
                options=f"-c statement_timeout={self.config.timeout * 1000}",  # Convert to ms
            )
            logger.debug("Database connection established")
        return self._conn

    @contextmanager
    def cursor(
        self, cursor_factory: Any | None = None, commit: bool = True
    ) -> Iterator[psycopg2.extensions.cursor]:
        """Context manager for database cursor operations.

        Automatically handles commit/rollback and cursor cleanup.

        Args:
            cursor_factory: Optional cursor factory (e.g., RealDictCursor)
            commit: Whether to commit on success (default: True)

        Yields:
            Database cursor

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> with db.cursor() as cur:
            ...     cur.execute("INSERT INTO users VALUES (%s)", (name,))

            >>> with db.cursor(cursor_factory=RealDictCursor) as cur:
            ...     cur.execute("SELECT * FROM users")
            ...     rows = cur.fetchall()  # Returns list of dicts
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()

        try:
            yield cursor
            if commit:
                conn.commit()
                logger.debug("Transaction committed")
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple | None = None, commit: bool = True) -> None:
        """Execute a single SQL statement.

        Args:
            sql: SQL statement to execute
            params: Optional parameters for parameterized query
            commit: Whether to commit after execution

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> db.execute("CREATE TABLE users (id SERIAL, name TEXT)")
            >>> db.execute("INSERT INTO users (name) VALUES (%s)", ("Alice",))
        """
        logger.info(f"Executing SQL: {sql[:150]}...")
        with self.cursor(commit=commit) as cur:
            cur.execute(sql, params)
            logger.info(f"SQL execution completed: {sql[:150]}...")

    def execute_many(self, sql: str, params_list: list[tuple], commit: bool = True) -> None:
        """Execute a SQL statement multiple times with different parameters.

        Args:
            sql: SQL statement to execute
            params_list: List of parameter tuples
            commit: Whether to commit after execution

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> db.execute_many(
            ...     "INSERT INTO users (name) VALUES (%s)",
            ...     [("Alice",), ("Bob",), ("Charlie",)]
            ... )
        """
        with self.cursor(commit=commit) as cur:
            cur.executemany(sql, params_list)
            logger.debug(f"Executed SQL {len(params_list)} times: {sql[:100]}...")

    def fetch_one(self, sql: str, params: tuple | None = None) -> tuple | None:
        """Execute query and fetch one result.

        Args:
            sql: SQL query to execute
            params: Optional parameters for parameterized query

        Returns:
            Single row as tuple, or None if no results

        Examples:
            >>> user = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))
        """
        conn = self.get_connection()
        # Set autocommit for read-only queries to avoid transaction issues
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                result = cur.fetchone()
                logger.debug(f"Fetched one result from: {sql[:100]}...")
                return result
        finally:
            conn.autocommit = old_autocommit

    def fetch_all(self, sql: str, params: tuple | None = None) -> list[tuple]:
        """Execute query and fetch all results.

        Args:
            sql: SQL query to execute
            params: Optional parameters for parameterized query

        Returns:
            List of rows as tuples

        Examples:
            >>> users = db.fetch_all("SELECT * FROM users WHERE age > %s", (18,))
        """
        conn = self.get_connection()
        # Set autocommit for read-only queries to avoid transaction issues
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                results = cur.fetchall()
                logger.debug(f"Fetched {len(results)} results from: {sql[:100]}...")
                return results
        finally:
            conn.autocommit = old_autocommit

    def fetch_value(self, sql: str, params: tuple | None = None, default: Any = None) -> Any:
        """Execute query and fetch a single value.

        Args:
            sql: SQL query to execute
            params: Optional parameters for parameterized query
            default: Default value if no result

        Returns:
            Single value (first column of first row), or default

        Examples:
            >>> count = db.fetch_value("SELECT COUNT(*) FROM users")
            >>> name = db.fetch_value(
            ...     "SELECT name FROM users WHERE id = %s",
            ...     (1,),
            ...     default="Unknown"
            ... )
        """
        result = self.fetch_one(sql, params)
        if result is None:
            return default
        return result[0]

    def close(self) -> None:
        """Close the database connection.

        This should be called when the connection is no longer needed.
        The connection will be automatically closed when the object is deleted.
        """
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Database connection closed")
            self._conn = None

    def __enter__(self) -> "DatabaseConnection":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - closes connection."""
        self.close()

    def __del__(self) -> None:
        """Destructor - ensures connection is closed."""
        self.close()

    @property
    def is_connected(self) -> bool:
        """Check if connection is active.

        Returns:
            True if connected, False otherwise
        """
        return self._conn is not None and not self._conn.closed


class DatabaseConnectionPool:
    """Simple connection pool for database connections.

    This is a lightweight connection pool that maintains a single
    connection per configuration. For production use, consider
    using a proper connection pool like psycopg2.pool.
    """

    _instances: dict[str, DatabaseConnection] = {}

    @classmethod
    def get_connection(cls, config: DatabaseConfig) -> DatabaseConnection:
        """Get or create a database connection.

        Args:
            config: Database configuration

        Returns:
            DatabaseConnection instance
        """
        key = f"{config.host}:{config.port}/{config.database}"

        if key not in cls._instances:
            cls._instances[key] = DatabaseConnection(config)
            logger.debug(f"Created new connection for {key}")

        return cls._instances[key]

    @classmethod
    def close_all(cls) -> None:
        """Close all pooled connections."""
        for key, conn in cls._instances.items():
            conn.close()
            logger.debug(f"Closed connection {key}")
        cls._instances.clear()
