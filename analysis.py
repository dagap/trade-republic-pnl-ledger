"""Analysis for the P&L dashboard.

Turns raw transaction rows into per-day P&L records and summary metadata.
Realized P&L matches sells against buy lots first-in-first-out per instrument
(the method German tax law mandates, § 20 Abs. 4 S. 7 EStG) and is net of
trading fees: a buy fee is capitalised into the lot's cost and a sell fee is
deducted from proceeds, so the realized figure is the one Trade Republic taxes.
A knocked-out or expired warrant is realized like a sell for its redemption
payout (often a few cents), so its loss lands on the day it was closed.
Dividends & interest count as income; capital-gains tax (withheld on sells,
refunded via "Tax Optimisation") is applied on its day; cash transfers are
ignored.

This module is pure computation — no file, network or template I/O — so it can
be unit-tested and reused independently of how the data is loaded or rendered.
"""

from __future__ import annotations

import re
from collections import defaultdict

# Transaction types
TRADE_BUY = "BUY"
TRADE_SELL = "SELL"
INCOME_TYPES = {"DIVIDEND", "INTEREST_PAYMENT"}
TAX_OPTIMIZATION = "TAX_OPTIMIZATION"   # tax refund from loss offsetting
# Trade Republic labels the same cash movement differently depending on the rail
# it settled over — an instant SEPA payment and an ordinary one arrive as
# TRANSFER_INSTANT_* and TRANSFER_*. Match the whole family, or a plain SEPA
# withdrawal silently vanishes from the funding totals.
TRANSFER_IN_TYPES = {"TRANSFER_INSTANT_INBOUND", "TRANSFER_INBOUND"}    # deposits
TRANSFER_OUT_TYPES = {"TRANSFER_INSTANT_OUTBOUND", "TRANSFER_OUTBOUND"}  # withdrawals
# Transfers are cash movements, not P&L — tracked separately as funding flows.
# A warrant that hits its knock-out barrier (or expires) is closed by the issuer,
# not sold: WARRANT_EXERCISE removes the shares with no cash, then TILG
# ("Tilgung", redemption) pays out whatever residual value is left, often cents.
WARRANT_EXERCISE = "WARRANT_EXERCISE"
REDEMPTION = "TILG"
# Brokers that report each closed trade's realized P&L themselves (Capital.com)
# arrive as POSITION_OPEN (when a position was entered — for the day view and
# the trade count) and CLOSED_TRADE (one per full or partial close, carrying
# ``pnl`` and the instrument detail). A stand-alone FEE (e.g. a knock-out fee)
# is a cost charged on its day.
POSITION_OPEN = "POSITION_OPEN"
CLOSED_TRADE = "CLOSED_TRADE"
FEE = "FEE"
DEFAULT_BROKER = "tr"


def _f(v: str) -> float:
    """Parse a numeric CSV cell that may be blank or ``None``."""
    if v is None:
        return 0.0
    v = v.strip()
    return float(v) if v else 0.0


def _close_lots(lots: list[list], qty: float) -> tuple[float, float, float, str]:
    """Consume ``qty`` from the front of ``lots`` (FIFO), in place.

    A lot is ``[qty, cost, gross, opened_at]``: ``cost`` includes the buy fee,
    ``gross`` is shares x price without it, ``opened_at`` the buy's timestamp.

    Returns ``(cost_removed, unmatched_qty, gross_removed, opened_at)`` —
    ``unmatched_qty`` > 0 means the position was opened before our data window;
    ``opened_at`` is the timestamp of the oldest lot consumed ("" if none).
    """
    remaining = qty
    cost_removed = gross_removed = 0.0
    opened_at = ""
    while remaining > 1e-9 and lots:
        lot = lots[0]
        if not opened_at:
            opened_at = lot[3]
        take = min(lot[0], remaining)
        share = take / lot[0]
        cost_removed += lot[1] * share
        gross_removed += lot[2] * share
        lot[1] -= lot[1] * share
        lot[2] -= lot[2] * share
        lot[0] -= take
        remaining -= take
        if lot[0] <= 1e-9:
            lots.pop(0)
    return cost_removed, remaining, gross_removed, opened_at


_DESC = re.compile(r"^(?:Buy|Sell) trade \S+ (.*?) auf (.+?), quantity")
_LONG = {"Long", "Call"}
_SHORT = {"Short", "Put"}


def _instrument(row: dict) -> dict:
    """Describe the instrument a trade row refers to, for the day view.

    Trade Republic's description reads ``Buy trade <ISIN> <product> auf
    <underlying>, quantity: N`` and a derivative's name ``Long 27.875,3158 $``
    (direction + knock-out level). Anything that doesn't fit falls back to the
    name / ISIN, so plain stocks and other brokers' exports still render.
    """
    symbol = (row.get("symbol") or "").strip()
    if row.get("underlying") is not None:      # a reader that knows the fields
        return {"s": symbol, "u": row["underlying"] or symbol, "side": row.get("side", ""),
                "ko": row.get("ko", ""), "prod": row.get("product", "")}
    name = " ".join((row.get("name") or "").split())
    m = _DESC.match(row.get("description") or "")
    product, underlying = (m.group(1), m.group(2)) if m else ("", "")
    # "NVIDIA CORP.      DL-,001" -> "NVIDIA CORP." (share-class junk after a wide gap)
    underlying = re.split(r"\s{2,}", underlying)[0].replace("Index®", "").replace("®", "").strip()
    first, _, rest = name.partition(" ")
    side = "Long" if first in _LONG else "Short" if first in _SHORT else ""
    return {
        "s": symbol,
        "u": underlying or (name if not side else "") or symbol,
        "side": side,
        "ko": rest if side else "",
        "prod": product,
    }


def _ts(row: dict) -> str:
    """The row's timestamp trimmed to whole seconds (``2026-11-12T07:10:18Z``).

    Exports mix milli- and microsecond precision; seconds parse the same in
    every browser and are all the day view needs.
    """
    dt = (row.get("datetime") or "").strip()
    return dt[:19] + "Z" if len(dt) >= 19 else dt


def _trade(date: str, row: dict, info: dict, qty: float, cost: float,
           gross: float, opened_at: str, pnl: float, fees: float,
           exit_price: float, how: str = "") -> dict:
    """One closed trade: ``d``/``p`` drive the analytics, the rest the day view.

    o/c = opened/closed timestamps, q = quantity closed, cost = entry cost incl.
    buy fee, ep/xp = entry/exit price per share, fee = all fees on the trade
    (<=0, already inside ``p``), how = "ko" for a knock-out / expiry.
    """
    return {
        "d": date,
        "p": round(pnl, 2),
        "o": opened_at,
        "c": _ts(row),
        **info,
        "q": round(qty, 6),
        "cost": round(cost, 2),
        "ep": round(gross / qty, 4) if qty else 0.0,
        "xp": round(exit_price, 4),
        "fee": round(fees, 2),
        "how": how,
    }


def compute_daily(rows: list[dict]):
    """Return ``(daily_records, flows, meta)``.

    ``meta["trades"]`` is a list of ``{d, p, ...}`` — one entry per SELL or
    knocked-out warrant with its realized P&L (FIFO, net of fees) — so the
    dashboard can profile wins and losses per closed trade, not only per day.
    Each also carries the detail the day view shows (see :func:`_trade`).

    ``daily_records`` is a list of ``{d, p, r, i, f, t, n}`` sorted by date:
        d = ISO date, p = net P&L, r = realized trading P&L (FIFO, net of
        fees), i = income (dividends + interest), f = fees paid that day (<=0,
        informational — already inside ``r`` on the day the lot is sold, so
        NOT added to ``p`` again), t = tax (signed: withheld <0, refunded >0),
        n = trade count.
    ``flows`` is a list of ``{d, dep, wd}`` for dates with cash movements:
        dep = deposits (>=0), wd = withdrawals (<=0).
    """
    # symbol -> FIFO queue of open lots [qty, cost, gross, opened_at] (cost =
    # money spent incl. buy fee, positive). Sells consume from the front.
    positions: dict[str, list[list]] = {}
    instruments: dict[str, dict] = {}     # symbol -> _instrument() of its last buy
    daily = defaultdict(lambda: {"r": 0.0, "i": 0.0, "f": 0.0, "t": 0.0, "n": 0})
    flows_by_date = defaultdict(lambda: {"dep": 0.0, "wd": 0.0})
    unknown_types: dict[str, int] = defaultdict(int)
    missing_basis = 0
    trades: list[dict] = []
    # symbol -> the trade record of a warrant closed by WARRANT_EXERCISE, awaiting
    # its TILG redemption payout
    exercised: dict[str, dict] = {}
    opened: dict[str, str] = {}           # POSITION_OPEN: trade id -> entry timestamp

    for row in rows:
        typ = (row.get("type") or "").strip()
        date = (row.get("date") or "").strip()
        if not date:
            continue

        amount = _f(row.get("amount"))
        fee = _f(row.get("fee"))          # already negative in the data
        # `tax` is a signed cash impact: negative = withheld on a profitable
        # sell, positive = refunded (Trade Republic "Tax Optimisation" / loss
        # offsetting). `amount` on a SELL is GROSS (shares x price); the tax is
        # withheld separately, so it must be added to the day, not folded in.
        tax = _f(row.get("tax"))
        symbol = (row.get("symbol") or "").strip()
        shares = _f(row.get("shares"))

        if typ == TRADE_BUY:
            lots = positions.setdefault(symbol, [])
            # amount negative -> cost positive; the buy fee is an acquisition
            # cost and is realized when this lot is sold.
            lots.append([shares, -amount - fee, -amount, _ts(row)])
            instruments[symbol] = _instrument(row)
            rec = daily[date]
            rec["f"] += fee
            rec["t"] += tax
            rec["n"] += 1

        elif typ == TRADE_SELL:
            # shares negative on a sell
            cost_removed, remaining, gross, opened_at = _close_lots(
                positions.get(symbol, []), -shares)
            if remaining > 1e-9:
                missing_basis += 1          # opened before our data window
            proceeds = amount + fee         # gross, positive; sell fee netted
            rec = daily[date]
            rec["r"] += proceeds - cost_removed   # realized P&L, net of fees
            trades.append(_trade(
                date, row, instruments.get(symbol) or _instrument(row), -shares,
                cost_removed, gross, opened_at, proceeds - cost_removed,
                fee + gross - cost_removed, _f(row.get("price"))))
            rec["f"] += fee
            rec["t"] += tax                 # capital-gains tax withheld (<=0)
            rec["n"] += 1

        elif typ == WARRANT_EXERCISE:
            # Position closed by the issuer: the whole cost is realized as a
            # loss now; the TILG redemption that follows adds back the residual.
            cost_removed, remaining, gross, opened_at = _close_lots(
                positions.get(symbol, []), -shares)
            if remaining > 1e-9:
                missing_basis += 1
            rec = daily[date]
            rec["r"] += amount - cost_removed      # amount is blank on a knock-out
            trade = _trade(
                date, row, instruments.get(symbol) or _instrument(row), -shares,
                cost_removed, gross, opened_at, amount - cost_removed,
                gross - cost_removed, 0.0, how="ko")
            trades.append(trade)
            exercised[symbol] = trade
            rec["n"] += 1

        elif typ == REDEMPTION:
            rec = daily[date]
            rec["r"] += amount                     # residual value paid out (>=0)
            rec["t"] += tax
            # Fold the payout into the closed trade, so a knock-out reads as one
            # trade with its true net loss rather than a loss plus a tiny "win".
            trade = exercised.pop(symbol, None)
            if trade is not None:
                trade["p"] = round(trade["p"] + amount, 2)
                if trade["q"]:
                    trade["xp"] = round(amount / trade["q"], 4)
            else:
                trades.append(_trade(
                    date, row, instruments.get(symbol) or _instrument(row), 0.0,
                    0.0, 0.0, "", amount, 0.0, 0.0, how="ko"))

        elif typ == POSITION_OPEN:
            opened[symbol] = _ts(row)
            daily[date]["n"] += 1

        elif typ == CLOSED_TRADE:
            # The broker's own realized P&L, taken as-is (already net of its
            # spread; no separate order fee).
            pnl = float(row.get("pnl") or 0.0)
            qty = abs(shares)
            cost = float(row.get("cost") or 0.0)
            rec = daily[date]
            rec["r"] += pnl
            rec["n"] += 1
            trades.append(_trade(
                date, row, _instrument(row), qty, cost, cost, opened.get(symbol, ""),
                pnl, 0.0, (cost + pnl) / qty if qty else 0.0, how=row.get("how", "")))

        elif typ == FEE:
            rec = daily[date]
            rec["r"] += amount              # a cost on its day (amount < 0)
            rec["f"] += amount

        elif typ in INCOME_TYPES:
            rec = daily[date]
            rec["i"] += amount              # dividend/interest cash
            rec["t"] += tax                 # withholding on the payout, if any

        elif typ == TAX_OPTIMIZATION:
            rec = daily[date]
            rec["t"] += tax                 # tax refund from loss offsetting (>=0)

        elif typ in TRANSFER_IN_TYPES:
            flows_by_date[date]["dep"] += amount    # deposit (>=0)

        elif typ in TRANSFER_OUT_TYPES:
            flows_by_date[date]["wd"] += amount     # withdrawal (<=0)

        # Transfers are tracked as funding flows only — they create no P&L day
        # record, so a pure transfer day never shows as a P&L cell.

        else:
            # A type we don't model. Counting it here means a new Trade Republic
            # transaction type surfaces in the dashboard footer instead of being
            # dropped without a trace, the way a plain TRANSFER_OUTBOUND once was.
            unknown_types[typ or "(blank)"] += 1

    daily_records = []
    for date in sorted(daily):
        v = daily[date]
        p = v["r"] + v["i"] + v["t"]    # fees already inside r
        daily_records.append(
            {
                "d": date,
                "p": round(p, 2),
                "r": round(v["r"], 2),
                "i": round(v["i"], 2),
                "f": round(v["f"], 2),
                "t": round(v["t"], 2),
                "n": v["n"],
            }
        )

    flows = [
        {"d": d, "dep": round(v["dep"], 2), "wd": round(v["wd"], 2)}
        for d, v in sorted(flows_by_date.items())
    ]

    # The data window spans every dated event, including pure cash-transfer
    # days, so an "All-time" range filter in the dashboard never drops a
    # deposit or withdrawal that happened on a day with no trades.
    all_dates = sorted({d["d"] for d in daily_records} | {f["d"] for f in flows})
    meta = {
        "missing_basis": missing_basis,
        # sorted most-frequent-first so the loudest omission reads first
        "unknown_types": dict(
            sorted(unknown_types.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "min_date": all_dates[0] if all_dates else None,
        "max_date": all_dates[-1] if all_dates else None,
        "n_days": len(daily_records),
        "trades": trades,
    }
    return daily_records, flows, meta


def _merge_days(lists: list[list[dict]]) -> list[dict]:
    out: dict[str, dict] = {}
    for days in lists:
        for d in days:
            m = out.setdefault(d["d"], {"d": d["d"], "p": 0.0, "r": 0.0, "i": 0.0,
                                        "f": 0.0, "t": 0.0, "n": 0})
            for k in ("p", "r", "i", "f", "t"):
                m[k] = round(m[k] + d[k], 2)
            m["n"] += d["n"]
    return [out[k] for k in sorted(out)]


def _merge_flows(lists: list[list[dict]]) -> list[dict]:
    out: dict[str, dict] = {}
    for flows in lists:
        for f in flows:
            m = out.setdefault(f["d"], {"d": f["d"], "dep": 0.0, "wd": 0.0})
            m["dep"] = round(m["dep"] + f["dep"], 2)
            m["wd"] = round(m["wd"] + f["wd"], 2)
    return [out[k] for k in sorted(out)]


def compute_by_broker(rows: list[dict]):
    """Run :func:`compute_daily` for each broker on its own rows and merge.

    Positions never mix across brokers (the same ISIN bought at one and sold at
    another isn't a round trip). Returns ``(days, flows, meta, per_broker)``
    where ``days``/``flows``/``meta`` cover all brokers and ``per_broker`` maps
    broker id -> ``{"days", "flows"}``. Every trade carries its broker as ``b``.
    """
    ids: list[str] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        b = r.get("broker") or DEFAULT_BROKER
        if b not in groups:
            ids.append(b)
        groups[b].append(r)
    if not ids:
        ids = [DEFAULT_BROKER]

    per: dict[str, dict] = {}
    trades: list[dict] = []
    unknown: dict[str, int] = defaultdict(int)
    missing = 0
    for b in ids:
        days, flows, meta = compute_daily(groups[b])
        per[b] = {"days": days, "flows": flows}
        for t in meta["trades"]:
            t["b"] = b
        trades += meta["trades"]
        missing += meta["missing_basis"]
        for k, v in meta["unknown_types"].items():
            unknown[k] += v

    days = _merge_days([per[b]["days"] for b in ids])
    flows = _merge_flows([per[b]["flows"] for b in ids])
    trades.sort(key=lambda t: (t["d"], t["c"]))
    all_dates = sorted({d["d"] for d in days} | {f["d"] for f in flows})
    meta = {
        "missing_basis": missing,
        "unknown_types": dict(sorted(unknown.items(), key=lambda kv: (-kv[1], kv[0]))),
        "min_date": all_dates[0] if all_dates else None,
        "max_date": all_dates[-1] if all_dates else None,
        "n_days": len(days),
        "trades": trades,
    }
    return days, flows, meta, per


def build_payload(rows: list[dict], broker_info=None) -> dict:
    """Return the full payload the dashboard consumes::

        {"days": [...], "flows": [...], "meta": {...},
         "brokers": {id: {"days": [...], "flows": [...]}}}

    ``days``/``flows`` cover every broker; ``brokers`` holds the same per broker,
    so the dashboard can switch between them. ``broker_info(id)`` supplies each
    broker's display metadata (``{"id", "name", "withholds_tax"}``), listed in
    ``meta["brokers"]``.
    """
    daily, flows, meta, per = compute_by_broker(rows)
    info = broker_info or (lambda b: {"id": b, "name": b, "withholds_tax": True})
    meta["brokers"] = [info(b) for b in per]
    meta["n_txns"] = len(rows)
    meta["total_pnl"] = round(sum(d["p"] for d in daily), 2)
    meta["deposits"] = round(sum(f["dep"] for f in flows), 2)
    meta["withdrawals"] = round(sum(f["wd"] for f in flows), 2)
    meta["net_deposited"] = round(meta["deposits"] + meta["withdrawals"], 2)
    return {"days": daily, "flows": flows, "meta": meta, "brokers": per}
