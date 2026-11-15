# P&L Ledger

A calendar-style trading journal that turns your brokers' exports into a
dashboard you can actually read at a glance — daily P&L on a colour-graded
calendar, an equity curve, and a few analytics built around one question:
*am I getting better?*

It started as a personal tool for reviewing my own trading. It reads
[Trade Republic](https://traderepublic.com) exports and
[Capital.com](https://capital.com) statements — side by side or one broker at a
time — and each broker is one small reader module, so adding another is easy.

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
  exit, net P&L by underlying and by long/short, and the full trade table —
  with a *Broker* column when your data spans more than one broker, so you can
  see at a glance where each trade was placed. Positions carried in from an earlier session are flagged as overnight, and
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
- **Several brokers, one ledger** — drop every broker's exports into `data/` and
  the dashboard combines them. A *Broker* switch narrows every panel to one
  broker, the *By broker* table compares them side by side for the selected
  period (click a row to focus it), and day cells and month tooltips show the
  split per broker.
- **Tax owed where none was withheld** — Trade Republic withholds
  capital-gains tax on every sale; Capital.com doesn't. For a broker that
  doesn't, the dashboard estimates the tax owed (default 26.375% = 25% + Soli,
  adjustable) on that broker's net gain for the year — later losses reduce it,
  like the loss pot — and shows it with a dashed underline as an estimate, never
  as cash. Tick *Deduct estimated tax* to see P&L after it; the choice and rate
  are remembered and carried into PDF reports.
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
uv run python build.py      # reads data/* -> dashboard.html
```

Then open `dashboard.html`. Out of the box it renders the bundled sample data
(`data/demo.csv`) — a few weeks of trading at two brokers, Trade Republic and
Capital.com — so you can see the whole thing working, broker switch and tax
estimate included, before pointing it at anything real.

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

### Capital.com

Capital.com's CSV transaction export leaves the instrument and trade id blank,
so use the **PDF statement** (the Client Daily Statement) instead; a day's
statement becomes available the next day. Save it into `data/`
under any name ending in `.pdf` and rebuild. Statements can overlap — rows are
de-duplicated by trade and ledger id — so you can keep adding daily ones or
pull a longer range. A Capital.com CSV export in `data/` is skipped with a note
in the footer.

Any number of statements can sit in `data/` together. Their rows are merged and
sorted by time, whatever the files are called, and a position opened in one
statement and closed in a later one is matched by its trade id. If the
statement with the opening isn't there, the close and its P&L still count — the
trade just has no entry time in the day view.

Reading PDFs needs [`pdfplumber`](https://github.com/jsvine/pdfplumber), which
`uv run` installs automatically on every platform. It's only imported when a
Capital.com statement is present, so a Trade Republic-only setup still runs on
the bare standard library (`python build.py`).

Your real data stays local — `.gitignore` keeps everything in `data/` except
`demo.csv` out of the repo.

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
- **Brokers are kept apart.** Each broker's rows are analysed on their own, so
  a position is never matched across brokers, then merged for the combined view.
  Capital.com reports each closed trade's realised P&L itself; that figure is
  used as-is (it's what the ledger cash ties out to), with overnight funding
  counted as interest and a knock-out fee as a cost on its day.
- **Transfers aren't P&L.** Deposits and withdrawals move your own money; they're
  tracked separately as funding, never as profit, and a pure-transfer day never
  shows up as a calendar cell.

## Project structure

The work is split so each piece has one job and can be read (and tested) on its
own:

```
loader.py      data access — find the exports, hand each to its broker reader, merge, de-dupe
brokers/       one reader per broker -> the common row format
  traderepublic.py   the CSV export for tracking tools
  common.py          any CSV already in the common format (with a broker column)
  capital.py         the PDF Client Daily Statement
analysis.py    pure computation — rows -> per-day P&L + funding + meta
build.py       orchestrator — assemble web/ + data -> dashboard.html (and report pages)
report.py      one day -> reports/daily_report_<date>.pdf via headless Chrome
serve.py       local server: the dashboard + the "Generate report" endpoint
web/
  template.html   HTML shell with placeholders
  styles.css      all styling
  core.js         the baked-in data, the broker / est.-tax view + date / money helpers,
                  shared by every page
  app.js          dashboard behaviour (vanilla JS, SVG charts)
  day-core.js     one day's numbers and section renderers (day view + report)
  day.js          the day view opened by clicking a calendar day
  report.html     printable report shell (with report.css / report.js)
data/demo.csv  bundled sample data (Trade Republic + Capital.com, common format)
tests/         pytest suite for the analysis, loader and broker readers
```

The build is a straight line: `load_transactions → build_payload → render`.
`render` inlines the stylesheet, scripts, and JSON data into the HTML shell so the
result is one portable file. `loader` and `analysis` are side-effect free, which
is what makes them easy to test:

```python
import brokers, loader, analysis
rows = loader.load_transactions("data")              # every row tagged with its broker
payload = analysis.build_payload(rows, brokers.info)  # {"days", "flows", "meta", "brokers"}
payload["meta"]["trades"]          # one record per closed trade (with its broker), for the day view
payload["brokers"]["capital"]      # the same days / flows for one broker
```

The estimated tax for brokers that don't withhold isn't in the payload: it
depends on the rate you pick, so `core.js` works it out in the browser from each
broker's day records.

### Adding a broker

Add a module to `brokers/` and list it in `READERS` in `brokers/__init__.py`. It
needs an `ID`, a display `NAME`, `WITHHOLDS_TAX`, a `detect(path, head)` that
recognises the broker's files and a `read(path)` that returns rows in the
common format — Trade Republic's CSV columns (`datetime`, `date`, `type`,
`symbol`, `shares`, `amount`, `fee`, `tax`, `transaction_id`, …). If the broker
reports realized P&L per trade itself, emit `POSITION_OPEN` / `CLOSED_TRADE` rows
the way `capital.py` does instead of buys and sells. Nothing else changes: the
broker switch, the by-broker table and the tax estimate pick it up on their own.

For a one-off you can skip the reader: convert the export to the common format
yourself, add a `broker` column, and drop the CSV into `data/` — `common.py`
reads any CSV with `broker` and `type` columns as-is. That's how
`data/demo.csv` holds sample data for both brokers in one file.

## Development

```sh
uv run pytest        # tests for the P&L math, loader precedence/de-dup and broker readers
uv run ruff check .  # lint
```

## Notes on the design

- **No framework, (almost) no runtime dependencies.** The back end is
  standard-library Python — the one exception, `pdfplumber`, is loaded only to
  read Capital.com statements; the front end is vanilla JS with hand-rolled SVG charts. For a tool
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
