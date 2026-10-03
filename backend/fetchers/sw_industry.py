import akshare as ak
import pandas as pd

from backend.core.fetch import fetch
from backend.core.units import pct


def _normalize_code(code: str) -> str:
    code = str(code).strip()
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def fetch_sw_industry() -> dict:
    realtime = fetch(ak.index_realtime_sw, symbol="一级行业", source="sw")
    spot = fetch(ak.stock_zh_a_spot, source="sina")
    pct_by_code = {_normalize_code(r["代码"]): r["涨跌幅"] for _, r in spot.iterrows()}

    industries = []
    for _, row in realtime.iterrows():
        code = str(row["指数代码"])
        price = float(row["最新价"])
        change_pct = None
        base = row.get("昨收盘")
        try:
            base = float(base)
            if base != 0 and not pd.isna(base):
                change_pct = pct((price - base) / base * 100)
        except (TypeError, ValueError):
            change_pct = None
        try:
            cons = fetch(ak.index_component_sw, symbol=code, source="sw")
            up = down = flat = 0
            for _, c in cons.iterrows():
                chg = pct_by_code.get(_normalize_code(c["证券代码"]))
                if chg is None:
                    continue
                chg = float(chg)
                if chg > 0:
                    up += 1
                elif chg < 0:
                    down += 1
                else:
                    flat += 1
        except Exception:
            up = down = flat = None
        # 成交额 raw unit is 百万元 (million yuan); convert to 亿元 by /100
        raw_amount = row.get("成交额")
        amount = None
        try:
            raw_amount = float(raw_amount)
            if not pd.isna(raw_amount):
                amount = round(raw_amount / 100, 2)
        except (TypeError, ValueError):
            amount = None
        industries.append({
            "code": code, "name": str(row["指数名称"]),
            "price": price, "change_pct": change_pct,
            "amount": amount,
            "up_count": up, "down_count": down, "flat_count": flat,
        })
    industries.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))
    return {"as_of": None, "industries": industries}
