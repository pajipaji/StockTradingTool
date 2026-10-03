# 股市脉搏看板 v3（交易工作流版）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 v2 的“三屏数据罗列”重构为顺应交易链的 4 工作区看板（盘前 → 大局情绪 → 主线穿透 → 复盘笔记），并补齐 `leaders`（行业→个股/连板梯队）与 `capital.margin_history`。

**Architecture:** 复用现有 akshare → 网络层 → fetchers → 快照 → FastAPI → 前端。后端新增 `leaders` 分区、`capital` 扩展；前端三大件（index.html/style.css/app.js）重写为顶栏 + 4 工作区 + 顶部指标自算 + 复盘问答 + localStorage 笔记。

**Tech Stack:** 同 v2（Python 3.9.6、akshare 1.18.88、FastAPI、原生前端、ECharts 本地）。

**Spec:** `docs/superpowers/specs/2026-10-03-stock-dashboard-design.md`（见 §18–23 v3 章节）

## Global Constraints
- 所有 akshare 调用经 `backend.core.fetch.fetch(fn, *args, source=..., use_cache=True)`；NaN 安全（`backend.core.units`）。
- Python 3.9.6：使用 `X | None` 的模块需 `from __future__ import annotations`；测试用 `python3 -m pytest` 从项目根运行。
- **无 git / 不提交**（用户要求）。
- 深色令牌不变：`--bg:#0e1117; --panel:#161b26; --panel-2:#1e2430; --border:#2a3141; --text:#e6e9ef; --text-muted:#8b93a7; --up:#ff4d4f; --down:#22c55e; --flat:#8b93a7; --accent:#3b82f6; --gold:#f5c451;`
- 快照分区键最终为 8 个：`overseas, a_index, sentiment, leaders, northbound, sw_industry, sector_flow, capital`。
- 工作区三为“行业→个股”穿透（非行业→概念→个股）；概念仅到领涨股。

---

## Task V1: `leaders` fetcher（行业→个股 + 连板梯队）

**Files:**
- Create: `backend/fetchers/leaders.py`
- Test: `tests/test_fetcher_leaders.py`

**Interfaces:**
- Produces: `fetch_leaders() -> dict`，键 `{as_of, by_industry[], boards_ladder[], strong_pool_top[]}`。
- 依赖：`stock_zh_index_daily`、`stock_zt_pool_em`、`stock_zt_pool_strong_em`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_leaders.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.leaders as mod
from backend.fetchers.leaders import fetch_leaders


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_leaders(monkeypatch):
    idx = pd.DataFrame([{"date": "2026-09-30", "open": 1, "high": 1, "low": 1, "close": 3800.0, "volume": 1}])
    zt = pd.DataFrame([
        {"代码": "002058", "名称": "紫竹高科", "涨跌幅": 10.02, "连板数": 2, "首次封板时间": "092500",
         "封板资金": 69384959, "换手率": 1.76, "所属行业": "电池"},
        {"代码": "002242", "名称": "九阳股份", "涨跌幅": 10.03, "连板数": 3, "首次封板时间": "093000",
         "封板资金": 164830000, "换手率": 4.58, "所属行业": "小家电"},
    ])
    strong = pd.DataFrame([
        {"代码": "301190", "名称": "善水科技", "涨跌幅": 20.0, "换手率": 7.9, "所属行业": "化学原料", "入选理由": "60日新高且近期多次涨停"},
        {"代码": "002058", "名称": "紫竹高科", "涨跌幅": 10.0, "换手率": 1.7, "所属行业": "电池", "入选理由": "60日新高"},
    ])

    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_strong_em", lambda date: strong)

    out = fetch_leaders()
    assert out["as_of"] == "20260930"
    inds = {g["industry"] for g in out["by_industry"]}
    assert "电池" in inds and "化学原料" in inds
    battery = next(g for g in out["by_industry"] if g["industry"] == "电池")
    assert battery["stocks"][0]["code"] == "002058" and battery["stocks"][0]["tag"] == "涨停"
    # 强势池中与涨停池重复的 002058 不该重复计入
    assert sum(1 for s in battery["stocks"] if s["code"] == "002058") == 1
    ladder = {d["boards"]: d["count"] for d in out["boards_ladder"]}
    assert ladder[2] == 1 and ladder[3] == 1
    assert any(s["code"] == "301190" for s in out["strong_pool_top"])
```

- [ ] **Step 2: 运行确认失败** — `python3 -m pytest tests/test_fetcher_leaders.py -v` → FAIL。

- [ ] **Step 3: 实现 `backend/fetchers/leaders.py`**

```python
from collections import Counter

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


def _latest_date() -> str:
    df = fetch(ak.stock_zh_index_daily, symbol="sh000001", source="sina")
    return str(df.iloc[-1]["date"]).replace("-", "")


def _stock_row(r, tag):
    return {
        "code": str(r["代码"]),
        "name": str(r["名称"]),
        "change_pct": _num(r.get("涨跌幅")),
        "boards": int(r["连板数"]) if r.get("连板数") == r.get("连板数") else None,
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
        counter = Counter(int(v) for v in zt["连板数"] if v == v)
        boards_ladder = [{"boards": b, "count": c} for b, c in sorted(counter.items())]

    strong_pool_top = []
    if len(strong):
        for _, r in strong.sort_values("涨跌幅", ascending=False).head(STRONG_TOP).iterrows():
            strong_pool_top.append({
                "code": str(r["代码"]), "name": str(r["名称"]),
                "change_pct": _num(r.get("涨跌幅")),
                "industry": str(r.get("所属行业", "")), "tag": str(r.get("入选理由", ""))[:20],
            })

    return {"as_of": date, "by_industry": by_industry_list,
            "boards_ladder": boards_ladder, "strong_pool_top": strong_pool_top}
```

- [ ] **Step 4: 运行确认通过** — `python3 -m pytest tests/test_fetcher_leaders.py -v` → PASS。

---

## Task V2: `capital` 增加 `margin_history`

**Files:**
- Modify: `backend/fetchers/capital.py`
- Test: `tests/test_fetcher_capital.py`（追加用例）

**Interfaces:**
- `fetch_capital()` 返回增加 `margin_history: [{date, balance}]`（近 20 个交易日）。

- [ ] **Step 1: 追加失败测试**（在 `tests/test_fetcher_capital.py` 末尾）

```python
def test_margin_history(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache(); fetchmod.LIMITER = RateLimiter(min_interval=0.0)
    import backend.fetchers.capital as cap

    def boom():
        raise RuntimeError("blocked")
    sse = pd.DataFrame([
        {"信用交易日期": "20260929", "融资融券余额": 1.90e12},
        {"信用交易日期": "20260930", "融资融券余额": 1.91e12},
    ])
    monkeypatch.setattr(cap.ak, "stock_market_fund_flow", boom)
    monkeypatch.setattr(cap.ak, "stock_margin_sse", lambda: sse)
    monkeypatch.setattr(cap.ak, "stock_margin_szse", boom)

    out = cap.fetch_capital()
    assert len(out["margin_history"]) == 2
    assert out["margin_history"][-1]["balance"] == 19100.0
    assert out["margin_total"] == 19100.0
```

- [ ] **Step 2: 运行确认失败** — `python3 -m pytest tests/test_fetcher_capital.py::test_margin_history -v` → FAIL（KeyError 'margin_history'）。

- [ ] **Step 3: 修改 `backend/fetchers/capital.py`** — 在 SSE 分支内构建 `margin_history`（近 20 行），并把它加入返回：

```python
    margin_total = None
    margin_history = []
    try:
        sse = fetch(ak.stock_margin_sse, source="sse")
        if not sse.empty:
            margin_total = to_yi(sse.iloc[-1].get("融资融券余额"))
            for _, r in sse.tail(20).iterrows():
                margin_history.append({"date": str(r["信用交易日期"]), "balance": to_yi(r["融资融券余额"])})
    except Exception as exc:
        notes.append(f"沪市两融获取失败: {exc}")
    ...
    return {"as_of": as_of, "main_net_inflow": main_net_inflow,
            "margin_total": margin_total, "margin_history": margin_history, "notes": notes}
```

- [ ] **Step 4: 运行确认通过** — `python3 -m pytest tests/test_fetcher_capital.py -v` → PASS。

---

## Task V3: API 注册 `leaders` 分区

**Files:**
- Modify: `backend/app.py`
- Modify: `tests/test_api.py`（如断言了分区键则更新；否则不改）

**Interfaces:**
- `DEFAULT_FETCHERS` 增加 `"leaders": fetch_leaders`。

- [ ] **Step 1: 修改 `backend/app.py`** — `from backend.fetchers.leaders import fetch_leaders`，并在 `DEFAULT_FETCHERS` 中 `sentiment` 之后加 `"leaders": fetch_leaders,`。

- [ ] **Step 2: 运行** — `python3 -m pytest tests/test_api.py -v` → PASS（build_app 注入测试不依赖具体键集合）。
- [ ] **Step 3: 全量** — `python3 -m pytest -v` → 全通过。

---

## Task V4: 前端骨架重排（`index.html`）

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 用下列内容替换 `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>股市脉搏 · 复盘工作台</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header class="topbar">
    <div class="brand">股市脉搏</div>
    <div class="tstat" id="tb-date">--</div>
    <div class="tstat" id="tb-turnover">成交额 --</div>
    <div class="tstat" id="tb-ratio">沪深比 --</div>
    <div class="tstat" id="tb-emotion">情绪 --</div>
    <div class="srcstatus" id="srcstatus"></div>
    <button id="refresh" class="btn">重新抓取</button>
  </header>

  <main>
    <section class="ws">
      <h2 class="ws-title">一 · 盘前外围映射</h2>
      <div class="cards" id="overseas-cards"></div>
      <div class="callout" id="premarket">--</div>
    </section>

    <section class="ws">
      <h2 class="ws-title">二 · 盘中/复盘 大局与情绪</h2>
      <div class="grid grid-3">
        <div class="panel"><h3>资金水位</h3><div class="cards" id="market-cards"></div></div>
        <div class="panel"><h3>市场情绪</h3><div class="chart gauge" id="chart-emotion"></div></div>
        <div class="panel"><h3>连板梯队</h3><div class="chart ladder" id="chart-ladder"></div></div>
      </div>
      <div class="grid grid-2">
        <div class="panel"><h3>大盘近60日</h3><div class="chart spark" id="chart-spark"></div></div>
        <div class="panel"><h3>涨跌分布</h3><div class="chart dist" id="chart-dist"></div></div>
      </div>
    </section>

    <section class="ws">
      <h2 class="ws-title">三 · 主线攻防（行业 → 个股）</h2>
      <div class="grid grid-3">
        <div class="panel"><h3>行业榜（同花顺）</h3>
          <div class="table-wrap short"><table id="industry-table"></table></div></div>
        <div class="panel"><h3>该行业涨停/强势个股 <span id="ind-name" class="muted"></span></h3>
          <div class="table-wrap short"><table id="industry-stocks"></table></div></div>
        <div class="panel"><h3>概念资金流 Top</h3>
          <div class="table-wrap short"><table id="concept-table"></table></div></div>
      </div>
      <div class="panel"><h3>强势股 Top（60日新高/多板）</h3>
        <div class="table-wrap short"><table id="strong-table"></table></div></div>
    </section>

    <section class="ws">
      <h2 class="ws-title">四 · 复盘笔记</h2>
      <div class="grid grid-2">
        <div class="panel"><h3>自动复盘</h3><div id="review-qa" class="qa"></div></div>
        <div class="panel"><h3>我的笔记</h3>
          <textarea id="note" placeholder="今天的交易心得…"></textarea>
          <div class="note-actions">
            <span id="note-status" class="muted"></span>
            <button class="mini-btn" id="note-save">保存</button>
            <button class="mini-btn" id="note-export">导出 .md</button>
          </div>
        </div>
      </div>
    </section>

    <section class="ws">
      <h2 class="ws-title">资金补充</h2>
      <div class="grid grid-2">
        <div class="panel"><h3>两融余额（近20日）</h3><div class="chart spark" id="chart-margin"></div></div>
        <div class="panel"><h3>主力/两融概览</h3><div class="cards" id="capital-cards"></div></div>
      </div>
    </section>
  </main>

  <div class="overlay" id="overlay">正在抓取数据，请稍候…</div>
  <script src="/static/vendor/echarts.min.js"></script>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 运行** — `python3 -m pytest tests/test_frontend_assets.py -v`（apps.js/style 已存在的旧断言仍应满足：引用 style.css、echarts 早于 app.js、11 令牌）。

---

## Task V5: 前端样式重排（`style.css`）

**Files:**
- Modify: `frontend/style.css`

- [ ] **Step 1: 用下列内容替换 `frontend/style.css`**

```css
:root {
  --bg:#0e1117; --panel:#161b26; --panel-2:#1e2430; --border:#2a3141;
  --text:#e6e9ef; --text-muted:#8b93a7; --up:#ff4d4f; --down:#22c55e;
  --flat:#8b93a7; --accent:#3b82f6; --gold:#f5c451;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
.topbar { display:flex; align-items:center; gap:14px; padding:10px 20px;
  background:var(--panel); border-bottom:1px solid var(--border);
  position:sticky; top:0; z-index:10; flex-wrap:wrap; }
.brand { font-size:17px; font-weight:700; color:var(--gold); letter-spacing:2px; }
.tstat { font-size:13px; color:var(--text-muted); font-variant-numeric:tabular-nums; }
.tstat b { color:var(--text); }
.srcstatus { margin-left:auto; font-size:12px; color:var(--text-muted); }
.btn { background:var(--accent); color:#fff; border:none; padding:6px 14px;
  border-radius:6px; cursor:pointer; font-size:13px; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
main { padding:14px 20px 60px; display:flex; flex-direction:column; gap:16px; }
.ws { border:1px solid var(--border); border-radius:10px; padding:12px 16px; background:var(--panel); }
.ws-title { margin:0 0 12px; font-size:14px; color:var(--accent); letter-spacing:1px; }
.grid { display:grid; gap:12px; margin-bottom:12px; }
.grid-2 { grid-template-columns:repeat(2,minmax(0,1fr)); }
.grid-3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
@media (max-width:1100px){ .grid-2,.grid-3{ grid-template-columns:1fr; } }
.panel { background:var(--panel-2); border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.panel h3 { margin:0 0 10px; font-size:13px; font-weight:600; color:var(--gold);
  display:flex; align-items:center; gap:8px; }
.cards { display:flex; flex-wrap:wrap; gap:8px; }
.card { background:#121722; border:1px solid var(--border); border-radius:8px; padding:8px 12px; min-width:126px; }
.card .name { color:var(--text-muted); font-size:12px; margin-bottom:3px; }
.card .val { font-size:18px; font-weight:700; font-variant-numeric:tabular-nums; }
.card .sub { font-size:12px; margin-top:1px; font-variant-numeric:tabular-nums; }
.callout { margin-top:10px; padding:10px 12px; border-left:3px solid var(--accent);
  background:#121722; border-radius:6px; font-size:13px; line-height:1.7; }
.chart { width:100%; height:180px; }
.chart.spark { height:150px; }
.chart.dist { height:130px; }
.chart.gauge { height:200px; }
.chart.ladder { height:200px; }
.table-wrap { max-height:360px; overflow:auto; }
.table-wrap.short { max-height:300px; }
table { width:100%; border-collapse:collapse; font-size:12.5px; font-variant-numeric:tabular-nums; }
th,td { padding:5px 8px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th { position:sticky; top:0; background:var(--panel-2); color:var(--text-muted); font-weight:500; }
th:first-child, td:first-child { text-align:left; }
tr.clickable { cursor:pointer; }
tr.clickable:hover td { background:#222a38; }
tr.selected td { background:#1c2740; }
.up{color:var(--up);} .down{color:var(--down);} .flat{color:var(--flat);} .muted{color:var(--text-muted);}
.error{color:var(--up);}
.qa { font-size:13px; line-height:1.9; }
.qa b { color:var(--gold); }
textarea#note { width:100%; min-height:150px; background:#121722; color:var(--text);
  border:1px solid var(--border); border-radius:6px; padding:10px; font-family:inherit; font-size:13px; resize:vertical; }
.note-actions { display:flex; align-items:center; gap:8px; margin-top:8px; }
.note-actions .muted { margin-right:auto; font-size:12px; }
.mini-btn { background:var(--panel-2); color:var(--text); border:1px solid var(--border);
  border-radius:5px; padding:4px 10px; cursor:pointer; font-size:12px; }
.mini-btn:hover { border-color:var(--accent); }
.overlay { position:fixed; inset:0; background:rgba(14,17,23,.78); color:var(--text);
  display:none; align-items:center; justify-content:center; font-size:15px; z-index:20; }
.overlay.show { display:flex; }
```

- [ ] **Step 2: 运行** — `python3 -m pytest tests/test_frontend_assets.py -v` → PASS。

---

## Task V6: 前端逻辑重写（`app.js`）

**Files:**
- Modify: `frontend/app.js`

- [ ] **Step 1: 用下列内容替换 `frontend/app.js`**

```javascript
const state = { charts:{}, snap:null, selectedIndustry:null };
const AXIS = { axisLine:{lineStyle:{color:"#2a3141"}}, splitLine:{lineStyle:{color:"#1e2430"}} };

function cls(v){ return v>0?"up":v<0?"down":"flat"; }
function num(v){ return Number.isFinite(Number(v)) ? Number(v) : null; }
function fmt(v,d=2){ const n=num(v); return n===null?"--":n.toFixed(d); }
function fmtPct(v){ const n=num(v); return n===null?"--":`${n>0?"+":""}${n.toFixed(2)}%`; }
function fmtYi(v){ const n=num(v); return n===null?"--":`${n.toLocaleString("zh-CN",{maximumFractionDigits:2})} 亿`; }
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function card(name,value,sub,klass=""){ return `<div class="card"><div class="name">${esc(name)}</div>
  <div class="val ${klass}">${value}</div><div class="sub ${klass}">${sub||""}</div></div>`; }
function err(m){ return `<span class="error">⚠ 数据源异常：${esc(m)}</span>`; }
function chart(id){ if(state.charts[id]) state.charts[id].dispose();
  state.charts[id]=echarts.init(document.getElementById(id),"dark"); return state.charts[id]; }

/* 顶栏 */
function emotionScore(s){
  if(!s || s.error || s.limit_up==null) return null;
  const up=num(s.limit_up)||0, dn=num(s.limit_down)||0,
        zb=num(s.zbgc_rate)||0, mb=num(s.max_boards)||0;
  let v = 50 + (up-dn)*0.4 - zb*100 + (mb-3)*4;
  return Math.max(0, Math.min(100, Math.round(v)));
}
function renderTopbar(snap){
  const a=snap.a_index||{}, t=a.turnover||{}, st=snap.sentiment||{};
  document.getElementById("tb-date").textContent = `交易日 ${snap.date||"--"}`;
  let turn = "成交额 --";
  if(num(t.total)!==null){
    const d=num(t.delta);
    turn = `成交额 <b>${fmtYi(t.total)}</b>` + (d===null?"":`（${d>0?"放量":"缩量"} ${fmtYi(Math.abs(d))}）`);
  }
  document.getElementById("tb-turnover").innerHTML = turn;
  let ratio="沪深比 --";
  if(num(t.sh)!==null && num(t.sz)!==null && (t.sh+t.sz)>0){
    const shp=Math.round(t.sh/(t.sh+t.sz)*100), szp=100-shp;
    const style = szp>=55 ? "科技/进攻" : (shp>=50 ? "防守/避险" : "均衡");
    ratio = `沪深比 <b>${shp}:${szp}</b> · ${style}`;
  }
  document.getElementById("tb-ratio").innerHTML = ratio;
  const e=emotionScore(st);
  document.getElementById("tb-emotion").innerHTML = e===null?"情绪 --":`情绪 <b>${e}</b>${e>=70?" 亢奋":e<=30?" 冰点":""}`;
  const src=snap.sources||{};
  document.getElementById("srcstatus").textContent = `数据源 ${Object.values(src).filter(v=>v==="ok").length}/${Object.keys(src).length} ok`;
}

/* 工作区一 */
function renderOverseas(s){
  const box=document.getElementById("overseas-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  let html="";
  (s.us_indices||[]).forEach(i=>html+=card(i.name,fmt(i.close),fmtPct(i.change_pct),cls(i.change_pct)));
  (s.futures||[]).forEach(f=>html+=card(f.name,fmt(f.price),fmtPct(f.change_pct),cls(f.change_pct)));
  (s.hk_indices||[]).filter(h=>h.code==="HSTECH"||h.code==="HSI").forEach(h=>html+=card(h.name+"(代理)",fmt(h.price),fmtPct(h.change_pct),cls(h.change_pct)));
  if(s.sox&&num(s.sox.value)!==null) html+=card("费城半导体",fmt(s.sox.value),fmtPct(s.sox.change_pct),cls(s.sox.change_pct));
  if(s.usd_cny&&num(s.usd_cny.mid)!==null) html+=card("美元(中行代理)",fmt(s.usd_cny.mid,4),"", "");
  box.innerHTML=html;

  const by={}; (s.futures||[]).forEach(f=>by[f.name]=num(f.change_pct));
  const a50=by["A50期指当月连续"];
  const hst=(s.hk_indices||[]).find(h=>h.code==="HSTECH");
  const sox=num(s.sox&&s.sox.change_pct);
  const parts=[]; if(a50!==null)parts.push(`A50期指 ${fmtPct(a50)}`);
  if(hst)parts.push(`恒生科技(代理) ${fmtPct(hst.change_pct)}`); if(sox!==null)parts.push(`费半 ${fmtPct(sox)}`);
  const sig=[a50,sox,hst?num(hst.change_pct):null].filter(v=>v!==null);
  const net = sig.length? sig.reduce((x,y)=>x+y,0)/sig.length : null;
  const mood = net===null?"外围数据不足": net>0.3?"外围偏暖，A股开盘有望高开": net<-0.3?"外围偏冷，防低开": "外围分化，开盘看资金选择";
  document.getElementById("premarket").innerHTML = `${parts.join(" · ")} → <b>${mood}</b>`;
}

/* 工作区二 */
function renderMarket(s){
  const box=document.getElementById("market-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  const t=s.turnover||{}, b=s.breadth||{};
  const d=num(t.delta);
  box.innerHTML =
    card("两市成交额",fmtYi(t.total), d===null?"":`${d>0?"放量":"缩量"} ${fmtYi(Math.abs(d))}`) +
    card("上涨/下跌",`${b.up??"--"}/${b.down??"--"}`,"") +
    card("涨停/跌停",`${b.limit_up??"--"}/${b.limit_down??"--"}`,"");
}
function renderLadder(s){
  if(s.error||!s.boards_ladder) return;
  const d=s.boards_ladder||[];
  chart("chart-ladder").setOption({
    tooltip:{trigger:"axis"}, grid:{left:36,right:12,top:10,bottom:22},
    xAxis:{type:"category",data:d.map(x=>`${x.boards}板`),...AXIS},
    yAxis:{type:"value",...AXIS},
    series:[{type:"bar",data:d.map(x=>x.count),itemStyle:{color:"#f5c451"}}]
  });
}
function renderEmotion(s){
  if(s.error) return;
  const e=emotionScore(s);
  chart("chart-emotion").setOption({
    series:[{type:"gauge",min:0,max:100,startAngle:210,endAngle:-30,radius:"92%",
      axisLine:{lineStyle:{width:12,color:[[0.3,"#22c55e"],[0.7,"#f5c451"],[1,"#ff4d4f"]]}},
      pointer:{itemStyle:{color:"#e6e9ef"}}, axisTick:{show:false}, splitLine:{length:10,lineStyle:{color:"#2a3141"}},
      axisLabel:{color:"#8b93a7",distance:14,fontSize:10}, detail:{valueAnimation:true,color:"#e6e9ef",fontSize:22,offsetCenter:[0,"58%"],formatter:"{value}"},
      title:{offsetCenter:[0,"85%"],color:"#8b93a7",fontSize:12},
      data:[{value:e===null?0:e,name:"情绪温度"}]}]
  });
}
function renderSpark(s){
  const hist=(s.history&&s.history["sh000001"])||[];
  chart("chart-spark").setOption({
    tooltip:{trigger:"axis"}, grid:{left:44,right:10,top:10,bottom:20},
    xAxis:{type:"category",data:hist.map(h=>h.date),...AXIS,axisLabel:{show:false}},
    yAxis:{type:"value",scale:true,...AXIS},
    series:[{type:"line",data:hist.map(h=>h.close),smooth:true,showSymbol:false,lineStyle:{color:"#3b82f6",width:2},areaStyle:{color:"rgba(59,130,246,.15)"}}]
  });
}
function renderDist(s){
  const dist=(s.breadth&&s.breadth.distribution)||[];
  chart("chart-dist").setOption({
    tooltip:{trigger:"axis"}, grid:{left:36,right:10,top:10,bottom:22},
    xAxis:{type:"category",data:dist.map(d=>d.label),...AXIS,axisLabel:{fontSize:10,color:"#8b93a7"}},
    yAxis:{type:"value",...AXIS,axisLabel:{fontSize:10}},
    series:[{type:"bar",data:dist.map(d=>({value:d.count,itemStyle:{color:(d.label.startsWith("-")||d.label.startsWith("≤"))?"#22c55e":"#ff4d4f"}}))}]
  });
}

/* 工作区三 */
function renderIndustries(snap){
  const sf=snap.sector_flow||{}, sw=snap.sw_industry||{}, ld=snap.leaders||{};
  const t=document.getElementById("industry-table");
  if(sf.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(sf.error)}</td></tr></tbody>`; return; }
  const inds=(sf.industries||[]).slice(0,30);
  if(!state.selectedIndustry && inds.length) state.selectedIndustry = inds[0].name;
  const rows=inds.map(i=>`<tr class="clickable ${i.name===state.selectedIndustry?"selected":""}" data-ind="${esc(i.name)}">
    <td>${esc(i.name)}</td><td class="${cls(i.change_pct)}">${fmtPct(i.change_pct)}</td>
    <td class="${cls(i.net_inflow)}">${fmt(i.net_inflow)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>行业</th><th>涨幅</th><th>净流入(亿)</th></tr></thead><tbody>${rows}</tbody>`;
  t.querySelectorAll("tr.clickable").forEach(tr=>tr.addEventListener("click",()=>{
    state.selectedIndustry=tr.dataset.ind; renderIndustries(state.snap); renderIndustryStocks(state.snap);
  }));
  renderIndustryStocks(snap);
  renderConcepts(snap);
  renderStrong(snap);
}
function renderIndustryStocks(snap){
  const ld=snap.leaders||{}, name=state.selectedIndustry;
  document.getElementById("ind-name").textContent = name?`· ${name}`:"";
  const t=document.getElementById("industry-stocks");
  if(ld.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(ld.error)}</td></tr></tbody>`; return; }
  const group=(ld.by_industry||[]).find(g=>g.industry===name);
  const stocks=group?group.stocks:[];
  if(!stocks.length){ t.innerHTML=`<tbody><tr><td class="muted">该行业今日无涨停/强势股</td></tr></tbody>`; return; }
  const rows=stocks.map(s=>`<tr><td>${esc(s.name)}</td><td class="up">${fmtPct(s.change_pct)}</td>
    <td>${s.boards??"--"}</td><td>${esc(s.tag)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>个股</th><th>涨幅</th><th>连板</th><th>标签</th></tr></thead><tbody>${rows}</tbody>`;
}
function renderConcepts(snap){
  const sf=snap.sector_flow||{}, t=document.getElementById("concept-table");
  if(sf.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(sf.error)}</td></tr></tbody>`; return; }
  const cs=(sf.concepts||[]).slice(0,10);
  const bottom=(sf.concepts||[]).slice(-10).reverse();
  const row=c=>`<tr><td>${esc(c.name)}</td><td class="${cls(c.change_pct)}">${fmtPct(c.change_pct)}</td>
    <td class="${cls(c.net_inflow)}">${fmt(c.net_inflow)}</td><td>${esc(c.leader)}</td></tr>`;
  t.innerHTML=`<thead><tr><th>概念</th><th>涨幅</th><th>净额</th><th>领涨股</th></tr></thead><tbody>`+
    `<tr><td colspan="4" class="up">净流入 Top10</td></tr>${cs.map(row).join("")}`+
    `<tr><td colspan="4" class="down">净流出 Top10</td></tr>${bottom.map(row).join("")}</tbody>`;
}
function renderStrong(snap){
  const ld=snap.leaders||{}, t=document.getElementById("strong-table");
  if(ld.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(ld.error)}</td></tr></tbody>`; return; }
  const rows=(ld.strong_pool_top||[]).map(s=>`<tr><td>${esc(s.name)}</td><td class="up">${fmtPct(s.change_pct)}</td>
    <td>${esc(s.industry)}</td><td class="muted">${esc(s.tag)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>个股</th><th>涨幅</th><th>行业</th><th>入选理由</th></tr></thead><tbody>${rows}</tbody>`;
}

/* 工作区四 */
function renderReview(snap){
  const a=snap.a_index||{}, t=a.turnover||{}, st=snap.sentiment||{}, sf=snap.sector_flow||{};
  const shp=(num(t.sh)!==null&&num(t.sz)!==null&&(t.sh+t.sz)>0)?Math.round(t.sh/(t.sh+t.sz)*100):null;
  const d=num(t.delta);
  let char="数据不足";
  if(shp!==null){
    const who = shp<45?"深强沪弱":(shp>55?"沪强深弱":"均衡");
    const amt = d===null?"":(d>0?"放量":d<0?"缩量":"平量");
    char = `${who}，${amt}` + (who==="深强沪弱"?"（资金偏科技进攻）":who==="沪强深弱"?"（资金偏权重防守）":"");
  }
  const up=(sf.industries||[])[0], topc=(sf.concepts||[])[0];
  const main = up?`${up.name}（${fmtPct(up.change_pct)}）`+(topc?` · 概念先锋：${topc.name}`:""):"数据不足";
  const inds=(sf.industries||[]); const bottom=inds.length?inds[inds.length-1]:null;
  const drain = bottom?`${bottom.name}（${fmtPct(bottom.change_pct)}）`:"数据不足";
  document.getElementById("review-qa").innerHTML =
    `<div><b>市场性格：</b>${esc(char)}</div>`+
    `<div><b>最强主线：</b>${esc(main)}</div>`+
    `<div><b>抽血来源：</b>${esc(drain)}</div>`;
}

/* 资金补充 */
function renderCapital(snap){
  const box=document.getElementById("capital-cards");
  const s=snap.capital||{};
  if(s.error){ box.innerHTML=err(s.error); return; }
  box.innerHTML =
    card("主力净流入", s.main_net_inflow==null?"--":`${s.main_net_inflow>0?"+":""}${fmtYi(s.main_net_inflow)}`, "", cls(s.main_net_inflow))+
    card("两融余额", fmtYi(s.margin_total), "");
  const h=s.margin_history||[];
  if(h.length) chart("chart-margin").setOption({
    tooltip:{trigger:"axis"}, grid:{left:56,right:10,top:10,bottom:20},
    xAxis:{type:"category",data:h.map(x=>x.date),...AXIS,axisLabel:{show:false}},
    yAxis:{type:"value",scale:true,...AXIS},
    series:[{type:"line",data:h.map(x=>x.balance),showSymbol:false,lineStyle:{color:"#f5c451",width:2}}]
  });
}

/* 笔记 */
function noteKey(){ return "review-note:"+((state.snap&&state.snap.date)||"unknown"); }
function loadNote(){ const ta=document.getElementById("note");
  ta.value=localStorage.getItem(noteKey())||""; document.getElementById("note-status").textContent=""; }
function saveNote(){ localStorage.setItem(noteKey(),document.getElementById("note").value);
  document.getElementById("note-status").textContent="已保存 "+new Date().toLocaleTimeString("zh-CN"); }
function exportNote(){
  const date=(state.snap&&state.snap.date)||"note";
  const text=`# 复盘 ${date}\n\n`+document.getElementById("note").value;
  const blob=new Blob([text],{type:"text/markdown"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=`复盘-${date}.md`; a.click();
}

function renderAll(snap){
  state.snap=snap;
  renderTopbar(snap);
  renderOverseas(snap.overseas||{});
  renderMarket(snap.a_index||{});
  renderEmotion(snap.sentiment||{});
  renderLadder(snap.sentiment||{});
  renderSpark(snap.a_index||{});
  renderDist(snap.a_index||{});
  renderIndustries(snap);
  renderReview(snap);
  renderCapital(snap);
  loadNote();
}

async function load(force){
  const overlay=document.getElementById("overlay"), btn=document.getElementById("refresh");
  overlay.classList.add("show"); btn.disabled=true;
  try {
    const res=force?await fetch("/api/refresh",{method:"POST"}):await fetch("/api/snapshot");
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    renderAll(await res.json());
  } catch(e){ document.getElementById("tb-date").textContent=`加载失败：${e.message}`; }
  finally { overlay.classList.remove("show"); btn.disabled=false; }
}

document.getElementById("refresh").addEventListener("click",()=>load(true));
document.getElementById("note-save").addEventListener("click",saveNote);
document.getElementById("note-export").addEventListener("click",exportNote);
window.addEventListener("resize",()=>Object.values(state.charts).forEach(c=>c.resize()));
load(false);
```

- [ ] **Step 2: 语法与测试** — `node --check frontend/app.js` → OK；`python3 -m pytest tests/ -v` → 全通过。

---

## Task V7: 前端资源测试更新 + 端到端验收

**Files:**
- Modify: `tests/test_frontend_assets.py`（断言新 id/结构）
- 验证：全量测试 + 真实服务

- [ ] **Step 1: 更新 `tests/test_frontend_assets.py`** — 追加断言 index.html 含新工作区标记：`"盘前外围映射"`、`"主线攻防"`、`"复盘笔记"`、`id="note"`、`id="chart-emotion"`。

- [ ] **Step 2: 全量测试** — `python3 -m pytest -v` → 全通过。

- [ ] **Step 3: 端到端** — 重启服务 `pkill -f "uvicorn backend.app:app"; nohup python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 >/tmp/uv.log 2>&1 &`；`curl -X POST localhost:8000/api/refresh` → 200；`curl localhost:8000/api/snapshot` → 200，且 JSON 严格可解析、`sources` 含 `leaders`；前端静态资源 200。

---

## 自检
- 覆盖 v3 spec §18–23：布局 §19 → V4/V5；`leaders` §20 → V1；`capital.margin_history` → V2；前端计算 §21 → V6；降级 §22（移除北向折线、行业→个股、代理标注）→ V4/V6。
- 分区键 8 个：overseas/a_index/sentiment/leaders/northbound/sw_industry/sector_flow/capital（V3 注册、V6 消费）。
- 无占位符；前端含完整代码。
