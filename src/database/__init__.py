"""Database management module for PostgreSQL.

This module provides classes for database connection management,
materialized view operations, and schema introspection.

Classes:
    DatabaseConnection: Manages database connections and cursor operations
    DatabaseConnectionPool: Simple connection pooling
    MaterializedViewManager: Create and manage materialized views
    SchemaManager: Query database schema information
    ViewInfo: Information about a materialized view
    TableInfo: Information about a database table
    ColumnInfo: Information about a table column
    IndexInfo: Information about an index

Example:
    >>> from config.settings import Settings
    >>> from src.database import DatabaseConnection, MaterializedViewManager
    >>>
    >>> settings = Settings()
    >>> db = DatabaseConnection(settings.database)
    >>> mv_manager = MaterializedViewManager(db)
    >>>
    >>> # Create a materialized view
    >>> mv_manager.create_view(
    ...     "mv_active_users",
    ...     "SELECT * FROM users WHERE active = true"
    ... )
    >>>
    >>> # List all views
    >>> views = mv_manager.list_views()
    >>> print(f"Found {len(views)} materialized views")
"""

from .connection import DatabaseConnection, DatabaseConnectionPool
from .mv_manager import MaterializedViewManager, ViewInfo
from .schema import ColumnInfo, IndexInfo, SchemaManager, TableInfo, TableStatistics

__all__ = [
    # Connection management
    "DatabaseConnection",
    "DatabaseConnectionPool",
    # Materialized view management
    "MaterializedViewManager",
    "ViewInfo",
    # Schema management
    "SchemaManager",
    "TableInfo",
    "ColumnInfo",
    "IndexInfo",
    "TableStatistics",
]
