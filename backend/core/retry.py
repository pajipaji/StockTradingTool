import functools
import random
import time


def retry(times: int = 3, base_delay: float = 1.0, jitter: float = 0.5,
          exceptions=(Exception,), sleeper=time.sleep, logger=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == times - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
                    if logger is not None:
                        logger.warning("retry %s/%s %s: %s", attempt + 1, times, func.__name__, exc)
                    sleeper(delay)
        return wrapper
    return decorator
