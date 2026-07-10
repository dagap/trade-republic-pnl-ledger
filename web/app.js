const PAYLOAD = /*__DATA__*/;
const DAYS = PAYLOAD.days;
const FLOWS = PAYLOAD.flows || [];
const META = PAYLOAD.meta;
const byDate = Object.fromEntries(DAYS.map(d => [d.d, d]));

const MONTHS = ["January","February","March","April","May","June","July",
  "August","September","October","November","December"];
const WD = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

/* ---------- date helpers (string-based, timezone-safe) ---------- */
function parse(s){ const [y,m,d]=s.split("-").map(Number); return {y,m:m-1,d}; }
function iso(y,m,d){ return `${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`; }
function mondayIdx(y,m,d){ return (new Date(y,m,d).getDay()+6)%7; }
function daysInMonth(y,m){ return new Date(y,m+1,0).getDate(); }
function addDays(s,n){ const p=parse(s); const dt=new Date(p.y,p.m,p.d+n); return iso(dt.getFullYear(),dt.getMonth(),dt.getDate()); }
function todayISO(){ const t=new Date(); return iso(t.getFullYear(),t.getMonth(),t.getDate()); }
function dnum(s){ const p=parse(s); return Date.UTC(p.y,p.m,p.d)/86400000; }   // integer day index
function fmtShort(s){ const p=parse(s); return new Date(p.y,p.m,p.d).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}); }

/* ---------- formatting ---------- */
function eur(v){
  if(Math.abs(v)<0.005) return "€0.00";
  const s=v<0?"−":"+";
  return s+"€"+Math.abs(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
}
function eurCompact(v){
  if(Math.abs(v)<0.005) return "€0";
  const s=v<0?"−":"+", a=Math.abs(v);
  if(a>=1000){ const k=a/1000; return s+"€"+(k>=100?Math.round(k):k.toFixed(1))+"k"; }
  return s+"€"+Math.round(a);
}
function cls(v){ return v>0.005?"pos":v<-0.005?"neg":"flat"; }

/* ---------- aggregation over a date range (inclusive) ---------- */
function agg(startISO,endISO){
  const a={net:0,realized:0,income:0,fees:0,tax:0,trades:0,win:0,loss:0,flat:0,
           best:null,worst:null,days:0};
  for(const d of DAYS){
    if(d.d<startISO||d.d>endISO) continue;
    a.net+=d.p; a.realized+=d.r; a.income+=d.i; a.fees+=d.f; a.tax+=d.t; a.trades+=d.n;
    a.days++;
    if(d.p>0.005) a.win++; else if(d.p<-0.005) a.loss++; else a.flat++;
    if(a.best===null||d.p>a.best.p) a.best=d;
    if(a.worst===null||d.p<a.worst.p) a.worst=d;
  }
  a.winRate = (a.win+a.loss)>0 ? a.win/(a.win+a.loss) : 0;
  a.avg = a.days>0 ? a.net/a.days : 0;
  return a;
}

/* ---------- stat cards (This Week / Month / Year / All-time) ---------- */
function startOfWeek(){ const t=new Date(); const off=(t.getDay()+6)%7;
  const s=new Date(t.getFullYear(),t.getMonth(),t.getDate()-off); return iso(s.getFullYear(),s.getMonth(),s.getDate()); }
function renderStats(){
  const now=todayISO(), np=parse(now);
  const cards=[
    ["This Week", startOfWeek(), now],
    ["This Month", iso(np.y,np.m,1), now],
    ["This Year", iso(np.y,0,1), now],
    ["All-time", META.min_date, META.max_date],
  ];
  const el=document.getElementById("stats"); el.innerHTML="";
  for(const [label,s,e] of cards){
    const a=agg(s,e);
    const wr=(a.win+a.loss)>0 ? Math.round(a.winRate*100)+"% win" : "no trades";
    el.insertAdjacentHTML("beforeend",`
      <div class="stat">
        <div class="label">${label}</div>
        <div class="value ${cls(a.net)}">${eur(a.net)}</div>
        <div class="sub"><b>${a.days}</b> day${a.days===1?"":"s"} · ${wr}</div>
      </div>`);
  }
}

/* ---------- period summary ---------- */
function aggFlows(s,e){
  let dep=0, wd=0;
  for(const f of FLOWS){ if(f.d>=s && f.d<=e){ dep+=f.dep; wd+=f.wd; } }
  return {dep, wd, net:dep+wd};
}
function renderSummary(s,e){
  const a=agg(s,e), fl=aggFlows(s,e);
  const bw = a.best? `${a.best.d.slice(5)} · ${eurCompact(a.best.p)}` : "—";
  const ww = a.worst? `${a.worst.d.slice(5)} · ${eurCompact(a.worst.p)}` : "—";
  document.getElementById("summary").innerHTML=`
    <div class="headline">
      <div class="label">Net P&amp;L · selected period</div>
      <div class="big ${cls(a.net)}">${eur(a.net)}</div>
      <div class="range-lbl">${s} → ${e}</div>
      <div class="funding">Deposited <b>${eur(fl.dep)}</b> · Withdrawn <b>${eur(fl.wd)}</b> · Net funded <b>${eur(fl.net)}</b></div>
    </div>
    <div class="metrics">
      <div class="metric"><div class="m-label">Win rate</div><div class="m-val">${(a.win+a.loss)?Math.round(a.winRate*100)+"%":"—"}</div></div>
      <div class="metric"><div class="m-label">Win / Loss days</div><div class="m-val"><span class="pos">${a.win}</span> / <span class="neg">${a.loss}</span></div></div>
      <div class="metric"><div class="m-label">Avg / day</div><div class="m-val ${cls(a.avg)}">${eurCompact(a.avg)}</div></div>
      <div class="metric"><div class="m-label">Best day</div><div class="m-val pos">${bw}</div></div>
      <div class="metric"><div class="m-label">Worst day</div><div class="m-val neg">${ww}</div></div>
      <div class="metric"><div class="m-label">Interest</div><div class="m-val ${cls(a.income)}">${eurCompact(a.income)}</div></div>
      <div class="metric"><div class="m-label">Fees</div><div class="m-val neg">${eurCompact(a.fees)}</div></div>
      <div class="metric"><div class="m-label">Tax net</div><div class="m-val ${cls(a.tax)}">${eurCompact(a.tax)}</div></div>
      <div class="metric"><div class="m-label">Trades</div><div class="m-val">${a.trades}</div></div>
    </div>`;
}

/* ---------- color scale for cells ---------- */
function buildScale(s,e){
  const vals=[];
  for(const d of DAYS){ if(d.d>=s&&d.d<=e && Math.abs(d.p)>0.005) vals.push(Math.abs(d.p)); }
  vals.sort((a,b)=>a-b);
  // robust scale: 90th percentile so a single outlier doesn't wash everything out
  const q = vals.length ? vals[Math.min(vals.length-1, Math.floor(vals.length*0.90))] : 1;
  return Math.max(q, 1);
}
function cellColor(p, scale){
  const t = Math.min(1, Math.sqrt(Math.abs(p)/scale));     // perceptual easing
  const accent = p>0 ? "var(--pos)" : "var(--neg)";
  const pct = Math.round((0.10 + 0.90*t)*100);             // floor so tiny days still tint
  const bg = `color-mix(in srgb, ${accent} ${pct}%, var(--cell))`;
  const textWhite = t>0.42;
  return {bg, text: textWhite ? "#fff" : "var(--text)", strong:t>0.42};
}

/* ---------- calendar ---------- */
function renderCalendar(s,e){
  const cal=document.getElementById("cal");
  const scale=buildScale(s,e);
  const today=todayISO();
  const ps=parse(s), pe=parse(e);
  let y=pe.y, m=pe.m, html="";   // newest month first, descending to earliest
  let any=false;
  while(y>ps.y || (y===ps.y && m>=ps.m)){
    const mAgg=agg(iso(y,m,1), iso(y,m,daysInMonth(y,m)));
    html+=`<div class="month">
      <div class="month-head">
        <div class="m-name">${MONTHS[m]} <span>${y}</span></div>
        <div class="m-total ${cls(mAgg.net)}">${eur(mAgg.net)}</div>
      </div>
      <div class="weekdays">${WD.map(w=>`<div>${w}</div>`).join("")}<div class="wk-head">Week</div></div>
      <div class="grid">`;
    const lead=mondayIdx(y,m,1);
    const dim=daysInMonth(y,m);
    let col=0, wkSum=0, wkHas=false;
    const flushWeek=()=>{
      html+=`<div class="wcell"><div class="wk-l">Week</div>`+
        (wkHas?`<div class="wk-a ${cls(wkSum)}">${eurCompact(wkSum)}</div>`
              :`<div class="wk-a flat">—</div>`)+`</div>`;
      wkSum=0; wkHas=false;
    };
    for(let i=0;i<lead;i++){ html+=`<div class="cell blank"></div>`; col++; }
    for(let day=1;day<=dim;day++){
      const ds=iso(y,m,day);
      const wknd=[5,6].includes(mondayIdx(y,m,day));
      const inRange = ds>=s && ds<=e;
      const rec=byDate[ds];
      const isToday = ds===today ? " today":"";
      const wk = wknd?" weekend":"";
      if(!inRange){
        html+=`<div class="cell empty out${wk}"><div class="daynum">${day}</div></div>`;
      } else if(rec && Math.abs(rec.p)>=0.005){
        const c=cellColor(rec.p, scale);
        html+=`<div class="cell has${wk}${isToday}" data-d="${ds}"
                 style="background:${c.bg}">
                 <div class="daynum" ${c.strong?'style="color:rgba(255,255,255,.85)"':''}>${day}</div>
                 <div><div class="amt" style="color:${c.text}">${eurCompact(rec.p)}</div>
                 ${rec.n?`<div class="tcount" ${c.strong?'style="color:rgba(255,255,255,.75)"':''}>${rec.n} trade${rec.n===1?"":"s"}</div>`:""}</div>
               </div>`;
      } else if(rec){ // activity but net ~0
        html+=`<div class="cell has empty${wk}${isToday}" data-d="${ds}">
                 <div class="daynum">${day}</div>
                 <div><div class="amt flat">€0</div><div class="tcount">${rec.n} trade${rec.n===1?"":"s"}</div></div></div>`;
      } else {
        html+=`<div class="cell empty${wk}${isToday}"><div class="daynum">${day}</div></div>`;
      }
      if(inRange && rec){ wkSum+=rec.p; wkHas=true; }
      col++;
      if(col===7){ flushWeek(); col=0; }
    }
    if(col>0){ while(col<7){ html+=`<div class="cell blank"></div>`; col++; } flushWeek(); }
    html+=`</div></div>`;
    any=true;
    m--; if(m<0){m=11;y--;}
  }
  cal.innerHTML = any ? html : `<div class="empty-state">No data in the selected range.</div>`;
  attachTips();
}

/* ---------- tooltip ---------- */
const tip=document.getElementById("tip");
function attachTips(){
  document.querySelectorAll(".cell.has").forEach(c=>{
    c.addEventListener("mousemove", ev=>{
      const rec=byDate[c.dataset.d]; if(!rec) return;
      const p=parse(rec.d);
      tip.querySelector(".t-date").textContent =
        new Date(p.y,p.m,p.d).toLocaleDateString("en-US",{weekday:"long",month:"long",day:"numeric",year:"numeric"});
      const net=tip.querySelector(".t-net");
      net.textContent=eur(rec.p); net.className="t-net "+cls(rec.p);
      tip.querySelector('[data-k="r"]').textContent=eur(rec.r);
      tip.querySelector('[data-k="i"]').textContent=eur(rec.i);
      tip.querySelector('[data-k="f"]').textContent=eur(rec.f);
      tip.querySelector('[data-k="t"]').textContent=eur(rec.t);
      tip.querySelector('[data-k="n"]').textContent=rec.n;
      const pad=14; let x=ev.clientX+pad, y=ev.clientY+pad;
      const r=tip.getBoundingClientRect();
      if(x+r.width>window.innerWidth-8) x=ev.clientX-r.width-pad;
      if(y+r.height>window.innerHeight-8) y=ev.clientY-r.height-pad;
      tip.style.left=x+"px"; tip.style.top=y+"px"; tip.classList.add("show");
    });
    c.addEventListener("mouseleave", ()=>tip.classList.remove("show"));
  });
}

/* ---------- equity curve (cumulative P&L) ---------- */
const EQ = {VBW:1000, VBH:220, PL:6, PR:6, PT:14, PB:6};
function renderEquity(s,e){
  const host=document.getElementById("eq"), eqEnd=document.getElementById("eq-end");
  const active=DAYS.filter(d=>d.d>=s && d.d<=e).sort((a,b)=>a.d<b.d?-1:1);
  if(!active.length){ host.innerHTML=`<div class="empty-state" style="padding:34px">No data in the selected range.</div>`; eqEnd.textContent=""; return; }

  const d0=dnum(s), d1=dnum(e), span=Math.max(1,d1-d0);
  let cum=0; const pts=[{x:d0,v:0,date:s}];
  for(const d of active){ cum+=d.p; pts.push({x:dnum(d.d),v:cum,date:d.d}); }
  pts.push({x:d1,v:cum,date:e});                        // hold the last value to the right edge

  const vals=pts.map(p=>p.v).concat([0]);
  let mn=Math.min(...vals), mx=Math.max(...vals);
  const padv=Math.max((mx-mn)*0.08, 1); mn-=padv; mx+=padv;

  const {VBW,VBH,PL,PR,PT,PB}=EQ, plotW=VBW-PL-PR, plotH=VBH-PT-PB;
  const X=x=>PL+(x-d0)/span*plotW;
  const Y=v=>PT+(mx-v)/(mx-mn)*plotH;
  const zeroY=Y(0), zf=zeroY/VBH;

  const line=pts.map((p,i)=>(i?"L":"M")+X(p.x).toFixed(1)+" "+Y(p.v).toFixed(1)).join(" ");
  const area=`M${X(pts[0].x).toFixed(1)} ${zeroY.toFixed(1)} `+
    pts.map(p=>`L${X(p.x).toFixed(1)} ${Y(p.v).toFixed(1)}`).join(" ")+
    ` L${X(pts[pts.length-1].x).toFixed(1)} ${zeroY.toFixed(1)} Z`;

  const end=pts[pts.length-1].v;
  eqEnd.textContent=eur(end); eqEnd.className="c-val "+cls(end);

  // max drawdown: largest peak-to-trough drop in cumulative equity
  let curPeak=pts[0].v, curPeakDate=pts[0].date, ddMax=0, ddP=pts[0], ddT=pts[0];
  for(const p of pts){
    if(p.v>curPeak){ curPeak=p.v; curPeakDate=p.date; }
    const dd=curPeak-p.v;
    if(dd>ddMax){ ddMax=dd; ddP={x:dnum(curPeakDate),v:curPeak}; ddT=p; }
  }
  document.getElementById("eq-dd").innerHTML =
    ddMax>0.005 ? `Max drawdown <b class="neg">${eur(-ddMax)}</b>` : "";
  const ddSvg = ddMax>0.005 ? `
      <line x1="${X(ddP.x).toFixed(1)}" y1="${Y(ddP.v).toFixed(1)}" x2="${X(ddT.x).toFixed(1)}" y2="${Y(ddP.v).toFixed(1)}" stroke="var(--neg-text)" stroke-width="1" stroke-dasharray="2 3" opacity=".6" vector-effect="non-scaling-stroke"/>
      <line x1="${X(ddT.x).toFixed(1)}" y1="${Y(ddP.v).toFixed(1)}" x2="${X(ddT.x).toFixed(1)}" y2="${Y(ddT.v).toFixed(1)}" stroke="var(--neg-text)" stroke-width="1" stroke-dasharray="2 3" opacity=".6" vector-effect="non-scaling-stroke"/>
      <circle cx="${X(ddP.x).toFixed(1)}" cy="${Y(ddP.v).toFixed(1)}" r="3" fill="var(--surface)" stroke="var(--text-2)" stroke-width="1.5"/>
      <circle cx="${X(ddT.x).toFixed(1)}" cy="${Y(ddT.v).toFixed(1)}" r="3.5" fill="var(--neg)"/>` : "";

  host.innerHTML=`
    <svg viewBox="0 0 ${VBW} ${VBH}" role="img" aria-label="Cumulative P&amp;L equity curve">
      <defs>
        <linearGradient id="eqg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="${VBH}">
          <stop offset="0" stop-color="var(--pos)"/><stop offset="${zf}" stop-color="var(--pos)"/>
          <stop offset="${zf}" stop-color="var(--neg)"/><stop offset="1" stop-color="var(--neg)"/>
        </linearGradient>
      </defs>
      <line x1="${PL}" y1="${zeroY.toFixed(1)}" x2="${VBW-PR}" y2="${zeroY.toFixed(1)}"
            stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="3 4"/>
      <path d="${area}" fill="url(#eqg)" fill-opacity="0.13"/>
      <path d="${line}" fill="none" stroke="url(#eqg)" stroke-width="2"
            vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
      ${ddSvg}
      <line id="eq-cross" y1="${PT}" y2="${VBH-PB}" stroke="var(--border-strong)" stroke-width="1" style="display:none"/>
      <circle id="eq-dot" r="3.5" style="display:none"/>
      <rect id="eq-hit" x="0" y="0" width="${VBW}" height="${VBH}" fill="transparent"/>
    </svg>
    <div class="axis"><span>${s}</span><span>${e}</span></div>`;

  // hover crosshair + tooltip
  const svg=host.querySelector("svg"), hit=host.querySelector("#eq-hit");
  const dot=host.querySelector("#eq-dot"), cross=host.querySelector("#eq-cross");
  const tip=document.getElementById("eq-tip");
  hit.addEventListener("mousemove", ev=>{
    const r=svg.getBoundingClientRect();
    const vbX=(ev.clientX-r.left)/r.width*VBW;
    let best=pts[0], bd=Infinity;
    for(const p of pts){ const d=Math.abs(X(p.x)-vbX); if(d<bd){bd=d; best=p;} }
    const px=X(best.x), py=Y(best.v), col=best.v>=0?"var(--pos)":"var(--neg)";
    dot.setAttribute("cx",px); dot.setAttribute("cy",py); dot.setAttribute("fill",col); dot.style.display="";
    cross.setAttribute("x1",px); cross.setAttribute("x2",px); cross.style.display="";
    tip.querySelector(".d").textContent=fmtShort(best.date);
    const v=tip.querySelector(".v"); v.textContent=eur(best.v); v.className="v "+cls(best.v);
    let x=ev.clientX+14, y=ev.clientY+14, tr=tip.getBoundingClientRect();
    if(x+tr.width>window.innerWidth-8) x=ev.clientX-tr.width-14;
    if(y+tr.height>window.innerHeight-8) y=ev.clientY-tr.height-14;
    tip.style.left=x+"px"; tip.style.top=y+"px"; tip.classList.add("show");
  });
  hit.addEventListener("mouseleave", ()=>{ tip.classList.remove("show"); dot.style.display="none"; cross.style.display="none"; });
}

/* ---------- analytics: win/loss profile ---------- */
function winLoss(s,e){
  const a=DAYS.filter(d=>d.d>=s&&d.d<=e);
  const wins=a.filter(d=>d.p>0.005).map(d=>d.p);
  const losses=a.filter(d=>d.p<-0.005).map(d=>d.p);
  const sum=x=>x.reduce((p,c)=>p+c,0);
  const nW=wins.length, nL=losses.length;
  const avgWin=nW?sum(wins)/nW:0, avgLoss=nL?sum(losses)/nL:0;
  const winRate=(nW+nL)?nW/(nW+nL):0;
  const payoff=avgLoss?Math.abs(avgWin/avgLoss):0;
  const needPayoff=(winRate>0&&winRate<1)?(1-winRate)/winRate:0;
  const expectancy=a.length?sum(a.map(d=>d.p))/a.length:0;
  return {avgWin,avgLoss,winRate,payoff,needPayoff,expectancy,nW,nL,
    largestWin:nW?Math.max(...wins):0, largestLoss:nL?Math.min(...losses):0};
}
function renderProfile(s,e){
  const w=winLoss(s,e), host=document.getElementById("profile");
  if(w.nW+w.nL===0){ host.innerHTML=`<div class="p-sub">No closed days in range.</div>`; return; }
  const scale=Math.max(Math.abs(w.avgWin),Math.abs(w.avgLoss),1);
  const beats=w.payoff>=w.needPayoff;
  let insight;
  if(w.payoff>0 && w.payoff<1)
    insight=`Your average loss (<b class="neg">${eur(w.avgLoss)}</b>) is <b>${(1/w.payoff).toFixed(1)}×</b> your average win (<b class="pos">${eur(w.avgWin)}</b>). At a ${Math.round(w.winRate*100)}% win rate you'd need a <b>${w.needPayoff.toFixed(2)}×</b> payoff just to break even — you're running <b class="${beats?'pos':'neg'}">${w.payoff.toFixed(2)}×</b>. Cutting losers sooner is the single fastest lever.`;
  else
    insight=`Average win <b class="pos">${eur(w.avgWin)}</b> vs loss <b class="neg">${eur(w.avgLoss)}</b> — payoff <b>${w.payoff.toFixed(2)}×</b> against <b>${w.needPayoff.toFixed(2)}×</b> needed to break even. Expectancy <b class="${cls(w.expectancy)}">${eur(w.expectancy)}</b>/day.`;
  host.innerHTML=`
    <div class="p-sub">${w.nW} winning days · ${w.nL} losing days</div>
    <div class="wl-bars">
      <div class="wl-row"><span class="wl-cap">Avg win</span>
        <span class="wl-track"><span class="wl-fill" style="width:${(Math.abs(w.avgWin)/scale*100).toFixed(1)}%;background:var(--pos)"></span></span>
        <span class="wl-num pos">${eur(w.avgWin)}</span></div>
      <div class="wl-row"><span class="wl-cap">Avg loss</span>
        <span class="wl-track"><span class="wl-fill" style="width:${(Math.abs(w.avgLoss)/scale*100).toFixed(1)}%;background:var(--neg)"></span></span>
        <span class="wl-num neg">${eur(w.avgLoss)}</span></div>
    </div>
    <div class="wl-stats">
      <div class="wl-stat"><div class="k">Payoff ratio</div><div class="v ${beats?'pos':'neg'}">${w.payoff.toFixed(2)}×</div></div>
      <div class="wl-stat"><div class="k">Break-even payoff</div><div class="v">${w.needPayoff.toFixed(2)}×</div></div>
      <div class="wl-stat"><div class="k">Expectancy / day</div><div class="v ${cls(w.expectancy)}">${eurCompact(w.expectancy)}</div></div>
      <div class="wl-stat"><div class="k">Largest loss</div><div class="v neg">${eurCompact(w.largestLoss)}</div></div>
    </div>
    <div class="insight">${insight}</div>`;
}

/* ---------- analytics: performance by weekday ---------- */
function weekdayStats(s,e){
  const b=Array.from({length:7},()=>[]);
  for(const d of DAYS){ if(d.d<s||d.d>e) continue;
    const p=parse(d.d); b[(new Date(p.y,p.m,p.d).getDay()+6)%7].push(d.p); }
  return b.map((arr,i)=>{
    const sum=arr.reduce((a,c)=>a+c,0), n=arr.length;
    const wl=arr.filter(x=>x>0.005).length, ll=arr.filter(x=>x<-0.005).length;
    return {i,label:WD[i],avg:n?sum/n:0,n,winRate:(wl+ll)?wl/(wl+ll):0,active:(wl+ll)>0};
  });
}
function renderWeekday(s,e){
  const wd=weekdayStats(s,e), host=document.getElementById("dow");
  const scale=Math.max(...wd.map(d=>Math.abs(d.avg)),1);
  const VBW=560,VBH=150,top=10,bot=VBH-38,mid=(top+bot)/2,half=(bot-top)/2,slot=VBW/7,bw=slot*0.44;
  let bars="";
  wd.forEach(d=>{
    const cx=(d.i+0.5)*slot;
    const up=d.avg>=0;
    const hh=Math.max(Math.abs(d.avg)/scale*half, d.active?2:0);
    const y=up?mid-hh:mid;
    if(d.active) bars+=`<rect x="${(cx-bw/2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" rx="3" fill="${up?'var(--pos)':'var(--neg)'}"/>`;
    bars+=`<text x="${cx.toFixed(1)}" y="${VBH-20}" text-anchor="middle" font-size="12.5" font-weight="600" fill="var(--muted)">${d.label}</text>`;
    bars+=`<text x="${cx.toFixed(1)}" y="${VBH-5}" text-anchor="middle" font-size="11" fill="${d.active?'var(--text-2)':'var(--muted)'}">${d.active?Math.round(d.winRate*100)+'%':'–'}</text>`;
  });
  host.innerHTML=`<svg viewBox="0 0 ${VBW} ${VBH}" role="img" aria-label="Average P&amp;L by weekday">
    <line x1="0" y1="${mid}" x2="${VBW}" y2="${mid}" stroke="var(--border-strong)" stroke-width="1"/>
    ${bars}</svg>`;
}

/* ---------- analytics: rolling payoff ratio ---------- */
function renderRolling(s,e){
  const host=document.getElementById("roll");
  const beEl=document.getElementById("roll-be"), nowEl=document.getElementById("roll-now");
  const info=winLoss(s,e);
  const be=(info.needPayoff>0)?info.needPayoff:1;   // payoff needed to break even at this win rate
  const N=10, CAP=4;
  const active=DAYS.filter(d=>d.d>=s&&d.d<=e).sort((a,b)=>a.d<b.d?-1:1);
  const pts=[];
  for(let i=0;i<active.length;i++){
    const win=active.slice(Math.max(0,i-N+1),i+1);
    const w=win.filter(d=>d.p>0.005), l=win.filter(d=>d.p<-0.005);
    if(w.length && l.length){
      const aw=w.reduce((a,c)=>a+c.p,0)/w.length;
      const al=Math.abs(l.reduce((a,c)=>a+c.p,0)/l.length);
      pts.push({x:dnum(active[i].d), v:Math.min(aw/al, CAP), date:active[i].d});
    }
  }
  if(pts.length<2){ host.innerHTML=`<div class="empty-state" style="padding:34px">Not enough winning and losing days in range to compute a rolling ratio yet.</div>`; beEl.textContent=""; nowEl.textContent=""; return; }

  const now=pts[pts.length-1].v;
  beEl.innerHTML=`Break-even <b>${be.toFixed(2)}×</b>`;
  nowEl.textContent=now.toFixed(2)+"×"; nowEl.className="c-val "+(now>=be?"pos":"neg");

  const d0=dnum(s), d1=dnum(e), span=Math.max(1,d1-d0);
  const ymax=Math.max(Math.max(...pts.map(p=>p.v)), be)*1.15, ymin=0;
  const VBW=1000,VBH=180,PL=6,PR=6,PT=16,PB=6,plotW=VBW-PL-PR,plotH=VBH-PT-PB;
  const X=x=>PL+(x-d0)/span*plotW, Y=v=>PT+(ymax-v)/(ymax-ymin)*plotH;
  const beY=Y(be), zf=beY/VBH;
  const line=pts.map((p,i)=>(i?"L":"M")+X(p.x).toFixed(1)+" "+Y(p.v).toFixed(1)).join(" ");

  host.innerHTML=`
    <svg viewBox="0 0 ${VBW} ${VBH}" role="img" aria-label="Rolling payoff ratio">
      <defs><linearGradient id="rollg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="${VBH}">
        <stop offset="0" stop-color="var(--pos)"/><stop offset="${zf}" stop-color="var(--pos)"/>
        <stop offset="${zf}" stop-color="var(--neg)"/><stop offset="1" stop-color="var(--neg)"/>
      </linearGradient></defs>
      <line x1="${PL}" y1="${beY.toFixed(1)}" x2="${VBW-PR}" y2="${beY.toFixed(1)}" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="3 4"/>
      <text x="${PL+2}" y="${(beY-5).toFixed(1)}" font-size="11" fill="var(--muted)">break-even ${be.toFixed(2)}×</text>
      <path d="${line}" fill="none" stroke="url(#rollg)" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
      <line id="roll-cross" y1="${PT}" y2="${VBH-PB}" stroke="var(--border-strong)" stroke-width="1" style="display:none"/>
      <circle id="roll-dot" r="3.5" style="display:none"/>
      <rect id="roll-hit" x="0" y="0" width="${VBW}" height="${VBH}" fill="transparent"/>
    </svg>
    <div class="axis"><span>${pts[0].date}</span><span>${pts[pts.length-1].date}</span></div>`;

  const svg=host.querySelector("svg"), hit=host.querySelector("#roll-hit");
  const dot=host.querySelector("#roll-dot"), cross=host.querySelector("#roll-cross"), tip=document.getElementById("eq-tip");
  hit.addEventListener("mousemove", ev=>{
    const r=svg.getBoundingClientRect(), vbX=(ev.clientX-r.left)/r.width*VBW;
    let best=pts[0], bd=Infinity;
    for(const p of pts){ const d=Math.abs(X(p.x)-vbX); if(d<bd){bd=d; best=p;} }
    const px=X(best.x), py=Y(best.v), col=best.v>=be?"var(--pos)":"var(--neg)";
    dot.setAttribute("cx",px); dot.setAttribute("cy",py); dot.setAttribute("fill",col); dot.style.display="";
    cross.setAttribute("x1",px); cross.setAttribute("x2",px); cross.style.display="";
    tip.querySelector(".d").textContent=fmtShort(best.date);
    const v=tip.querySelector(".v"); v.textContent=best.v.toFixed(2)+"× payoff"; v.className="v "+(best.v>=be?"pos":"neg");
    let x=ev.clientX+14, y=ev.clientY+14, tr=tip.getBoundingClientRect();
    if(x+tr.width>window.innerWidth-8) x=ev.clientX-tr.width-14;
    if(y+tr.height>window.innerHeight-8) y=ev.clientY-tr.height-14;
    tip.style.left=x+"px"; tip.style.top=y+"px"; tip.classList.add("show");
  });
  hit.addEventListener("mouseleave", ()=>{ tip.classList.remove("show"); dot.style.display="none"; cross.style.display="none"; });
}

/* ---------- filter wiring ---------- */
const startEl=document.getElementById("start"), endEl=document.getElementById("end");
function clampToData(v){ return v<META.min_date?META.min_date : v>META.max_date?META.max_date : v; }
function refresh(){
  let s=startEl.value||META.min_date, e=endEl.value||META.max_date;
  if(s>e){ [s,e]=[e,s]; startEl.value=s; endEl.value=e; }
  renderSummary(s,e); renderEquity(s,e); renderProfile(s,e); renderWeekday(s,e); renderRolling(s,e); renderCalendar(s,e); markPreset();
}
function setRange(s,e){ startEl.value=clampToData(s); endEl.value=clampToData(e); refresh();
  document.getElementById("cal").scrollTop=0; }   // latest month is at the top

document.getElementById("presets").addEventListener("click", ev=>{
  const b=ev.target.closest(".preset"); if(!b) return;
  const p=b.dataset.preset, end=META.max_date;
  if(p==="all") setRange(META.min_date, META.max_date);
  else if(p==="ytd"){ const y=parse(end).y; setRange(iso(y,0,1), end); }
  else if(p==="mtd"){ const d=parse(end); setRange(iso(d.y,d.m,1), end); }
  else setRange(addDays(end, -(Number(p)-1)), end);
});
function markPreset(){
  const s=startEl.value, e=endEl.value, end=META.max_date;
  let active="";
  if(s===META.min_date && e===META.max_date) active="all";
  else if(e===end){
    const pe=parse(end), y=pe.y;
    if(s===iso(y,0,1)) active="ytd";
    else if(s===iso(y,pe.m,1)) active="mtd";
    else for(const n of [7,30,90]) if(s===addDays(end,-(n-1))) active=String(n);
  }
  document.querySelectorAll(".preset").forEach(b=>b.classList.toggle("active", b.dataset.preset===active));
}
startEl.addEventListener("change", refresh);
endEl.addEventListener("change", refresh);

/* ---------- collapsible panels (state persisted) ---------- */
function initCollapse(){
  let st={};
  try{ st=JSON.parse(localStorage.getItem("pnl-collapsed")||"{}"); }catch(e){}
  document.querySelectorAll(".collapsible").forEach(sec=>{
    const key=sec.dataset.collapse;
    if(st[key]) sec.classList.add("collapsed");
    const head=sec.querySelector(".collapse-toggle");
    if(head) head.addEventListener("click", ()=>{
      sec.classList.toggle("collapsed");
      st[key]=sec.classList.contains("collapsed");
      try{ localStorage.setItem("pnl-collapsed", JSON.stringify(st)); }catch(e){}
    });
  });
}

/* ---------- theme ---------- */
const themeBtn=document.getElementById("themeBtn");
function applyTheme(t){
  document.documentElement.setAttribute("data-theme",t);
  document.getElementById("themeIcon").textContent = t==="dark"?"◑":"◐";
  document.getElementById("themeLbl").textContent = t==="dark"?"Dark":"Light";
  try{ localStorage.setItem("pnl-theme",t); }catch(e){}
}
themeBtn.addEventListener("click", ()=>{
  applyTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark");
});

/* ---------- init ---------- */
(function init(){
  let t="dark"; try{ t=localStorage.getItem("pnl-theme")||"dark"; }catch(e){}
  applyTheme(t);
  document.getElementById("brand-sub").textContent =
    `${META.min_date} — ${META.max_date} · ${META.n_txns} transactions · ${META.n_days} active days`;
  const note = META.missing_basis
    ? ` · ${META.missing_basis} sell(s) had no prior cost basis in the data (treated as zero cost)`
    : "";
  document.getElementById("footer").innerHTML =
    `Realized P&amp;L via running average-cost per instrument · dividends &amp; interest as income · fees deducted · capital-gains tax withheld and tax-optimisation refunds both included · cash transfers excluded${note}.<br>`+
    `Regenerate with <code>python build.py</code> after updating <code>data/*.csv</code>.`;
  startEl.min=endEl.min=META.min_date; startEl.max=endEl.max=META.max_date;
  startEl.value=META.min_date; endEl.value=META.max_date;
  renderStats();
  refresh();
  initCollapse();
})();
