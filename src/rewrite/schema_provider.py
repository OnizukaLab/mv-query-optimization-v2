"""Schema provider for dynamic schema information retrieval.

This module provides SchemaProvider class that dynamically fetches
schema information from PostgreSQL database, including table columns,
foreign key relationships, and primary keys.
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ForeignKeyRelation:
    """Foreign key relationship information.
    
    Attributes:
        from_table: Source table name
        from_column: Source column name
        to_table: Target table name
        to_column: Target column name
        constraint_name: Foreign key constraint name
    """
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    constraint_name: str


class SchemaProvider:
    """PostgreSQL schema information provider.
    
    This class dynamically fetches schema information from a PostgreSQL
    database, including table columns, foreign key relationships, and
    primary keys. Results are cached to minimize database queries.
    
    Attributes:
        db_config: Database connection configuration
        _column_cache: Cache of table columns
        _fk_cache: Cache of foreign key relationships
        _pk_cache: Cache of primary keys
    """

    def __init__(self, db_config: dict | None = None):
        """Initialize SchemaProvider.
        
        Args:
            db_config: Database configuration dict with keys:
                - host: Database host
                - port: Database port
                - database: Database name
                - user: Database user
                - password: Database password
                If None, will attempt to use environment variables or defaults.
        """
        self.db_config = db_config or self._get_default_config()
        self._column_cache: dict[str, list[str]] = {}
        self._fk_cache: dict[tuple[str, str], list[ForeignKeyRelation]] = {}
        self._pk_cache: dict[str, list[str]] = {}
        self._connection = None

    def _get_default_config(self) -> dict:
        """Get default database configuration from environment or settings.
        
        Returns:
            Database configuration dict
        """
        import os
        
        return {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "imdb"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
        }

    def _get_connection(self):
        """Get database connection (lazily initialized).
        
        Returns:
            psycopg2 connection object
            
        Raises:
            ImportError: If psycopg2 is not installed
            Exception: If connection fails
        """
        if self._connection is not None:
            return self._connection
        
        try:
            import psycopg2
        except ImportError:
            logger.warning("psycopg2 not installed, SchemaProvider will use fallback")
            raise ImportError(
                "psycopg2 is required for SchemaProvider. "
                "Install it with: pip install psycopg2-binary"
            )
        
        try:
            self._connection = psycopg2.connect(**self.db_config)
            logger.info(f"Connected to database: {self.db_config['database']}")
            return self._connection
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def get_table_columns(self, table_name: str, use_cache: bool = True) -> list[str]:
        """Get column names for a table.
        
        Args:
            table_name: Table name
            use_cache: Whether to use cached results (default: True)
            
        Returns:
            List of column names in order
            
        Raises:
            Exception: If query fails
        """
        # Check cache first
        if use_cache and table_name in self._column_cache:
            return self._column_cache[table_name]
        
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            query = """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position;
            """
            
            cur.execute(query, (table_name,))
            columns = [row[0] for row in cur.fetchall()]
            cur.close()
            
            # Cache the result
            self._column_cache[table_name] = columns
            
            logger.debug(f"Retrieved {len(columns)} columns for table {table_name}")
            return columns
            
        except ImportError:
            # Fallback to static schema
            logger.warning(f"Using fallback schema for table {table_name}")
            from .schema import get_table_columns
            try:
                columns = get_table_columns(table_name)
                self._column_cache[table_name] = columns
                return columns
            except KeyError:
                logger.error(f"Table {table_name} not found in fallback schema")
                return []
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            # Try fallback
            try:
                from .schema import get_table_columns
                return get_table_columns(table_name)
            except:
                return []

    def get_foreign_key_relations(
        self,
        from_tables: list[str],
        to_tables: list[str],
        use_cache: bool = True,
    ) -> list[ForeignKeyRelation]:
        """Get foreign key relationships between table sets.
        
        Args:
            from_tables: List of source table names
            to_tables: List of target table names
            use_cache: Whether to use cached results (default: True)
            
        Returns:
            List of ForeignKeyRelation objects
        """
        # Create cache key
        cache_key = (tuple(sorted(from_tables)), tuple(sorted(to_tables)))
        
        # Check cache
        if use_cache and cache_key in self._fk_cache:
            return self._fk_cache[cache_key]
        
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            query = """
                SELECT
                    kcu1.table_name AS from_table,
                    kcu1.column_name AS from_column,
                    kcu2.table_name AS to_table,
                    kcu2.column_name AS to_column,
                    tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu1
                    ON tc.constraint_name = kcu1.constraint_name
                    AND tc.table_schema = kcu1.table_schema
                JOIN information_schema.referential_constraints rc
                    ON tc.constraint_name = rc.constraint_name
                    AND tc.table_schema = rc.constraint_schema
                JOIN information_schema.key_column_usage kcu2
                    ON rc.unique_constraint_name = kcu2.constraint_name
                    AND rc.unique_constraint_schema = kcu2.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND kcu1.table_name = ANY(%s)
                    AND kcu2.table_name = ANY(%s);
            """
            
            cur.execute(query, (from_tables, to_tables))
            
            fk_relations = []
            for row in cur.fetchall():
                fk_relations.append(ForeignKeyRelation(
                    from_table=row[0],
                    from_column=row[1],
                    to_table=row[2],
                    to_column=row[3],
                    constraint_name=row[4]
                ))
            
            cur.close()
            
            # Cache the result
            self._fk_cache[cache_key] = fk_relations
            
            logger.debug(
                f"Retrieved {len(fk_relations)} FK relations between "
                f"{from_tables} and {to_tables}"
            )
            return fk_relations
            
        except ImportError:
            logger.warning("psycopg2 not available, cannot fetch FK relations")
            return []
        except Exception as e:
            logger.error(f"Error fetching FK relations: {e}")
            return []

    def get_primary_key(
        self,
        table_name: str,
        use_cache: bool = True
    ) -> Optional[list[str]]:
        """Get primary key columns for a table.
        
        Args:
            table_name: Table name
            use_cache: Whether to use cached results (default: True)
            
        Returns:
            List of primary key column names, or None if no PK found
        """
        # Check cache
        if use_cache and table_name in self._pk_cache:
            return self._pk_cache[table_name]
        
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            query = """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = 'public'
                    AND tc.table_name = %s
                ORDER BY kcu.ordinal_position;
            """
            
            cur.execute(query, (table_name,))
            pk_columns = [row[0] for row in cur.fetchall()]
            cur.close()
            
            # Cache the result
            result = pk_columns if pk_columns else None
            self._pk_cache[table_name] = result
            
            logger.debug(f"Retrieved PK for {table_name}: {result}")
            return result
            
        except ImportError:
            logger.warning("psycopg2 not available, cannot fetch PK")
            return None
        except Exception as e:
            logger.error(f"Error fetching PK for {table_name}: {e}")
            return None

    def get_all_tables(self, schema: str = 'public') -> list[str]:
        """Get list of all tables in schema.
        
        Args:
            schema: Schema name (default: 'public')
            
        Returns:
            List of table names
        """
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """
            
            cur.execute(query, (schema,))
            tables = [row[0] for row in cur.fetchall()]
            cur.close()
            
            logger.debug(f"Retrieved {len(tables)} tables from schema {schema}")
            return tables
            
        except ImportError:
            logger.warning("Using fallback schema list")
            from .schema import IMDB_SCHEMA
            return list(IMDB_SCHEMA.keys())
        except Exception as e:
            logger.error(f"Error fetching tables: {e}")
            return []

    def clear_cache(self):
        """Clear all cached data."""
        self._column_cache.clear()
        self._fk_cache.clear()
        self._pk_cache.clear()
        logger.info("Schema cache cleared")

    def close(self):
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
