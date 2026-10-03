import pandas as pd
import pytest

import backend.fetchers.northbound as mod
from backend.fetchers.northbound import fetch_northbound


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_northbound(monkeypatch):
    summary = pd.DataFrame([
        {"交易日": "2026-10-03", "资金方向": "北向", "板块": "沪股通", "成交净买额": 30.1, "上涨数": 941, "持平数": 41, "下跌数": 662},
        {"交易日": "2026-10-03", "资金方向": "南向", "板块": "港股通(沪)", "成交净买额": 50.0, "上涨数": 1, "持平数": 1, "下跌数": 1},
        {"交易日": "2026-10-03", "资金方向": "北向", "板块": "深股通", "成交净买额": 20.8, "上涨数": 880, "持平数": 30, "下跌数": 700},
    ])
    hist = pd.DataFrame([{"日期": "2026-09-30", "当日成交净买额": 5.0},
                         {"日期": "2026-10-01", "当日成交净买额": 12.3}])
    monkeypatch.setattr(mod.ak, "stock_hsgt_fund_flow_summary_em", lambda: summary)
    monkeypatch.setattr(mod.ak, "stock_hsgt_hist_em", lambda symbol: hist)

    out = fetch_northbound()
    assert {s["board"] for s in out["summary"]} == {"沪股通", "深股通"}
    assert abs(out["total_net_buy"] - 50.9) < 1e-6
    assert out["history"][-1]["net_buy"] == 12.3


def test_fetch_northbound_nan_counts(monkeypatch):
    summary = pd.DataFrame([
        {"交易日": "2026-10-03", "资金方向": "北向", "板块": "沪股通", "成交净买额": float("nan"),
         "上涨数": float("nan"), "持平数": 41, "下跌数": float("nan")},
    ])
    hist = pd.DataFrame([{"日期": "2026-10-01", "当日成交净买额": 12.3}])
    monkeypatch.setattr(mod.ak, "stock_hsgt_fund_flow_summary_em", lambda: summary)
    monkeypatch.setattr(mod.ak, "stock_hsgt_hist_em", lambda symbol: hist)

    out = fetch_northbound()
    s = out["summary"][0]
    assert s["up"] is None
    assert s["flat"] == 41
    assert s["down"] is None
