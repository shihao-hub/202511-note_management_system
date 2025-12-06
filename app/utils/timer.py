import asyncio
import functools
import time

from loguru import logger


def print_interval_time(func):
    # 异步函数执行期间可能挂起，而 time.perf_counter() 依然可以准确测量 wall-clock 时间（总耗时）
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                res = await func(*args, **kwargs)
            finally:
                end = time.perf_counter()
                logger.debug(f"the '{func.__name__}' coroutine takes {(end - start) * 1000:.3f} ms")
            return res

        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                res = func(*args, **kwargs)
            finally:
                end = time.perf_counter()
                logger.debug(f"the '{func.__name__}' func takes {(end - start) * 1000:.3f} ms")
            return res

        return sync_wrapper


class IntervalTimer:
    """区间计时器， 但是意义不大

    Usage:
        with IntervalTimer() as timer:
            sleep(0.3)
            print(timer.interval)
            sleep(0.6)
            print(timer.interval)
    """

    def __init__(self, log_enabled:bool=True):
        self._log_enabled = log_enabled
        self._status = "init"

    @property
    def interval(self):
        """获取从进来到出去"""
        if self._status in ["init", "exit"]:
            raise Exception(f"IntervalTimer(status='{self._status}') 实例需要在 with 语句中使用")
        return time.time() - self._start_time # perf_counter

    def print(self, prefix: str = "", suffix: str = ""):
        # enabled 参数用于控制是否真的打印内容，主要目的是不改动旧有代码，让代码自包含一些信息
        if not self._log_enabled:
            return

        if prefix:
            if not prefix.startswith("["):
                prefix = "[" + prefix
            if not prefix.endswith("]"):
                prefix = prefix + "]"

        if suffix and not suffix.startswith("-"):
            suffix = " - " + suffix.lstrip()
        logger.debug(f"{prefix} 耗时：{self.interval * 1000:.3f} ms / {self.interval:.6f} s{suffix}")

    def __enter__(self):
        self._status = "enter"
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._status = "exit"
        return False
