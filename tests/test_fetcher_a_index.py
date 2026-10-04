import pandas as pd
import pytest

import backend.fetchers.a_index as mod
from backend.fetchers.a_index import fetch_a_index


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_a_index(monkeypatch):
    spot = pd.DataFrame([
        {"代码": "sh000001", "名称": "上证指数", "最新价": 3880.5, "涨跌额": 12.3, "涨跌幅": 0.31, "成交量": 4.1e10, "成交额": 5.2e11},
        {"代码": "sz399001", "名称": "深证成指", "最新价": 12000.0, "涨跌额": -30.0, "涨跌幅": -0.25, "成交量": 5e10, "成交额": 6e11},
    ])
    hist = pd.DataFrame([
        {"date": "2026-09-30", "open": 3800.0, "high": 3820.0, "low": 3790.0, "close": 3810.0, "volume": 3.9e10},
        {"date": "2026-10-03", "open": 3870.0, "high": 3890.0, "low": 3860.0, "close": 3880.5, "volume": 4.1e10},
    ])
    legu = pd.DataFrame([
        {"item": "上涨", "value": 3000}, {"item": "下跌", "value": 1800},
        {"item": "平盘", "value": 200}, {"item": "涨停", "value": 60}, {"item": "跌停", "value": 10},
        {"item": "活跃度", "value": "正常"},
    ])
    allspot = pd.DataFrame([{"代码": f"sz{100000+i}", "名称": "x", "涨跌幅": v}
                            for i, v in enumerate([-8, -6, -4, -1, 1, 4, 6, 9])])
    monkeypatch.setattr(mod.ak, "stock_zh_index_spot_sina", lambda: spot)
    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: hist)
    monkeypatch.setattr(mod.ak, "stock_market_activity_legu", lambda: legu)
    monkeypatch.setattr(mod.ak, "stock_sse_deal_daily", lambda: pd.DataFrame([{"单日情况": "成交金额", "股票": 6759.46}]))
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: allspot)

    out = fetch_a_index()
    assert out["breadth"]["up"] == 3000
    buckets = {d["label"]: d["count"] for d in out["breadth"]["distribution"]}
    assert buckets["≤-7%"] == 1 and buckets["≥7%"] == 1
    assert out["history"]["sh000001"][-1]["close"] == 3880.5
    assert out["turnover"]["sh"] == 6759.46


def test_ma(monkeypatch):
    import backend.fetchers.a_index as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    n = 70
    hist = pd.DataFrame([{"date": f"2026-0{1+(i//28)}-{1+i%28:02d}", "open": 1, "high": 1, "low": 1,
                          "close": float(100 + i), "volume": 1} for i in range(n)])
    monkeypatch.setattr(m.ak, "stock_zh_index_spot_sina", lambda: pd.DataFrame([{"代码":"sh000001","名称":"上证指数","最新价":169.0,"涨跌额":1,"涨跌幅":1,"成交量":1,"成交额":1}]))
    monkeypatch.setattr(m.ak, "stock_zh_index_daily", lambda symbol: hist)
    monkeypatch.setattr(m.ak, "stock_market_activity_legu", lambda: pd.DataFrame([{"item":"上涨","value":1}]))
    monkeypatch.setattr(m.ak, "stock_sse_deal_daily", lambda: pd.DataFrame([{"单日情况":"成交金额","股票":1.0}]))
    monkeypatch.setattr(m.ak, "stock_zh_a_spot", lambda: pd.DataFrame([{"代码":"sz000001","涨跌幅":1.0}]))
    out = m.fetch_a_index()
    # closes 100..169, ma20 = mean(150..169)=159.5, ma60=mean(110..169)=139.5
    assert out["ma"]["ma20"] == 159.5
    assert out["ma"]["ma60"] == 139.5
    assert out["ma"]["bias60"] is not None
