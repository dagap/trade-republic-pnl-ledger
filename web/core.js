/* ---------- shared core: the baked-in data + date / money helpers ----------
   Loaded first by both the dashboard and the printable day report, so every
   page reads the same payload and formats numbers the same way. */
const PAYLOAD = /*__DATA__*/;
const META = PAYLOAD.meta;
/* brokers in the data: [{id, name, withholds_tax}] */
const BROKERS = META.brokers || [];
const brokerName = id => (BROKERS.find(b => b.id === id) || {}).name || id;

/* ---------- the view: which broker(s), and whether estimated tax is deducted ----------
   Brokers that don't withhold capital-gains tax at source (withholds_tax=false)
   get an estimate of the tax owed, `x` on each day record (<=0 when owing,
   >0 when a later loss reduces what's owed). It is worked out per broker per
   calendar year the way the German loss pot works: tax owed to date =
   rate × max(0, year-to-date realized P&L + income), and each day's `x` is the
   change in that. `x` is always computed (to display); it's only folded into
   the day's net `p` when VIEW.estTax is on. The dashboard keeps VIEW in
   localStorage; the printable report receives it as REPORT.view. */
const DEFAULT_TAX_RATE = 0.26375;        // 25% Abgeltungsteuer + 5.5% Soli, no church tax
const VIEW = {broker: "all", estTax: false, rate: DEFAULT_TAX_RATE};
(function loadView(){
  let saved = {};
  if (typeof REPORT !== "undefined" && REPORT.view) saved = REPORT.view;
  else { try { saved = JSON.parse(localStorage.getItem("pnl-view") || "{}"); } catch (e) {} }
  if (typeof saved.broker === "string" && (saved.broker === "all" || BROKERS.some(b => b.id === saved.broker)))
    VIEW.broker = saved.broker;
  if (typeof saved.estTax === "boolean") VIEW.estTax = saved.estTax;
  if (typeof saved.rate === "number" && saved.rate >= 0 && saved.rate <= 1) VIEW.rate = saved.rate;
})();
function saveView(){ try { localStorage.setItem("pnl-view", JSON.stringify(VIEW)); } catch (e) {} }
/* any broker in the current view that doesn't withhold tax? */
function viewHasEstTax(){
  return BROKERS.some(b => !b.withholds_tax && (VIEW.broker === "all" || VIEW.broker === b.id));
}

function estTaxByDay(days, rate){
  const out = {}; let year = null, base = 0, owed = 0;
  for (const d of [...days].sort((a, b) => a.d < b.d ? -1 : 1)) {
    const y = d.d.slice(0, 4);
    if (y !== year) { year = y; base = 0; owed = 0; }
    base += d.r + d.i;
    const now = rate * Math.max(0, base);
    out[d.d] = -(now - owed); owed = now;
  }
  return out;
}
/* one broker's day records under the current view (x filled, p adjusted) */
function brokerDays(id){
  const src = (PAYLOAD.brokers && PAYLOAD.brokers[id]) ? PAYLOAD.brokers[id].days : [];
  const info = BROKERS.find(b => b.id === id) || {withholds_tax: true};
  const est = info.withholds_tax ? {} : estTaxByDay(src, VIEW.rate);
  return src.map(d => {
    const x = Math.round((est[d.d] || 0) * 100) / 100;
    return {...d, x, p: d.p + (VIEW.estTax ? x : 0)};
  });
}
function mergeDays(lists){
  const m = {};
  for (const days of lists) for (const d of days) {
    const r = m[d.d] || (m[d.d] = {d: d.d, p: 0, r: 0, i: 0, f: 0, t: 0, x: 0, n: 0});
    for (const k of ["p", "r", "i", "f", "t", "x"]) r[k] += d[k] || 0;
    r.n += d.n;
  }
  return Object.values(m).sort((a, b) => a.d < b.d ? -1 : 1);
}
function viewIds(){ return VIEW.broker === "all" ? BROKERS.map(b => b.id) : [VIEW.broker]; }

let DAYS, FLOWS, TRADES, byDate;
/* rebuild the data globals for the current VIEW */
function applyView(){
  if (!PAYLOAD.brokers || !BROKERS.length) {          // a payload from before brokers existed
    DAYS = PAYLOAD.days; FLOWS = PAYLOAD.flows || []; TRADES = META.trades || [];
  } else {
    const ids = viewIds();
    DAYS = mergeDays(ids.map(brokerDays));
    const fl = {};
    for (const id of ids) for (const f of (PAYLOAD.brokers[id].flows || [])) {
      const r = fl[f.d] || (fl[f.d] = {d: f.d, dep: 0, wd: 0}); r.dep += f.dep; r.wd += f.wd;
    }
    FLOWS = Object.values(fl).sort((a, b) => a.d < b.d ? -1 : 1);
    TRADES = (META.trades || []).filter(t => ids.includes(t.b || ids[0]));
  }
  byDate = Object.fromEntries(DAYS.map(d => [d.d, d]));
}
applyView();

const MONTHS = ["January","February","March","April","May","June","July",
  "August","September","October","November","December"];
const WD = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];   // calendar runs Sunday-first

/* ---------- date helpers (string-based, timezone-safe) ---------- */
function parse(s){ const [y,m,d]=s.split("-").map(Number); return {y,m:m-1,d}; }
function iso(y,m,d){ return `${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`; }
function weekdayIdx(y,m,d){ return new Date(y,m,d).getDay(); }   // 0=Sun … 6=Sat
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

