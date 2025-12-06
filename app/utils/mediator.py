import functools
from concurrent.futures import ThreadPoolExecutor


@functools.lru_cache(maxsize=None)
def get_thread_pool_executor(max_workers: int = 5, thread_name_prefix: str = "") -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="")
