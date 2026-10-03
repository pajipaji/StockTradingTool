from backend.core.ratelimit import RateLimiter


def test_sleeps_when_too_fast():
    now = {"t": 100.0}
    slept = []
    def clock():
        return now["t"]
    def sleeper(seconds):
        slept.append(seconds)
        now["t"] += seconds
    rl = RateLimiter(min_interval=1.0, clock=clock, sleeper=sleeper)
    rl.wait("sina")
    assert slept == []
    now["t"] += 0.3
    rl.wait("sina")
    assert slept and abs(slept[-1] - 0.7) < 1e-6


def test_independent_per_source():
    slept = []
    rl = RateLimiter(min_interval=1.0, clock=lambda: 0.0, sleeper=slept.append)
    rl.wait("a"); rl.wait("b")
    assert slept == []
