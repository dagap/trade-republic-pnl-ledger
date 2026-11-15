/* ---------- day view: click a calendar day for its trade-by-trade report ----------
   The numbers and section renderers live in day-core.js (the DV namespace) so the
   printable PDF report can reuse them; this file only wires up the overlay:
   open / step / close, and the "Generate report" button. */
(function(){
  const {dayTrades,summarize,headerHTML,kpisHTML,drawEquity,drawTimeline,barsHTML,tableHTML,card,hideTip,METHOD_NOTE}=DV;
  const overlay=document.getElementById("dv"), body=document.getElementById("dv-body");
  const btnPrev=document.getElementById("dv-prev"), btnNext=document.getElementById("dv-next");
  const btnReport=document.getElementById("dv-report"), status=document.getElementById("dv-status");
  const selTheme=document.getElementById("dv-theme");
  const TRADE_DAYS=[...new Set(DAYS.map(d=>d.d))].sort();
  let CUR=null, lastFocus=null;

  /* ---------- render ---------- */
  function render(){
    const date=CUR, rec=byDate[date], ts=dayTrades(date), S=ts.length?summarize(ts):null;
    let html=headerHTML(date,rec,ts,S);
    if(S){
      html+=kpisHTML(S)+
        card("Equity curve","Cumulative realised net P&amp;L, stepping at each exit",`<div class="dv-chart" id="dv-eq"></div>`)+
        card("Trade timeline","Each bar runs from entry to exit; the number at the end is net P&amp;L"+
             (S.carried.length?" · ◂ marks a position opened on an earlier day":""),`<div class="dv-chart" id="dv-tl"></div>`)+
        `<div class="dv-grid">`+
          card("Net by underlying","Sum of net P&amp;L per underlying",barsHTML(S.byU,g=>g.k))+
          card("Long vs short","Sum of net P&amp;L by product direction",barsHTML(S.bySide,g=>g.k))+
        `</div>`+
        card("All trades","One row per closed trade, in entry order",tableHTML(ts))+
        `<details class="dv-foot"><summary>How these numbers are worked out</summary>
          <p>${METHOD_NOTE}</p></details>`;
    }
    body.innerHTML=html;
    if(S){ drawEquity(document.getElementById("dv-eq"),ts,date); drawTimeline(document.getElementById("dv-tl"),ts,date); }
    const i=TRADE_DAYS.indexOf(date);
    btnPrev.disabled=i<=0; btnNext.disabled=i<0||i>=TRADE_DAYS.length-1;
    btnReport.disabled=!S;
    btnReport.title=S?"Save this day as a PDF in reports/":"No closed trades on this day";
    setStatus("");
  }

  /* ---------- generate report ----------
     Needs the local report server (serve.py): a static HTML file can't write to
     disk. Opened straight from the file system, the button explains how to start it. */
  const SERVED=location.protocol.startsWith("http");
  let statusTimer;
  function setStatus(text,kind){
    clearTimeout(statusTimer);
    status.textContent=text; status.className="dv-status"+(kind?" "+kind:"");
    if(text && kind!=="busy") statusTimer=setTimeout(()=>setStatus(""),kind==="err"?12000:6000);
  }
  /* PDF theme: light unless this viewer picked dark before (remembered per browser). */
  try{ if(localStorage.getItem("pnl-report-theme")==="dark") selTheme.value="dark"; }catch(e){}
  selTheme.addEventListener("change",()=>{
    try{ localStorage.setItem("pnl-report-theme",selTheme.value); }catch(e){}
  });

  async function generateReport(){
    if(!SERVED){
      setStatus("Reports need the local server: run  uv run python serve.py","err");
      return;
    }
    const date=CUR;
    btnReport.disabled=true; setStatus("Generating PDF…","busy");
    try{
      const res=await fetch("api/report",{method:"POST",headers:{"Content-Type":"application/json"},
                                          body:JSON.stringify({date,theme:selTheme.value,view:VIEW})});
      const out=await res.json().catch(()=>({error:`HTTP ${res.status}`}));
      if(!res.ok) throw new Error(out.error||`HTTP ${res.status}`);
      if(CUR===date) setStatus(`Saved ${out.path}`,"ok");
    }catch(err){
      if(CUR===date) setStatus(`Report failed: ${err.message}`,"err");
    }finally{
      if(CUR===date) btnReport.disabled=!TRADES.some(t=>t.d===date);
    }
  }

  /* ---------- open / step / close ---------- */
  function openDay(date){
    if(!overlay.hidden && CUR===date) return;
    if(overlay.hidden) lastFocus=document.activeElement;
    CUR=date;
    document.getElementById("tip").classList.remove("show");
    hideTip();
    overlay.hidden=false; document.body.classList.add("dv-open");
    render();
    overlay.scrollTop=0;
    overlay.querySelector(".dv-panel").focus({preventScroll:true});
  }
  function step(n){
    const i=TRADE_DAYS.indexOf(CUR)+n;
    if(i>=0 && i<TRADE_DAYS.length){ CUR=TRADE_DAYS[i]; hideTip(); render(); overlay.scrollTop=0; }
  }
  function close(){
    overlay.hidden=true; document.body.classList.remove("dv-open"); hideTip();
    const cell=document.querySelector(`.cell[data-d="${CUR}"]`);
    (cell||lastFocus)?.focus?.({preventScroll:true});
  }

  document.getElementById("cal").addEventListener("click",ev=>{
    const c=ev.target.closest(".cell.has[data-d]"); if(c) openDay(c.dataset.d);
  });
  document.getElementById("cal").addEventListener("keydown",ev=>{
    if(ev.key!=="Enter" && ev.key!==" ") return;
    const c=ev.target.closest(".cell.has[data-d]"); if(c){ ev.preventDefault(); openDay(c.dataset.d); }
  });
  // calendar cells are re-rendered on every navigation: make the clickable ones keyboard-reachable
  new MutationObserver(()=>document.querySelectorAll("#cal .cell.has[data-d]").forEach(c=>{
    if(!c.hasAttribute("tabindex")){ c.tabIndex=0; c.setAttribute("role","button"); c.setAttribute("aria-label",`Open ${c.dataset.d}`); }
  })).observe(document.getElementById("cal"),{childList:true,subtree:true});
  document.querySelectorAll("#cal .cell.has[data-d]").forEach(c=>{ c.tabIndex=0; c.setAttribute("role","button"); });

  btnPrev.addEventListener("click",()=>step(-1));
  btnNext.addEventListener("click",()=>step(1));
  btnReport.addEventListener("click",generateReport);
  document.getElementById("dv-close").addEventListener("click",close);
  overlay.addEventListener("click",ev=>{ if(ev.target===overlay) close(); });
  document.addEventListener("keydown",ev=>{
    if(overlay.hidden) return;
    if(ev.key==="Escape") close();
    else if(ev.key==="ArrowLeft" && !ev.target.closest("input,summary")) step(-1);
    else if(ev.key==="ArrowRight" && !ev.target.closest("input,summary")) step(1);
  });
  let rt; window.addEventListener("resize",()=>{ if(overlay.hidden) return; clearTimeout(rt); rt=setTimeout(render,120); });
})();
