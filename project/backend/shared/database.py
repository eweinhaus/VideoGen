"""
Database client.

Supabase PostgreSQL client with connection pooling and query utilities.
"""

import asyncio
from typing import Optional, Any, Callable
from supabase import create_client, Client
from shared.config import settings
from shared.errors import RetryableError, ConfigError


class DatabaseClient:
    """Supabase database client wrapper with connection pooling and retry logic."""
    
    def __init__(self):
        """Initialize database client."""
        try:
            self.client: Client = create_client(
                settings.supabase_url,
                settings.supabase_service_key
            )
        except Exception as e:
            raise ConfigError(f"Failed to initialize database client: {str(e)}") from e
    
    async def _execute_sync(self, func: Callable[[], Any], max_attempts: int = 3) -> Any:
        """
        Execute a synchronous Supabase operation in an async context.
        
        Args:
            func: Synchronous function to execute
            max_attempts: Maximum number of retry attempts
            
        Returns:
            Function result
            
        Raises:
            RetryableError: If operation fails after all retries
        """
        last_error = None
        for attempt in range(max_attempts):
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, func)
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    delay = 2 ** (attempt + 1)
                    await asyncio.sleep(delay)
                else:
                    raise RetryableError(
                        f"Database operation failed after {max_attempts} attempts: {str(e)}"
                    ) from e
        
        if last_error:
            raise RetryableError(f"Database operation failed: {str(last_error)}") from last_error
    
    def table(self, table_name: str):
        """
        Get a table query builder with async execution support.
        
        Args:
            table_name: Name of the table
            
        Returns:
            AsyncTableQueryBuilder wrapper
        """
        return AsyncTableQueryBuilder(self, table_name)
    
    async def health_check(self) -> bool:
        """
        Check database connection health.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            await self._execute_sync(
                lambda: self.client.table("jobs").select("id").limit(1).execute()
            )
            return True
        except Exception:
            return False
    
    async def execute_query(self, query_func: Callable[[], Any], max_attempts: int = 3) -> Any:
        """
        Execute a query with retry logic.
        
        Args:
            query_func: Function that returns a query result
            max_attempts: Maximum number of retry attempts
            
        Returns:
            Query result
            
        Raises:
            RetryableError: If query fails after all retries
        """
        return await self._execute_sync(query_func, max_attempts)
    
    def transaction(self):
        """
        Create a transaction context manager.
        
        Note: Supabase uses PostgREST which doesn't support traditional transactions.
        This is a placeholder for application-level transaction handling.
        For atomic operations, use RPC functions or handle at application level.
        
        Returns:
            Context manager for transaction-like operations
        """
        from contextlib import contextmanager
        
        @contextmanager
        def _transaction():
            try:
                yield self.client
            except Exception as e:
                # Rollback would be handled at application level
                raise
        
        return _transaction()
    
    async def close(self):
        """Close database connections (no-op for Supabase client)."""
        # Supabase client doesn't require explicit cleanup
        pass


class AsyncTableQueryBuilder:
    """Async wrapper for Supabase table query builder."""
    
    def __init__(self, db_client: DatabaseClient, table_name: str):
        """Initialize async table query builder."""
        self.db_client = db_client
        self.table_name = table_name
        self._query_builder = db_client.client.table(table_name)
    
    def select(self, *args, **kwargs):
        """Chain select operation."""
        self._query_builder = self._query_builder.select(*args, **kwargs)
        return self
    
    def insert(self, *args, **kwargs):
        """Chain insert operation."""
        self._query_builder = self._query_builder.insert(*args, **kwargs)
        return self
    
    def update(self, *args, **kwargs):
        """Chain update operation."""
        self._query_builder = self._query_builder.update(*args, **kwargs)
        return self
    
    def delete(self, *args, **kwargs):
        """Chain delete operation."""
        self._query_builder = self._query_builder.delete(*args, **kwargs)
        return self
    
    def eq(self, *args, **kwargs):
        """Chain eq filter."""
        self._query_builder = self._query_builder.eq(*args, **kwargs)
        return self
    
    def gte(self, *args, **kwargs):
        """Chain gte (greater than or equal) filter."""
        self._query_builder = self._query_builder.gte(*args, **kwargs)
        return self
    
    def gt(self, *args, **kwargs):
        """Chain gt (greater than) filter."""
        self._query_builder = self._query_builder.gt(*args, **kwargs)
        return self
    
    def lte(self, *args, **kwargs):
        """Chain lte (less than or equal) filter."""
        self._query_builder = self._query_builder.lte(*args, **kwargs)
        return self
    
    def lt(self, *args, **kwargs):
        """Chain lt (less than) filter."""
        self._query_builder = self._query_builder.lt(*args, **kwargs)
        return self
    
    def limit(self, *args, **kwargs):
        """Chain limit operation."""
        self._query_builder = self._query_builder.limit(*args, **kwargs)
        return self
    
    def order(self, *args, **kwargs):
        """Chain order operation."""
        self._query_builder = self._query_builder.order(*args, **kwargs)
        return self
    
    def range(self, *args, **kwargs):
        """Chain range operation (for pagination: range(offset, offset + limit - 1))."""
        self._query_builder = self._query_builder.range(*args, **kwargs)
        return self
    
    def single(self):
        """
        Chain single operation (returns single result instead of array).
        
        Note: This method may not be available on all query builder types.
        Use limit(1) as a fallback if this raises AttributeError.
        """
        try:
            # Check if underlying query builder supports single()
            if not hasattr(self._query_builder, 'single'):
                available_methods = [m for m in dir(self._query_builder) if not m.startswith('_')]
                raise AttributeError(
                    f"Underlying query builder does not support 'single()' method. "
                    f"Available methods: {', '.join(available_methods[:15])}. "
                    f"Query builder type: {type(self._query_builder)}. "
                    f"Use limit(1) instead of single() as a fallback."
                )
            self._query_builder = self._query_builder.single()
            return self
        except AttributeError as e:
            # Re-raise with more context
            raise AttributeError(
                f"AsyncTableQueryBuilder.single() failed: {str(e)}. "
                f"Table: {self.table_name}, Builder type: {type(self._query_builder)}. "
                f"Use limit(1) instead of single() as a fallback."
            ) from e
    
    async def execute(self, max_attempts: int = 3) -> Any:
        """
        Execute the query asynchronously.
        
        Args:
            max_attempts: Maximum number of retry attempts
            
        Returns:
            Query result
        """
        query_builder = self._query_builder
        return await self.db_client._execute_sync(
            lambda: query_builder.execute(),
            max_attempts
        )


# Singleton instance
db = DatabaseClient()
