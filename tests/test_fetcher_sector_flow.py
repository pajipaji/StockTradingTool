import pandas as pd
import pytest

import backend.fetchers.sector_flow as mod
from backend.fetchers.sector_flow import fetch_sector_flow


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sector_flow(monkeypatch):
    concepts = pd.DataFrame([
        {"行业": "重组蛋白", "行业指数": 851.77, "行业-涨跌幅": 3.78, "流入资金": 95.52, "流出资金": 75.58,
         "净额": 19.94, "公司家数": 128, "领涨股": "泰诺麦博", "领涨股-涨跌幅": 19.99},
        {"行业": "银行", "行业指数": 3000.0, "行业-涨跌幅": -0.2, "流入资金": 10.0, "流出资金": 20.0,
         "净额": -10.0, "公司家数": 42, "领涨股": "X", "领涨股-涨跌幅": 1.0},
    ])
    industries = pd.DataFrame([
        {"板块": "生物制品", "涨跌幅": 4.63, "总成交额": 236.62, "净流入": 14.36, "上涨家数": 53,
         "下跌家数": 2, "领涨股": "康希诺", "领涨股-涨跌幅": 20.0},
    ])
    monkeypatch.setattr(mod.ak, "stock_fund_flow_concept", lambda symbol: concepts)
    monkeypatch.setattr(mod.ak, "stock_board_industry_summary_ths", lambda: industries)

    out = fetch_sector_flow()
    assert out["concepts"][0]["name"] == "重组蛋白"
    assert out["concepts"][0]["net_inflow"] == 19.94
    assert out["industries"][0]["name"] == "生物制品"
    assert out["industries"][0]["up_count"] == 53
