/* ---------- day-view core: the numbers and section renderers for one day ----------
   Shared by the interactive day view (day.js) and the printable day report
   (report.js). Uses the globals from core.js (TRADES, byDate, eur, cls, parse).
   Every closed trade in META.trades carries o/c (opened/closed timestamps), the
   instrument (u, side, ko, prod, s), q, cost, ep/xp, fee and how ("ko" = knocked
   out). Charts are plain SVG sized to their host's real width, so labels stay
   legible on a phone and fit an A4 page. */
const DV=(()=>{
  /* ---------- helpers ---------- */
  const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const MINUS="−";
  function eur0(v,signed=true){
    const a=Math.round(Math.abs(v));
    if(a===0) return "€0";
    return (v<0?MINUS:signed?"+":"")+"€"+a.toLocaleString("en-US");
  }
  const num=(v,d=2)=>Number(v).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
  const qty=v=>Number(v).toLocaleString("en-US",{maximumFractionDigits:4});
  const pct=v=>(Math.round(v*10)/10).toFixed(1).replace(/\.0$/,"")+"%";
  const ms=iso=>new Date(iso).getTime();
  const hm=t=>new Date(t).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
  const localDay=iso=>{ const d=new Date(iso); return iso && `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };
  const shortDate=iso=>new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric"});
  function hold(min){
    if(min<1) return "<1 min";
    if(min<60) return Math.round(min)+" min";
    if(min<1440){ const h=Math.floor(min/60), m=Math.round(min%60); return `${h}h ${String(m).padStart(2,"0")}m`; }
    const d=Math.floor(min/1440), h=Math.round((min%1440)/60); return `${d}d ${h}h`;
  }
  const tone=v=>v>0.005?"var(--pos)":v<-0.005?"var(--neg)":"var(--border-strong)";
  const toneText=v=>v>0.005?"var(--pos-text)":v<-0.005?"var(--neg-text)":"var(--muted)";
  const arrow=t=>t.side==="Long"?"▲":t.side==="Short"?"▼":"";
  const textW=(s,px=12)=>String(s).length*px*0.6;   // label width estimate, no layout pass needed
  function niceTicks(lo,hi,count){
    const range=hi-lo||1, raw=range/count, mag=10**Math.floor(Math.log10(raw)), n=raw/mag;
    const step=(n<=1?1:n<=2?2:n<=5?5:10)*mag, out=[];
    for(let v=Math.ceil(lo/step)*step; v<=hi+step*1e-9; v+=step) out.push(Math.abs(v)<step*1e-9?0:v);
    return out;
  }
  function timeTicks(t0,t1,maxTicks){
    const span=(t1-t0)/60000;
    const step=[5,10,15,30,60,120,180,240,360,720].find(s=>span/s<=maxTicks)||1440;
    const d=new Date(t0); d.setSeconds(0,0);
    d.setMinutes(Math.ceil((d.getHours()*60+d.getMinutes())/step)*step-d.getHours()*60);
    const out=[]; for(let t=d.getTime(); t<=t1; t+=step*60000) out.push(t);
    return out;
  }
  const tipEl=()=>document.getElementById("eq-tip");
  function showTip(ev,dLine,vHTML,vCls,sLine){
    const ftip=tipEl(); if(!ftip) return;
    ftip.querySelector(".d").textContent=dLine;
    const v=ftip.querySelector(".v"); v.innerHTML=vHTML; v.className="v "+(vCls||"");
    ftip.querySelector(".s").textContent=sLine||"";
    let x=ev.clientX+14, y=ev.clientY+14; const r=ftip.getBoundingClientRect();
    if(x+r.width>window.innerWidth-8) x=ev.clientX-r.width-14;
    if(y+r.height>window.innerHeight-8) y=ev.clientY-r.height-14;
    ftip.style.left=x+"px"; ftip.style.top=y+"px"; ftip.classList.add("show");
  }
  const hideTip=()=>tipEl()?.classList.remove("show");

  /* ---------- the numbers ---------- */
  function dayTrades(date){
    const ts=TRADES.filter(t=>t.d===date).map(t=>({...t}));
    // number in entry order (a carried-in position counts from when it was opened)
    ts.sort((a,b)=>(a.o||a.c)<(b.o||b.c)?-1:1).forEach((t,i)=>{
      t.n=i+1;
      t.holdMin=t.o?(ms(t.c)-ms(t.o))/60000:0;
      t.carried=!!t.o && localDay(t.o)!==localDay(t.c);
      t.ret=t.cost?t.p/t.cost:0;
    });
    let cum=0;
    [...ts].sort((a,b)=>a.c<b.c?-1:1).forEach(t=>{ cum+=t.p; t.cum=cum; });
    return ts;
  }
  function summarize(ts){
    const sum=(a,f)=>a.reduce((s,t)=>s+f(t),0);
    const wins=ts.filter(t=>t.p>0.005), losses=ts.filter(t=>t.p<=0.005);
    const net=sum(ts,t=>t.p), fees=sum(ts,t=>t.fee||0);
    const gW=sum(wins,t=>t.p), gL=-sum(losses,t=>t.p);
    const group=key=>{
      const g={};
      for(const t of ts){ const k=key(t); const x=g[k]||(g[k]={k,net:0,n:0,w:0}); x.net+=t.p; x.n++; if(t.p>0.005) x.w++; }
      return Object.values(g).sort((a,b)=>b.net-a.net);
    };
    const ranked=[...ts].sort((a,b)=>b.p-a.p);
    const held=ts.filter(t=>t.o);
    const carried=ts.filter(t=>t.carried);
    return {
      net, fees, gross:net-fees, n:ts.length, wins:wins.length, losses:losses.length,
      winRate:ts.length?wins.length/ts.length:0,
      pf:gL>0.005?gW/gL:null,
      avgWin:wins.length?gW/wins.length:0, avgLoss:losses.length?-gL/losses.length:0,
      best:ranked[0], worst:ranked[ranked.length-1], ranked,
      avgHold:held.length?sum(held,t=>t.holdMin)/held.length:null,
      longest:held.length?held.reduce((a,t)=>t.holdMin>a.holdMin?t:a):null,
      turnover:sum(ts,t=>t.cost||0),
      byU:group(t=>t.u||t.s||"—"), bySide:group(t=>t.side||"Other"),
      carried, carriedNet:sum(carried,t=>t.p),
    };
  }

  /* ---------- sections ---------- */
  function dayTitle(date){
    const p=parse(date);
    return new Date(p.y,p.m,p.d).toLocaleDateString("en-US",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
  }
  function subLine(rec,S){
    const nU=S?S.byU.length:0;
    return S
      ? `${S.n} closed trade${S.n===1?"":"s"} · ${nU} underlying${nU===1?"":"s"} · times in your local timezone`
      : `${rec?rec.n:0} transaction${rec&&rec.n===1?"":"s"} · no positions closed`;
  }
  /* the one-paragraph plain-English summary of the day */
  function takeHTML(rec,S){
    let take="";
    if(S){
      const b=v=>`<b class="${cls(v)}">${eur0(v)}</b>`;
      const lead=S.byU[0], tail=S.byU[S.byU.length-1];
      if(S.net>=0){
        take=`Closed ${b(S.net)} net over <b>${S.n}</b> trade${S.n===1?"":"s"}.`;
        if(lead && S.byU.length>1) take+=` <b>${esc(lead.k)}</b> was the engine at ${b(lead.net)}`;
        else if(lead) take+=` All of it in <b>${esc(lead.k)}</b>`;
        if(S.n>=3 && S.net>0.5){
          const share=(S.ranked[0].p+S.ranked[1].p)/S.net*100;
          take+=`, and the two best trades delivered <b>${pct(share)}</b> of the day's net.`;
        } else take+=".";
      } else {
        take=`Gave back ${b(S.net)} over <b>${S.n}</b> trade${S.n===1?"":"s"}.`;
        if(tail && S.byU.length>1) take+=` <b>${esc(tail.k)}</b> did the most damage at ${b(tail.net)}`;
        else if(tail) take+=` All of it in <b>${esc(tail.k)}</b>`;
        if(S.n>=3){
          const r=S.ranked, share=(r[r.length-1].p+r[r.length-2].p)/S.net*100;
          take+=`; the two worst trades account for <b>${pct(share)}</b> of it.`;
        } else take+=".";
      }
      if(S.carried.length)
        take+= S.n===1 ? ` It was carried in from an earlier session.`
          : ` <b>${S.carried.length}</b> of them ${S.carried.length===1?"was":"were"} carried in from an earlier session (${b(S.carriedNet)}).`;
      if(rec && Math.abs(rec.p-S.net)>=0.5)
        take+=` After tax and interest the day closes at ${b(rec.p)}.`;
    } else if(rec){
      take=`Nothing was closed on this day, so there's no trade report. The day's net is <b class="${cls(rec.p)}">${eur(rec.p)}</b>`+
           ` (interest ${eur(rec.i)}, tax ${eur(rec.t)}).`;
    }
    return take;
  }
  function headerHTML(date,rec,ts,S){
    const take=takeHTML(rec,S);
    return `<header class="dv-head">
        <h2 id="dv-title">${dayTitle(date)}</h2>
        <p class="dv-sub">${subLine(rec,S)}</p>
        ${take?`<p class="dv-take">${take}</p>`:""}
      </header>`;
  }

  function kpisHTML(S){
    const k=(label,val,valCls,note)=>`<div class="dv-card"><div class="dv-kl">${label}</div>
      <div class="dv-kv ${valCls||""}">${val}</div><div class="dv-kn">${note}</div></div>`;
    return `<section class="dv-kpis" aria-label="Key figures">
      ${k("Net P&amp;L",eur0(S.net),cls(S.net),`Gross ${eur0(S.gross)} · fees ${eur0(S.fees,false)}`)}
      ${k("Win rate",pct(S.winRate*100),"",`${S.wins} win${S.wins===1?"":"s"} · ${S.losses} loss${S.losses===1?"":"es"}`)}
      ${k("Profit factor",S.pf===null?(S.wins?"no losses":"—"):S.pf.toFixed(1)+"×","",`Avg win ${eur0(S.avgWin)} · avg loss ${eur0(S.avgLoss)}`)}
      ${k("Best trade",eur0(S.best.p),cls(S.best.p),`Worst ${eur0(S.worst.p)}`)}
      ${k("Average hold",S.avgHold===null?"—":hold(S.avgHold),"",S.longest?`Longest ${hold(S.longest.holdMin)}${S.longest.carried?" · overnight":""}`:"")}
      ${k("Capital deployed",eur0(S.turnover,false),"","Sum of all entry costs")}
    </section>`;
  }

  /* the time window the charts span: from the first same-day entry (or first
     exit) to the last exit; positions carried in from an earlier day are
     clipped to its left edge */
  function window_(ts,date){
    const pts=[];
    for(const t of ts){ pts.push(ms(t.c)); if(t.o && !t.carried) pts.push(ms(t.o)); }
    let t0=Math.min(...pts), t1=Math.max(...pts);
    if(t1-t0<10*60000){ const mid=(t0+t1)/2; t0=mid-5*60000; t1=mid+5*60000; }
    return [t0,t1];
  }

  function drawEquity(host,ts,date){
    const W=Math.max(240,host.clientWidth||900), H=240;
    const [t0,t1]=window_(ts,date);
    const byExit=[...ts].sort((a,b)=>a.c<b.c?-1:1);
    const vals=[0,...byExit.map(t=>t.cum)];
    let lo=Math.min(...vals), hi=Math.max(...vals);
    const yt=niceTicks(lo,hi,4); lo=Math.min(lo,yt[0]); hi=Math.max(hi,yt[yt.length-1]);
    if(hi-lo<1){ hi+=1; lo-=1; }
    const m={t:18, r:18, b:26, l:Math.max(...yt.map(v=>textW(eur0(v,false),11)))+14};
    const X=t=>m.l+(t-t0)/(t1-t0)*(W-m.l-m.r), Y=v=>m.t+(hi-v)/(hi-lo)*(H-m.t-m.b);
    let path=`M${X(t0).toFixed(1)} ${Y(0).toFixed(1)}`;
    for(const t of byExit) path+=` H${X(ms(t.c)).toFixed(1)} V${Y(t.cum).toFixed(1)}`;
    const end=byExit[byExit.length-1];
    let g="";
    for(const v of yt) g+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--border)"/>`+
      `<text x="${m.l-8}" y="${Y(v).toFixed(1)}" dy=".35em" text-anchor="end" font-size="11" fill="var(--muted)">${eur0(v,false)}</text>`;
    for(const t of timeTicks(t0,t1,Math.max(2,Math.floor((W-m.l)/80))))
      g+=`<text x="${X(t).toFixed(1)}" y="${H-6}" text-anchor="middle" font-size="11" fill="var(--muted)">${hm(t)}</text>`;
    const dots=byExit.map((t,i)=>`<circle class="dv-dot" data-i="${i}" cx="${X(ms(t.c)).toFixed(1)}" cy="${Y(t.cum).toFixed(1)}" r="4.5" fill="${tone(t.p)}" stroke="var(--surface)" stroke-width="1.5"/>`).join("");
    const ex=X(ms(end.c)), ey=Y(end.cum), anchorEnd=ex>W-m.r-60;
    host.innerHTML=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative net P&amp;L after each exit, ending at ${eur0(end.cum)}">
      ${g}
      <line x1="${m.l}" x2="${W-m.r}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--border-strong)"/>
      <path d="${path}" fill="none" stroke="var(--text-2)" stroke-width="2" stroke-linejoin="round"/>
      ${dots}
      <text x="${(anchorEnd?ex-8:ex+8).toFixed(1)}" y="${(ey-10).toFixed(1)}" text-anchor="${anchorEnd?"end":"start"}" font-size="12" font-weight="700" fill="${toneText(end.cum)}">${eur0(end.cum)}</text>
      <rect class="dv-hit" x="${m.l}" y="0" width="${W-m.l-m.r}" height="${H}" fill="transparent"/>
    </svg>`;
    const svg=host.querySelector("svg"), circles=[...svg.querySelectorAll(".dv-dot")];
    svg.querySelector(".dv-hit").addEventListener("mousemove",ev=>{
      const r=svg.getBoundingClientRect(), mx=(ev.clientX-r.left)*(W/r.width);
      let best=0; byExit.forEach((t,i)=>{ if(Math.abs(X(ms(t.c))-mx)<Math.abs(X(ms(byExit[best].c))-mx)) best=i; });
      circles.forEach((c,i)=>c.setAttribute("r",i===best?6.5:4.5));
      const t=byExit[best];
      showTip(ev,`#${t.n} ${t.u} ${t.side} · exit ${hm(ms(t.c))}`,
        `${eur(t.p)}`,cls(t.p),`running total ${eur(t.cum)}`);
    });
    svg.querySelector(".dv-hit").addEventListener("mouseleave",()=>{ hideTip(); circles.forEach(c=>c.setAttribute("r",4.5)); });
  }

  function drawTimeline(host,ts,date){
    const W=Math.max(240,host.clientWidth||900), rowH=26;
    const rows=[...ts].sort((a,b)=>a.n-b.n);
    const [t0,t1]=window_(ts,date);
    const label=t=>`#${t.n} ${t.u} ${arrow(t)}`.trim();
    const m={t:4, b:26, l:Math.min(W*0.4,Math.max(...rows.map(t=>textW(label(t))))+14),
             r:Math.max(...rows.map(t=>textW(eur0(t.p))))+12};
    const H=m.t+rows.length*rowH+m.b, bh=15;
    const X=t=>m.l+(Math.max(t,t0)-t0)/(t1-t0)*(W-m.l-m.r);
    let g="";
    for(const t of timeTicks(t0,t1,Math.max(2,Math.floor((W-m.l-m.r)/80)))){
      const x=X(t).toFixed(1);
      g+=`<line x1="${x}" x2="${x}" y1="${m.t}" y2="${H-m.b}" stroke="var(--border)"/>`+
         `<text x="${x}" y="${H-6}" text-anchor="middle" font-size="11" fill="var(--muted)">${hm(t)}</text>`;
    }
    rows.forEach((t,i)=>{
      const yc=m.t+i*rowH+rowH/2, x0=t.o?X(ms(t.o)):X(ms(t.c)), x1=X(ms(t.c)), w=Math.max(3,x1-x0);
      const fit=Math.floor((m.l-14)/(12*0.6)), full=label(t);
      const lbl=full.length>fit?`#${t.n} ${t.u}`.slice(0,Math.max(4,fit-3))+"… "+arrow(t):full;
      g+=`<text x="${m.l-10}" y="${yc}" dy=".35em" text-anchor="end" font-size="12" fill="var(--text-2)">${esc(lbl)}</text>`;
      g+=`<rect class="dv-tbar" data-i="${i}" x="${x0.toFixed(1)}" y="${(yc-bh/2).toFixed(1)}" width="${w.toFixed(1)}" height="${bh}" rx="3" fill="${tone(t.p)}"/>`;
      if(t.carried) g+=`<text x="${(x0+3).toFixed(1)}" y="${yc}" dy=".35em" font-size="10" font-weight="700" fill="var(--surface)">◂ ${shortDate(t.o)}</text>`;
      if(t.how==="ko") g+=`<text x="${(x0+w-3).toFixed(1)}" y="${yc}" dy=".35em" text-anchor="end" font-size="10" font-weight="700" fill="var(--surface)">KO</text>`;
      g+=`<text x="${(x0+w+6).toFixed(1)}" y="${yc}" dy=".35em" font-size="12" font-weight="650" fill="${toneText(t.p)}">${eur0(t.p)}</text>`;
      g+=`<rect class="dv-rowhit" data-i="${i}" x="0" y="${yc-rowH/2}" width="${W}" height="${rowH}" fill="transparent"/>`;
    });
    host.innerHTML=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of ${rows.length} trades from entry to exit, coloured by win or loss">${g}</svg>`;
    const svg=host.querySelector("svg");
    svg.querySelectorAll(".dv-rowhit").forEach(hit=>{
      hit.addEventListener("mousemove",ev=>{
        const t=rows[Number(hit.dataset.i)];
        svg.classList.add("hovering");
        svg.querySelectorAll(".dv-tbar").forEach(b=>b.classList.toggle("on",b.dataset.i===hit.dataset.i));
        const inn=t.o?(t.carried?`${shortDate(t.o)} ${hm(ms(t.o))}`:hm(ms(t.o))):"before data";
        showTip(ev,`#${t.n} ${t.u} ${t.side} ${t.prod}`.trim(),eur(t.p),cls(t.p),
          `in ${inn} → ${t.how==="ko"?"knocked out":"out"} ${hm(ms(t.c))}`+(t.o?` · ${hold(t.holdMin)}`:"")+
          ` · ${qty(t.q)} @ ${num(t.ep,2)} → ${num(t.xp,t.xp<0.1?3:2)}`);
      });
    });
    svg.addEventListener("mouseleave",()=>{ hideTip(); svg.classList.remove("hovering"); });
  }

  function barsHTML(groups,labelOf){
    const max=Math.max(1,...groups.map(g=>Math.abs(g.net)));
    return `<div class="dv-hbars">`+groups.map(g=>{
      const w=(Math.abs(g.net)/max*50).toFixed(1);
      const side=g.net>=0?`left:50%`:`right:50%`;
      return `<div class="dv-hb">
          <div class="dv-hb-l"><span>${esc(labelOf(g))}</span><span class="dv-hb-n">${g.n} trade${g.n===1?"":"s"} · ${g.w}W</span></div>
          <div class="dv-hb-track"><div class="dv-hb-fill" style="${side};width:${w}%;background:${tone(g.net)}"></div></div>
          <div class="dv-hb-v ${cls(g.net)}">${eur0(g.net)}</div>
        </div>`;
    }).join("")+`</div>`;
  }

  function tableHTML(ts){
    const multi=BROKERS.length>1;   // a Broker column only when the data spans several
    const rows=[...ts].sort((a,b)=>a.n-b.n).map(t=>{
      const inn=!t.o?`<span class="flat">—</span>`
        : t.carried?`${shortDate(t.o)} ${hm(ms(t.o))} <span class="dv-pill">overnight</span>`:hm(ms(t.o));
      const out=hm(ms(t.c))+(t.how==="ko"?` <span class="dv-pill neg">knocked out</span>`:"");
      return `<tr>
        <td class="flat">${t.n}</td><td>${inn}</td><td>${out}</td>
        <td class="r">${t.o?hold(t.holdMin):"—"}</td>
        <td class="wrap">${esc(t.u)}</td>${multi?`<td class="wrap">${esc(t.b?brokerName(t.b):"—")}</td>`:""}
        <td>${t.side?`<span class="dv-pill">${t.side} ${arrow(t)}</span>`:"—"}</td>
        <td>${esc(t.prod)||"—"}</td><td>${esc(t.ko)||"—"}</td>
        <td class="r">${qty(t.q)}</td><td class="r">${num(t.ep,t.ep>=1000?0:2)}</td><td class="r">${num(t.xp,t.xp>=1000?0:t.xp<0.1&&t.xp>0?3:2)}</td>
        <td class="r">${num(t.cost)}</td>
        <td class="r ${cls(t.p)}"><b>${eur(t.p)}</b></td>
        <td class="r ${cls(t.p)}">${t.cost?(t.ret>0?"+":t.ret<0?MINUS:"")+pct(Math.abs(t.ret*100)):"—"}</td>
        <td class="flat mono" title="${esc(t.s)}">${esc(t.s.length>14?"…"+t.s.slice(-8):t.s)}</td>
      </tr>`;
    }).join("");
    return `<div class="dv-tw"><table class="dv-table">
      <thead><tr><th>#</th><th>In</th><th>Out</th><th class="r">Hold</th><th>Underlying</th>${multi?"<th>Broker</th>":""}<th>Side</th><th>Product</th>
        <th>KO / strike</th><th class="r">Qty</th><th class="r">Entry</th><th class="r">Exit</th><th class="r">Cost</th>
        <th class="r">Net</th><th class="r">Return</th><th>ISIN / ID</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  const card=(title,cap,inner,extra="")=>`<section class="dv-card dv-sec"${extra}>
      <h3>${title}</h3><p class="dv-cap">${cap}</p>${inner}</section>`;

  const METHOD_NOTE=`Each sell is matched against the instrument's open buy lots first-in-first-out, the same way the rest of the
          dashboard (and the German tax rules) do it, so a position bought on an earlier day shows up here as carried in
          overnight. Net P&amp;L is the sell proceeds minus the matched entry cost, net of the order fee on both legs; it is
          before capital-gains tax. Return is net P&amp;L divided by the entry cost of the certificate, not the move in the
          underlying. A knocked-out position is closed at its redemption value. Long/short is the product's direction and the
          KO / strike level is taken from the product name. Capital.com trades use the realised P&amp;L on Capital.com's
          statement as-is; their entry cost is the knock-out option's value at entry, converted at the statement's FX rate.`;

  return {esc,eur0,hold,dayTrades,summarize,dayTitle,subLine,takeHTML,headerHTML,kpisHTML,
          drawEquity,drawTimeline,barsHTML,tableHTML,card,hideTip,METHOD_NOTE};
})();
