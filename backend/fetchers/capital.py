from __future__ import annotations

import datetime as dt

import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import to_yi


def _range_start() -> str:
    return (dt.date.today() - dt.timedelta(days=60)).strftime("%Y%m%d")


def _latest_date() -> str:
    df = fetch(ak.stock_zh_index_daily, symbol="sh000001", source="sina")
    return str(df.iloc[-1]["date"]).replace("-", "")


def _strip(code: str) -> str:
    code = str(code).strip()
    for p in ("sh", "sz", "bj"):
        if code.startswith(p):
            return code[len(p):]
    return code


def _num(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return round(f, nd)


def _spot_map() -> dict:
    try:
        spot = fetch(ak.stock_zh_a_spot, source="sina")
    except Exception:
        return {}
    m = {}
    for _, r in spot.iterrows():
        code = _strip(r["代码"])
        try:
            m[code] = (float(r["最新价"]), float(r["涨跌幅"]))
        except (TypeError, ValueError):
            m[code] = (None, None)
    return m


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
    fin_net_today = None
    try:
        sse = fetch(ak.stock_margin_sse, start_date=_range_start(),
                    end_date=dt.date.today().strftime("%Y%m%d"), source="sse")
        if not sse.empty:
            sse = sse.assign(_d=sse["信用交易日期"].astype(str)).sort_values("_d").reset_index(drop=True)
            margin_total = to_yi(sse.iloc[-1]["融资融券余额"])
            if len(sse) >= 2 and "融资余额" in sse.columns:
                fin_net_today = to_yi(sse.iloc[-1]["融资余额"] - sse.iloc[-2]["融资余额"])
            for _, r in sse.tail(20).iterrows():
                margin_history.append({
                    "date": str(r["信用交易日期"]),
                    "balance": to_yi(r["融资融券余额"]),
                    "fin_balance": to_yi(r.get("融资余额")),
                    "sec_balance": to_yi(r.get("融券余量金额")),
                })
    except Exception as exc:
        notes.append(f"沪市两融获取失败: {exc}")
    try:
        fetch(ak.stock_margin_szse, source="szse")
    except Exception as exc:
        notes.append(f"深市两融获取失败(已跳过): {exc}")

    fin_buy_top = []
    fin_sell_top = []
    try:
        date = _latest_date()
        det = fetch(ak.stock_margin_detail_sse, date=date, source="sse")
        if det is not None and not det.empty:
            spot = _spot_map()
            if "融资买入额" in det.columns and "融资偿还额" in det.columns:
                d = det.assign(_net=det["融资买入额"].astype(float) - det["融资偿还额"].astype(float))
                for _, r in d.sort_values("_net", ascending=False).head(10).iterrows():
                    code = _strip(r["标的证券代码"])
                    price, chg = spot.get(code, (None, None))
                    fin_buy_top.append({"code": code, "name": str(r["标的证券简称"]),
                                        "price": price, "change_pct": chg, "net_buy": to_yi(r["_net"])})
            if "融券卖出量" in det.columns:
                for _, r in det.sort_values("融券卖出量", ascending=False).head(10).iterrows():
                    code = _strip(r["标的证券代码"])
                    price, chg = spot.get(code, (None, None))
                    fin_sell_top.append({"code": code, "name": str(r["标的证券简称"]),
                                         "price": price, "change_pct": chg,
                                         "sec_sell": _num(r.get("融券卖出量"), 0),
                                         "sec_balance": _num(r.get("融券余量"), 0)})
    except Exception as exc:
        notes.append(f"两融明细获取失败: {exc}")

    northbound_active_top = []
    notes.append("北向个股活跃成交数据已停止披露")

    return {"as_of": as_of, "main_net_inflow": main_net_inflow,
            "margin_total": margin_total, "margin_history": margin_history,
            "fin_net_today": fin_net_today, "fin_buy_top": fin_buy_top,
            "fin_sell_top": fin_sell_top, "northbound_active_top": northbound_active_top,
            "notes": notes}
