import os
import time

from backend.core.ratelimit import RateLimiter
from backend.core.retry import retry

LIMITER = RateLimiter(float(os.environ.get("DASHBOARD_MIN_INTERVAL", "0.8")))
RETRY_TIMES = int(os.environ.get("DASHBOARD_RETRY_TIMES", "3"))
_CACHE = {}


def reset_cache() -> None:
    _CACHE.clear()


def _key(fn, args, kwargs):
    return (fn, args, tuple(sorted(kwargs.items())))


def fetch(fn, *args, source: str, use_cache: bool = True, **kwargs):
    key = _key(fn, args, kwargs)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    LIMITER.wait(source)
    runner = retry(times=RETRY_TIMES, base_delay=1.0, jitter=0.5, sleeper=time.sleep)(fn)
    result = runner(*args, **kwargs)
    if use_cache:
        _CACHE[key] = result
    return result
