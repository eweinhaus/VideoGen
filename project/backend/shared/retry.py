"""
Retry logic with exponential backoff.

Decorator for automatic retry with exponential backoff on retryable errors.
"""

import asyncio
import functools
from typing import Callable, Type, Tuple, Any, TypeVar

from shared.errors import RetryableError, RateLimitError
from shared.logging import get_logger

T = TypeVar("T")
logger = get_logger("retry")


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: int = 2,
    retryable_exceptions: Tuple[Type[Exception], ...] = (RetryableError, RateLimitError)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 2)
        retryable_exceptions: Tuple of exception types to retry on (default: RetryableError)
    
    Returns:
        Decorated function
    
    Example:
        @retry_with_backoff(max_attempts=3, base_delay=2)
        async def call_api():
            # Will retry on RetryableError
            response = await api_client.call(...)
            return response
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                last_exception = None
                
                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            # Exponential backoff: 2s, 4s, 8s, etc.
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                f"Retry attempt {attempt + 1}/{max_attempts} for {func.__name__} "
                                f"after {delay}s delay",
                                extra={"error": str(e), "attempt": attempt + 1}
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"All {max_attempts} retry attempts failed for {func.__name__}",
                                extra={"error": str(e)}
                            )
                    except Exception as e:
                        # Don't retry on non-retryable exceptions
                        logger.error(
                            f"Non-retryable error in {func.__name__}: {str(e)}",
                            extra={"error": str(e)}
                        )
                        raise
                
                # All retries failed, raise last exception
                if last_exception:
                    raise last_exception
                raise RuntimeError(f"Function {func.__name__} failed after {max_attempts} attempts")
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                last_exception = None
                
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            # Exponential backoff: 2s, 4s, 8s, etc.
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                f"Retry attempt {attempt + 1}/{max_attempts} for {func.__name__} "
                                f"after {delay}s delay",
                                extra={"error": str(e), "attempt": attempt + 1}
                            )
                            import time
                            time.sleep(delay)
                        else:
                            logger.error(
                                f"All {max_attempts} retry attempts failed for {func.__name__}",
                                extra={"error": str(e)}
                            )
                    except Exception as e:
                        # Don't retry on non-retryable exceptions
                        logger.error(
                            f"Non-retryable error in {func.__name__}: {str(e)}",
                            extra={"error": str(e)}
                        )
                        raise
                
                # All retries failed, raise last exception
                if last_exception:
                    raise last_exception
                raise RuntimeError(f"Function {func.__name__} failed after {max_attempts} attempts")
            
            return sync_wrapper
    
    return decorator
