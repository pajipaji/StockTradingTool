from backend.core.units import to_yi, pct


def test_to_yi():
    assert to_yi(1_0000_0000) == 1.0
    assert to_yi(5.2e11) == 5200.0
    assert to_yi(None) is None
    assert to_yi("abc") is None


def test_pct():
    assert pct("1.234") == 1.23
    assert pct(None) is None


def test_nan_returns_none():
    assert pct(float("nan")) is None
    assert to_yi(float("nan")) is None
