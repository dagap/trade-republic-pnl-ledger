/* ---------- printable day report ----------
   Lays out one day on A4 pages: masthead, headline result, key figures, the
   intraday charts, net by underlying / direction and the trade list. All
   numbers come from day-core.js (DV), so they match the interactive day view.
   REPORT = {date, generated} is injected by report.py. */
(function(){
  const {esc,eur0,hold,dayTrades,summarize,dayTitle,subLine,takeHTML,drawEquity,drawTimeline,barsHTML,METHOD_NOTE}=DV;
  const date=REPORT.date, rec=byDate[date], ts=dayTrades(date), S=ts.length?summarize(ts):null;
  const root=document.getElementById("rp");

  const num=(v,d=2)=>Number(v).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
  const qty=v=>Number(v).toLocaleString("en-US",{maximumFractionDigits:4});
  const pct=v=>(Math.round(v*10)/10).toFixed(1).replace(/\.0$/,"")+"%";
  const hm=iso=>new Date(iso).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
  const shortDate=iso=>new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric"});
  const arrow=t=>t.side==="Long"?"▲":t.side==="Short"?"▼":"";
  const generated=new Date(REPORT.generated).toLocaleString("en-GB",
    {day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"});

  const section=(title,cap,inner,extra="")=>`<section class="rp-sec${extra}">
      <div class="rp-sec-h"><h2>${title}</h2>${cap?`<p>${cap}</p>`:""}</div>${inner}</section>`;

  function masthead(){
    return `<header class="rp-mast">
        <div class="rp-brand"><span class="rp-mark" aria-hidden="true"></span>P&amp;L Ledger</div>
        <div class="rp-kind">Daily trading report</div>
      </header>`;
  }

  function hero(){
    const net=S?S.net:(rec?rec.p:0);
    const after=rec && S && Math.abs(rec.p-S.net)>=0.5
      ? `<div class="rp-net-after">${eur0(rec.p)} after tax &amp; interest</div>` : "";
    return `<section class="rp-hero">
        <div class="rp-hero-l">
          <div class="rp-eyebrow">Trading day</div>
          <h1>${dayTitle(date)}</h1>
          <p class="rp-sub">${subLine(rec,S)}</p>
        </div>
        <div class="rp-hero-r">
          <div class="rp-eyebrow">Net P&amp;L</div>
          <div class="rp-net ${cls(net)}">${eur0(net)}</div>
          ${after}
        </div>
      </section>
      <p class="rp-take">${takeHTML(rec,S)}</p>`;
  }

  function kpis(){
    const k=(label,val,valCls,note)=>`<div class="rp-kpi"><div class="rp-kl">${label}</div>
      <div class="rp-kv ${valCls||""}">${val}</div><div class="rp-kn">${note}</div></div>`;
    return `<section class="rp-kpis">
      ${k("Win rate",pct(S.winRate*100),"",`${S.wins} win${S.wins===1?"":"s"} · ${S.losses} loss${S.losses===1?"":"es"}`)}
      ${k("Profit factor",S.pf===null?(S.wins?"no losses":"—"):S.pf.toFixed(1)+"×","",`Avg win ${eur0(S.avgWin)} · avg loss ${eur0(S.avgLoss)}`)}
      ${k("Best trade",eur0(S.best.p),cls(S.best.p),`Worst ${eur0(S.worst.p)}`)}
      ${k("Gross P&amp;L",eur0(S.gross),cls(S.gross),`Fees ${eur0(S.fees,false)}`)}
      ${k("Average hold",S.avgHold===null?"—":hold(S.avgHold),"",S.longest?`Longest ${hold(S.longest.holdMin)}${S.longest.carried?" · overnight":""}`:"")}
      ${k("Capital deployed",eur0(S.turnover,false),"","Sum of all entry costs")}
    </section>`;
  }

  function table(){
    const rows=[...ts].sort((a,b)=>a.n-b.n).map(t=>{
      const inn=!t.o?"—":t.carried?`${shortDate(t.o)} ${hm(t.o)}<span class="rp-tag">O/N</span>`:hm(t.o);
      const out=hm(t.c)+(t.how==="ko"?`<span class="rp-tag neg">KO</span>`:"");
      const prod=[t.prod,t.ko].filter(Boolean).map(esc).join(" · ")||"—";
      return `<tr>
        <td class="n">${t.n}</td><td>${inn}</td><td>${out}</td><td class="r">${t.o?hold(t.holdMin):"—"}</td>
        <td><b>${esc(t.u)}</b><div class="rp-isin">${esc(t.s.length>14?"…"+t.s.slice(-8):t.s)}${BROKERS.length>1&&t.b?" · "+esc(brokerName(t.b)):""}</div></td>
        <td>${t.side?`${t.side} ${arrow(t)}`:"—"}</td>
        <td class="rp-prod">${prod}</td>
        <td class="r">${qty(t.q)}</td><td class="r">${num(t.ep)}</td><td class="r">${num(t.xp,t.xp<0.1&&t.xp>0?3:2)}</td>
        <td class="r">${num(t.cost)}</td>
        <td class="r ${cls(t.p)}"><b>${eur(t.p)}</b></td>
        <td class="r ${cls(t.p)}">${t.cost?(t.ret>0?"+":t.ret<0?"−":"")+pct(Math.abs(t.ret*100)):"—"}</td>
      </tr>`;
    }).join("");
    return `<table class="rp-table">
      <thead><tr><th class="n">#</th><th>In</th><th>Out</th><th class="r">Hold</th><th>Underlying</th><th>Side</th>
        <th>Product</th><th class="r">Qty</th><th class="r">Entry</th><th class="r">Exit</th><th class="r">Cost</th>
        <th class="r">Net</th><th class="r">Return</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="10">${S.n} trade${S.n===1?"":"s"}</td><td class="r">${num(S.turnover)}</td>
        <td class="r ${cls(S.net)}"><b>${eur(S.net)}</b></td><td></td></tr></tfoot></table>`;
  }

  let html=masthead()+hero();
  if(S){
    html+=kpis()+
      section("Equity curve","Cumulative realised net P&amp;L, stepping at each exit",`<div class="rp-chart" id="rp-eq"></div>`)+
      section("Trade timeline","Each bar runs from entry to exit; the number at the end is net P&amp;L"+
              (S.carried.length?" · ◂ marks a position opened on an earlier day":""),`<div class="rp-chart" id="rp-tl"></div>`)+
      `<div class="rp-grid">`+
        section("Net by underlying","",barsHTML(S.byU,g=>g.k))+
        section("Long vs short","",barsHTML(S.bySide,g=>g.k))+
      `</div>`+
      section("All trades","One row per closed trade, in entry order · O/N = carried in overnight · KO = knocked out",table()," rp-sec-table")+
      `<section class="rp-note"><h2>Methodology</h2><p>${METHOD_NOTE}</p></section>`;
  }
  html+=`<footer class="rp-foot">Generated ${esc(generated)} · P&amp;L Ledger · figures in EUR, times in local time</footer>`;
  root.innerHTML=html;
  if(S){ drawEquity(document.getElementById("rp-eq"),ts,date); drawTimeline(document.getElementById("rp-tl"),ts,date); }
  document.title=`Daily report · ${date}`;
})();
