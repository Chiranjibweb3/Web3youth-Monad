import asyncio
from loguru import logger
from typing import Any, Callable, Optional, Tuple, Dict
from web3 import AsyncWeb3


def _format_log_prefix(account_index: Optional[int]) -> str:
    """Format log prefix based on account index."""
    return f"[{account_index}] " if account_index is not None else ""


async def make_request_with_retry(
    original_make_request,
    account_index: Optional[int] = None,
    request_timeout: int = 10,
    max_retries: int = 50,
    *args,
    **kwargs
) -> Any:
    """
    Generic RPC request handler with retry logic.
    
    Args:
        original_make_request: The original make_request method from the web3 provider
        account_index: Account index for logging purposes (can be None)
        request_timeout: Timeout for the request in seconds
        max_retries: Maximum number of retry attempts
        args: Positional arguments to pass to the request method
        kwargs: Keyword arguments to pass to the request method
        
    Returns:
        The response from the request
        
    Raises:
        Exception: The last exception encountered after all retries fail
    """
    retries = 0
    last_exception = None
    log_prefix = _format_log_prefix(account_index)
    
    while retries <= max_retries:
        try:
            # Apply timeout to the request using asyncio.wait_for
            return await asyncio.wait_for(
                original_make_request(*args, **kwargs),
                timeout=request_timeout
            )
        except asyncio.TimeoutError as e:
            retries += 1
            last_exception = e
            logger.warning(
                f"{log_prefix}RPC call timed out after {request_timeout}s (attempt {retries}/{max_retries}). "
                f"Retrying immediately..."
            )
            # Add a small delay before retry to avoid overwhelming the RPC server
            await asyncio.sleep(0.1)
        except Exception as e:
            retries += 1
            last_exception = e
            
            # Log the retry attempt with detailed error information
            logger.warning(
                f"{log_prefix}RPC call failed (attempt {retries}/{max_retries}): {str(e)}. "
                f"Retrying immediately..."
            )
            # Add a small delay before retry to avoid overwhelming the RPC server
            await asyncio.sleep(0.1)
        
    logger.error(f"{log_prefix}All {max_retries} retry attempts failed. Last error: {last_exception}")
    raise last_exception


class Web3RetryMiddleware:
    """
    A middleware class that wraps a Web3 provider's make_request method with retry logic.
    This class is designed to be used with a Web3 instance to add retry functionality
    to all RPC calls.
    """
    
    def __init__(
        self, 
        provider, 
        account_index: Optional[int] = None,
        request_timeout: int = 60,
        max_retries: int = 50
    ):
        """
        Initialize the middleware with the provider and retry settings.
        
        Args:
            provider: The Web3 provider to wrap
            account_index: Account index for logging purposes (can be None)
            request_timeout: Timeout for requests in seconds
            max_retries: Maximum number of retry attempts
        """
        self.provider = provider
        self.account_index = account_index
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        
        # Store the original make_request method
        self._original_make_request = provider.make_request
        
        # Replace the provider's make_request with our wrapped version
        provider.make_request = self._make_request_with_retry
    
    async def _make_request_with_retry(self, *args, **kwargs):
        """Wrapper method that calls the generic retry function"""
        return await make_request_with_retry(
            self._original_make_request,
            self.account_index,
            self.request_timeout,
            self.max_retries,
            *args,
            **kwargs
        )


def create_web3_client(
    rpc_url: str,
    account_index: Optional[int] = None,
    proxy: Optional[str] = None,
    request_timeout: int = 60,
    max_retries: int = 50
) -> AsyncWeb3:
    """
    Create a configured AsyncWeb3 client with retry middleware.
    
    Args:
        rpc_url: The RPC endpoint URL
        account_index: Account index for logging purposes (can be None)
        proxy: Optional proxy URL in format 'user:pass@host:port'
        request_timeout: Timeout for requests in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        AsyncWeb3 instance with retry middleware configured
    """
    # Prepare request kwargs
    request_kwargs = {}
    
    # Configure proxy if provided
    if proxy:
        request_kwargs["proxy"] = f"http://{proxy}"
        request_kwargs["ssl"] = False
    
    # Create Web3 instance with AsyncHTTPProvider
    web3 = AsyncWeb3(
        AsyncWeb3.AsyncHTTPProvider(
            endpoint_uri=rpc_url,
            request_kwargs=request_kwargs,
        )
    )
    
    # Apply retry middleware
    Web3RetryMiddleware(
        web3.provider,
        account_index,
        request_timeout=request_timeout,
        max_retries=max_retries
    )
    
    return web3 