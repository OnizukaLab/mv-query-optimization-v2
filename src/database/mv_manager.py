"""Materialized View management for PostgreSQL.

This module provides functionality for creating, managing, and querying
materialized views in PostgreSQL.
"""

import logging
import re
from dataclasses import dataclass

from src.core.models import MaterializedView

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass
class ViewInfo:
    """Information about a materialized view.

    Attributes:
        name: View name
        definition: SQL definition of the view
        size_bytes: Size in bytes
        row_count: Number of rows
        has_data: Whether view has been populated
    """

    name: str
    definition: str | None = None
    size_bytes: int | None = None
    row_count: int | None = None
    has_data: bool = True


class MaterializedViewManager:
    """Manages materialized views in PostgreSQL.

    This class provides methods for creating, dropping, refreshing,
    and querying materialized views.

    Attributes:
        db: Database connection instance
        schema: Database schema name (default: 'public')

    Examples:
        >>> mv_manager = MaterializedViewManager(db_connection)
        >>> mv_manager.create_view("mv_users", "SELECT * FROM users WHERE active = true")
        >>> views = mv_manager.list_views()
        >>> mv_manager.drop_view("mv_users")
    """

    def __init__(self, db: DatabaseConnection, schema: str = "public"):
        """Initialize materialized view manager.

        Args:
            db: Database connection
            schema: Database schema name (default: 'public')
        """
        self.db = db
        self.schema = schema
        logger.debug(f"MaterializedViewManager initialized for schema '{schema}'")

    def create_view(
        self, view_name: str, query: str, replace: bool = True, with_data: bool = True
    ) -> bool:
        """Create a materialized view.

        Args:
            view_name: Name of the materialized view
            query: SQL query defining the view
            replace: Whether to replace if exists (default: True)
            with_data: Whether to populate immediately (default: True)

        Returns:
            True if successful, False otherwise

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> mv_manager.create_view(
            ...     "mv_active_users",
            ...     "SELECT * FROM users WHERE active = true"
            ... )
        """
        # Sanitize view name
        view_name = self._sanitize_identifier(view_name)

        try:
            # Drop if exists and replace is True
            if replace and self.view_exists(view_name):
                logger.info(f"Dropping existing view '{view_name}' for replacement")
                self.drop_view(view_name, cascade=True)

            # Create the materialized view
            with_clause = "WITH DATA" if with_data else "WITH NO DATA"
            sql = f"""
                CREATE MATERIALIZED VIEW {self.schema}.{view_name}
                AS {query}
                {with_clause}
            """

            logger.info(f"Creating materialized view '{view_name}'")
            self.db.execute(sql)
            logger.info(f"Successfully created view '{view_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to create view '{view_name}': {e}")
            raise

    def create_view_from_model(self, view: MaterializedView, replace: bool = True) -> bool:
        """Create a materialized view from a MaterializedView model.

        Args:
            view: MaterializedView model instance
            replace: Whether to replace if exists

        Returns:
            True if successful

        Examples:
            >>> view = MaterializedView(
            ...     view_id="mv_1",
            ...     node_id="node_123",
            ...     create_sql="SELECT * FROM users",
            ...     size=1024,
            ...     maintenance_cost=0.5
            ... )
            >>> mv_manager.create_view_from_model(view)
        """
        # Check if create_sql already contains CREATE MATERIALIZED VIEW
        if view.create_sql.strip().upper().startswith("CREATE MATERIALIZED VIEW"):
            # SQL is complete, execute directly
            try:
                # Extract view name from SQL
                # Pattern: CREATE MATERIALIZED VIEW <view_name> AS
                import re
                match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+(\w+)', view.create_sql, re.IGNORECASE)
                actual_view_name = match.group(1) if match else view.view_id
                
                # Drop existing view if replace is True
                if replace and self.view_exists(actual_view_name):
                    logger.info(f"Dropping existing view '{actual_view_name}' for replacement")
                    self.drop_view(actual_view_name, cascade=True)
                
                logger.info(f"Creating materialized view '{actual_view_name}'")
                self.db.execute(view.create_sql)
                logger.info(f"Successfully created view '{actual_view_name}'")
                return True
            except Exception as e:
                logger.error(f"Failed to create view '{view.view_id}': {e}")
                raise
        else:
            # SQL is just the query part, use create_view method
            return self.create_view(view_name=view.view_id, query=view.create_sql, replace=replace)

    def drop_view(self, view_name: str, if_exists: bool = True, cascade: bool = False) -> bool:
        """Drop a materialized view.

        Args:
            view_name: Name of the view to drop
            if_exists: Don't raise error if view doesn't exist
            cascade: Drop dependent objects as well

        Returns:
            True if dropped, False if didn't exist (when if_exists=True)

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> mv_manager.drop_view("mv_active_users")
            >>> mv_manager.drop_view("mv_old", cascade=True)
        """
        view_name = self._sanitize_identifier(view_name)

        try:
            if_exists_clause = "IF EXISTS" if if_exists else ""
            cascade_clause = "CASCADE" if cascade else ""

            sql = f"""
                DROP MATERIALIZED VIEW {if_exists_clause}
                {self.schema}.{view_name}
                {cascade_clause}
            """

            logger.info(f"Dropping materialized view '{view_name}'")
            self.db.execute(sql)
            logger.info(f"Successfully dropped view '{view_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to drop view '{view_name}': {e}")
            if not if_exists:
                raise
            return False

    def drop_all_views(self, pattern: str | None = None) -> int:
        """Drop all materialized views in the schema.

        Args:
            pattern: Optional SQL LIKE pattern to filter views (e.g., 'mv_%')

        Returns:
            Number of views dropped

        Examples:
            >>> # Drop all views
            >>> count = mv_manager.drop_all_views()

            >>> # Drop only views starting with 'mv_'
            >>> count = mv_manager.drop_all_views(pattern="mv_%")
        """
        views = self.list_views(pattern=pattern)
        dropped = 0

        for view_name in views:
            try:
                self.drop_view(view_name, if_exists=True)
                dropped += 1
            except Exception as e:
                logger.warning(f"Failed to drop view '{view_name}': {e}")

        logger.info(f"Dropped {dropped} materialized views")
        return dropped

    def refresh_view(self, view_name: str, concurrently: bool = False) -> bool:
        """Refresh a materialized view.

        Args:
            view_name: Name of the view to refresh
            concurrently: Use CONCURRENTLY option (requires unique index)

        Returns:
            True if successful

        Raises:
            psycopg2.Error: Database operation errors

        Examples:
            >>> mv_manager.refresh_view("mv_active_users")
            >>> mv_manager.refresh_view("mv_stats", concurrently=True)
        """
        view_name = self._sanitize_identifier(view_name)
        concurrent_clause = "CONCURRENTLY" if concurrently else ""

        sql = f"""
            REFRESH MATERIALIZED VIEW {concurrent_clause}
            {self.schema}.{view_name}
        """

        logger.info(f"Refreshing materialized view '{view_name}'")
        self.db.execute(sql)
        logger.info(f"Successfully refreshed view '{view_name}'")
        return True

    def view_exists(self, view_name: str) -> bool:
        """Check if a materialized view exists.

        Args:
            view_name: Name of the view

        Returns:
            True if view exists, False otherwise

        Examples:
            >>> if mv_manager.view_exists("mv_users"):
            ...     print("View exists")
        """
        view_name = self._sanitize_identifier(view_name)

        sql = """
            SELECT EXISTS (
                SELECT 1
                FROM pg_matviews
                WHERE schemaname = %s AND matviewname = %s
            )
        """

        result = self.db.fetch_value(sql, (self.schema, view_name), default=False)
        return bool(result)

    def list_views(self, pattern: str | None = None) -> list[str]:
        """List all materialized views in the schema.

        Args:
            pattern: Optional SQL LIKE pattern to filter views

        Returns:
            List of view names

        Examples:
            >>> views = mv_manager.list_views()
            >>> print(f"Found {len(views)} views: {views}")

            >>> # List only views starting with 'mv_'
            >>> mv_views = mv_manager.list_views(pattern="mv_%")
        """
        sql = """
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = %s
        """
        params = [self.schema]

        if pattern:
            sql += " AND matviewname LIKE %s"
            params.append(pattern)

        sql += " ORDER BY matviewname"

        results = self.db.fetch_all(sql, tuple(params))
        view_names = [row[0] for row in results]

        logger.debug(f"Found {len(view_names)} materialized views")
        return view_names

    def get_view_info(self, view_name: str) -> ViewInfo | None:
        """Get detailed information about a materialized view.

        Args:
            view_name: Name of the view

        Returns:
            ViewInfo object, or None if view doesn't exist

        Examples:
            >>> info = mv_manager.get_view_info("mv_users")
            >>> print(f"View size: {info.size_bytes} bytes")
            >>> print(f"Row count: {info.row_count}")
        """
        if not self.view_exists(view_name):
            return None

        view_name = self._sanitize_identifier(view_name)

        # Get basic info
        sql = """
            SELECT
                schemaname,
                matviewname,
                definition,
                ispopulated
            FROM pg_matviews
            WHERE schemaname = %s AND matviewname = %s
        """
        result = self.db.fetch_one(sql, (self.schema, view_name))

        if not result:
            return None

        # Get size
        size_bytes = self.get_view_size(view_name)

        # Get row count (if populated)
        row_count = None
        if result[3]:  # ispopulated
            try:
                count_sql = f"SELECT COUNT(*) FROM {self.schema}.{view_name}"
                row_count = self.db.fetch_value(count_sql)
            except Exception as e:
                logger.warning(f"Failed to get row count for '{view_name}': {e}")

        return ViewInfo(
            name=result[1],
            definition=result[2],
            size_bytes=size_bytes,
            row_count=row_count,
            has_data=result[3],
        )

    def get_view_size(self, view_name: str) -> int:
        """Get the size of a materialized view in bytes.

        Args:
            view_name: Name of the view

        Returns:
            Size in bytes, or 0 if view doesn't exist

        Examples:
            >>> size = mv_manager.get_view_size("mv_users")
            >>> print(f"View size: {size / 1024 / 1024:.2f} MB")
        """
        view_name = self._sanitize_identifier(view_name)

        sql = """
            SELECT pg_total_relation_size(%s)
        """

        full_name = f"{self.schema}.{view_name}"
        size = self.db.fetch_value(sql, (full_name,), default=0)

        return int(size) if size else 0

    def get_total_size(self, pattern: str | None = None) -> int:
        """Get total size of all materialized views.

        Args:
            pattern: Optional SQL LIKE pattern to filter views

        Returns:
            Total size in bytes

        Examples:
            >>> total = mv_manager.get_total_size()
            >>> print(f"Total MV size: {total / 1024 / 1024:.2f} MB")
        """
        views = self.list_views(pattern=pattern)
        total_size = sum(self.get_view_size(view) for view in views)

        logger.debug(f"Total size of {len(views)} views: {total_size} bytes")
        return total_size

    def get_view_definition(self, view_name: str) -> str | None:
        """Get the SQL definition of a materialized view.

        Args:
            view_name: Name of the view

        Returns:
            SQL definition, or None if view doesn't exist

        Examples:
            >>> definition = mv_manager.get_view_definition("mv_users")
            >>> print(definition)
        """
        view_name = self._sanitize_identifier(view_name)

        sql = """
            SELECT definition
            FROM pg_matviews
            WHERE schemaname = %s AND matviewname = %s
        """

        return self.db.fetch_value(sql, (self.schema, view_name))

    @staticmethod
    def _sanitize_identifier(name: str) -> str:
        """Sanitize an SQL identifier to prevent SQL injection.

        Args:
            name: Identifier to sanitize

        Returns:
            Sanitized identifier

        Raises:
            ValueError: If identifier is invalid
        """
        # Remove quotes if present
        name = name.strip('"')

        # Check for valid identifier pattern
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            raise ValueError(f"Invalid identifier: {name}")

        return name

    def create_index(
        self,
        view_name: str,
        column_names: list[str],
        index_name: str | None = None,
        unique: bool = False,
    ) -> bool:
        """Create an index on a materialized view.

        Args:
            view_name: Name of the view
            column_names: List of column names for the index
            index_name: Optional custom index name
            unique: Whether to create a unique index

        Returns:
            True if successful

        Examples:
            >>> mv_manager.create_index("mv_users", ["user_id"], unique=True)
            >>> mv_manager.create_index("mv_orders", ["customer_id", "order_date"])
        """
        view_name = self._sanitize_identifier(view_name)
        columns = ", ".join(self._sanitize_identifier(col) for col in column_names)

        if index_name is None:
            index_name = f"{view_name}_{'_'.join(column_names)}_idx"

        index_name = self._sanitize_identifier(index_name)
        unique_clause = "UNIQUE" if unique else ""

        sql = f"""
            CREATE {unique_clause} INDEX {index_name}
            ON {self.schema}.{view_name} ({columns})
        """

        logger.info(f"Creating index '{index_name}' on view '{view_name}'")
        self.db.execute(sql)
        logger.info(f"Successfully created index '{index_name}'")
        return True
