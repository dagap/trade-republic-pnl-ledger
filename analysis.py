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


def _f(v: str) -> float:
    """Parse a numeric CSV cell that may be blank or ``None``."""
    if v is None:
        return 0.0
    v = v.strip()
    return float(v) if v else 0.0


def _close_lots(lots: list[list[float]], qty: float) -> tuple[float, float]:
    """Consume ``qty`` from the front of ``lots`` (FIFO), in place.

    Returns ``(cost_removed, unmatched_qty)`` — ``unmatched_qty`` > 0 means the
    position was opened before our data window.
    """
    remaining = qty
    cost_removed = 0.0
    while remaining > 1e-9 and lots:
        lot = lots[0]
        take = min(lot[0], remaining)
        cost_removed += lot[1] * take / lot[0]
        lot[1] -= lot[1] * take / lot[0]
        lot[0] -= take
        remaining -= take
        if lot[0] <= 1e-9:
            lots.pop(0)
    return cost_removed, remaining


def compute_daily(rows: list[dict]):
    """Return ``(daily_records, flows, meta)``.

    ``meta["trades"]`` is a list of ``{d, p}`` — one entry per SELL or
    knocked-out warrant with its realized P&L (FIFO, net of fees) — so the dashboard can profile wins and
    losses per closed trade, not only per day.

    ``daily_records`` is a list of ``{d, p, r, i, f, t, n}`` sorted by date:
        d = ISO date, p = net P&L, r = realized trading P&L (FIFO, net of
        fees), i = income (dividends + interest), f = fees paid that day (<=0,
        informational — already inside ``r`` on the day the lot is sold, so
        NOT added to ``p`` again), t = tax (signed: withheld <0, refunded >0),
        n = trade count.
    ``flows`` is a list of ``{d, dep, wd}`` for dates with cash movements:
        dep = deposits (>=0), wd = withdrawals (<=0).
    """
    # symbol -> FIFO queue of open lots [qty, cost] (cost = money spent incl.
    # buy fee, positive). Sells consume from the front.
    positions: dict[str, list[list[float]]] = {}
    daily = defaultdict(lambda: {"r": 0.0, "i": 0.0, "f": 0.0, "t": 0.0, "n": 0})
    flows_by_date = defaultdict(lambda: {"dep": 0.0, "wd": 0.0})
    unknown_types: dict[str, int] = defaultdict(int)
    missing_basis = 0
    trades: list[dict] = []
    # symbol -> the trade record of a warrant closed by WARRANT_EXERCISE, awaiting
    # its TILG redemption payout
    exercised: dict[str, dict] = {}

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
            lots.append([shares, -amount - fee])
            rec = daily[date]
            rec["f"] += fee
            rec["t"] += tax
            rec["n"] += 1

        elif typ == TRADE_SELL:
            # shares negative on a sell
            cost_removed, remaining = _close_lots(positions.get(symbol, []), -shares)
            if remaining > 1e-9:
                missing_basis += 1          # opened before our data window
            proceeds = amount + fee         # gross, positive; sell fee netted
            rec = daily[date]
            rec["r"] += proceeds - cost_removed   # realized P&L, net of fees
            trades.append({"d": date, "p": round(proceeds - cost_removed, 2)})
            rec["f"] += fee
            rec["t"] += tax                 # capital-gains tax withheld (<=0)
            rec["n"] += 1

        elif typ == WARRANT_EXERCISE:
            # Position closed by the issuer: the whole cost is realized as a
            # loss now; the TILG redemption that follows adds back the residual.
            cost_removed, remaining = _close_lots(positions.get(symbol, []), -shares)
            if remaining > 1e-9:
                missing_basis += 1
            rec = daily[date]
            rec["r"] += amount - cost_removed      # amount is blank on a knock-out
            trade = {"d": date, "p": round(amount - cost_removed, 2)}
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
            else:
                trades.append({"d": date, "p": round(amount, 2)})

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


def build_payload(rows: list[dict]) -> dict:
    """Return the full ``{"days": [...], "flows": [...], "meta": {...}}`` payload
    the dashboard consumes, wrapping :func:`compute_daily` and adding totals."""
    daily, flows, meta = compute_daily(rows)
    meta["n_txns"] = len(rows)
    meta["total_pnl"] = round(sum(d["p"] for d in daily), 2)
    meta["deposits"] = round(sum(f["dep"] for f in flows), 2)
    meta["withdrawals"] = round(sum(f["wd"] for f in flows), 2)
    meta["net_deposited"] = round(meta["deposits"] + meta["withdrawals"], 2)
    return {"days": daily, "flows": flows, "meta": meta}
