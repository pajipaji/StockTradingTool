# 股市脉搏看板（akshare + FastAPI + ECharts）设计文档 — v2

- 日期：2026-10-03
- 状态：待评审（v2 增强版）
- 作者：openCode / 用户
- 关联需求来源：用户手写笔记两张 + 专业复盘视角点评
- 上一版：v1（核心五块）→ 本版升级为「3 屏 + 情绪博弈 + 概念主线」

---

## 1. 背景与目标

### 1.1 背景
基于 `akshare` 构建本地"股市脉搏"每日复盘看板。v1 确认了工程架构与数据源可用性；v2 采纳专业复盘点评，把"数据堆叠"升级为"高效率复盘"。

关键网络结论（沿用 v1，仍然成立）：
- 东财 `clist/get`（批量实时列表）被 WAF 硬封，不可用。
- 但东财 **`push2ex` / `datacenter`** 系列（涨停池、大盘资金流、沪深港通）**可用**；新浪、同花顺、乐咕、交易所源稳定。

### 1.2 目标（v2）
围绕 A 股复盘主线 **「看大盘情绪 → 找资金主线 → 析高低切换/赚钱效应 → 备次日策略」**，交付 3 屏深色盘面风看板：

**屏一 · 市场全局与情绪**
1. **外围风向**：A50 期指 / 美股三大 / 恒生指数·恒生科技（港股中概代理）/ 费城半导体 / 美元（中行牌价）
2. **A股大盘与量能**：上证/深证/创业板/科创50 点位涨跌幅 + **两市成交额及较上一交易日增减（放量/缩量）**
3. **情绪博弈仪表盘**：涨停数、跌停数、**炸板率**、**最高连板高度**、**连板晋级率**、涨跌家数
4. **涨跌分布梯度直方图** + 大盘近 60 日走势（含成交额柱）

**屏二 · 资金主线与板块轮动**
5. **概念资金流 Top**：同花顺概念**净流入 Top10 / 净流出 Top10**（含领涨股、涨跌幅），支持一键切换排序
6. **同花顺行业(90)**：涨跌幅 / 净流入 / 上涨·下跌家数 / 领涨股
7. **申万一级行业(31)**：**ECharts 热力图 Treemap**（块大小=成交额，颜色=涨跌幅）+ 色阶表

**屏三 · 长线资金**
8. **北向资金**：概览卡（沪股通/深股通净买额 + 涨跌家数）+ 近 30 日趋势
9. **主力资金 & 融资融券**（best-effort，源不稳则局部标注异常）

### 1.3 非目标
- 盘中高频实时刷新（本版为**每日快照**）
- 个股 K 线/回测/交易
- 历史日期浏览（不做日期下拉）
- 离岸人民币 CNH 实时（无稳定源，用中行美元牌价代理）
- 美股全市场涨跌家数（东财 `stock_us_spot_em` 被封）

### 1.4 交付形态
- 方案 B：`FastAPI 后端 + 原生 HTML/CSS/JS + 本地 ECharts`，每日快照缓存。
- 一条命令启动（`run.sh`），页面「重新抓取」按钮可强制刷新当日快照。

### 1.5 视觉风格
深色专业盘面风（dark pro），红涨绿跌。

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│ akshare：新浪 / 同花顺 / 乐咕 / 交易所 / 东财push2ex+datacenter │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ 网络抓取层 backend/core/                                     │
│ force_ipv4() · RateLimiter · retry() · fetch(缓存/限速/重试) │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ Fetcher 层 backend/fetchers/                                 │
│ overseas · a_index · sentiment · northbound · sw_industry ·  │
│ sector_flow · capital                                        │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ 快照服务 services/snapshot.py                                │
│ 组装 7 分区 → 错误隔离 →（量能增减）对比上一快照 → 原子写     │
│ data/snapshots/YYYY-MM-DD.json                               │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ API backend/app.py：GET / · GET /api/snapshot · POST /api/refresh │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ 前端 frontend/（3 屏 + ECharts Treemap / 直方图 / 折线 / 柱） │
└────────────────────────────────────────────────────────────┘
```

---

## 3. 数据源可用性矩阵（已实测，v2 更新）

### 3.1 主用数据源

| 看板用途 | akshare 接口 | 关键参数 | 状态 |
|---|---|---|---|
| 美股三大指数 | `index_us_stock_sina` | `.DJI/.IXIC/.INX` | ✅ |
| A50/美股期指 | `futures_global_spot_em` | 名称含 `A50期指当月连续`、`小型标普当月连续` | ✅ |
| 港股/中概风向 | `stock_hk_index_spot_sina` | 筛 `HSI/HSTECH/HSCEI/HSCCI` | ✅ |
| 费城半导体 | `macro_global_sox_index` | — | ✅ |
| 美元汇率（中行牌价） | `currency_boc_sina` | `symbol="美元"` | ✅（代理） |
| A股指数实时 | `stock_zh_index_spot_sina` | — | ✅ |
| A股指数历史 | `stock_zh_index_daily` | `sh000001` 等 | ✅ |
| 全市场涨跌家数/涨停跌停 | `stock_market_activity_legu` | — | ✅ |
| **涨停池** | `stock_zt_pool_em` | `date=YYYYMMDD` | ✅ 含 `连板数/炸板次数/涨停统计` |
| **跌停池** | `stock_zt_pool_dtgc_em` | `date` | ✅ 含 `连续跌停/开板次数` |
| **炸板池** | `stock_zt_pool_zbgc_em` | `date` | ✅ |
| **昨日涨停（晋级）** | `stock_zt_pool_previous_em` | `date` | ✅ 含 `昨日连板数/涨停统计` |
| 概念资金流 | `stock_fund_flow_concept` | `即时` | ✅ 387 概念 |
| 同花顺行业(90) | `stock_board_industry_summary_ths` | — | ✅ 含净流入/涨跌家数/领涨股 |
| 申万一级实时 | `index_realtime_sw` | `一级行业` | ✅ 31 个 |
| 申万成分股 | `index_component_sw` | `801010` 等 | ✅ |
| 全A个股实时 | `stock_zh_a_spot` | — | ✅ 5571 只（约 20s） |
| 上交所每日成交 | `stock_sse_deal_daily` | — | ✅ |
| 沪深港通 | `stock_hsgt_fund_flow_summary_em` | — | ✅（datacenter） |
| 北向历史 | `stock_hsgt_hist_em` | `北向资金` | ✅ |

### 3.2 best-effort / 降级源

| 用途 | 接口 | 状态 | 处理 |
|---|---|---|---|
| 大盘主力资金 | `stock_market_fund_flow` | ⚠️ 时通时断 | 屏三卡，失败标注异常 |
| 融资融券 | `stock_margin_sse`（沪✅）/ `stock_margin_szse`（深❌bug） | ⚠️ | 只用可用部分，标注 |
| 深交所成交 | `stock_szse_summary` | ❌ bug | 指数成交额兜底 |
| 离岸人民币 CNH | — | ❌ 无 | 用 `currency_boc_sina` 美元代理 |
| 东财实时列表类 | `*_spot_em` / `stock_board_*_em`(clist) | ❌ 硬封 | 用新浪/同花顺替代 |

### 3.3 东财诊断结论（沿用）
- 非 TLS 指纹、非请求头问题；IPv6 出口被 RST（强制 IPv4 缓解）；`clist/get` 接口级硬封；叠加频率封禁。
- **`push2ex`/`datacenter`（涨停池、资金流、北向）不受影响，可用。**

---

## 4. 网络与抓取层（沿用 v1）

### 4.1 `net.py` `force_ipv4()`
```python
import socket
_ORIGINAL = None
_APPLIED = False

def force_ipv4() -> bool:
    global _ORIGINAL, _APPLIED
    if _APPLIED:
        return False
    _ORIGINAL = socket.getaddrinfo
    def _ipv4_only(host, *args, **kwargs):
        results = _ORIGINAL(host, *args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results
    socket.getaddrinfo = _ipv4_only
    _APPLIED = True
    return True
```

### 4.2 `ratelimit.py` `RateLimiter`
按 `source` 记录上次请求时间，间隔不足则 sleep；可注入 `clock/sleeper` 便于测试。

### 4.3 `retry.py` `retry()`
指数退避 + 抖动，可注入 `sleeper`；默认 3 次。

### 4.4 `fetch.py` `fetch()`
```
fetch(fn, *args, source, use_cache=True, **kwargs)
LIMITER / RETRY_TIMES / reset_cache()
```
- 缓存 key = `(module, fn名, args, sorted(kwargs))` → 同一快照内 `stock_zh_a_spot` 只抓一次（a_index 与 sw_industry 共享）。
- 所有 akshare 调用必须经此入口。

### 4.5 日志
标准库 `logging`，控制台 + `backend/data/logs/app.log`。

---

## 5. Fetcher 设计

统一契约：`fetch_xxx() -> dict`；成功返回分区 dict；失败抛异常由快照服务捕获。

### 5.1 `overseas.py` — ① 外围风向
- 美股三大：`index_us_stock_sina`(.DJI/.IXIC/.INX) → 收盘/涨跌幅。
- 期指：`futures_global_spot_em` 筛 `A50期指当月连续`、`小型标普当月连续`。
- 港股：`stock_hk_index_spot_sina` 筛 `HSI`(恒生指数)、`HSTECH`(恒生科技)、`HSCEI`(国企)、`HSCCI`(中资企业)。
- 费半：`macro_global_sox_index` 取最后一行 → 最新值/涨跌幅。
- 汇率：`currency_boc_sina("美元", start=近7天, end=今天)` 取最后一行 `央行中间价`（或汇买价）。
- 输出：
```jsonc
{
  "as_of": "2026-10-02",
  "us_indices": [{"code":".DJI","name":"道琼斯","close":42345.67,"change":123.4,"change_pct":0.29}],
  "futures": [{"code":"CN00Y","name":"A50期指当月连续","price":13830.0,"change_pct":0.14}],
  "hk_indices": [{"code":"HSI","name":"恒生指数","price":23972.29,"change_pct":-2.60}],
  "sox": {"date":"2026-10-02","value":5200.0,"change_pct":0.8},
  "usd_cny": {"date":"2026-10-03","mid":7.1050,"note":"中行牌价(代理，非离岸CNH)"}
}
```

### 5.2 `a_index.py` — ② A股指数 / 量能 / 涨跌分布
- 指数：`stock_zh_index_spot_sina` 筛 上证 `sh000001`、深成 `sz399001`、创业板 `sz399006`、科创50 `sh000688`、沪深300 `sh000300`、中证1000 `sh000852`。
- 走势：`stock_zh_index_daily(code)` 近 **60** 日。
- 涨跌家数：`stock_market_activity_legu`。
- **涨跌分布梯度**：`stock_zh_a_spot` 的 `涨跌幅` 分桶：
  `[≤-7, -7~-5, -5~-3, -3~0, 0~3, 3~5, 5~7, ≥7]` → `distribution: [{label, count}]`。
- 成交额：沪市 `stock_sse_deal_daily`；深市 `stock_szse_summary` 异常 → 用深证成指成交额兜底；`total` = 沪+深（有兜底则 `notes` 标注）。
- 输出：
```jsonc
{
  "as_of": "2026-10-03",
  "prev_date": "2026-09-30",
  "indices": [{"code":"sh000001","name":"上证指数","price":3880.5,"change_pct":0.31,"amount":5.2e11}],
  "history": {"sh000001":[{"date":"2026-08-01","close":3810.0,"volume":3.9e10}]},
  "turnover": {"sh":5200.0,"sz":6800.0,"total":12000.0,"unit":"亿元","notes":[]},
  "breadth": {"up":3000,"down":1800,"flat":200,"limit_up":60,"limit_down":10,"activity":"正常",
              "distribution":[{"label":"≤-7%","count":30},{"label":"≥7%","count":120}]}
}
```
> `turnover.delta` 由快照服务补充（见 §5.8）。

### 5.3 `sentiment.py` — ③ 情绪博弈
- 最新交易日 `latest_date`：取 `stock_zh_index_daily("sh000001")` 最后一行的日期，转 `YYYYMMDD`。
- 涨停池：`stock_zt_pool_em(date=latest_date)` → `涨停数=行数`、`最高连板=max(连板数)`、`连板分布`。
- 跌停池：`stock_zt_pool_dtgc_em(date)` → `跌停数=行数`。
- 炸板池：`stock_zt_pool_zbgc_em(date)` → `炸板数=行数`；`炸板率 = 炸板数/(涨停数+炸板数)`。
- 昨日涨停：`stock_zt_pool_previous_em(date)` → `晋级率 = count(涨跌幅≥9.8%)/行数`（近似，主板 10%）。
- 输出：
```jsonc
{
  "date": "20260930",
  "limit_up": 52,
  "limit_down": 9,
  "zbgc": 12,
  "zbgc_rate": 0.1875,
  "max_boards": 5,
  "boards_distribution": [{"boards":1,"count":30},{"boards":2,"count":12}],
  "promotion_rate": 0.42,
  "prev_limit_up_count": 57,
  "top_boards": [{"name":"紫竹高科","boards":2,"industry":"电池"}]
}
```

### 5.4 `northbound.py` — ⑧ 北向资金（降权）
- `stock_hsgt_fund_flow_summary_em`：北向（沪股通/深股通）净买额 + 上涨/持平/下跌数。
- `stock_hsgt_hist_em("北向资金")` 近 **30** 日净买额趋势。
- 输出 `{as_of, total_net_buy, summary[], history[]}`。

### 5.5 `sw_industry.py` — ⑦ 申万一级（热图数据源）
- `index_realtime_sw("一级行业")` 31 行业：点位/涨幅/成交额。
- 行业涨跌家数：`index_component_sw(code)` × `stock_zh_a_spot`（规范化代码后 join）。
- 输出 `{as_of, industries:[{code,name,price,change_pct,amount,up_count,down_count,flat_count}]}`，按涨幅降序。

### 5.6 `sector_flow.py` — ⑤⑥ 概念 + 同花顺行业资金
- 概念：`stock_fund_flow_concept("即时")` → `concepts:[{name,index,change_pct,net_inflow,inflow,outflow,company_count,leader,leader_change_pct}]`。
- 行业：`stock_board_industry_summary_ths()` → `industries:[{name,change_pct,amount,net_inflow,up_count,down_count,leader,leader_change_pct}]`。
- 前端据此算 Top10 净流入/净流出、排序切换。
- 输出 `{as_of, concepts[], industries[]}`。

### 5.7 `capital.py` — ⑨ 主力/两融（best-effort）
- 主力资金：`stock_market_fund_flow()` 取最后一行 `主力净流入-净额`（换算亿元）。
- 两融：`stock_margin_sse()` 最后一行 `融资融券余额`；深市 `stock_margin_szse` 失败则跳过。
- 输出 `{as_of, main_net_inflow, margin_total, notes[]}`；子项失败进 `notes`，整源失败由快照服务标 `error`。

### 5.8 `services/snapshot.py` — 快照服务
```python
SECTIONS = {
    "overseas": fetch_overseas,
    "a_index": fetch_a_index,
    "sentiment": fetch_sentiment,
    "northbound": fetch_northbound,
    "sw_industry": fetch_sw_industry,
    "sector_flow": fetch_sector_flow,
    "capital": fetch_capital,
}
```
- 逐个分区抓取，`try/except` 错误隔离，失败写 `{"error": ...}`。
- **量能增减**：构建后若 `a_index.turnover` 存在，加载上一交易日快照（扫描目录取 `< date` 的最大文件名），写入 `turnover.prev_total` 与 `turnover.delta`（无则 `null`）。
- 原子写：`.tmp` → `os.replace`。
- `load_snapshot` / `get_or_create(force=)`。

---

## 6. 快照数据模型（`data/snapshots/YYYY-MM-DD.json`）

```jsonc
{
  "date": "2026-10-03",
  "generated_at": "2026-10-03T16:30:12+08:00",
  "sources": { "overseas":"ok","a_index":"ok","sentiment":"ok","northbound":"ok",
               "sw_industry":"ok","sector_flow":"ok","capital":"ok" },

  "overseas": { "...": "见 §5.1" },
  "a_index":  { "...": "见 §5.2，turnover 额外含 prev_total/delta" },
  "sentiment": { "...": "见 §5.3" },
  "northbound": { "...": "见 §5.4" },
  "sw_industry": { "...": "见 §5.5" },
  "sector_flow": { "...": "见 §5.6" },
  "capital": { "...": "见 §5.7" }
}
```

约定：金额统一亿元；涨跌幅为百分比数值；缺失 `null`；异常分区 `{"error": "..."}`。
`a_index.turnover` 增加：
```jsonc
"turnover": {"sh":5200.0,"sz":6800.0,"total":12000.0,"unit":"亿元",
             "prev_total":10500.0,"delta":1500.0,"notes":[]}
```

---

## 7. API 设计（FastAPI）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 `frontend/index.html` |
| GET | `/api/snapshot` | 当日快照；无缓存则触发抓取 |
| POST | `/api/refresh` | 强制重抓并覆盖当日快照 |
| GET | `/healthz` | `{"ok": true}` |

- 不做历史浏览（无 `/api/dates`、无 `/api/snapshot/{date}`）。
- 全部源失败 → 502；部分失败正常返回（前端分区标注）。
- `build_app(data_dir=None, fetchers=None)` 便于测试注入。

---

## 8. 前端设计（深色盘面风，3 屏）

### 8.1 技术
原生 HTML/CSS/JS + **本地 ECharts**（`frontend/vendor/echarts.min.js`）。`fetch('/api/snapshot')`；刷新按钮 `POST /api/refresh`。

### 8.2 布局
```
┌──────────────────────────────────────────────────────────────────────────┐
│ 顶栏：股市脉搏 │ 日期 2026-10-03 16:30 │ 数据源：7/7 ok │ [ 重新抓取 ]     │
├──────────────────────────────────────────────────────────────────────────┤
│ 【屏一 · 市场全局与情绪】                                                  │
│ ┌───────────────────────────────┐ ┌────────────────────────────────────┐ │
│ │ 外围风向                       │ │ A股大盘（点位/涨跌幅）              │ │
│ │ A50 / 纳指 / 恒生 / 恒生科技   │ │ 上证 深证 创业板 科创50             │ │
│ │ 费半 / 美元(中行)              │ │ 两市成交额 12000亿 (较昨 +1500亿)   │ │
│ └───────────────────────────────┘ └────────────────────────────────────┘ │
│ ┌───────────────────────────────┐ ┌────────────────────────────────────┐ │
│ │ 情绪博弈                       │ │ 大盘近60日走势 + 成交额柱 (ECharts) │ │
│ │ 涨停52 跌停9 炸板12(炸板率19%) │ │                                    │ │
│ │ 最高5连板 晋级率42%            │ │                                    │ │
│ └───────────────────────────────┘ └────────────────────────────────────┘ │
│ ┌─涨跌分布梯度直方图(ECharts)──────────────────────────────────────────┐ │
│ └──────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────┤
│ 【屏二 · 资金主线与板块轮动】                                              │
│ ┌───────────────────────────────┐ ┌────────────────────────────────────┐ │
│ │ 概念资金流 (同花顺 387)        │ │ 申万一级热力图 Treemap             │ │
│ │ 净流入 Top10 / 净流出 Top10    │ │ 块=成交额, 色=涨跌幅               │ │
│ │ [按净额|按涨幅] 切换           │ │                                    │ │
│ └───────────────────────────────┘ └────────────────────────────────────┘ │
│ ┌─同花顺行业(90) 表格：涨幅|净流入|涨跌家数|领涨股 (可排序)─────────────┐ │
│ └──────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────┤
│ 【屏三 · 长线资金】                                                        │
│ ┌─北向资金概览卡 + 近30日趋势折线─────────────────────────────────────┐ │
│ ├─主力资金(净流入) · 融资融券余额(概览卡)─────────────────────────────┤ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 8.3 设计令牌（精确值）
```css
:root {
  --bg:#0e1117; --panel:#161b26; --panel-2:#1e2430; --border:#2a3141;
  --text:#e6e9ef; --text-muted:#8b93a7; --up:#ff4d4f; --down:#22c55e;
  --flat:#8b93a7; --accent:#3b82f6; --gold:#f5c451;
}
```
涨跌幅颜色：`>0` 红、`<0` 绿、`=0` 灰；金额自动换算 亿。

### 8.4 ECharts 组件
1. 大盘走势折线 + 成交额柱（双图或双 Y）。
2. 涨跌分布梯度直方图（横向 8 桶，红绿配色）。
3. 申万一级 **Treemap**（`value=成交额`，`visualMap` 按 `change_pct` 红绿着色）。
4. 北向净买额柱状（正红负绿）。
5. 概念 Top10 表格（条形内嵌或纯表）。

### 8.5 交互
- 刷新按钮：loading 遮罩 → `POST /api/refresh` → 重建图表。
- 概念/行业表支持按「净额 / 涨跌幅」切换排序。
- 分区 `error` → 显示「⚠ 数据源异常：<msg>」，其余区正常。
- 顶栏显示数据源状态 `ok数/总数`。

---

## 9. 错误处理与降级

| 场景 | 处理 |
|---|---|
| 单 fetcher 抛异常 | 快照捕获，该分区 `error`，其余继续 |
| 子项降级（深市成交/深市两融/主力资金失败） | 返回部分数据 + `notes` |
| 抓取失败但有旧缓存 | 返回旧缓存 + `stale: true` |
| `stock_zh_a_spot` 超时 | 提高重试；涨跌分布/申万家数允许为空 |
| 首次运行无上一快照 | `turnover.delta = null`，前端显示 `--` |
| 申万成分缓存缺失 | 首次抓取，之后 T+7 缓存 |

---

## 10. 测试策略
- `pytest`；默认 `-m "not network"`。
- `test_net/ratelimit/retry/fetch/units/logging`：核心层单测。
- `test_snapshot`：错误隔离 + 量能增减（构造昨日快照）+ 原子写 + 缓存。
- `test_fetcher_*`：用内存 DataFrame monkeypatch 各 akshare 函数，断言标准化输出与计算（涨跌分布分桶、炸板率、晋级率、Top 排序）。
- `test_api`：`GET /`、`GET /api/snapshot`、`POST /api/refresh`、`/healthz`、全失败 502。
- `test_frontend_assets`：文件存在 + 关键引用。
- `test_network_smoke`：联网冒烟，标记 `@pytest.mark.network`。

---

## 11. 依赖与环境
- Python 3.9.6；akshare 1.18.88；pandas。
- 新增：`fastapi`、`uvicorn[standard]`、`pytest`。
- ECharts 本地 vendor。
```bash
pip3 install --user fastapi "uvicorn[standard]" pytest
```

---

## 12. 目录结构
```
炒股小工具/
├─ backend/
│  ├─ app.py
│  ├─ core/{logging,net,ratelimit,retry,fetch,units}.py
│  ├─ fetchers/{overseas,a_index,sentiment,northbound,sw_industry,sector_flow,capital}.py
│  ├─ services/snapshot.py
│  └─ data/{snapshots,cache,logs}/
├─ frontend/{index.html,style.css,app.js,vendor/echarts.min.js}
├─ tests/{conftest.py,fixtures/,test_*.py}
├─ docs/superpowers/{specs,plans}/
├─ requirements.txt · run.sh · README.md · pytest.ini
```

---

## 13. 实现里程碑
- **M1** 脚手架 + 网络层(fetch/ratelimit/retry/net/units) + 快照服务（含量能增减）+ `a_index`
- **M2** fetchers：`overseas` / `sentiment` / `northbound` / `sw_industry` / `sector_flow` / `capital`
- **M3** FastAPI + 深色前端 3 屏 + ECharts（Treemap/直方图/折线/柱）
- **M4** `run.sh`、README、联网冒烟、端到端验收

---

## 14. 风险与缓解
| 风险 | 缓解 |
|---|---|
| 东财 `clist/get` 硬封 | 主用新浪/同花顺/乐咕/交易所 + 东财 push2ex/datacenter |
| 频率封禁 | 限速 + 退避 + 缓存 + 旧快照降级 |
| 主力资金/深市两融不稳 | best-effort + 分区异常标注 |
| 无离岸 CNH | 中行美元牌价代理并标注 |
| 全A抓取慢(20s) | 每日快照 + `fetch` 缓存复用 |
| ECharts CDN 不可用 | 本地 vendor |
| akshare 字段变动 | 版本固定 + 解析容错 + fixture 测试 |

---

## 15. 决策记录
| # | 决策 | 理由 |
|---|---|---|
| 1 | 交付 B（FastAPI+前端），每日快照 | 用户选择 |
| 2 | 深色盘面风，红涨绿跌 | 用户选择 |
| 3 | 升级为 3 屏 + 情绪 + 概念主线 | 采纳专业复盘点评 |
| 4 | 强制 IPv4 | 东财 IPv6 出口被 RST |
| 5 | 不用东财 `clist/get` | 接口级硬封 |
| 6 | 涨停/跌停/炸板/连板走 `push2ex` | 实测可用 |
| 7 | 概念主线用同花顺 `stock_fund_flow_concept` | 387 概念，净额/领涨股 |
| 8 | 行业用同花顺 `stock_board_industry_summary_ths` | 含涨跌家数与净流入 |
| 9 | 申万一级用 Treemap | 全局空间感 |
| 10 | 涨跌分布/申万家数自算（`stock_zh_a_spot`） | 无需被封接口 |
| 11 | 汇率用中行美元牌价代理 | 无稳定 CNH 源 |
| 12 | 主力/两融 best-effort 入屏三 | 源不稳但可容错 |
| 13 | 量能增减 = 今日 vs 上一交易日快照 | 无历史时间序列源 |
| 14 | 北向降权为概览卡 | 2024 后北向披露弱化 |
| 15 | 不做历史浏览；走势 60 日；北向 30 日 | 用户裁定 |

---

## 16. 需求裁定（已确认）
| # | 问题 | 裁定 |
|---|---|---|
| 1 | 汇率 | 用中行美元牌价代理 |
| 2 | 主力资金/两融 | best-effort 纳入屏三 |
| 3 | 量能增减 | 今日 vs 上一交易日快照 |
| 4 | 走势周期 / 北向天数 | 60 日 / 30 日 |
| 5 | 历史快照浏览 | 不需要 |

## 17. 修订记录
- 2026-10-03 v1：核心五块，FastAPI + 深色前端 + 每日快照。
- 2026-10-03 v2：采纳复盘点评——新增情绪博弈（涨停/跌停/炸板率/连板/晋级率）、概念主线 Top、申万 Treemap 热图、涨跌分布直方图、放缩量增减、外围扩展（恒生/费半/汇率）、北向降权、主力/两融 best-effort；重排为 3 屏；fetcher 由 5 增至 7。

---

# v3 重构：按「交易工作流」重排（2026-10-03 追加）

## 18. v3 目标
摒弃"屏一/屏二/屏三"技术堆叠，改为顺应交易思考链的**工作区**布局：
`盘前风向 → 盘中大局与情绪 → 主线结构穿透 → 复盘笔记`。提升信息密度与决策穿透，去除冗余/失效模块。

## 19. v3 布局（覆盖 §8.2）

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 顶栏：交易日 | 两市成交额(较昨放量/缩量) | 沪深比+风格标签 | 情绪温度计(0-100) │
│                                                     [重新抓取]  数据源 x/8    │
├────────────────────────────────────────────────────────────────────────────┤
│ 工作区一 · 盘前外围映射                                                      │
│  [美股 道/纳/标] [费半] [恒生科技(中概代理)] [A50期指] [美元(中行代理)]      │
│  → 自动开盘预判一句话                                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ 工作区二 · 盘中/复盘 大局与情绪                                              │
│  [成交额+放缩量] [沪深比] [情绪温度]                                         │
│  [涨停/跌停/炸板率/最高连板]  [连板梯队迷你条]                               │
│  [大盘近60日 Sparkline(小)]  [涨跌分布单行堆叠条]                            │
├────────────────────────────────────────────────────────────────────────────┤
│ 工作区三 · 主线攻防（穿透）                                                  │
│  ┌ 行业榜(同花顺90, 涨幅/净流入Top|Bottom) ┐ ┌ 该行业个股(涨停/强势) ┐        │
│  │ 点击行业 → 中栏刷新                     │ │ 龙头: 连板/封板/换手 │        │
│  └────────────────────────────────────────┘ └─────────────────────┘        │
│  [概念资金流 Top10 净流入/流出（含领涨股）]  ← 仅概念级，不做概念→个股       │
├────────────────────────────────────────────────────────────────────────────┤
│ 工作区四 · 复盘笔记                                                          │
│  [自动三问三答: 市场性格 / 最强主线 / 抽血来源]                              │
│  [Markdown 笔记框] [保存(localStorage)] [导出 .md]                           │
├────────────────────────────────────────────────────────────────────────────┤
│ 资金补充：两融余额变化(沪) | 板块主力资金(同花顺净流入)                      │
└────────────────────────────────────────────────────────────────────────────┘
```

## 20. v3 数据模型增量
快照新增分区 `leaders`；`capital` 增加 `margin_history`；其余沿用 v2。

```jsonc
"leaders": {
  "as_of": "20260930",
  "by_industry": [
    { "industry": "生物制品",
      "stocks": [
        {"code":"688185","name":"康希诺","change_pct":20.0,"boards":1,"seal_time":"093000",
         "seal_amount":null,"turnover":9.32,"tag":"涨停"}
      ] }
  ],
  "boards_ladder": [ {"boards":1,"count":30}, {"boards":2,"count":12} ],
  "strong_pool_top": [ {"code":"301190","name":"善水科技","change_pct":20.0,"industry":"化学原料","tag":"60日新高"} ]
}
"capital": {
  "as_of": "...", "main_net_inflow": null, "margin_total": 9295.42,
  "margin_history": [ {"date":"2026-09-30","balance":9295.42} ],
  "notes": []
}
```
- `leaders` 来源：`stock_zt_pool_em`（涨停，含 `连板数/首次封板时间/封板资金/所属行业`）+ `stock_zt_pool_strong_em`（强势，含 `所属行业/入选理由`）。
- `by_industry`：把涨停/强势股按 `所属行业`（同花顺行业名）分组；左栏行业榜来自 `sector_flow.industries`，靠名称匹配。
- `margin_history`：`stock_margin_sse` 近 20 行 `融资融券余额`。

## 21. v3 前端计算（纯前端）
- **沪深比** = turnover.sh / (sh+sz)；标签：深市占比 >55% → "科技/进攻"，沪市占比 >45% 且银行权重 → "防守/避险"（简化为占比阈值）。
- **情绪温度** = clamp(50 + (limit_up - limit_down)*0.4 - zbgc_rate*100 + (max_boards-3)*4, 0, 100)。
- **开盘预判**：由 A50期指/恒生科技/费半涨跌幅合成一句话（正/负/分化）。
- **复盘三问**：
  - 市场性格：由沪深比 + 放缩量 生成（深强沪弱/沪强深弱 × 放量/缩量 → 进攻/存量博弈）。
  - 最强主线：sector_flow 净流入 Top1 行业 → 对应概念资金流 Top1。
  - 抽血来源：申万或同花顺行业涨跌幅 Bottom（如"大金融回调"）。
- **笔记**：`localStorage["review-note:<date>"]` 保存；导出为 `复盘-<date>.md`。

## 22. v3 降级与移除
- **移除**「北向近30日净买额折线」（数据不公布/空白）；北向仅保留概览卡或整块移除，UI 用两融+板块资金替代。
- **不做**「概念→个股」穿透（无成分源）；概念仅到"领涨股"。
- **代理并标注**：中概金龙 → 恒生科技；离岸 CNH → 中行美元。
- **不做**行业→概念映射（无映射源）；工作区三为"行业→个股"直接穿透。

## 23. v3 修订记录
- 2026-10-03 v3：按交易工作流重排为 4 工作区 + 顶栏；新增 `leaders` 分区（行业→个股+连板梯队）、`capital.margin_history`；前端新增 Sparkline/单行堆叠条/情绪温度/沪深比/复盘问答/localStorage 笔记；移除北向净买额折线；确认 4 项数据降级。

---

# v4 升级：资深股民四步复盘法（2026-10-03 追加）

## 24. v4 目标
补强"传导链 + 资金动态 + 梯队明细 + 资金拆分"，落实四步：看外围传导 → 算资金水位与情绪周期 → 选主线与梯队龙头 → 抓资金合力。

## 25. v4 数据模型增量
```jsonc
// overseas 增加
"us_sectors": [
  {"etf":"XLK","name":"信息技术","change_pct":0.8,"a_share":"半导体/算力/CPO"},
  {"etf":"SOX","name":"费城半导体","change_pct":2.4,"a_share":"芯片封测/半导体设备/CPO"}
  /* ... 11 GICS ETF + 费半 */
]

// a_index 增加
"ma": {"ma20":3810.0,"ma60":3700.0,"bias60":2.3},   // 基于 sh000001
"turnover": { /* 原字段 */ "ma5":14200.0,"ma10":13800.0 }

// leaders.boards_ladder 增加股票明细
"boards_ladder": [
  {"boards":4,"count":1,"stocks":[{"name":"XX","seal_time":"093100","tag":"涨停"}]},
  ...
]
// leaders.strong_pool_top 增加交易要素
"strong_pool_top": [
  {"code":"301190","name":"善水科技","price":35.93,"change_pct":20.0,
   "zt_stat":"3/3","turnover":7.95,"industry":"化学原料","tag":"60日新高且近期多次涨停"}
]

// capital 增加两融拆分 + 融资净买入 Top
"margin_history": [{"date":"2026-09-30","balance":13154.13,"fin_balance":13050.0,"sec_balance":104.13}],
"fin_buy_top": [{"code":"688185","name":"康希诺","net_buy":3.2}]
```

## 26. v4 前端布局（覆盖 v3 §19 的工作区一/二/三与资金补充）
- 工作区一：宽基卡片 + **美股 GICS 11 行业 + 费半**表格（列：行业 | 涨跌幅 | A股映射）；保留开盘预判。
- 工作区二：量能（值 + 较昨增减 + MA5/MA10）· 上证60日 **日K + MA20/MA60 + 乖离率** · **连板梯队卡片（几板：股票A 首封09:31、…）** · 涨跌分布条。
- 工作区三：行业榜 → 该行业涨停/强势个股；**强势股表增加 最新价 / 涨停统计 / 换手 / 入选理由**；概念资金流 Top。
- 资金面：**融资余额 vs 融券余额双线** + **融资净买入 Top10 个股**；北向改为「已停止披露」。

## 27. v4 降级
- 北向个股/持仓接口（`stock_hsgt_individual_em`/`hold_stock_em`）返回 None（2024 后停更）→ 移除，不展示空白。
- 5/10日均量无历史成交额序列 → 用已存快照逐日累积计算（数据不足时显示 `--`）。

## 28. v4 修订记录
- 2026-10-03 v4：新增美股 GICS 行业映射、量能均量对比、大盘均线乖离、连板梯队股票明细、强势股交易要素、两融拆分与融资净买入 Top；北向按停更移除。

---

# v5 布局重构：信息密度与杠杆/外资三表（2026-10-03 追加）

## 29. v5 布局调整
- **工作区一**：左右两列——左=外围指数卡片，右=美股行业映射表；区块内不产生页面级滚动。
- 移除工作区一底部"开盘预判"文案。
- **工作区二**：
  - 上排三栏：① 资金水位与交易风格（两市成交额/较上日增减/上涨下跌/涨停跌停）② 市场情绪温度计（gauge + 炸板率/突破新高/赚钱效应）③ 连板梯队与龙头（带股名、独立滚动）
  - 下排双栏：④ 大盘近60日(MA20/MA60) ⑤ 全市场涨跌分布梯度
- **资金面**：双 Y 轴两融折线（左=融资余额，右=融券余额）+ 概览卡（两融总余额/融资净买入(较前一日)/融券余额）+ 三表（融资净买入 Top10、融券卖出/余量 Top10、北向活跃成交 Top10）。

## 30. v5 数据增量
```jsonc
// leaders 增加
"new_high_count": 23,   // 强势股池中 是否新高=='是' 的数量

// capital 增加
"fin_net_today": 25.4,  // 融资净买入(较前一日) = Δ融资余额(亿)
"fin_buy_top": [{"code":"688008","name":"盛美上海","price":108.5,"change_pct":5.2,"net_buy":0.95}],
"fin_sell_top": [{"code":"...","name":"...","price":..,"change_pct":..,"sec_sell":..,"sec_balance":..}],
"northbound_active_top": []   // 无源（停更）；前端显示"已停止披露"
```
融资/融券明细的 price/change_pct 通过 `stock_zh_a_spot`（新浪全A，已缓存）按代码（去 sh/sz/bj 前缀）关联。

## 31. v5 降级
- 北向「活跃成交 Top10 / 前十大合计」无数据源（`stock_hsgt_individual_em` 仅单股历史；`hold_stock_em`/`board_rank_em`/`individual_detail_em` 返回 None）→ 该表显示"北向个股数据已停止披露"，保留北向净买额聚合卡。

## 32. v5 修订记录
- 2026-10-03 v5：工作区一/二重排、移除开盘预判、连板梯队带股名、情绪温度计补充指标；两融拆分为融资/融券双 Y 轴 + 三表（含代码/价格/涨跌幅）；北向个股按停更占位。

---

# v6 · 程序现状总览（接口清单 + 逻辑梳理，2026-10-04）

> 本章为**当前代码实况**（截至 tag/commit `6a516b0`），是理解本程序的总入口。前文 §1–32 为设计演进过程，本章为准。

## 33. 运行方式与总体架构

- 启动：`./run.sh`（`python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`）。
- 浏览器打开 `http://127.0.0.1:8000`。
- 数据流：
  ```
  akshare ─► 网络抓取层(core) ─► Fetcher(7 分区) ─► 快照服务(组装/清洗/落盘)
        ─► FastAPI(/api/snapshot.json) ─► 前端(app.js) ─► ECharts 渲染
  ```
- 目录：`backend/{core,fetchers,services,data}` · `frontend/{index.html,style.css,app.js,vendor/echarts.min.js}` · `tests/`。

## 34. 网络与抓取层（`backend/core/`）

| 模块 | 作用 |
|---|---|
| `net.force_ipv4()` | 全局只解析 IPv4（修复东财 IPv6 出口被 RST）；启动时调用一次、幂等 |
| `ratelimit.RateLimiter` | 按 `source` 维护最小请求间隔（默认 0.8s，`DASHBOARD_MIN_INTERVAL` 可调） |
| `retry.retry()` | 指数退避 + 抖动重试（默认 3 次，`DASHBOARD_RETRY_TIMES` 可调） |
| `fetch.fetch(fn, *args, source, use_cache=True)` | **唯一** akshare 调用入口：限速 + 重试 + 进程内缓存（缓存键含函数对象与参数，同一次快照内 `stock_zh_a_spot` 只抓一次） |
| `units.to_yi/pct` | 金额→亿元、数值规整；对 NaN 返回 `None`（保证 JSON 合法） |
| `logging` | 控制台 + `backend/data/logs/app.log` |

## 35. 数据源接口清单（已注册分区共 24 个唯一接口；另有 2 个未注册，见 §38）

### 分区① `overseas` 外围风向（6 个接口）
| akshare 接口 | 参数 | 用途 |
|---|---|---|
| `index_us_stock_sina` | `.DJI/.IXIC/.INX` | 美股三大指数收盘/涨跌幅 |
| `futures_global_spot_em` | — | A50期指当月连续、小型标普；**COMEX黄金(GC00Y)**、**NYMEX原油近月** |
| `stock_us_daily` | `XLK…XLRE`(GICS 11 ETF) | 美股行业涨跌幅（映射 A 股概念） |
| `stock_hk_index_spot_sina` | — | 恒生指数/恒生科技/国企/中资（取 HSI、HSTECH） |
| `macro_global_sox_index` | — | 费城半导体 |
| `currency_boc_sina` | `symbol="美元"` | 汇率代理（中行牌价 ÷100；假期取最近有效 `央行中间价`） |

### 分区② `a_index` A股指数 / 量能 / 涨跌分布（5 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_zh_index_spot_sina` | — | 指数实时点位/涨跌幅/成交额 |
| `stock_zh_index_daily` | `sh000001,sz399001,sz399006,sh000300,sh000852,sh000688,sz399303` | 近60日走势（含 MA20/MA60/乖离） |
| `stock_market_activity_legu` | — | 全市场上涨/下跌/涨停/跌停 |
| `stock_sse_deal_daily` | — | 沪市成交金额（行 `单日情况=="成交金额"`，列 `股票`） |
| `stock_zh_a_spot` | — | 全A行情（计算涨跌分布梯度） |

### 分区③ `sentiment` 情绪博弈（5 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_zh_index_daily` | `sh000001` | 取最近交易日 `YYYYMMDD` |
| `stock_zt_pool_em` | `date` | 涨停池：涨停数、最高连板、封板资金/时间、所属行业 |
| `stock_zt_pool_dtgc_em` | `date` | 跌停池：跌停数 |
| `stock_zt_pool_zbgc_em` | `date` | 炸板池 → 炸板率 = 炸板/(涨停+炸板) |
| `stock_zt_pool_previous_em` | `date` | 昨日涨停今日表现 → 晋级率 |

### 分区④ `leaders` 行业→个股 + 连板梯队（3 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_zh_index_daily` | `sh000001` | 最近交易日 |
| `stock_zt_pool_em` | `date` | 按 `所属行业` 分组个股 + 连板梯队(带股名) |
| `stock_zt_pool_strong_em` | `date` | 强势股池：最新价/涨停统计/换手/入选理由/是否新高 |

### 分区⑤ `northbound` 北向资金（2 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_hsgt_fund_flow_summary_em` | — | 北向（沪股通/深股通）净买额 + 涨跌家数 |
| `stock_hsgt_hist_em` | `symbol="北向资金"` | 近30日净买额趋势 |

### 分区⑥ `sector_flow` 概念 / 同花顺行业资金（2 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_fund_flow_concept` | `symbol="即时"` | 概念资金流（387 概念，净额/领涨股） |
| `stock_board_industry_summary_ths` | — | 同花顺行业(90)：涨跌幅/净流入/涨跌家数/领涨股 |

### 分区⑦ `capital` 两融 / 主力 / 融资净买入（6 个接口）
| 接口 | 参数 | 用途 |
|---|---|---|
| `stock_market_fund_flow` | — | 大盘主力净流入（best-effort，时通时断） |
| `stock_margin_sse` | `start_date,end_date`(近60天) | 融资余额/融券余额/两融总额（**默认 end_date 硬编码为 20230922，必须显式传区间**） |
| `stock_margin_szse` | — | 深市两融（best-effort，常失败） |
| `stock_zh_index_daily` | `sh000001` | 最近交易日 |
| `stock_margin_detail_sse` | `date` | 个股融资明细 → 融资净买入 Top10、融券卖出 Top10 |
| `stock_zh_a_spot` | — | 给融资/融券明细关联最新价/涨跌幅（缓存复用） |

## 36. 快照逻辑（`backend/services/snapshot.py`）

- `build_snapshot(fetchers, data_dir, date)`：逐个分区 `try/except` **错误隔离**，失败分区写 `{"error": ...}`，`sources[name]="error"`。
- **量能增减与均量**：`_attach_turnover_delta` 读取最近 10 个历史快照的总额 → 写 `turnover.prev_total/delta/ma5/ma10`（不足 5/10 天则为 `null`）。
- **NaN 兜底**：`_sanitize` 递归把 `NaN/Infinity` 转 `None`（避免 FastAPI 序列化 500）。
- **原子写**：`.tmp` → `os.replace`。
- **全失败不落盘**：若所有分区都是 `error`，不写文件并返回，便于下次重试（避免把一整天缓存成 502）。
- `get_or_create(force=False)`：命中当日缓存直接返回；`force=True` 强制重抓。

## 37. API 与前端

- 路由：`GET /`（index.html，**no-store**）、`GET /api/snapshot`、`POST /api/refresh`、`GET /healthz`、`/static/*`（**no-store**）；全部源失败与部分失败语义见 §7。
- 前端 5 个工作区（`frontend/app.js`）：
  1. **盘前外围映射**：外围指数（分「股市与期指」「港股/大宗/汇率」两组）+ 美股 GICS 行业映射表。
  2. **盘中/复盘 大局与情绪**：资金水位与交易风格（含 **今日风格偏好市值梯度条** 沪深300/创业板指/中证1000/国证2000）+ 情绪温度计（炸板率/突破新高/赚钱效应）+ 连板梯队与龙头（带股名）+ 上证近60日(MA20/MA60) + 涨跌分布。
  3. **主线攻防**：行业榜 → 点击 → 该行业涨停/强势个股 + 概念资金流 Top + 强势股 Top。
  4. **资金面**：两融双轴折线 + 概览卡 + 融资净买入/融券卖出/北向 三表。
  5. **复盘笔记**：自动三问三答 + Markdown 笔记（localStorage 保存 + 导出 .md）。
- 顶栏：交易日 · 两市成交额(放缩量) · 沪深比+风格 · 情绪温度 · 数据源 x/7 · 重新抓取。

## 38. 未注册 / 不可用接口

- **未注册（代码保留）**：`backend/fetchers/sw_industry.py`（`index_realtime_sw`、`index_component_sw`）——被 `sector_flow` 取代且较慢，未加入 `DEFAULT_FETCHERS`。
- **东财 `clist/get` 批量实时类（被 WAF 硬封，弃用）**：`stock_zh_a_spot_em`、`stock_us_spot_em`、`stock_zh_index_spot_em`、`stock_board_industry_name_em`、`stock_zt_pool_*_em`(实时列表口径) 等 → 改用新浪/同花顺/乐咕/交易所与东财 `push2ex`/`datacenter`。
- **北向个股停更（返回 None）**：`stock_hsgt_hold_stock_em`、`stock_hsgt_stock_statistics_em`、`stock_hsgt_individual_detail_em`、`stock_hsgt_board_rank_em` → 界面占位「已停止披露」。
- **无稳定源**：离岸人民币 CNH（用中行美元代理）、微盘股指数（用国证2000代理）、纳斯达克中国金龙 HXC（用恒生科技代理）。

## 39. 测试与版本

- 离线单元测试：`python3 -m pytest`（默认 `-m "not network"`）→ **49 passed**，零联网、约 1s。
- 联网冒烟：`python3 -m pytest -m network`（真实抓取 a_index）。
- 已提交历史：`7bbb706`(v3) → `3884a91`(tag v5, v4/v5) → `ac69a43`(外围分组+风格条) → `6a516b0`(禁缓存修复)。

## 40. v6 修订记录
- 2026-10-04 v6：新增「程序现状总览」——26 个接口清单（按分区/参数/用途）、网络层、快照逻辑、API/前端 5 工作区、未注册与不可用接口、测试与版本。
