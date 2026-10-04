# 股市脉搏看板 v5 布局重构实现计划

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps `- [ ]`.

**Goal:** 重排工作区一/二、移除开盘预判、连板梯队带股名、情绪温度计补指标；资金面拆分为融资/融券双轴 + 三表（融资净买入 Top / 融券 Top / 北向占位），融资表补代码/价格/涨跌幅。

**Spec:** `docs/superpowers/specs/2026-10-03-stock-dashboard-design.md`（§29–32）

## Global Constraints
- akshare 经 `backend.core.fetch.fetch(...)`；金额亿元（`to_yi`）；涨跌幅为百分比数值。
- Python 3.9.6（含 `X | None` 的模块需 `from __future__ import annotations`）；`python3 -m pytest` 从根运行。
- **无 git / 不提交**。离线单测不得联网（stub 所有新依赖）。
- 深色令牌不变。快照分区键保持 7 个。

---

## Task W1: `leaders` 增加 `new_high_count`

**Files:** Modify `backend/fetchers/leaders.py`; Test `tests/test_fetcher_leaders.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
def test_new_high_count(monkeypatch):
    import backend.fetchers.leaders as m, backend.core.fetch as fm
    from backend.core.ratelimit import RateLimiter
    import pandas as pd
    fm.reset_cache(); fm.LIMITER = RateLimiter(min_interval=0.0)
    idx = pd.DataFrame([{"date":"2026-09-30","open":1,"high":1,"low":1,"close":3800.0,"volume":1}])
    zt = pd.DataFrame([{"代码":"002058","名称":"A","涨跌幅":10.0,"连板数":1,"首次封板时间":"092500","封板资金":1,"换手率":1,"所属行业":"电池"}])
    strong = pd.DataFrame([
        {"代码":"301190","名称":"B","涨跌幅":20.0,"最新价":30.0,"涨停统计":"3/3","换手率":7.0,"所属行业":"化工","入选理由":"60日新高","是否新高":"是"},
        {"代码":"301191","名称":"C","涨跌幅":9.0,"最新价":10.0,"涨停统计":"1/1","换手率":5.0,"所属行业":"化工","入选理由":"量价齐升","是否新高":"否"},
    ])
    monkeypatch.setattr(m.ak,"stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(m.ak,"stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(m.ak,"stock_zt_pool_strong_em", lambda date: strong)
    out = m.fetch_leaders()
    assert out["new_high_count"] == 1
```

- [ ] **Step 2: 运行确认失败** — FAIL。

- [ ] **Step 3: 实现** — 在 `fetch_leaders` 计算 `strong_pool_top` 后加入：

```python
    new_high_count = 0
    if len(strong) and "是否新高" in strong.columns:
        new_high_count = int((strong["是否新高"].astype(str) == "是").sum())
```

返回 dict 增加 `"new_high_count": new_high_count`。

- [ ] **Step 4: 通过** — `python3 -m pytest tests/test_fetcher_leaders.py -v` → PASS。

---

## Task W2: `capital` 融资/融券拆分与三表数据

**Files:** Modify `backend/fetchers/capital.py`（整体替换）；Test `tests/test_fetcher_capital.py`（更新+追加）

**Interfaces:** 返回增加 `fin_net_today`、`fin_sell_top`、`northbound_active_top`；`fin_buy_top` 每项增加 `price/change_pct`。

- [ ] **Step 1: 用下列内容替换 `backend/fetchers/capital.py`**

```python
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
            if len(sse) >= 2:
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
        spot = _spot_map()
        if det is not None and not det.empty:
            if "融资买入额" in det.columns and "融资偿还额" in det.columns:
                d = det.assign(_net=det["融资买入额"].astype(float) - det["融资偿还额"].astype(float))
                for _, r in d.sort_values("_net", ascending=False).head(10).iterrows():
                    code = str(r["标的证券代码"])
                    price, chg = spot.get(code, (None, None))
                    fin_buy_top.append({"code": code, "name": str(r["标的证券简称"]),
                                        "price": price, "change_pct": chg, "net_buy": to_yi(r["_net"])})
            if "融券卖出量" in det.columns:
                for _, r in det.sort_values("融券卖出量", ascending=False).head(10).iterrows():
                    code = str(r["标的证券代码"])
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
```

- [ ] **Step 2: 更新 `tests/test_fetcher_capital.py`**
  - 每个调用 `fetch_capital()` 的测试**必须** stub：`stock_zh_index_daily`、`stock_margin_detail_sse`、`stock_margin_sse`、`stock_margin_szse`、`stock_market_fund_flow`、`stock_zh_a_spot`（新增，供 `_spot_map`）。
  - 更新 `test_margin_split_and_fin_buy` 断言：`fin_buy_top[0]` 含 `price/change_pct`（用 stub 的 spot 提供）；新增断言 `fin_sell_top` 非空且含 `sec_sell`；`fin_net_today` 等于最新与上一日 `融资余额` 之差（亿元）。

- [ ] **Step 3: 通过** — `python3 -m pytest tests/test_fetcher_capital.py -v`；`python3 -m pytest -m "not network" -q` 仍**快速且零联网**。

---

## Task W3: 前端 `index.html` 布局重排

**Files:** Modify `frontend/index.html`

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
    <!-- 工作区一：左右两列 -->
    <section class="ws">
      <h2 class="ws-title">一 · 盘前外围映射</h2>
      <div class="grid grid-2 fill">
        <div class="panel"><h3>外围指数</h3><div class="cards" id="overseas-cards"></div></div>
        <div class="panel"><h3>美股行业映射</h3>
          <div class="table-wrap short"><table id="us-sector-table"></table></div></div>
      </div>
    </section>

    <!-- 工作区二：上三栏 + 下双栏 -->
    <section class="ws">
      <h2 class="ws-title">二 · 盘中/复盘 大局与情绪</h2>
      <div class="grid grid-3">
        <div class="panel">
          <h3>资金水位与交易风格</h3>
          <div class="cards compact" id="market-cards"></div>
        </div>
        <div class="panel">
          <h3>市场情绪温度计</h3>
          <div class="chart gauge" id="chart-emotion"></div>
          <div class="emotion-extra" id="emotion-extra"></div>
        </div>
        <div class="panel">
          <h3>连板梯队与龙头 <span class="muted">（按板数）</span></h3>
          <div class="ladder-cards" id="ladder-cards"></div>
        </div>
      </div>
      <div class="grid grid-2">
        <div class="panel"><h3>上证指数近60日（MA20/MA60）</h3><div class="chart spark" id="chart-spark"></div></div>
        <div class="panel"><h3>全市场涨跌分布梯度</h3><div class="chart dist" id="chart-dist"></div></div>
      </div>
    </section>

    <!-- 工作区三：主线攻防 -->
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
      <div class="panel"><h3>强势股 Top（最新价/涨停统计/换手）</h3>
        <div class="table-wrap short"><table id="strong-table"></table></div></div>
    </section>

    <!-- 工作区四：资金面 -->
    <section class="ws">
      <h2 class="ws-title">四 · 资金面（杠杆与外资）</h2>
      <div class="panel"><h3>两融趋势（左轴融资 / 右轴融券）</h3>
        <div class="chart spark" id="chart-margin" style="height:220px"></div>
        <div class="cards" id="capital-cards"></div>
      </div>
      <div class="grid grid-3">
        <div class="panel"><h3>融资净买入 Top10</h3>
          <div class="table-wrap short"><table id="fin-buy-table"></table></div></div>
        <div class="panel"><h3>融券卖出 Top10</h3>
          <div class="table-wrap short"><table id="fin-sell-table"></table></div></div>
        <div class="panel"><h3>北向资金活跃成交 Top10</h3>
          <div class="table-wrap short"><table id="north-table"></table></div></div>
      </div>
    </section>

    <!-- 工作区五：复盘笔记 -->
    <section class="ws">
      <h2 class="ws-title">五 · 复盘笔记</h2>
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
  </main>

  <div class="overlay" id="overlay">正在抓取数据，请稍候…</div>
  <script src="/static/vendor/echarts.min.js"></script>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 通过** — `python3 -m pytest tests/test_frontend_assets.py -v`（需先按 W5 更新断言）。

---

## Task W4: 前端 `style.css` 与 `app.js`

**Files:** Modify `frontend/style.css`、`frontend/app.js`

- [ ] **Step 1: `style.css` 追加/调整**

```css
.cards.compact { gap:6px; }
.cards.compact .card { min-width:104px; padding:6px 10px; }
.cards.compact .card .val { font-size:16px; }
.emotion-extra { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
.emotion-extra .pill { background:#121722; border:1px solid var(--border); border-radius:14px;
  padding:3px 10px; font-size:12px; color:var(--text-muted); }
.emotion-extra .pill b { color:var(--text); }
.ladder-cards { display:flex; flex-direction:column; gap:6px; max-height:260px; overflow:auto; }
.rung { border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-size:12.5px; }
.rung .rung-head { color:var(--gold); font-weight:600; margin-bottom:3px; }
.rung .stk { color:var(--text-muted); margin-right:10px; }
```

- [ ] **Step 2: `app.js` 关键函数**（在 v4 基础上修改/新增）
  - `renderOverseas(s)`：**移除** `premarket` 相关代码与 `#premarket` 引用；保留宽基卡片 + `renderUsSectors(s)` 调用。
  - `renderUsSectors(s)`：不变（表格）。
  - `renderMarket(s)`：改为 4 个紧凑卡：两市成交额、较上日增减、上涨/下跌、涨停/跌停：

```javascript
function renderMarket(s){
  const box=document.getElementById("market-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  const t=s.turnover||{}, b=s.breadth||{}, d=num(t.delta);
  box.innerHTML =
    card("两市成交额", fmtYi(t.total), (t.ma5!=null?`MA5 ${fmtYi(t.ma5)}`:"")) +
    card("较上日增减", d===null?"--":`${d>0?"+":""}${fmtYi(Math.abs(d))}`, d===null?"":(d>0?"放量":"缩量"), cls(d)) +
    card("上涨/下跌", `${b.up??"--"}/${b.down??"--"}`, "") +
    card("涨停/跌停", `${b.limit_up??"--"}/${b.limit_down??"--"}`, "");
}
```
  - 新增 `renderEmotionExtra(aIndex, sentiment, leaders)`：

```javascript
function renderEmotionExtra(aIndex, st, ld){
  const box=document.getElementById("emotion-extra");
  const b=aIndex.breadth||{};
  const eff = (b.up!=null&&b.down!=null&&(b.up+b.down)>0) ? Math.round(b.up/(b.up+b.down)*100) : null;
  const zb = num(st.zbgc_rate);
  box.innerHTML =
    `<span class="pill">炸板率 <b>${zb===null?"--":(zb*100).toFixed(0)+"%"}</b></span>`+
    `<span class="pill">突破新高 <b>${ld.new_high_count??"--"} 家</b></span>`+
    `<span class="pill">赚钱效应 <b>${eff===null?"--":eff+"%"}</b></span>`;
}
```
  - `renderAll`：`renderMarket(snap.a_index||{})` 后调用 `renderEmotionExtra(snap.a_index||{}, snap.sentiment||{}, snap.leaders||{})`。
  - `renderCapital(snap)`：双 Y 轴两融 + 概览 4 卡 + 三表：

```javascript
function renderCapital(snap){
  const s=snap.capital||{};
  const box=document.getElementById("capital-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  const d=num(s.fin_net_today);
  box.innerHTML =
    card("两融总余额", fmtYi(s.margin_total), "") +
    card("融资净买入", d===null?"--":`${d>0?"+":""}${fmtYi(Math.abs(d))}`, "较前一日", cls(d)) +
    card("融券余额", (s.margin_history&&s.margin_history.length)?fmtYi(s.margin_history.at(-1).sec_balance):"--", "") +
    card("北向(个股)", "已停止披露", "");

  const h=s.margin_history||[];
  if(h.length) chart("chart-margin").setOption({
    tooltip:{trigger:"axis"}, legend:{show:true,textStyle:{color:"#8b93a7"},top:0},
    grid:{left:64,right:64,top:32,bottom:20},
    xAxis:{type:"category",data:h.map(x=>x.date),...AXIS,axisLabel:{show:false}},
    yAxis:[{type:"value",scale:true,name:"融资(亿)",...AXIS},{type:"value",scale:true,name:"融券(亿)",...AXIS}],
    series:[
      {name:"融资余额",type:"line",data:h.map(x=>x.fin_balance),showSymbol:false,lineStyle:{color:"#ff4d4f",width:2}},
      {name:"融券余额",type:"line",yAxisIndex:1,data:h.map(x=>x.sec_balance),showSymbol:false,lineStyle:{color:"#22c55e",width:2}}
    ]
  });
  const trow=(x,cols)=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${fmt(x.price)}</td>
    <td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td class="${cls(x.net_buy)}">${fmt(x.net_buy)}</td><td class="down">${fmt(x.sec_sell)}</td></tr>`;
  const buy=document.getElementById("fin-buy-table"), sell=document.getElementById("fin-sell-table"), north=document.getElementById("north-table");
  buy.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>融资净买入(亿)</th></tr></thead><tbody>`+
    (s.fin_buy_top||[]).map(x=>trow(x)).join("")+`</tbody>`;
  sell.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>融券卖出量</th></tr></thead><tbody>`+
    (s.fin_sell_top||[]).map(x=>trow(x)).join("")+`</tbody>`;
  const nrows=(s.northbound_active_top||[]).length
    ? (s.northbound_active_top||[]).map(x=>`<tr><td>${esc(x.code||"")}</td><td>${esc(x.name||"")}</td><td>${fmt(x.price)}</td><td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td>${fmt(x.net_buy)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">北向个股活跃成交数据已停止披露</td></tr>`;
  north.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>净成交(亿)</th></tr></thead><tbody>${nrows}</tbody>`;
}
```
  - 删除对 `#premarket` 的引用（若其它处引用一并清理）。

- [ ] **Step 3: 语法与测试** — `node --check frontend/app.js` → OK；`python3 -m pytest -m "not network" -q` 全通过。

---

## Task W5: 测试与端到端验收

- [ ] **Step 1: 更新 `tests/test_frontend_assets.py`** — v5 结构断言：`id="us-sector-table"`、`id="ladder-cards"`、`id="emotion-extra"`、`id="fin-buy-table"`、`id="fin-sell-table"`、`id="north-table"`；断言 index.html **不含** `id="premarket"`。
- [ ] **Step 2: 全量** — `python3 -m pytest -m "not network" -q` → 全通过且快。
- [ ] **Step 3: 端到端** — 重启服务，`POST /api/refresh` → 200；检查 `leaders.new_high_count` 为整数、`capital.fin_buy_top[0]` 含 `price/change_pct`、`fin_sell_top` 非空、`fin_net_today` 非空、`northbound_active_top` 为空且 `notes` 含停更说明；严格 JSON；静态资源 200。

---

## 自检
- §29 布局 → W3/W4；§30 数据增量 → W1/W2；§31 降级（北向占位）→ W2/W4；W5 测试与 E2E。无占位符。
