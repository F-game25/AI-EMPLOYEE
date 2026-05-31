"""
PostgreSQL Async Connection Pool for Python Backend

Manages a reusable pool of async database connections with:
- Connection pooling (min/max size, query limits)
- Automatic reconnection on errors
- Query timeout protection
- Connection lifecycle management

Usage:
    pool = await DatabasePool.init()
    result = await pool.fetchrow('SELECT * FROM deals WHERE deal_id=$1', deal_id)
    await pool.close()
"""

import asyncio
import asyncpg
import logging
import os
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)


class DatabasePool:
    """Singleton PostgreSQL async connection pool."""

    _pool: Optional[asyncpg.Pool] = None
    _initialized = False

    @classmethod
    async def init(cls) -> 'DatabasePool':
        """Initialize or return existing connection pool.

        Raises RuntimeError if connection fails and REQUIRE_POSTGRES=1
        """
        if cls._pool is not None:
            return cls

        # Read configuration from environment
        host = os.getenv('DATABASE_HOST', 'localhost')
        port = int(os.getenv('DATABASE_PORT', 5432))
        database = os.getenv('DATABASE_NAME', 'ai_employee')
        user = os.getenv('DATABASE_USER', 'ai_user')
        password = os.getenv('DATABASE_PASSWORD')
        ssl = os.getenv('DATABASE_SSL', 'prefer')

        pool_min = int(os.getenv('DATABASE_POOL_MIN', 5))
        pool_max = int(os.getenv('DATABASE_POOL_MAX', 20))

        logger.info(
            f"Initializing PostgreSQL pool: {user}@{host}:{port}/{database} "
            f"(min={pool_min}, max={pool_max})"
        )

        try:
            cls._pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,

                # Pool sizing
                min_size=pool_min,
                max_size=pool_max,

                # Connection lifecycle
                max_queries=50000,  # Recycle connection after 50k queries
                max_inactive_connection_lifetime=300,  # Reuse after 5min idle

                # Timeouts
                timeout=10.0,  # Wait max 10s for available connection
                command_timeout=10.0,  # Query timeout

                # SSL
                ssl=ssl if ssl != 'prefer' else 'prefer',
                server_settings={
                    'application_name': 'ai-employee-backend',
                    'jit': 'off',  # Disable JIT for consistent perf on short queries
                },

                # Connection initialization
                init=cls._init_connection,

                # Record format (return dicts, not tuples)
                record_class=dict,
            )

            cls._initialized = True
            logger.info("✓ PostgreSQL pool initialized successfully")
            return cls

        except Exception as e:
            logger.error(f"✗ Failed to initialize PostgreSQL pool: {e}")

            if os.getenv('REQUIRE_POSTGRES') == '1':
                raise RuntimeError(f"Database unavailable and REQUIRE_POSTGRES=1: {e}")

            logger.warning("Continuing without database (dev mode)")
            cls._initialized = False
            return cls

    @classmethod
    async def _init_connection(cls, conn: asyncpg.Connection) -> None:
        """Initialize each new connection (timezone, etc.)."""
        await conn.execute("SET timezone = 'UTC'")
        await conn.execute("SET search_path TO public")

    @classmethod
    async def execute(
        cls,
        query: str,
        *args,
        fetch_one: bool = False,
        fetch_val: bool = False,
        timeout: float = 10.0,
    ) -> Any:
        """Execute a query with optional timeout.

        Args:
            query: SQL query string (use $1, $2 for parameters)
            *args: Query parameters
            fetch_one: Return single row (dict) instead of list
            fetch_val: Return single value instead of row
            timeout: Query timeout in seconds

        Returns:
            List of dicts, single dict, single value, or None

        Raises:
            RuntimeError: If pool not initialized and fallback disabled
            asyncpg.Error: Database errors
        """
        if cls._pool is None:
            raise RuntimeError("Database pool not initialized. Call init() first.")

        try:
            async with cls._pool.acquire() as conn:
                async with conn.transaction():
                    if fetch_val:
                        return await asyncio.wait_for(
                            conn.fetchval(query, *args),
                            timeout=timeout
                        )
                    elif fetch_one:
                        return await asyncio.wait_for(
                            conn.fetchrow(query, *args),
                            timeout=timeout
                        )
                    else:
                        return await asyncio.wait_for(
                            conn.fetch(query, *args),
                            timeout=timeout
                        )

        except asyncio.TimeoutError:
            logger.error(f"Query timeout ({timeout}s): {query[:100]}")
            raise
        except asyncpg.Error as e:
            logger.error(f"Database error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            raise

    @classmethod
    async def transaction(cls, operations: List[tuple]) -> None:
        """Execute multiple operations in a single transaction.

        Args:
            operations: List of (query, *args) tuples

        Example:
            await pool.transaction([
                ('INSERT INTO deals VALUES ($1, $2)', deal_id, tenant_id),
                ('INSERT INTO audit_logs VALUES ($1, $2)', log_id, tenant_id),
            ])
        """
        if cls._pool is None:
            raise RuntimeError("Database pool not initialized. Call init() first.")

        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                for operation in operations:
                    query = operation[0]
                    args = operation[1:]
                    await conn.execute(query, *args)

    @classmethod
    async def health_check(cls) -> Dict[str, Any]:
        """Check pool health.

        Returns:
            {
                'healthy': bool,
                'poolStats': {'totalSize': int, 'freeSize': int, 'freeConnections': list},
                'queryTime': float (ms),
                'error': str or None
            }
        """
        import time

        if cls._pool is None:
            return {
                'healthy': False,
                'poolStats': None,
                'queryTime': 0,
                'error': 'Pool not initialized',
            }

        start = time.time()
        try:
            # Acquire connection with timeout
            async with asyncio.timeout(5.0):
                async with cls._pool.acquire() as conn:
                    result = await conn.fetchval('SELECT NOW()')

            elapsed = (time.time() - start) * 1000

            return {
                'healthy': True,
                'poolStats': {
                    'totalSize': cls._pool.get_size(),
                    'freeSize': cls._pool.get_idle_size(),
                    'minSize': cls._pool.get_min_size(),
                    'maxSize': cls._pool.get_max_size(),
                },
                'queryTime': elapsed,
                'timestamp': result,
                'error': None,
            }

        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            return {
                'healthy': False,
                'poolStats': {
                    'totalSize': cls._pool.get_size(),
                    'freeSize': cls._pool.get_idle_size(),
                    'minSize': cls._pool.get_min_size(),
                    'maxSize': cls._pool.get_max_size(),
                },
                'queryTime': elapsed,
                'timestamp': None,
                'error': 'Health check timeout',
            }

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return {
                'healthy': False,
                'poolStats': {
                    'totalSize': cls._pool.get_size(),
                    'freeSize': cls._pool.get_idle_size(),
                    'minSize': cls._pool.get_min_size(),
                    'maxSize': cls._pool.get_max_size(),
                },
                'queryTime': elapsed,
                'timestamp': None,
                'error': str(e),
            }

    @classmethod
    async def close(cls) -> None:
        """Close all connections and terminate pool."""
        if cls._pool is None:
            return

        try:
            await cls._pool.close()
            cls._pool = None
            cls._initialized = False
            logger.info("PostgreSQL pool closed")
        except Exception as e:
            logger.error(f"Error closing pool: {e}")
            raise

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if pool is initialized and ready."""
        return cls._initialized and cls._pool is not None

    @classmethod
    def get_stats(cls) -> Optional[Dict[str, Any]]:
        """Get current pool statistics."""
        if cls._pool is None:
            return None

        return {
            'totalSize': cls._pool.get_size(),
            'freeSize': cls._pool.get_idle_size(),
            'minSize': cls._pool.get_min_size(),
            'maxSize': cls._pool.get_max_size(),
            'queueSize': cls._pool.get_size() - cls._pool.get_idle_size(),
        }


# Convenience functions for common operations
async def fetch_one(query: str, *args) -> Optional[Dict[str, Any]]:
    """Fetch single row as dict."""
    return await DatabasePool.execute(query, *args, fetch_one=True)


async def fetch_all(query: str, *args) -> List[Dict[str, Any]]:
    """Fetch all rows as list of dicts."""
    return await DatabasePool.execute(query, *args)


async def fetch_val(query: str, *args) -> Any:
    """Fetch single value."""
    return await DatabasePool.execute(query, *args, fetch_val=True)


async def execute(query: str, *args) -> None:
    """Execute query without returning results."""
    await DatabasePool.execute(query, *args)
