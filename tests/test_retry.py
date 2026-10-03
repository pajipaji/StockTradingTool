import pytest
from backend.core.retry import retry


def test_succeeds_after_failures():
    calls = {"n": 0}
    delays = []

    @retry(times=3, base_delay=1.0, jitter=0.0, sleeper=delays.append)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    assert delays == [1.0, 2.0]


def test_raises_after_exhaustion():
    @retry(times=2, base_delay=0.0, jitter=0.0, sleeper=lambda s: None)
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        always_fail()
