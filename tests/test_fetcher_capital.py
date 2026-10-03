import pandas as pd
import pytest

import backend.fetchers.capital as mod
from backend.fetchers.capital import fetch_capital


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_capital_partial(monkeypatch):
    mf = pd.DataFrame([{"日期": "2026-09-30", "主力净流入-净额": 3.5e10}])
    sse = pd.DataFrame([{"信用交易日期": "20260930", "融资融券余额": 1.9e12}])

    def szse():
        raise RuntimeError("szse down")

    monkeypatch.setattr(mod.ak, "stock_market_fund_flow", lambda: mf)
    monkeypatch.setattr(mod.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(mod.ak, "stock_margin_szse", szse)

    out = fetch_capital()
    assert out["main_net_inflow"] == 350.0
    assert out["margin_total"] is not None
    assert any("深" in n for n in out["notes"])


def test_margin_history(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache(); fetchmod.LIMITER = RateLimiter(min_interval=0.0)
    import backend.fetchers.capital as cap

    def boom():
        raise RuntimeError("blocked")
    sse = pd.DataFrame([
        {"信用交易日期": "20260929", "融资融券余额": 1.90e12},
        {"信用交易日期": "20260930", "融资融券余额": 1.91e12},
    ])
    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)

    out = cap.fetch_capital()
    assert len(out["margin_history"]) == 2
    assert out["margin_history"][-1]["balance"] == 19100.0
    assert out["margin_total"] == 19100.0


def test_margin_history_descending(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache(); fetchmod.LIMITER = RateLimiter(min_interval=0.0)
    import backend.fetchers.capital as cap

    def boom():
        raise RuntimeError("blocked")
    sse = pd.DataFrame([
        {"信用交易日期": "20260930", "融资融券余额": 1.93e12},
        {"信用交易日期": "20260929", "融资融券余额": 1.92e12},
        {"信用交易日期": "20260928", "融资融券余额": 1.91e12},
    ])
    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)

    out = cap.fetch_capital()
    assert out["margin_total"] == 19300.0
    assert out["margin_history"][0]["date"] == "20260928"
    assert out["margin_history"][-1]["date"] == "20260930"
    assert out["margin_history"][-1]["balance"] == 19300.0


def test_margin_sse_requests_recent_range(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache(); fetchmod.LIMITER = RateLimiter(min_interval=0.0)
    import backend.fetchers.capital as cap
    from datetime import date, timedelta

    calls = {}
    sse = pd.DataFrame([{"信用交易日期": "20260930", "融资融券余额": 1.9e12}])

    def boom():
        raise RuntimeError("blocked")

    def fake_sse(**k):
        calls.update(k)
        return sse

    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", fake_sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)

    cap.fetch_capital()
    today = date.today()
    assert calls.get("end_date") == today.strftime("%Y%m%d")
    assert calls.get("start_date") == (today - timedelta(days=60)).strftime("%Y%m%d")
