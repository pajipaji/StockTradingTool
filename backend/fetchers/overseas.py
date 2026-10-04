import datetime as dt
import math

import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct

US_INDICES = {".DJI": "道琼斯", ".IXIC": "纳斯达克", ".INX": "标普500"}
FUTURE_KEYS = ("A50期指当月连续", "小型标普当月连续")
HK_CODES = {"HSI": "恒生指数", "HSTECH": "恒生科技指数", "HSCEI": "恒生国企指数", "HSCCI": "恒生中资企业指数"}
US_SECTORS = [
    ("XLK", "信息技术", "半导体/算力/CPO"),
    ("XLC", "通信服务", "传媒/游戏/云计算"),
    ("XLY", "非必需消费", "消费电子/汽车/免税"),
    ("XLP", "必需消费", "食品饮料/白酒"),
    ("XLF", "金融", "银行/保险/券商"),
    ("XLV", "医疗保健", "创新药/CXO/医疗器械"),
    ("XLI", "工业", "工程机械/机器人/军工"),
    ("XLE", "能源", "石油石化/煤炭"),
    ("XLB", "原材料", "有色/化工/钢铁"),
    ("XLU", "公用事业", "电力/水务"),
    ("XLRE", "房地产", "地产/建材"),
]


def _us_sectors() -> list:
    rows = []
    for etf, name, a_share in US_SECTORS:
        try:
            df = fetch(ak.stock_us_daily, symbol=etf, source="sina")
        except Exception:
            continue
        if df is None or df.empty:
            continue
        last = df.iloc[-1]
        prev = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
        close = float(last["close"])
        rows.append({"etf": etf, "name": name,
                     "change_pct": pct((close - prev) / prev * 100) if prev else None,
                     "a_share": a_share})
    return rows


def _us_indices():
    rows, as_of = [], None
    for code, name in US_INDICES.items():
        df = fetch(ak.index_us_stock_sina, symbol=code, source="sina")
        if df.empty:
            continue
        last = df.iloc[-1]
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
        close = float(last["close"])
        as_of = str(last["date"])
        rows.append({
            "code": code, "name": name, "close": close,
            "change": pct(close - prev_close),
            "change_pct": pct((close - prev_close) / prev_close * 100) if prev_close else None,
        })
    return rows, as_of


def fetch_overseas() -> dict:
    us_indices, as_of = _us_indices()

    fdf = fetch(ak.futures_global_spot_em, source="em_push2ex")
    futures = []
    for _, row in fdf.iterrows():
        if any(k in str(row["名称"]) for k in FUTURE_KEYS):
            futures.append({
                "code": str(row["代码"]), "name": str(row["名称"]),
                "price": float(row["最新价"]) if row["最新价"] == row["最新价"] else None,
                "change_pct": pct(row.get("涨跌幅")),
            })

    hkdf = fetch(ak.stock_hk_index_spot_sina, source="sina")
    hk_indices = []
    for _, row in hkdf.iterrows():
        code = str(row["代码"])
        if code in HK_CODES:
            hk_indices.append({
                "code": code, "name": HK_CODES.get(code, str(row["名称"])),
                "price": float(row["最新价"]), "change_pct": pct(row.get("涨跌幅")),
            })

    sox = {}
    try:
        sdf = fetch(ak.macro_global_sox_index, source="legu")
        if not sdf.empty:
            last = sdf.iloc[-1]
            sox = {"date": str(last["日期"]), "value": float(last["最新值"]), "change_pct": pct(last.get("涨跌幅"))}
    except Exception:
        sox = {}

    usd_cny = {}
    try:
        end = dt.date.today()
        start = end - dt.timedelta(days=7)
        fdf2 = fetch(ak.currency_boc_sina, symbol="美元",
                     start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), source="sina")
        if not fdf2.empty:
            last = fdf2.iloc[-1]
            mid = float(last["央行中间价"])
            if math.isfinite(mid):
                usd_cny = {"date": str(last["日期"]), "mid": mid,
                           "note": "中行牌价(代理，非离岸CNH)"}
    except Exception:
        usd_cny = {}

    sectors = _us_sectors()
    if sox and sox.get("change_pct") is not None:
        sectors.append({"etf": "SOX", "name": "费城半导体",
                        "change_pct": sox.get("change_pct"), "a_share": "芯片封测/半导体设备/CPO"})

    return {"as_of": as_of, "us_indices": us_indices, "futures": futures,
            "hk_indices": hk_indices, "sox": sox, "usd_cny": usd_cny,
            "us_sectors": sectors}
