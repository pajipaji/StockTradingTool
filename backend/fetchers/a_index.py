import akshare as ak
import pandas as pd

from backend.core.fetch import fetch
from backend.core.units import pct

TARGET_INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000300": "沪深300",
    "sh000852": "中证1000",
    "sh000688": "科创50",
}
HISTORY_DAYS = 60
DIST_BUCKETS = [
    ("≤-7%", lambda v: v <= -7), ("-7~-5%", lambda v: -7 < v <= -5),
    ("-5~-3%", lambda v: -5 < v <= -3), ("-3~0%", lambda v: -3 < v < 0),
    ("0~3%", lambda v: 0 <= v < 3), ("3~5%", lambda v: 3 <= v < 5),
    ("5~7%", lambda v: 5 <= v < 7), ("≥7%", lambda v: v >= 7),
]


def _ma(values, n):
    if len(values) < n:
        return None
    return round(sum(values[-n:]) / n, 2)


def _distribution(spot_df) -> list:
    values = []
    for v in spot_df["涨跌幅"]:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return [{"label": label, "count": sum(1 for v in values if fn(v))} for label, fn in DIST_BUCKETS]


def fetch_a_index() -> dict:
    spot = fetch(ak.stock_zh_index_spot_sina, source="sina")
    spot_by_code = {str(r["代码"]): r for _, r in spot.iterrows()}

    indices, history = [], {}
    for code, name in TARGET_INDICES.items():
        row = spot_by_code.get(code)
        if row is None:
            continue
        indices.append({
            "code": code, "name": name,
            "price": float(row["最新价"]),
            "change": pct(row.get("涨跌额")),
            "change_pct": pct(row.get("涨跌幅")),
            "amount": float(row["成交额"]) if row.get("成交额") is not None else None,
            "volume": float(row["成交量"]) if row.get("成交量") is not None else None,
        })
        hist = fetch(ak.stock_zh_index_daily, symbol=code, source="sina").tail(HISTORY_DAYS)
        history[code] = [
            {"date": str(r["date"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"])}
            for _, r in hist.iterrows()
        ]

    legu = fetch(ak.stock_market_activity_legu, source="legu")
    bmap = {str(r["item"]): r["value"] for _, r in legu.iterrows()}
    allspot = fetch(ak.stock_zh_a_spot, source="sina")
    breadth = {
        "up": int(bmap.get("上涨", 0)), "down": int(bmap.get("下跌", 0)),
        "flat": int(bmap.get("平盘", 0)), "limit_up": int(bmap.get("涨停", 0)),
        "limit_down": int(bmap.get("跌停", 0)), "activity": str(bmap.get("活跃度", "")),
        "distribution": _distribution(allspot),
    }

    notes = []
    sh_amount = None
    try:
        sse = fetch(ak.stock_sse_deal_daily, source="sse")
        row = sse[sse["单日情况"].astype(str) == "成交金额"].head(1)
        if not row.empty and not pd.isna(row.iloc[0]["股票"]):
            sh_amount = float(row.iloc[0]["股票"])
        else:
            notes.append("沪市成交额获取失败")
    except Exception:
        notes.append("沪市成交额获取失败")
    sz_amount = None
    for i in indices:
        if i["code"] == "sz399001" and i["amount"] is not None:
            sz_amount = round(i["amount"] / 1e8, 2)
    if sz_amount is None:
        notes.append("深市成交额获取失败")
    total = None
    if sh_amount is not None or sz_amount is not None:
        total = round((sh_amount or 0) + (sz_amount or 0), 2)

    turnover = {"sh": sh_amount, "sz": sz_amount, "total": total, "unit": "亿元", "notes": notes}

    prev_date = None
    if history.get("sh000001"):
        dates = [h["date"] for h in history["sh000001"]]
        prev_date = dates[-2] if len(dates) >= 2 else dates[-1]

    ma = {"ma20": None, "ma60": None, "bias60": None}
    if history.get("sh000001"):
        closes = [h["close"] for h in history["sh000001"]]
        ma20, ma60 = _ma(closes, 20), _ma(closes, 60)
        close = closes[-1]
        ma = {"ma20": ma20, "ma60": ma60,
              "bias60": round((close - ma60) / ma60 * 100, 2) if ma60 else None}

    return {
        "as_of": history.get("sh000001", [{}])[-1].get("date") if history.get("sh000001") else None,
        "prev_date": prev_date, "indices": indices, "history": history,
        "turnover": turnover, "breadth": breadth, "ma": ma,
    }
