import time


class RateLimiter:
    def __init__(self, min_interval: float = 0.8, clock=time.monotonic, sleeper=time.sleep):
        self.min_interval = float(min_interval)
        self._clock = clock
        self._sleep = sleeper
        self._last = {}

    def wait(self, source: str) -> None:
        if self.min_interval <= 0:
            self._last[source] = self._clock()
            return
        now = self._clock()
        last = self._last.get(source)
        if last is not None:
            remaining = self.min_interval - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last[source] = now
