from datetime import date, timedelta

import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import to_yi


def fetch_capital() -> dict:
    notes = []
    as_of = None
    main_net_inflow = None
    try:
        mf = fetch(ak.stock_market_fund_flow, source="em_datacenter")
        if not mf.empty:
            last = mf.iloc[-1]
            as_of = str(last.get("日期"))
            main_net_inflow = to_yi(last.get("主力净流入-净额"))
    except Exception as exc:
        notes.append(f"主力资金获取失败: {exc}")

    margin_total = None
    margin_history = []
    try:
        today = date.today()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=60)).strftime("%Y%m%d")
        sse = fetch(ak.stock_margin_sse, start_date=start, end_date=end, source="sse")
        if not sse.empty:
            sse = sse.assign(_d=sse["信用交易日期"].astype(str)).sort_values("_d").reset_index(drop=True)
            margin_total = to_yi(sse.iloc[-1]["融资融券余额"])
            margin_history = [{"date": r["信用交易日期"].__str__(), "balance": to_yi(r["融资融券余额"])}
                              for _, r in sse.tail(20).iterrows()]
    except Exception as exc:
        notes.append(f"沪市两融获取失败: {exc}")
    try:
        fetch(ak.stock_margin_szse, source="szse")
    except Exception as exc:
        notes.append(f"深市两融获取失败(已跳过): {exc}")

    return {"as_of": as_of, "main_net_inflow": main_net_inflow,
            "margin_total": margin_total, "margin_history": margin_history, "notes": notes}
