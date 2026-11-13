/* ---------- shared core: the baked-in data + date / money helpers ----------
   Loaded first by both the dashboard and the printable day report, so every
   page reads the same payload and formats numbers the same way. */
const PAYLOAD = /*__DATA__*/;
const DAYS = PAYLOAD.days;
const FLOWS = PAYLOAD.flows || [];
const META = PAYLOAD.meta;
const TRADES = META.trades || [];        // one {d,p} per closed sell (FIFO, net of fees)
const byDate = Object.fromEntries(DAYS.map(d => [d.d, d]));

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

