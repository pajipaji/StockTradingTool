import datetime as dt
import pandas as pd
import pytest

import backend.fetchers.overseas as mod
from backend.fetchers.overseas import fetch_overseas


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_overseas(monkeypatch):
    def us_index(symbol):
        return pd.DataFrame([
            {"date": "2026-10-01", "open": 1, "high": 1, "low": 1, "close": 100.0, "volume": 1, "amount": 1},
            {"date": "2026-10-02", "open": 1, "high": 1, "low": 1, "close": 101.0, "volume": 1, "amount": 1},
        ])
    futures = pd.DataFrame([
        {"代码": "CN00Y", "名称": "A50期指当月连续", "最新价": 13830.0, "涨跌额": 20.0, "涨跌幅": 0.14},
        {"代码": "XX", "名称": "不相关", "最新价": 1.0, "涨跌额": 0.0, "涨跌幅": 0.0},
    ])
    hk = pd.DataFrame([
        {"代码": "HSI", "名称": "恒生指数", "最新价": 23972.29, "涨跌额": -641.0, "涨跌幅": -2.60},
        {"代码": "HSTECH", "名称": "恒生科技指数", "最新价": 4157.94, "涨跌额": -96.0, "涨跌幅": -2.26},
        {"代码": "OTHER", "名称": "无关", "最新价": 1.0, "涨跌额": 0.0, "涨跌幅": 0.0},
    ])
    sox = pd.DataFrame([{"日期": "2026-10-02", "最新值": 5200.0, "涨跌幅": 0.8}])
    fx = pd.DataFrame([{"日期": "2026-10-03", "央行中间价": 7.1050}])

    monkeypatch.setattr(mod.ak, "index_us_stock_sina", us_index)
    monkeypatch.setattr(mod.ak, "futures_global_spot_em", lambda: futures)
    monkeypatch.setattr(mod.ak, "stock_hk_index_spot_sina", lambda: hk)
    monkeypatch.setattr(mod.ak, "macro_global_sox_index", lambda: sox)
    monkeypatch.setattr(mod.ak, "currency_boc_sina", lambda **k: fx)

    out = fetch_overseas()
    assert next(i for i in out["us_indices"] if i["code"] == ".DJI")["change_pct"] == 1.0
    assert {f["name"] for f in out["futures"]} == {"A50期指当月连续"}
    assert {h["code"] for h in out["hk_indices"]} == {"HSI", "HSTECH"}
    assert out["sox"]["value"] == 5200.0
    assert out["usd_cny"]["mid"] == 7.1050


def test_fetch_overseas_nan_mid(monkeypatch):
    import math

    def us_index(symbol):
        return pd.DataFrame([{"date": "2026-10-02", "close": 101.0}])
    futures = pd.DataFrame([
        {"代码": "CN00Y", "名称": "A50期指当月连续", "最新价": 13830.0, "涨跌幅": 0.14},
    ])
    hk = pd.DataFrame([{"代码": "HSI", "名称": "恒生指数", "最新价": 1.0, "涨跌幅": 0.0}])
    sox = pd.DataFrame([{"日期": "2026-10-02", "最新值": 5200.0, "涨跌幅": 0.8}])
    fx = pd.DataFrame([{"日期": "2026-10-03", "央行中间价": float("nan")}])

    monkeypatch.setattr(mod.ak, "index_us_stock_sina", us_index)
    monkeypatch.setattr(mod.ak, "futures_global_spot_em", lambda: futures)
    monkeypatch.setattr(mod.ak, "stock_hk_index_spot_sina", lambda: hk)
    monkeypatch.setattr(mod.ak, "macro_global_sox_index", lambda: sox)
    monkeypatch.setattr(mod.ak, "currency_boc_sina", lambda **k: fx)

    out = fetch_overseas()
    usd_cny = out["usd_cny"]
    assert usd_cny == {} or usd_cny.get("mid") is None
    assert not (isinstance(usd_cny.get("mid"), float) and math.isnan(usd_cny["mid"]))
