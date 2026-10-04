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
    monkeypatch.setattr(fetchmod, "RETRY_TIMES", 1)


def test_fetch_capital_partial(monkeypatch):
    mf = pd.DataFrame([{"日期": "2026-09-30", "主力净流入-净额": 3.5e10}])
    sse = pd.DataFrame([{"信用交易日期": "20260930", "融资融券余额": 1.9e12}])

    def szse():
        raise RuntimeError("szse down")

    monkeypatch.setattr(mod.ak, "stock_market_fund_flow", lambda: mf)
    monkeypatch.setattr(mod.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(mod.ak, "stock_margin_szse", szse)
    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: pd.DataFrame([{"date": "2026-09-30"}]))
    monkeypatch.setattr(mod.ak, "stock_margin_detail_sse", lambda **k: pd.DataFrame())
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda **k: pd.DataFrame())

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
        {"信用交易日期": "20260929", "融资融券余额": 1.90e12, "融资余额": 1.80e12},
        {"信用交易日期": "20260930", "融资融券余额": 1.91e12, "融资余额": 1.81e12},
    ])
    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)
    monkeypatch.setattr(cap.ak, "stock_zh_index_daily", lambda symbol: pd.DataFrame([{"date": "2026-09-30"}]))
    monkeypatch.setattr(cap.ak, "stock_margin_detail_sse", lambda **k: pd.DataFrame())
    monkeypatch.setattr(cap.ak, "stock_zh_a_spot", lambda **k: pd.DataFrame())

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
        {"信用交易日期": "20260930", "融资融券余额": 1.93e12, "融资余额": 1.83e12},
        {"信用交易日期": "20260929", "融资融券余额": 1.92e12, "融资余额": 1.82e12},
        {"信用交易日期": "20260928", "融资融券余额": 1.91e12, "融资余额": 1.81e12},
    ])
    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)
    monkeypatch.setattr(cap.ak, "stock_zh_index_daily", lambda symbol: pd.DataFrame([{"date": "2026-09-30"}]))
    monkeypatch.setattr(cap.ak, "stock_margin_detail_sse", lambda **k: pd.DataFrame())
    monkeypatch.setattr(cap.ak, "stock_zh_a_spot", lambda **k: pd.DataFrame())

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
    monkeypatch.setattr(cap.ak, "stock_zh_index_daily", lambda symbol: pd.DataFrame([{"date": "2026-09-30"}]))
    monkeypatch.setattr(cap.ak, "stock_margin_detail_sse", lambda **k: pd.DataFrame())
    monkeypatch.setattr(cap.ak, "stock_zh_a_spot", lambda **k: pd.DataFrame())

    cap.fetch_capital()
    today = date.today()
    assert calls.get("end_date") == today.strftime("%Y%m%d")
    assert calls.get("start_date") == (today - timedelta(days=60)).strftime("%Y%m%d")


def test_margin_split_and_fin_buy(monkeypatch):
    import backend.fetchers.capital as cap, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    sse = pd.DataFrame([
        {"信用交易日期":"20260929","融资余额":1.29e12,"融券余量金额":1.1e10,"融资融券余额":1.301e12},
        {"信用交易日期":"20260930","融资余额":1.30e12,"融券余量金额":1.2e10,"融资融券余额":1.312e12},
    ])
    det = pd.DataFrame([
        {"信用交易日期":"20260930","标的证券代码":"688185","标的证券简称":"康希诺","融资买入额":5.0e8,"融资偿还额":2.0e8,"融券卖出量":100000,"融券余量":500000},
        {"信用交易日期":"20260930","标的证券代码":"600519","标的证券简称":"贵州茅台","融资买入额":1.0e8,"融资偿还额":0.9e8,"融券卖出量":200000,"融券余量":800000},
    ])
    spot = pd.DataFrame([
        {"代码":"688185","最新价":28.5,"涨跌幅":3.2},
        {"代码":"600519","最新价":1700.0,"涨跌幅":-1.5},
    ])
    monkeypatch.setattr(cap.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(cap.ak,"stock_market_fund_flow", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(cap.ak,"stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak,"stock_margin_szse", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(cap.ak,"stock_margin_detail_sse", lambda **k: det)
    monkeypatch.setattr(cap.ak,"stock_zh_a_spot", lambda **k: spot)
    out = cap.fetch_capital()
    m = out["margin_history"][-1]
    assert m["fin_balance"] == 13000.0 and m["sec_balance"] == 120.0
    assert out["fin_net_today"] == 100.0
    assert out["fin_buy_top"][0]["name"] == "康希诺"
    assert out["fin_buy_top"][0]["net_buy"] == 3.0
    assert out["fin_buy_top"][0]["price"] == 28.5
    assert out["fin_buy_top"][0]["change_pct"] == 3.2
    assert out["fin_sell_top"]
    assert out["fin_sell_top"][0]["name"] == "贵州茅台"
    assert out["fin_sell_top"][0]["sec_sell"] == 200000.0
    assert out["fin_sell_top"][0]["price"] == 1700.0
    assert out["fin_sell_top"][0]["change_pct"] == -1.5
    assert out["northbound_active_top"] == []
    assert any("北向" in n for n in out["notes"])
