from concurrent.futures import ThreadPoolExecutor
from typing import Callable

# 2 workers: safe for Render free tier (1 vCPU)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-worker")


def submit(fn: Callable, *args, **kwargs):
    return _executor.submit(fn, *args, **kwargs)


def shutdown(wait: bool = False) -> None:
    _executor.shutdown(wait=wait)
