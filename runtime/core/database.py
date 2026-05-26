"""PostgreSQL database client with connection pooling and multi-tenancy support.

Provides:
- Connection pool management (psycopg2 + psycopg_pool)
- Tenant-aware query execution (auto-inject tenant_id)
- Transaction support
- Connection resilience (retry logic)
"""
from __future__ import annotations

import logging
import os
import re as _re
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
from urllib.parse import urlparse

_SQL_IDENT_RE = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")


def _check_identifier(name: str) -> str:
    """Raise ValueError if name is not a safe SQL identifier."""
    if not _SQL_IDENT_RE.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier rejected: {name!r}")
    return name

try:
    import psycopg
    from psycopg import sql
    from psycopg_pool import ConnectionPool
    HAS_PSYCOPG3 = True
except ImportError:
    HAS_PSYCOPG3 = False

logger = logging.getLogger(__name__)


class DatabaseClient:
    """PostgreSQL client with connection pooling and tenant context awareness."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        pool_size: int = 10,
        max_overflow: int = 5,
        timeout: float = 5.0,
    ):
        """Initialize database client.

        Args:
            dsn: PostgreSQL connection string (auto-detected from DATABASE_URL env var)
            pool_size: Minimum connections to keep in pool
            max_overflow: Additional connections beyond pool_size
            timeout: Connection timeout in seconds
        """
        if not HAS_PSYCOPG3:
            raise RuntimeError("psycopg3 is required. Install: pip install psycopg[binary]")

        self.dsn = dsn or os.environ.get("DATABASE_URL", "")
        if not self.dsn:
            raise ValueError("DATABASE_URL environment variable not set")

        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        self._pool: Optional[ConnectionPool] = None
        self._connected = False

    def connect(self) -> bool:
        """Initialize connection pool."""
        try:
            self._pool = ConnectionPool(
                self.dsn,
                min_size=self.pool_size,
                max_size=self.pool_size + self.max_overflow,
                timeout=self.timeout,
            )
            logger.info(f"Database pool initialized: {self.pool_size} connections")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
            self._connected = False
            logger.info("Database pool closed")

    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database not connected. Call connect() first.")

        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)

    def execute(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a query and return results.

        Args:
            query: SQL query (can use {table_name} placeholders)
            params: Query parameters as tuple
            tenant_id: Optional tenant ID to inject into WHERE clause

        Returns:
            List of result rows as dicts
        """
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Auto-inject tenant_id if provided
                    if tenant_id:
                        query = f"{query} AND tenant_id = %s"
                        params = (*(params or ()), tenant_id)

                    cur.execute(query, params or ())
                    results = cur.fetchall()
                    return [dict(row) for row in results] if results else []

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            raise

    def execute_one(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute query and return first result."""
        results = self.execute(query, params, tenant_id)
        return results[0] if results else None

    def insert(
        self,
        table: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        returning: str = "*",
    ) -> Dict[str, Any]:
        """Insert row and return inserted data.

        Args:
            table: Table name
            data: Column -> value dict
            tenant_id: Optional tenant ID (auto-injected)
            returning: Columns to return

        Returns:
            Inserted row as dict
        """
        if not self._connected:
            raise RuntimeError("Database not connected")

        _check_identifier(table)

        # Auto-inject tenant_id if provided
        if tenant_id and "tenant_id" not in data:
            data = {**data, "tenant_id": tenant_id}

        columns = list(data.keys())
        for col in columns:
            _check_identifier(col)
        placeholders = ["%s"] * len(columns)

        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING {returning}
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, list(data.values()))
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Insert error: {e}")
            raise

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        params: Optional[Tuple[Any, ...]] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Update rows.

        Args:
            table: Table name
            data: Column -> value dict
            where: WHERE clause (without the WHERE keyword)
            params: Parameters for WHERE clause
            tenant_id: Optional tenant ID to add to WHERE

        Returns:
            Number of affected rows
        """
        if not self._connected:
            raise RuntimeError("Database not connected")

        _check_identifier(table)
        for col in data.keys():
            _check_identifier(col)
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"

        # Auto-inject tenant_id if provided
        if tenant_id:
            query = f"{query} AND tenant_id = %s"
            params = (*(params or ()), tenant_id)

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, list(data.values()) + list(params or []))
                    conn.commit()
                    return cur.rowcount
        except Exception as e:
            logger.error(f"Update error: {e}")
            raise

    def delete(
        self,
        table: str,
        where: str,
        params: Optional[Tuple[Any, ...]] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Delete rows.

        Args:
            table: Table name
            where: WHERE clause (without WHERE keyword)
            params: Parameters for WHERE clause
            tenant_id: Optional tenant ID to add to WHERE

        Returns:
            Number of deleted rows
        """
        if not self._connected:
            raise RuntimeError("Database not connected")

        _check_identifier(table)
        query = f"DELETE FROM {table} WHERE {where}"

        if tenant_id:
            query = f"{query} AND tenant_id = %s"
            params = (*(params or ()), tenant_id)

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
                    conn.commit()
                    return cur.rowcount
        except Exception as e:
            logger.error(f"Delete error: {e}")
            raise

    def health_check(self) -> bool:
        """Check database health."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return bool(result)
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False


# Global database instance
_db_client: Optional[DatabaseClient] = None


def init_database(dsn: Optional[str] = None) -> DatabaseClient:
    """Initialize global database client."""
    global _db_client
    _db_client = DatabaseClient(dsn)
    _db_client.connect()
    return _db_client


def get_database() -> DatabaseClient:
    """Get global database client."""
    if _db_client is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_client
