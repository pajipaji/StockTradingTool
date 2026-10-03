import pandas as pd
import pytest

import backend.fetchers.leaders as mod
from backend.fetchers.leaders import fetch_leaders


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_leaders(monkeypatch):
    idx = pd.DataFrame([{"date": "2026-09-30", "open": 1, "high": 1, "low": 1, "close": 3800.0, "volume": 1}])
    zt = pd.DataFrame([
        {"代码": "002058", "名称": "紫竹高科", "涨跌幅": 10.02, "连板数": 2, "首次封板时间": "092500",
         "封板资金": 69384959, "换手率": 1.76, "所属行业": "电池"},
        {"代码": "002242", "名称": "九阳股份", "涨跌幅": 10.03, "连板数": 3, "首次封板时间": "093000",
         "封板资金": 164830000, "换手率": 4.58, "所属行业": "小家电"},
    ])
    strong = pd.DataFrame([
        {"代码": "301190", "名称": "善水科技", "涨跌幅": 20.0, "换手率": 7.9, "所属行业": "化学原料", "入选理由": "60日新高且近期多次涨停"},
        {"代码": "002058", "名称": "紫竹高科", "涨跌幅": 10.0, "换手率": 1.7, "所属行业": "电池", "入选理由": "60日新高"},
    ])

    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_strong_em", lambda date: strong)

    out = fetch_leaders()
    assert out["as_of"] == "20260930"
    inds = {g["industry"] for g in out["by_industry"]}
    assert "电池" in inds and "化学原料" in inds
    battery = next(g for g in out["by_industry"] if g["industry"] == "电池")
    assert battery["stocks"][0]["code"] == "002058" and battery["stocks"][0]["tag"] == "涨停"
    # 强势池中与涨停池重复的 002058 不该重复计入
    assert sum(1 for s in battery["stocks"] if s["code"] == "002058") == 1
    ladder = {d["boards"]: d["count"] for d in out["boards_ladder"]}
    assert ladder[2] == 1 and ladder[3] == 1
    assert any(s["code"] == "301190" for s in out["strong_pool_top"])
