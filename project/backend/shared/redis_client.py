"""
Redis client.

Redis connection and caching utilities.
"""

import json
from typing import Optional, Any
import redis.asyncio as aioredis
from shared.config import settings
from shared.errors import RetryableError, ConfigError


class RedisClient:
    """Async Redis client with connection pooling and JSON support."""
    
    def __init__(self):
        """Initialize Redis client."""
        try:
            self.client: aioredis.Redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=False  # We'll handle encoding ourselves
            )
            self.prefix = "videogen:cache:"
        except Exception as e:
            raise ConfigError(f"Failed to initialize Redis client: {str(e)}") from e
    
    def _prefix_key(self, key: str) -> str:
        """Add namespace prefix to key."""
        return f"{self.prefix}{key}"
    
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None
    ) -> bool:
        """
        Set a string value in Redis.
        
        Args:
            key: Cache key
            value: String value to store
            ex: Expiration time in seconds (optional)
            
        Returns:
            True if successful
        """
        try:
            prefixed_key = self._prefix_key(key)
            await self.client.set(prefixed_key, value.encode("utf-8"), ex=ex)
            return True
        except Exception as e:
            raise RetryableError(f"Failed to set Redis key: {str(e)}") from e
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get a string value from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            String value or None if not found
        """
        try:
            prefixed_key = self._prefix_key(key)
            result = await self.client.get(prefixed_key)
            if result is None:
                return None
            return result.decode("utf-8")
        except Exception as e:
            raise RetryableError(f"Failed to get Redis key: {str(e)}") from e
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key from Redis.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was deleted, False if it didn't exist
        """
        try:
            prefixed_key = self._prefix_key(key)
            result = await self.client.delete(prefixed_key)
            return result > 0
        except Exception as e:
            raise RetryableError(f"Failed to delete Redis key: {str(e)}") from e
    
    async def set_json(
        self,
        key: str,
        data: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a JSON-serialized value in Redis.
        
        Args:
            key: Cache key
            data: Python object to serialize and store
            ttl: Time to live in seconds (optional)
            
        Returns:
            True if successful
        """
        try:
            json_str = json.dumps(data, default=str)  # default=str handles datetime, UUID, etc.
            return await self.set(key, json_str, ex=ttl)
        except Exception as e:
            raise RetryableError(f"Failed to set JSON in Redis: {str(e)}") from e
    
    async def get_json(self, key: str) -> Optional[Any]:
        """
        Get and deserialize a JSON value from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            Deserialized Python object or None if not found
        """
        try:
            json_str = await self.get(key)
            if json_str is None:
                return None
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise RetryableError(f"Failed to decode JSON from Redis: {str(e)}") from e
        except Exception as e:
            raise RetryableError(f"Failed to get JSON from Redis: {str(e)}") from e
    
    async def health_check(self) -> bool:
        """
        Check Redis connection health.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
    
    async def close(self):
        """Close Redis connection."""
        await self.client.close()


# Singleton instance
redis_client = RedisClient()

# Alias for convenience
redis = redis_client
