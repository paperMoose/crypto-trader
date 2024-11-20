import asyncio
import functools
import logging
from typing import TypeVar, Callable, Any, Tuple, Type
from aiohttp import ClientError, ClientResponse
from .schemas import GeminiAPIError

logger = logging.getLogger(__name__)

T = TypeVar('T')

def should_retry(exception: Exception, response: ClientResponse = None, retry_exceptions: Tuple[Type[Exception], ...] = None) -> bool:
    """
    Determine if the request should be retried based on the exception and response
    
    Args:
        exception: The exception that was raised
        response: The response object if available
        retry_exceptions: Tuple of exception types to retry on
    """
    # Handle Gemini API errors
    if isinstance(exception, GeminiAPIError):
        # Don't retry client errors (4xx)
        return False
        
    # Don't retry successful responses
    if isinstance(response, ClientResponse) and response.status < 500:
        return False
        
    # If specific exceptions are provided, only retry those
    if retry_exceptions:
        return isinstance(exception, retry_exceptions)
        
    # Default retry behavior for common errors
    return isinstance(exception, (
        ClientError,
        ConnectionError,
        TimeoutError,
    ))

def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = None,
):
    """
    Decorator that adds retry logic to async functions
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exception types to retry on
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    response = await func(*args, **kwargs)
                    return response
                except Exception as e:
                    last_exception = e
                    
                    # Get response object if available
                    response = getattr(e, 'response', None)
                    
                    if not should_retry(e, response, exceptions) or attempt + 1 == max_retries:
                        logger.error(
                            f"Final attempt failed for {func.__name__}: {str(e)}"
                            f" Response: {response if response else 'N/A'}"
                        )
                        raise
                    
                    delay = base_delay * (exponential_base ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {str(e)}"
                        f" Response: {response if response else 'N/A'}"
                        f" Retrying in {delay:.1f} seconds..."
                    )
                    await asyncio.sleep(delay)
            
            raise last_exception
            
        return wrapper
    return decorator 