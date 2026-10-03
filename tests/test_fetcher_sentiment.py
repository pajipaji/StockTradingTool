import pandas as pd
import pytest

import backend.fetchers.sentiment as mod
from backend.fetchers.sentiment import fetch_sentiment


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sentiment(monkeypatch):
    idx = pd.DataFrame([{"date": "2026-09-30", "open": 1, "high": 1, "low": 1, "close": 3800.0, "volume": 1}])
    zt = pd.DataFrame([
        {"代码": "002058", "名称": "紫竹高科", "连板数": 2, "所属行业": "电池"},
        {"代码": "002242", "名称": "九阳股份", "连板数": 3, "所属行业": "小家电"},
        {"代码": "600000", "名称": "浦发银行", "连板数": 1, "所属行业": "银行"},
    ])
    dt_ = pd.DataFrame([{"代码": "600156", "名称": "华升股份"}])
    zb = pd.DataFrame([{"代码": "300001", "名称": "x"}])
    prev = pd.DataFrame([
        {"代码": "000002", "名称": "万科A", "涨跌幅": 9.97},
        {"代码": "000003", "名称": "B", "涨跌幅": 2.0},
    ])

    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_dtgc_em", lambda date: dt_)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_zbgc_em", lambda date: zb)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_previous_em", lambda date: prev)

    out = fetch_sentiment()
    assert out["date"] == "20260930"
    assert out["limit_up"] == 3 and out["limit_down"] == 1
    assert out["zbgc"] == 1
    assert abs(out["zbgc_rate"] - 0.25) < 1e-6
    assert out["max_boards"] == 3
    assert out["top_boards"][0]["name"] == "九阳股份"
    assert out["promotion_rate"] == 0.5
