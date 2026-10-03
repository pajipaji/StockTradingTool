import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct

HISTORY_DAYS = 30


def _to_int(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return int(result)


def fetch_northbound() -> dict:
    summary_df = fetch(ak.stock_hsgt_fund_flow_summary_em, source="em_datacenter")
    north = summary_df[summary_df["资金方向"].astype(str) == "北向"]
    summary, total, as_of = [], 0.0, None
    for _, row in north.iterrows():
        net = float(row["成交净买额"]) if row["成交净买额"] == row["成交净买额"] else 0.0
        total += net
        as_of = str(row["交易日"])
        summary.append({"board": str(row["板块"]), "net_buy": pct(net),
                        "up": _to_int(row["上涨数"]), "flat": _to_int(row["持平数"]),
                        "down": _to_int(row["下跌数"])})

    hist_df = fetch(ak.stock_hsgt_hist_em, symbol="北向资金", source="em_datacenter").tail(HISTORY_DAYS)
    history = [{"date": str(r["日期"]), "net_buy": pct(r["当日成交净买额"])} for _, r in hist_df.iterrows()]

    return {"as_of": as_of, "total_net_buy": pct(total), "summary": summary, "history": history}
