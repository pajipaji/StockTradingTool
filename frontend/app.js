const state = { charts:{}, snap:null, selectedIndustry:null };
const AXIS = { axisLine:{lineStyle:{color:"#2a3141"}}, splitLine:{lineStyle:{color:"#1e2430"}} };

function cls(v){ return v>0?"up":v<0?"down":"flat"; }
function num(v){ if(v===null||v===undefined||v==="") return null; const n=Number(v); return Number.isFinite(n)?n:null; }
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
  renderUsSectors(s);
  const box=document.getElementById("overseas-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  let html="";
  (s.us_indices||[]).forEach(i=>html+=card(i.name,fmt(i.close),fmtPct(i.change_pct),cls(i.change_pct)));
  (s.futures||[]).forEach(f=>html+=card(f.name,fmt(f.price),fmtPct(f.change_pct),cls(f.change_pct)));
  (s.hk_indices||[]).filter(h=>h.code==="HSTECH"||h.code==="HSI").forEach(h=>html+=card(h.name+"(代理)",fmt(h.price),fmtPct(h.change_pct),cls(h.change_pct)));
  if(s.sox&&num(s.sox.value)!==null) html+=card("费城半导体",fmt(s.sox.value),fmtPct(s.sox.change_pct),cls(s.sox.change_pct));
  if(s.usd_cny&&num(s.usd_cny.mid)!==null) html+=card("美元(中行代理)",fmt(s.usd_cny.mid,4),"", "");
  box.innerHTML=html;
}
function renderUsSectors(s){
  const t=document.getElementById("us-sector-table");
  if(s.error){ t.innerHTML=`<tbody><tr><td class="error">${esc(s.error)}</td></tr></tbody>`; return; }
  const rows=(s.us_sectors||[]).map(x=>`<tr><td>${esc(x.name)}</td>
    <td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td class="muted">${esc(x.a_share)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>美股行业</th><th>涨跌幅</th><th>A股映射</th></tr></thead><tbody>${rows}</tbody>`;
}

/* 工作区二 */
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
function renderLadder(s){
  const box=document.getElementById("ladder-cards");
  if(s.error){ box.innerHTML=err(s.error); return; }
  const d=(s.boards_ladder||[]).slice().sort((a,b)=>b.boards-a.boards);
  box.innerHTML=d.map(r=>{
    const stk=(r.stocks||[]).map(x=>`<span class="stk">${esc(x.name)}${x.seal_time?`(${esc(x.seal_time.slice(0,4))})`:""}</span>`).join("");
    return `<div class="rung"><div class="rung-head">${r.boards} 板 · ${r.count} 家</div><div>${stk||"--"}</div></div>`;
  }).join("") || `<span class="muted">今日无涨停</span>`;
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
      {type:"line",name:"收盘",data:closes,smooth:true,showSymbol:false,lineStyle:{color:"#3b82f6",width:2},
        markLine:{silent:true,symbol:"none",data:[{yAxis:m.ma60,lineStyle:{color:"#8b93a7",type:"dashed"},label:{formatter:"MA60",color:"#8b93a7"}}]}},
      {type:"line",name:"MA20",data:ma(20),showSymbol:false,lineStyle:{color:"#f5c451",width:1}}
    ]
  });
}
function renderDist(s){
  if(s.error) return;
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
  const sf=snap.sector_flow||{}, ld=snap.leaders||{};
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
  const rows=(ld.strong_pool_top||[]).map(s=>`<tr><td>${esc(s.name)}</td><td>${fmt(s.price)}</td>
    <td class="${cls(s.change_pct)}">${fmtPct(s.change_pct)}</td><td>${esc(s.zt_stat||"")}</td>
    <td>${num(s.turnover)==null?"--":fmt(s.turnover)+"%"}</td><td>${esc(s.industry)}</td></tr>`).join("");
  t.innerHTML=`<thead><tr><th>个股</th><th>最新价</th><th>涨幅</th><th>涨停统计</th><th>换手</th><th>行业</th></tr></thead><tbody>${rows}</tbody>`;
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
  const trow=(x,last)=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${fmt(x.price)}</td>
    <td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td>${fmt(last==="sec_sell"?x.sec_sell:x.net_buy)}</td></tr>`;
  const buy=document.getElementById("fin-buy-table"), sell=document.getElementById("fin-sell-table"), north=document.getElementById("north-table");
  buy.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>融资净买入(亿)</th></tr></thead><tbody>`+
    (s.fin_buy_top||[]).map(x=>trow(x,"net_buy")).join("")+`</tbody>`;
  sell.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>融券卖出量</th></tr></thead><tbody>`+
    (s.fin_sell_top||[]).map(x=>trow(x,"sec_sell")).join("")+`</tbody>`;
  const nrows=(s.northbound_active_top||[]).length
    ? (s.northbound_active_top||[]).map(x=>`<tr><td>${esc(x.code||"")}</td><td>${esc(x.name||"")}</td><td>${fmt(x.price)}</td><td class="${cls(x.change_pct)}">${fmtPct(x.change_pct)}</td><td>${fmt(x.net_buy)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">北向个股活跃成交数据已停止披露</td></tr>`;
  north.innerHTML=`<thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>净成交(亿)</th></tr></thead><tbody>${nrows}</tbody>`;
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
  renderEmotionExtra(snap.a_index||{}, snap.sentiment||{}, snap.leaders||{});
  renderEmotion(snap.sentiment||{});
  renderLadder(snap.leaders||{});
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
