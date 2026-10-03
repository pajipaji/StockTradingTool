import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct


def fetch_sector_flow() -> dict:
    cdf = fetch(ak.stock_fund_flow_concept, symbol="即时", source="ths")
    concepts = []
    for _, row in cdf.iterrows():
        concepts.append({
            "name": str(row["行业"]),
            "index": float(row["行业指数"]) if row.get("行业指数") == row.get("行业指数") else None,
            "change_pct": pct(row.get("行业-涨跌幅")),
            "net_inflow": pct(row.get("净额")),
            "inflow": pct(row.get("流入资金")),
            "outflow": pct(row.get("流出资金")),
            "company_count": int(row["公司家数"]) if row.get("公司家数") == row.get("公司家数") else None,
            "leader": str(row.get("领涨股", "")),
            "leader_change_pct": pct(row.get("领涨股-涨跌幅")),
        })
    concepts.sort(key=lambda x: (x["net_inflow"] is None, -(x["net_inflow"] or 0)))

    idf = fetch(ak.stock_board_industry_summary_ths, source="ths")
    industries = []
    for _, row in idf.iterrows():
        industries.append({
            "name": str(row["板块"]),
            "change_pct": pct(row.get("涨跌幅")),
            "amount": pct(row.get("总成交额")),
            "net_inflow": pct(row.get("净流入")),
            "up_count": int(row["上涨家数"]) if row.get("上涨家数") == row.get("上涨家数") else None,
            "down_count": int(row["下跌家数"]) if row.get("下跌家数") == row.get("下跌家数") else None,
            "leader": str(row.get("领涨股", "")),
            "leader_change_pct": pct(row.get("领涨股-涨跌幅")),
        })
    industries.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))

    return {"as_of": None, "concepts": concepts, "industries": industries}
