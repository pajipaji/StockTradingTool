import pandas as pd
import pytest

import backend.fetchers.sw_industry as mod
from backend.fetchers.sw_industry import fetch_sw_industry


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sw_industry(monkeypatch):
    realtime = pd.DataFrame([
        {"指数代码": "801010", "指数名称": "农林牧渔", "昨收盘": 100.0, "最新价": 110.0, "成交额": 20000.0},
        {"指数代码": "801030", "指数名称": "基础化工", "昨收盘": 100.0, "最新价": 95.0, "成交额": 30000.0},
    ])
    def cons(symbol):
        return pd.DataFrame({"证券代码": ["000505", "000592", "999999"]})
    spot = pd.DataFrame([
        {"代码": "sz000505", "涨跌幅": 2.0}, {"代码": "sz000592", "涨跌幅": -1.0},
        {"代码": "sh999999", "涨跌幅": 0.0},
    ])
    monkeypatch.setattr(mod.ak, "index_realtime_sw", lambda symbol: realtime)
    monkeypatch.setattr(mod.ak, "index_component_sw", cons)
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: spot)

    out = fetch_sw_industry()
    ind = next(i for i in out["industries"] if i["code"] == "801010")
    assert (ind["up_count"], ind["down_count"], ind["flat_count"]) == (1, 1, 1)
    assert ind["change_pct"] == 10.0
    assert ind["amount"] == 200.0
    assert out["industries"][0]["code"] == "801010"


def test_fetch_sw_industry_nan_amount(monkeypatch):
    realtime = pd.DataFrame([
        {"指数代码": "801010", "指数名称": "农林牧渔", "昨收盘": 100.0, "最新价": 110.0, "成交额": float("nan")},
    ])
    def cons(symbol):
        return pd.DataFrame({"证券代码": []})
    spot = pd.DataFrame([{"代码": "sz000505", "涨跌幅": 2.0}])
    monkeypatch.setattr(mod.ak, "index_realtime_sw", lambda symbol: realtime)
    monkeypatch.setattr(mod.ak, "index_component_sw", cons)
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: spot)

    out = fetch_sw_industry()
    assert out["industries"][0]["amount"] is None


def test_fetch_sw_industry_one_failure_does_not_abort(monkeypatch):
    import backend.core.fetch as fetchmod
    monkeypatch.setattr(fetchmod, "RETRY_TIMES", 1)

    realtime = pd.DataFrame([
        {"指数代码": "801010", "指数名称": "农林牧渔", "昨收盘": 100.0, "最新价": 110.0, "成交额": 1.0},
        {"指数代码": "801030", "指数名称": "基础化工", "昨收盘": 100.0, "最新价": 110.0, "成交额": 2.0},
    ])
    def cons(symbol):
        if symbol == "801010":
            raise RuntimeError("boom")
        return pd.DataFrame({"证券代码": ["000505"]})
    spot = pd.DataFrame([{"代码": "sz000505", "涨跌幅": 2.0}])
    monkeypatch.setattr(mod.ak, "index_realtime_sw", lambda symbol: realtime)
    monkeypatch.setattr(mod.ak, "index_component_sw", cons)
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: spot)

    out = fetch_sw_industry()
    a = next(i for i in out["industries"] if i["code"] == "801010")
    b = next(i for i in out["industries"] if i["code"] == "801030")
    assert a["up_count"] is None and a["down_count"] is None and a["flat_count"] is None
    assert (b["up_count"], b["down_count"], b["flat_count"]) == (1, 0, 0)
