import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar, Any
from functools import partial

# Centralized thread pool for database operations
# Adjust max_workers based on DB connection pool limits (currently 10-20)
db_thread_pool = ThreadPoolExecutor(max_workers=20, thread_name_prefix="db_sync")

T = TypeVar("T")

async def run_in_db_pool(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Run a synchronous blocking function in the database thread pool.
    
    Usage:
        result = await run_in_db_pool(sync_function, arg1, arg2, kwarg1=value)
        
    Note: kwargs are handled via partial because run_in_executor doesn't support them directly.
    """
    loop = asyncio.get_event_loop()
    
    if kwargs:
        func = partial(func, **kwargs)
        
    return await loop.run_in_executor(
        db_thread_pool,
        func,
        *args
    )
