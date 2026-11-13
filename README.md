# P&L Ledger

A calendar-style trading journal that turns a broker's transaction export into a
dashboard you can actually read at a glance — daily P&L on a colour-graded
calendar, an equity curve, and a few analytics built around one question:
*am I getting better?*

It started as a personal tool for reviewing my own trading (the export format is
[Trade Republic](https://traderepublic.com)'s), but the P&L logic is general and
the whole thing is dependency-free.

![P&L Ledger dashboard](docs/dashboard.png)

## Motivation

I trade actively, and my broker's app is great for placing orders but useless for
reflection — it shows you a balance, not a story. What I actually wanted was to
*see* my P&L: which days I made money, which days I handed it back, and whether
the mistakes I keep promising myself I'll fix are actually getting fixed.
Scrolling a list of transactions doesn't tell you that; a calendar you can take
in at a glance does.

So I built the tool I wished I had — something that lets me look at a month and
immediately spot the pattern, then dig into the numbers behind it: how big my
losers are next to my winners, which days of the week I trade well or badly, and
whether my edge is trending the right way. It ended up being as much a coaching
tool as a dashboard. The point was never perfect accounting — it was to make my
own trading habits impossible to ignore.

## What it does

- **Daily P&L calendar** — every trading day coloured green/red by size, with the
  amount and trade count in the cell and a full breakdown on hover — including
  the running total up to that day, both within the selected period and
  all-time. Click a day to open its day view (below). One month at a time with prev/next navigation, a weekly total in the
  right margin and per-weekday totals along the bottom.
- **Day view** — click any trading day for a trade-by-trade report: headline
  KPIs (net, win rate, profit factor, best/worst trade, average hold, capital
  deployed), an intraday equity curve, a timeline of every position from entry to
  exit, net P&L by underlying and by long/short, and the full trade table.
  Positions carried in from an earlier session are flagged as overnight, and
  knock-outs are marked. Step between days with ← / →, close with Esc.

  ![Day view](docs/day-view.png)
- **PDF day reports** — the day view's *Generate report* button saves a
  print-ready A4 report of that day to `reports/daily_report_<date>.pdf`
  (headline result, key figures, both charts, the breakdowns and the trade
  table), ready to send on. See [Day reports](#day-reports-pdf).
- **Yearly view** — flip the calendar to *Year* and the same grid shows twelve
  months instead of days: each month coloured by its net P&L with the trade and
  day count, four months to a row, with quarter totals and best month, worst
  month, months up/down and the year total in the rows beneath. Hover a month
  for the full breakdown plus trading days and win rate. The choice is remembered.
- **Realized P&L the way the taxman sees it** — sells are matched against buy
  lots first-in-first-out per instrument (the method German tax law mandates)
  and the gain is net of trading fees, so it ties out to what Trade Republic
  shows and taxes. Profit lands on the day you *closed*, not the day you opened.
  Dividends and interest count as income; capital-gains tax is applied on its
  day; deposits and withdrawals are kept out of P&L.
- **Equity curve** with the max drawdown marked.
- **Month-by-month bars** — net P&L per month, green above the line and red
  below, so a good or bad stretch is obvious at a glance. Hover a bar for the
  trading days, win rate and trade count behind it. Months are clipped to the
  selected range (marked with a `*`), so the bars always add up to the period
  total.
- **Avg win / avg loss by month** — sits beside the month bars: average win
  and average loss per month (per closed trade, or per trading day), with the
  payoff ratio above each pair so you can see whether losses are shrinking
  month over month.
- **Win/loss profile** — average win vs. average loss, payoff ratio, and the
  payoff you'd need to break even at your win rate. (Turns out a good win rate
  doesn't save you if your losers are twice your winners.)
- **Rolling payoff ratio** — a trailing-window view so you can watch whether the
  thing you're working on is actually trending the right way.
- **Performance by weekday**, live stat cards (this week / month / year /
  all-time), date-range filtering with presets, deposit/withdrawal totals, a
  light/dark toggle, and collapsible panels — state remembered between visits.

The output is a **single self-contained `dashboard.html`** — no server, no build
step at view time, no external requests. Open it in any browser. (Only saving
PDF reports needs the tiny local server below.)

## Quick start

```sh
uv run python build.py      # reads data/*.csv -> dashboard.html
```

Then open `dashboard.html`. Out of the box it renders the bundled sample data
(`data/demo.csv`), so you can see the whole thing working before pointing it at
anything real.

> Uses [uv](https://docs.astral.sh/uv/). No `uv`? Any Python 3.9+ works:
> `python build.py`. There are no third-party runtime dependencies.

## Using your own data

### Exporting from Trade Republic

Trade Republic can hand you a CSV that's meant for exactly this kind of tool. In
the app, open **Profile → Statements & transaction export**, choose the
transaction export, and pick the **"CSV export for tracking tools"** option
(not the PDF statement or the tax-tool export — those don't carry the right
columns). Choose your date range and export. That file is what this project
reads.

### Loading it

Drop one or more of those CSVs into `data/` and rebuild. Multiple files are
merged and de-duplicated by `transaction_id`, so you can keep dropping in fresh
exports over time without worrying about overlap. As soon as a real export is
present, the bundled `demo.csv` steps aside automatically.

```sh
cp ~/Downloads/transactions.csv data/
uv run python build.py
```

The columns that matter are `date`, `type`, `symbol`, `shares`, `amount`, `fee`,
`tax`, and `transaction_id`. `type` drives everything —
`BUY` / `SELL` / `DIVIDEND` / `INTEREST_PAYMENT` / `TAX_OPTIMIZATION` /
`TRANSFER_INSTANT_INBOUND` / `TRANSFER_INSTANT_OUTBOUND`.

Your real data stays local — `.gitignore` keeps every CSV except `demo.csv` out
of the repo.

## Day reports (PDF)

A static HTML file can't write to disk, so to save reports from the dashboard,
serve it locally instead of opening `dashboard.html`:

```sh
uv run python serve.py      # opens http://127.0.0.1:8765 (localhost only)
```

Click a day, then **Generate report**: the PDF lands in
`reports/daily_report_<date>.pdf` (the folder is created on first use and is
git-ignored; generating the same day again overwrites it). The server re-reads
`data/` on every page load, so a fresh export only needs a browser refresh.

You can also make one straight from the shell:

```sh
uv run python report.py 2026-11-13
uv run python report.py 2026-11-13 --theme dark
```

Reports are light by default; pick *Dark PDF* next to the button (or pass
`--theme dark`) for a dark version. The day view remembers your choice.

The PDF is printed by a headless **Chrome, Chromium or Edge** already on your
machine — still no Python dependencies. If it isn't found automatically, point
`CHROME_PATH` at the browser executable. The report's look lives in
`web/report.html` / `report.css` / `report.js`; the numbers come from the same
code as the day view, so the two always agree.

## How the P&L is calculated

The interesting logic lives in [`analysis.py`](analysis.py). A few decisions
worth calling out:

- **FIFO lot matching.** Each instrument keeps a queue of open buy lots, and a
  sell consumes the oldest first — the method German tax law mandates (§ 20
  Abs. 4 S. 7 EStG), so the realized figure ties out to what the broker taxes.
  The buy fee is part of a lot's cost and the sell fee comes off the proceeds,
  so realized P&L is net of fees. Positions held across days and partial exits
  fall out naturally, and each closed trade remembers when its lot was opened —
  which is how the day view can flag a position carried in overnight.
- **Knock-outs close a position too.** A warrant that hits its barrier arrives
  as `WARRANT_EXERCISE` (shares removed, no cash) plus a `TILG` redemption of
  the residual value; the two are folded into one losing trade.
- **Tax is a signed cash impact.** On a profitable sell, tax is *withheld*
  (negative). When the broker later refunds it via loss-offsetting
  (`TAX_OPTIMIZATION`, positive), that's added back on the day it lands. Over a
  losing period the two roughly cancel — which is easy to get wrong if you only
  read the tax on dividend rows, so there's a test pinning exactly this.
- **Transfers aren't P&L.** Deposits and withdrawals move your own money; they're
  tracked separately as funding, never as profit, and a pure-transfer day never
  shows up as a calendar cell.

## Project structure

The work is split so each piece has one job and can be read (and tested) on its
own:

```
loader.py      data access — find, merge, de-dupe the CSVs
analysis.py    pure computation — rows -> per-day P&L + funding + meta
build.py       orchestrator — assemble web/ + data -> dashboard.html (and report pages)
report.py      one day -> reports/daily_report_<date>.pdf via headless Chrome
serve.py       local server: the dashboard + the "Generate report" endpoint
web/
  template.html   HTML shell with placeholders
  styles.css      all styling
  core.js         the baked-in data + date / money helpers, shared by every page
  app.js          dashboard behaviour (vanilla JS, SVG charts)
  day-core.js     one day's numbers and section renderers (day view + report)
  day.js          the day view opened by clicking a calendar day
  report.html     printable report shell (with report.css / report.js)
data/demo.csv  bundled sample data
tests/         pytest suite for the analysis and loader
```

The build is a straight line: `load_transactions → build_payload → render`.
`render` inlines the stylesheet, scripts, and JSON data into the HTML shell so the
result is one portable file. `loader` and `analysis` are side-effect free, which
is what makes them easy to test:

```python
import loader, analysis
rows = loader.load_transactions("data")
payload = analysis.build_payload(rows)   # {"days": [...], "flows": [...], "meta": {...}}
payload["meta"]["trades"]                # one record per closed trade, used by the day view
```

## Development

```sh
uv run pytest        # tests for the P&L math + loader precedence/de-dup
uv run ruff check .  # lint
```

## Notes on the design

- **No framework, no runtime dependencies.** The back end is standard-library
  Python; the front end is vanilla JS with hand-rolled SVG charts. For a tool
  this size, a build toolchain and a charting library would be more moving parts
  than the problem needs — and it keeps the output genuinely portable.
- **Self-contained output on purpose.** A single HTML file with the data baked in
  is trivial to share, archive month-to-month, or open years later. The
  front-end sources stay split for editing; `build.py` is what stitches them
  together.
- **Colour is never the only signal.** Green/red is the one pairing that trips up
  colour-blind readers, so every day cell also carries its number and an exact
  breakdown on hover.

## License

[MIT](LICENSE)
