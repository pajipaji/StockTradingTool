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


def test_ladder_and_strong_fields(monkeypatch):
    import backend.fetchers.leaders as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    zt = pd.DataFrame([
        {"代码":"002058","名称":"紫竹高科","涨跌幅":10.0,"连板数":2,"首次封板时间":"092500","封板资金":69384959,"换手率":1.7,"所属行业":"电池"},
        {"代码":"600000","名称":"浦发","涨跌幅":10.0,"连板数":2,"首次封板时间":"093000","封板资金":100.0,"换手率":2.0,"所属行业":"银行"},
    ])
    strong = pd.DataFrame([{"代码":"301190","名称":"善水科技","涨跌幅":20.0,"最新价":35.93,"涨停统计":"3/3","换手率":7.95,"所属行业":"化学原料","入选理由":"60日新高"}])
    monkeypatch.setattr(m.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(m.ak,"stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(m.ak,"stock_zt_pool_strong_em", lambda date: strong)
    out = m.fetch_leaders()
    rung = next(x for x in out["boards_ladder"] if x["boards"] == 2)
    names = [s["name"] for s in rung["stocks"]]
    assert "紫竹高科" in names and "浦发" in names
    assert rung["stocks"][0]["name"] == "紫竹高科"   # 按封板资金降序
    s0 = out["strong_pool_top"][0]
    assert s0["price"] == 35.93 and s0["zt_stat"] == "3/3" and s0["turnover"] == 7.95


def test_new_high_count(monkeypatch):
    import backend.fetchers.leaders as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    zt = pd.DataFrame([{"代码":"002058","名称":"A","涨跌幅":10.0,"连板数":1,"首次封板时间":"092500","封板资金":1,"换手率":1,"所属行业":"电池"}])
    strong = pd.DataFrame([
        {"代码":"301190","名称":"B","涨跌幅":20.0,"最新价":30.0,"涨停统计":"3/3","换手率":7.0,"所属行业":"化工","入选理由":"60日新高","是否新高":"是"},
        {"代码":"301191","名称":"C","涨跌幅":9.0,"最新价":10.0,"涨停统计":"1/1","换手率":5.0,"所属行业":"化工","入选理由":"量价齐升","是否新高":"否"},
    ])
    monkeypatch.setattr(m.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(m.ak,"stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(m.ak,"stock_zt_pool_strong_em", lambda date: strong)
    out = m.fetch_leaders()
    assert out["new_high_count"] == 1
