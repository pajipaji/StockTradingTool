from collections import Counter

import akshare as ak

from backend.core.fetch import fetch


def _latest_date() -> str:
    df = fetch(ak.stock_zh_index_daily, symbol="sh000001", source="sina")
    return str(df.iloc[-1]["date"]).replace("-", "")


def fetch_sentiment() -> dict:
    date = _latest_date()

    zt = fetch(ak.stock_zt_pool_em, date=date, source="em_push2ex")
    dt_pool = fetch(ak.stock_zt_pool_dtgc_em, date=date, source="em_push2ex")
    zb = fetch(ak.stock_zt_pool_zbgc_em, date=date, source="em_push2ex")

    limit_up = int(len(zt))
    limit_down = int(len(dt_pool))
    zbgc = int(len(zb))
    denom = limit_up + zbgc
    zbgc_rate = round(zbgc / denom, 4) if denom else None

    boards = []
    distribution = []
    if "连板数" in zt.columns and limit_up:
        boards = [int(v) for v in zt["连板数"].tolist()]
        distribution = [{"boards": b, "count": c} for b, c in sorted(Counter(boards).items())]
    max_boards = max(boards) if boards else None

    top_boards = []
    if limit_up and "连板数" in zt.columns:
        sorted_zt = zt.sort_values("连板数", ascending=False).head(5)
        top_boards = [{"name": str(r["名称"]), "boards": int(r["连板数"]), "industry": str(r.get("所属行业", ""))}
                      for _, r in sorted_zt.iterrows()]

    prev = fetch(ak.stock_zt_pool_previous_em, date=date, source="em_push2ex")
    prev_count = int(len(prev))
    promotion_rate = None
    if prev_count and "涨跌幅" in prev.columns:
        promoted = sum(1 for v in prev["涨跌幅"] if float(v) >= 9.8)
        promotion_rate = round(promoted / prev_count, 4)

    return {
        "date": date, "limit_up": limit_up, "limit_down": limit_down,
        "zbgc": zbgc, "zbgc_rate": zbgc_rate, "max_boards": max_boards,
        "boards_distribution": distribution, "promotion_rate": promotion_rate,
        "prev_limit_up_count": prev_count, "top_boards": top_boards,
    }
