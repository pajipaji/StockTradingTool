import akshare as ak

from backend.core.fetch import fetch

STRONG_TOP = 30
MAX_PER_INDUSTRY = 8


def _num(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return round(f, nd)


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _latest_date() -> str:
    df = fetch(ak.stock_zh_index_daily, symbol="sh000001", source="sina")
    return str(df.iloc[-1]["date"]).replace("-", "")


def _stock_row(r, tag):
    return {
        "code": str(r["代码"]),
        "name": str(r["名称"]),
        "change_pct": _num(r.get("涨跌幅")),
        "boards": _int_or_none(r.get("连板数")),
        "seal_time": str(r.get("首次封板时间", "") or ""),
        "seal_amount": _num(r.get("封板资金"), 0),
        "turnover": _num(r.get("换手率")),
        "tag": tag,
    }


def fetch_leaders() -> dict:
    date = _latest_date()
    zt = fetch(ak.stock_zt_pool_em, date=date, source="em_push2ex")
    strong = fetch(ak.stock_zt_pool_strong_em, date=date, source="em_push2ex")

    by_industry = {}
    seen_codes = set()
    if len(zt):
        for _, r in zt.iterrows():
            ind = str(r.get("所属行业", "")).strip() or "其他"
            by_industry.setdefault(ind, []).append(_stock_row(r, "涨停"))
            seen_codes.add(str(r["代码"]))

    if len(strong):
        for _, r in strong.sort_values("涨跌幅", ascending=False).iterrows():
            code = str(r["代码"])
            if code in seen_codes:
                continue
            ind = str(r.get("所属行业", "")).strip() or "其他"
            row = _stock_row(r, str(r.get("入选理由", "强势"))[:20])
            row["boards"] = None
            row["seal_time"] = ""
            row["seal_amount"] = None
            by_industry.setdefault(ind, []).append(row)

    by_industry_list = []
    for ind, stocks in by_industry.items():
        stocks.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))
        by_industry_list.append({"industry": ind, "stocks": stocks[:MAX_PER_INDUSTRY]})

    boards_ladder = []
    if len(zt) and "连板数" in zt.columns:
        by_board = {}
        for _, r in zt.iterrows():
            b = _int_or_none(r.get("连板数"))
            if b is None:
                continue
            by_board.setdefault(b, []).append({
                "name": str(r["名称"]), "seal_time": str(r.get("首次封板时间", "") or ""),
                "seal_amount": _num(r.get("封板资金"), 0), "tag": "涨停"})
        boards_ladder = [
            {"boards": b, "count": len(v),
             "stocks": sorted(v, key=lambda x: -(x["seal_amount"] or 0))[:10]}
            for b, v in sorted(by_board.items())
        ]

    strong_pool_top = []
    if len(strong):
        for _, r in strong.sort_values("涨跌幅", ascending=False).head(STRONG_TOP).iterrows():
            strong_pool_top.append({
                "code": str(r["代码"]), "name": str(r["名称"]),
                "price": _num(r.get("最新价")),
                "change_pct": _num(r.get("涨跌幅")),
                "zt_stat": str(r.get("涨停统计", "")),
                "turnover": _num(r.get("换手率")),
                "industry": str(r.get("所属行业", "")), "tag": str(r.get("入选理由", ""))[:20],
            })

    new_high_count = 0
    if len(strong) and "是否新高" in strong.columns:
        new_high_count = int((strong["是否新高"].astype(str) == "是").sum())

    return {"as_of": date, "by_industry": by_industry_list,
            "boards_ladder": boards_ladder, "strong_pool_top": strong_pool_top,
            "new_high_count": new_high_count}
