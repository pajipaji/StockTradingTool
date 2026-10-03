import backend.core.fetch as fetchmod
from backend.core.fetch import fetch
from backend.core.ratelimit import RateLimiter


def setup_function(_):
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_returns_and_caches():
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        return {"v": calls["n"]}

    a = fetch(fake, source="sina")
    b = fetch(fake, source="sina")
    assert a == b == {"v": 1}
    assert fetch(fake, source="sina", use_cache=False) == {"v": 2}


def test_retries_until_success(monkeypatch):
    monkeypatch.setattr(fetchmod, "RETRY_TIMES", 3)
    monkeypatch.setattr(fetchmod.time, "sleep", lambda s: None)
    state = {"n": 0}
    def flaky():
        state["n"] += 1
        if state["n"] < 2:
            raise ValueError("x")
        return "ok"
    assert fetch(flaky, source="x", use_cache=False) == "ok"
