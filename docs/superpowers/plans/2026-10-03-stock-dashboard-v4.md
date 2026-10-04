# 股市脉搏看板 v4 实现计划（资深股民四步复盘法）

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** 在 v3 基础上补强：①美股 GICS 行业映射 ②量能对比+均量+大盘均线乖离 ③连板梯队股票明细+强势股交易要素 ④两融拆分+融资净买入 Top；北向按停更移除。

**Architecture:** 复用现有 akshare→网络层→fetchers→快照→FastAPI→前端。后端改 4 个 fetcher + 快照服务；前端三件重写对应区块。

**Tech Stack:** Python 3.9.6、akshare 1.18.88、FastAPI、原生前端 + 本地 ECharts。

**Spec:** `docs/superpowers/specs/2026-10-03-stock-dashboard-design.md`（§24–28）

## Global Constraints
- akshare 调用一律经 `backend.core.fetch.fetch(...)`；金额统一亿元（`to_yi`）；涨跌幅为百分比数值。
- Python 3.9.6（含 `X | None` 的模块需 `from __future__ import annotations`）；`python3 -m pytest` 从项目根运行。
- **无 git / 不提交**。
- 深色令牌与 v3 相同。快照分区键保持 7 个（overseas/a_index/sentiment/leaders/northbound/sector_flow/capital）。

---

## Task U1: `overseas` 增加美股行业映射 `us_sectors`

**Files:** Modify `backend/fetchers/overseas.py`; Test `tests/test_fetcher_overseas.py`（追加）

**Interfaces:** `fetch_overseas()` 返回增加 `us_sectors: [{etf,name,change_pct,a_share}]`（11 GICS + SOX）。

- [ ] **Step 1: 追加失败测试**

```python
def test_us_sectors(monkeypatch):
    import backend.fetchers.overseas as m
    import backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    import pandas as pd
    def daily(symbol):
        return pd.DataFrame([{"date":"2026-10-01","open":1,"high":1,"low":1,"close":100.0,"volume":1},
                             {"date":"2026-10-02","open":1,"high":1,"low":1,"close":102.0,"volume":1}])
    monkeypatch.setattr(m.ak,"index_us_stock_sina", lambda symbol: daily(symbol))
    monkeypatch.setattr(m.ak,"futures_global_spot_em", lambda: pd.DataFrame([{"代码":"CN00Y","名称":"A50期指当月连续","最新价":1.0,"涨跌幅":0.1}]))
    monkeypatch.setattr(m.ak,"stock_hk_index_spot_sina", lambda: pd.DataFrame([{"代码":"HSI","名称":"恒生指数","最新价":1.0,"涨跌幅":-1.0}]))
    monkeypatch.setattr(m.ak,"macro_global_sox_index", lambda: pd.DataFrame([{"日期":"2026-10-02","最新值":100.0,"涨跌幅":2.4}]))
    monkeypatch.setattr(m.ak,"currency_boc_sina", lambda **k: pd.DataFrame([{"日期":"2026-10-03","央行中间价":7.1}]))
    monkeypatch.setattr(m.ak,"stock_us_daily", daily)
    out = m.fetch_overseas()
    etfs = {s["etf"] for s in out["us_sectors"]}
    assert "XLK" in etfs and "XLV" in etfs and "SOX" in etfs
    xlk = next(s for s in out["us_sectors"] if s["etf"] == "XLK")
    assert xlk["change_pct"] == 2.0 and xlk["a_share"]
```

- [ ] **Step 2: 运行确认失败** — `python3 -m pytest tests/test_fetcher_overseas.py::test_us_sectors -v` → FAIL。

- [ ] **Step 3: 实现** — 在 `overseas.py` 增加常量与函数，并在 `fetch_overseas` 返回中加入 `us_sectors`：

```python
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
```

在 `fetch_overseas` 里 `sox` 计算之后：

```python
    sectors = _us_sectors()
    if sox and sox.get("change_pct") is not None:
        sectors.append({"etf": "SOX", "name": "费城半导体",
                        "change_pct": sox.get("change_pct"), "a_share": "芯片封测/半导体设备/CPO"})
```

返回 dict 增加 `"us_sectors": sectors`。

- [ ] **Step 4: 运行确认通过** — `python3 -m pytest tests/test_fetcher_overseas.py -v` → PASS。

---

## Task U2: `a_index` 均线乖离 + 快照算量能 MA5/MA10

**Files:** Modify `backend/fetchers/a_index.py`、`backend/services/snapshot.py`；Test `tests/test_fetcher_a_index.py`、`tests/test_snapshot.py`（追加）

**Interfaces:** `a_index` 返回增加 `ma:{ma20,ma60,bias60}`（基于 sh000001）；快照 `a_index.turnover` 增加 `ma5`、`ma10`。

- [ ] **Step 1: 追加失败测试（a_index）**

```python
def test_ma(monkeypatch):
    import backend.fetchers.a_index as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    n = 70
    hist = pd.DataFrame([{"date": f"2026-0{1+(i//28)}-{1+i%28:02d}", "open": 1, "high": 1, "low": 1,
                          "close": float(100 + i), "volume": 1} for i in range(n)])
    monkeypatch.setattr(m.ak, "stock_zh_index_spot_sina", lambda: pd.DataFrame([{"代码":"sh000001","名称":"上证指数","最新价":169.0,"涨跌额":1,"涨跌幅":1,"成交量":1,"成交额":1}]))
    monkeypatch.setattr(m.ak, "stock_zh_index_daily", lambda symbol: hist)
    monkeypatch.setattr(m.ak, "stock_market_activity_legu", lambda: pd.DataFrame([{"item":"上涨","value":1}]))
    monkeypatch.setattr(m.ak, "stock_sse_deal_daily", lambda: pd.DataFrame([{"单日情况":"成交金额","股票":1.0}]))
    monkeypatch.setattr(m.ak, "stock_zh_a_spot", lambda: pd.DataFrame([{"代码":"sz000001","涨跌幅":1.0}]))
    out = m.fetch_a_index()
    # closes 100..169, ma20 = mean(150..169)=159.5, ma60=mean(110..169)=139.5
    assert out["ma"]["ma20"] == 159.5
    assert out["ma"]["ma60"] == 139.5
    assert out["ma"]["bias60"] is not None
```

- [ ] **Step 2: 运行确认失败** — FAIL。

- [ ] **Step 3: 实现 `a_index.py`** — 增加 `_ma` 并在返回前计算：

```python
def _ma(values, n):
    if len(values) < n:
        return None
    return round(sum(values[-n:]) / n, 2)
```

在 `prev_date` 计算附近：

```python
    ma = {"ma20": None, "ma60": None, "bias60": None}
    if history.get("sh000001"):
        closes = [h["close"] for h in history["sh000001"]]
        ma20, ma60 = _ma(closes, 20), _ma(closes, 60)
        close = closes[-1]
        ma = {"ma20": ma20, "ma60": ma60,
              "bias60": round((close - ma60) / ma60 * 100, 2) if ma60 else None}
```

返回 dict 增加 `"ma": ma`。

- [ ] **Step 4: 追加失败测试（snapshot 量能 MA）**

```python
def test_turnover_ma(tmp_path):
    import json
    from backend.services.snapshot import build_snapshot
    for i, total in enumerate([100.0, 110.0, 120.0, 130.0, 140.0], start=20):
        d = f"2026-09-{i:02d}"
        (tmp_path / f"{d}.json").write_text(json.dumps(
            {"date": d, "sources": {}, "a_index": {"turnover": {"total": total}}}), encoding="utf-8")
    def idx():
        return {"turnover": {"total": 150.0, "sh": 1, "sz": 1, "unit": "亿元", "notes": []}}
    snap = build_snapshot({"a_index": idx}, tmp_path, date="2026-09-30")
    t = snap["a_index"]["turnover"]
    assert t["prev_total"] == 140.0 and t["delta"] == 10.0
    # 可用总额 [100,110,120,130,140,150] 共6天 -> ma5=mean(110..150)=130.0
    assert t["ma5"] == 130.0
    assert t["ma10"] is None
```

- [ ] **Step 5: 运行确认失败** — FAIL。

- [ ] **Step 6: 实现快照服务** — 将 `_attach_turnover_delta` 扩展为同时算 `ma5/ma10`（保留 `prev_total/delta`）：

```python
def _attach_turnover_delta(snapshot: dict, data_dir: Path, date: str) -> None:
    section = snapshot.get("a_index")
    if not isinstance(section, dict) or not isinstance(section.get("turnover"), dict):
        return
    turnover = section["turnover"]
    totals = []
    for p in sorted(Path(data_dir).glob("????-??-??.json")):
        if p.stem >= date:
            continue
        snap = load_snapshot(data_dir, p.stem)
        t = ((snap or {}).get("a_index") or {}).get("turnover") or {}
        if isinstance(t, dict) and t.get("total") is not None:
            totals.append(t["total"])
    cur = turnover.get("total")
    series = totals + ([cur] if cur is not None else [])
    turnover["prev_total"] = totals[-1] if totals else None
    turnover["delta"] = round(cur - totals[-1], 2) if (cur is not None and totals) else None
    turnover["ma5"] = round(sum(series[-5:]) / 5, 2) if len(series) >= 5 else None
    turnover["ma10"] = round(sum(series[-10:]) / 10, 2) if len(series) >= 10 else None
```

- [ ] **Step 7: 运行确认通过** — `python3 -m pytest tests/test_fetcher_a_index.py tests/test_snapshot.py -v` → PASS。

---

## Task U3: `leaders` 梯队带股票名 + 强势股交易要素

**Files:** Modify `backend/fetchers/leaders.py`；Test `tests/test_fetcher_leaders.py`（追加）

**Interfaces:** `boards_ladder` 每项增加 `stocks:[{name,seal_time,seal_amount,tag}]`；`strong_pool_top` 每项增加 `price,zt_stat,turnover`。

- [ ] **Step 1: 追加失败测试**

```python
def test_ladder_and_strong_fields(monkeypatch):
    import backend.fetchers.leaders as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    zt = pd.DataFrame([
        {"代码":"002058","名称":"紫竹高科","涨跌幅":10.0,"连板数":2,"首次封板时间":"092500","封板资金":69384959,"换手率":1.7,"所属行业":"电池"},
        {"代码":"600000","名称":"浦发","涨跌幅":10.0,"连板数":2,"首次封板时间":"093000","封板资金":100.0,"换手率":2.0,"所属行业":"银行"},
    ])
    strong = pd.DataFrame([{"代码":"301190","名称":"善水科技","涨跌幅":20.0,"最新价":35.93,"涨停统计":"3/3","换手率":7.95,"所属行业":"化学原料","入选理由":"60日新高"}])
    monkeypatch.setattr(m.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(m.ak,"stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(m.ak,"stock_zt_pool_strong_em", lambda date: strong)
    out = m.fetch_leaders()
    rung = next(x for x in out["boards_ladder"] if x["boards"] == 2)
    names = [s["name"] for s in rung["stocks"]]
    assert "紫竹高科" in names and "浦发" in names
    assert rung["stocks"][0]["name"] == "紫竹高科"   # 按封板资金降序
    s0 = out["strong_pool_top"][0]
    assert s0["price"] == 35.93 and s0["zt_stat"] == "3/3" and s0["turnover"] == 7.95
```

- [ ] **Step 2: 运行确认失败** — FAIL。

- [ ] **Step 3: 实现** — 替换 `boards_ladder` 构建：

```python
    boards_ladder = []
    if len(zt) and "连板数" in zt.columns:
        by_board = {}
        for _, r in zt.iterrows():
            b = int(r["连板数"])
            by_board.setdefault(b, []).append({
                "name": str(r["名称"]), "seal_time": str(r.get("首次封板时间", "") or ""),
                "seal_amount": _num(r.get("封板资金"), 0), "tag": "涨停"})
        boards_ladder = [
            {"boards": b, "count": len(v),
             "stocks": sorted(v, key=lambda x: -(x["seal_amount"] or 0))[:10]}
            for b, v in sorted(by_board.items())
        ]
```

替换 `strong_pool_top` 构建：

```python
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
```

- [ ] **Step 4: 运行确认通过** — PASS。

---

## Task U4: `capital` 两融拆分 + 融资净买入 Top

**Files:** Modify `backend/fetchers/capital.py`；Test `tests/test_fetcher_capital.py`（追加）

**Interfaces:** `margin_history` 每项增加 `fin_balance`（融资余额）、`sec_balance`（融券余量金额）；返回增加 `fin_buy_top:[{code,name,net_buy}]`。

- [ ] **Step 1: 追加失败测试**

```python
def test_margin_split_and_fin_buy(monkeypatch):
    import backend.fetchers.capital as cap, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    sse = pd.DataFrame([{"信用交易日期":"20260930","融资余额":1.30e12,"融券余量金额":1.2e10,"融资融券余额":1.312e12}])
    det = pd.DataFrame([
        {"信用交易日期":"20260930","标的证券代码":"688185","标的证券简称":"康希诺","融资买入额":5.0e8,"融资偿还额":2.0e8},
        {"信用交易日期":"20260930","标的证券代码":"600519","标的证券简称":"贵州茅台","融资买入额":1.0e8,"融资偿还额":0.9e8},
    ])
    monkeypatch.setattr(cap.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(cap.ak,"stock_market_fund_flow", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(cap.ak,"stock_margin_sse", lambda **k: sse)
    monkeypatch.setattr(cap.ak,"stock_margin_szse", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(cap.ak,"stock_margin_detail_sse", lambda **k: det)
    out = cap.fetch_capital()
    m = out["margin_history"][-1]
    assert m["fin_balance"] == 13000.0 and m["sec_balance"] == 120.0
    assert out["fin_buy_top"][0]["name"] == "康希诺"
    assert out["fin_buy_top"][0]["net_buy"] == 3.0
```

- [ ] **Step 2: 运行确认失败** — FAIL。

- [ ] **Step 3: 实现 `capital.py`**
  - 增加 `_latest_date()`（用 `stock_zh_index_daily("sh000001")` 末行日期转 YYYYMMDD）。
  - SSE 行增加 `fin_balance`、`sec_balance`：

```python
        for _, r in sse.tail(20).iterrows():
            margin_history.append({
                "date": str(r["信用交易日期"]),
                "balance": to_yi(r["融资融券余额"]),
                "fin_balance": to_yi(r.get("融资余额")),
                "sec_balance": to_yi(r.get("融券余量金额")),
            })
```

  - 新增融资净买入 Top：

```python
    fin_buy_top = []
    try:
        date = _latest_date()
        det = fetch(ak.stock_margin_detail_sse, date=date, source="sse")
        if det is not None and not det.empty and "融资买入额" in det.columns:
            det = det.assign(_net=det["融资买入额"].astype(float) - det["融资偿还额"].astype(float))
            for _, r in det.sort_values("_net", ascending=False).head(10).iterrows():
                fin_buy_top.append({"code": str(r["标的证券代码"]), "name": str(r["标的证券简称"]),
                                    "net_buy": to_yi(r["_net"])})
    except Exception as exc:
        notes.append(f"融资净买入明细获取失败: {exc}")
```

  - 返回 dict 增加 `"fin_buy_top": fin_buy_top`。

- [ ] **Step 4: 运行确认通过** — PASS。

---

## Task U5: 前端区块重写（index.html / style.css / app.js）

**Files:** Modify `frontend/index.html`、`frontend/style.css`、`frontend/app.js`

- [ ] **Step 1: `index.html`** — 在 v3 基础上：
  - 工作区一：`<div class="panel"><h3>美股行业映射</h3><div class="table-wrap short"><table id="us-sector-table"></table></div></div>`（置于 `overseas-cards` 之后、`premarket` 之前）。
  - 工作区二：保留 `market-cards`、`chart-emotion`；把 `连板梯队` 面板改为 `<div id="ladder-cards" class="ladder-cards"></div>`（替换 chart-ladder）；保留 `chart-spark`/`chart-dist`。
  - 工作区三：`strong-table` 表头后续由 JS 改列，无需改 html。
  - 资金补充：把 `chart-margin` 保留；新增 `<div class="table-wrap short"><table id="fin-buy-table"></table></div>`。

> 保持所有既有 id 不变，仅新增 `us-sector-table`、`ladder-cards`、`fin-buy-table`，并将 `chart-ladder` 替换为 `ladder-cards`。

- [ ] **Step 2: `style.css`** — 追加：

```css
.ladder-cards { display:flex; flex-direction:column; gap:6px; max-height:300px; overflow:auto; }
.rung { border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-size:12.5px; }
.rung .rung-head { color:var(--gold); font-weight:600; margin-bottom:3px; }
.rung .stk { color:var(--text-muted); margin-right:10px; }
```

- [ ] **Step 3: `app.js`**
  - `renderOverseas` 末尾调用 `renderUsSectors(s)`：

```javascript
function renderUsSectors(s){
  const t=document.getElementById("us-sector-table");
  if(s.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(s.error)}</td></tr></tbody>`; return; }
  const rows=(s.us_sectors||[]).map(x=>`<tr><td>${esc(x.name)}</td>
    <td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td class="muted">${esc(x.a_share)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>美股行业</th><th>涨跌幅</th><th>A股映射</th></tr></thead><tbody>${rows}</tbody>`;
}
```
  - 删除 `renderLadder` 的 ECharts 版本，改为卡片版：

```javascript
function renderLadder(s){
  const box=document.getElementById("ladder-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  const d=(s.boards_ladder||[]).slice().sort((a,b)=>b.boards-a.boards);
  box.innerHTML=d.map(r=>{
    const stk=(r.stocks||[]).map(x=>`<span class="stk">${esc(x.name)}${x.seal_time?`(${esc(x.seal_time.slice(0,4))})`:""}</span>`).join("");
    return `<div class="rung"><div class="rung-head">${r.boards} 板 · ${r.count} 家</div><div>${stk||"--"}</div></div>`;
  }).join("") || `<span class="muted">今日无涨停</span>`;
}
```
  - `renderMarket` 显示均量：在成交额卡 sub 增加 `MA5/MA10`：

```javascript
    card("两市成交额", fmtYi(t.total),
      `${d===null?"":(d>0?"放量":"缩量")+" "+fmtYi(Math.abs(d))}${t.ma5!=null?` · MA5 ${fmtYi(t.ma5)}`:""}${t.ma10!=null?` · MA10 ${fmtYi(t.ma10)}`:""}`)
```
  - `renderSpark` 增加 MA20/MA60 线与乖离率标题：

```javascript
function renderSpark(s){
  if(s.error) return;
  const hist=(s.history&&s.history["sh000001"])||[];
  const closes=hist.map(h=>h.close);
  const ma=(n)=>closes.map((_,i)=> i>=n-1 ? +(closes.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n).toFixed(2) : null);
  const m=s.ma||{};
  chart("chart-spark").setOption({
    title:{text:`上证指数 近60日 · 乖离(MA60) ${fmtPct(m.bias60)}`.replace("--",""),textStyle:{color:"#8b93a7",fontSize:11}},
    tooltip:{trigger:"axis"}, grid:{left:48,right:12,top:32,bottom:20},
    xAxis:{type:"category",data:hist.map(h=>h.date),...AXIS,axisLabel:{show:false}},
    yAxis:{type:"value",scale:true,...AXIS},
    legend:{show:false},
    series:[
      {type:"line",name:"收盘",data:closes,smooth:true,showSymbol:false,lineStyle:{color:"#3b82f6",width:2}},
      {type:"line",name:"MA20",data:ma(20),showSymbol:false,lineStyle:{color:"#f5c451",width:1}},
      {type:"line",name:"MA60",data:ma(60),showSymbol:false,lineStyle:{color:"#8b93a7",width:1}}
    ]
  });
}
```
  - `renderStrong` 改列：个股 | 最新价 | 涨幅 | 涨停统计 | 换手 | 行业：

```javascript
function renderStrong(snap){
  const ld=snap.leaders||{}, t=document.getElementById("strong-table");
  if(ld.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(ld.error)}</td></tr></tbody>`; return; }
  const rows=(ld.strong_pool_top||[]).map(s=>`<tr><td>${esc(s.name)}</td><td>${fmt(s.price)}</td>
    <td class="${cls(s.change_pct)}">${fmtPct(s.change_pct)}</td><td>${esc(s.zt_stat||"")}</td>
    <td>${fmt(s.turnover)}%</td><td>${esc(s.industry)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>个股</th><th>最新价</th><th>涨幅</th><th>涨停统计</th><th>换手</th><th>行业</th></tr></thead><tbody>${rows}</tbody>`;
}
```
  - `renderCapital`：两融双线 + 融资净买入表：

```javascript
function renderCapital(snap){
  const s=snap.capital||{}, box=document.getElementById("capital-cards"), ft=document.getElementById("fin-buy-table");
  if(s.error){ box.innerHTML=err(s.error); ft.innerHTML=""; return; }
  box.innerHTML=card("主力净流入", s.main_net_inflow==null?"--":`${s.main_net_inflow>0?"+":""}${fmtYi(s.main_net_inflow)}`,"",cls(s.main_net_inflow))+
    card("两融余额", fmtYi(s.margin_total),"");
  const h=s.margin_history||[];
  if(h.length) chart("chart-margin").setOption({
    tooltip:{trigger:"axis"}, legend:{show:true,textStyle:{color:"#8b93a7"},top:0}, grid:{left:56,right:12,top:32,bottom:20},
    xAxis:{type:"category",data:h.map(x=>x.date),...AXIS,axisLabel:{show:false}}, yAxis:{type:"value",scale:true,...AXIS},
    series:[
      {name:"融资余额",type:"line",data:h.map(x=>x.fin_balance),showSymbol:false,lineStyle:{color:"#ff4d4f",width:2}},
      {name:"融券余额",type:"line",data:h.map(x=>x.sec_balance),showSymbol:false,lineStyle:{color:"#22c55e",width:2}}
    ]
  });
  const rows=(s.fin_buy_top||[]).map(x=>`<tr><td>${esc(x.name)}</td><td class="up">${fmt(x.net_buy)}</td></tr>`).join("");
  ft.innerHTML=`<thead><tr><th>融资净买入 Top10</th><th>净买入(亿)</th></tr></thead><tbody>${rows}</tbody>`;
}
```
  - `renderAll` 中 `renderOverseas` 后已含 `renderUsSectors`；`renderLadder` 改读 `snap.leaders`（v3 已修）。

- [ ] **Step 4: 语法与测试** — `node --check frontend/app.js` → OK；`python3 -m pytest tests/test_frontend_assets.py -v` → PASS。

---

## Task U6: 测试与端到端验收

- [ ] **Step 1: 更新 `tests/test_frontend_assets.py`** — 追加断言 index.html 含 `id="us-sector-table"`、`id="ladder-cards"`、`id="fin-buy-table"`。
- [ ] **Step 2: 全量** — `python3 -m pytest -v` → 全通过。
- [ ] **Step 3: 端到端** — 重启服务，`POST /api/refresh` → 200；检查 `us_sectors` 有 12 项、`leaders.boards_ladder[].stocks` 非空、`strong_pool_top[0].price/zt_stat`、`capital.fin_buy_top` 非空、`margin_history[].fin_balance/sec_balance`；严格 JSON；静态资源 200。

---

## 自检
- §25 数据增量：us_sectors→U1；a_index.ma/turnover.ma→U2；boards_ladder.stocks/strong fields→U3；capital split/fin_buy_top→U4；§26 前端→U5；§27 降级（北向移除/均量累积）→U2/U5。无占位符。
