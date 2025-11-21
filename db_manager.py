"""
Improved Database Manager for CCTV Tool with Connection Pooling
Provides thread-safe database connection management using SQLAlchemy
"""

import pyodbc
import logging
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from contextlib import contextmanager
from urllib.parse import quote_plus

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections with connection pooling for the CCTV Tool
    Thread-safe and optimized for concurrent access
    """

    def __init__(self, use_pooling=True):
        """
        Initialize database connection manager

        Args:
            use_pooling: Whether to use connection pooling (default: True)
        """
        self.use_pooling = use_pooling
        self.engine = None
        self.conn = None  # For backward compatibility
        self._setup_connection()

    def _setup_connection(self):
        """Setup database connection or connection pool"""
        try:
            driver = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')
            server = os.getenv('DB_SERVER')
            database = os.getenv('DB_DATABASE')
            username = os.getenv('DB_USERNAME')
            password = os.getenv('DB_PASSWORD')

            if self.use_pooling:
                # Use SQLAlchemy connection pooling
                conn_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server},1433;"
                    f"DATABASE={database};"
                    f"UID={username};"
                    f"PWD={password};"
                    f"TrustServerCertificate=yes;"
                    f"MARS_Connection=yes;"  # Multiple Active Result Sets
                )

                # Create connection string for SQLAlchemy
                params = quote_plus(conn_str)
                sa_conn_str = f"mssql+pyodbc:///?odbc_connect={params}"

                # Create engine with connection pooling
                self.engine = create_engine(
                    sa_conn_str,
                    pool_size=10,  # Maximum 10 connections in pool
                    max_overflow=20,  # Allow 20 additional connections beyond pool_size
                    pool_timeout=30,  # Wait 30 seconds for connection from pool
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    pool_pre_ping=True,  # Test connections before using
                    echo=False,  # Set to True for SQL debug logging
                )

                # Configure connection to use autocommit
                @event.listens_for(Engine, "connect")
                def set_connection_config(dbapi_conn, connection_record):
                    dbapi_conn.autocommit = True

                # Create a single connection for backward compatibility
                self.conn = self.engine.raw_connection()

                logger.info(f"✓ Database connection pool established (driver: {driver})")
                logger.info(f"  Pool size: 10, Max overflow: 20, Timeout: 30s")

            else:
                # Use direct pyodbc connection (legacy mode)
                conn_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server},1433;"
                    f"DATABASE={database};"
                    f"UID={username};"
                    f"PWD={password};"
                    f"TrustServerCertificate=yes;"
                )

                self.conn = pyodbc.connect(conn_str, autocommit=True)
                logger.info(f"✓ Database connection established (driver: {driver})")

        except Exception as e:
            logger.error(f"Failed to setup database connection: {e}")
            self.engine = None
            self.conn = None
            raise

    @contextmanager
    def get_connection(self):
        """
        Context manager to get a connection from the pool

        Usage:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
        """
        if self.use_pooling and self.engine:
            conn = self.engine.raw_connection()
            try:
                yield conn
            finally:
                conn.close()  # Return to pool
        else:
            # Legacy mode - use shared connection
            yield self.conn

    @contextmanager
    def get_cursor(self):
        """
        Context manager to get a cursor with automatic cleanup

        Usage:
            with db_manager.get_cursor() as cursor:
                cursor.execute("SELECT ...")
                results = cursor.fetchall()
        """
        if self.use_pooling and self.engine:
            conn = self.engine.raw_connection()
            cursor = None
            try:
                cursor = conn.cursor()
                yield cursor
            finally:
                if cursor:
                    cursor.close()
                conn.close()  # Return to pool
        else:
            # Legacy mode - create cursor from shared connection
            cursor = self.conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """
        Execute a query with automatic connection management

        Args:
            query: SQL query string
            params: Query parameters (optional)
            fetch_one: Return single row (default: False)
            fetch_all: Return all rows (default: False)

        Returns:
            Query results or None
        """
        try:
            with self.get_cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            raise

    def reconnect(self):
        """Reconnect to database if connection is lost"""
        try:
            if self.conn:
                self.conn.close()
        except:
            pass

        if self.engine:
            self.engine.dispose()

        self._setup_connection()
        logger.info("Database reconnected")

    def close(self):
        """Close database connections"""
        try:
            if self.conn:
                self.conn.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")

        try:
            if self.engine:
                self.engine.dispose()
                logger.info("Connection pool disposed")
        except Exception as e:
            logger.error(f"Error disposing connection pool: {e}")

    def get_pool_status(self):
        """Get connection pool statistics"""
        if self.use_pooling and self.engine:
            pool_obj = self.engine.pool
            return {
                'size': pool_obj.size(),
                'checked_in': pool_obj.checkedin(),
                'checked_out': pool_obj.checkedout(),
                'overflow': pool_obj.overflow(),
                'total': pool_obj.size() + pool_obj.overflow()
            }
        return None

    def __del__(self):
        """Cleanup on deletion"""
        self.close()


# For backward compatibility, create a singleton instance
_db_manager_instance = None


def get_db_manager(use_pooling=True):
    """
    Get or create the DatabaseManager singleton instance

    Args:
        use_pooling: Whether to use connection pooling (default: True)

    Returns:
        DatabaseManager instance
    """
    global _db_manager_instance
    if _db_manager_instance is None:
        _db_manager_instance = DatabaseManager(use_pooling=use_pooling)
    return _db_manager_instance
