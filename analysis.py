"""Analysis for the P&L dashboard.

Turns raw transaction rows into per-day P&L records and summary metadata.
Realized P&L matches sells against buy lots first-in-first-out per instrument
(the method German tax law mandates, § 20 Abs. 4 S. 7 EStG) and is net of
trading fees: a buy fee is capitalised into the lot's cost and a sell fee is
deducted from proceeds, so the realized figure is the one Trade Republic taxes.
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
TRANSFER_IN = "TRANSFER_INSTANT_INBOUND"    # cash deposit
TRANSFER_OUT = "TRANSFER_INSTANT_OUTBOUND"  # cash withdrawal
# Transfers are cash movements, not P&L — tracked separately as funding flows.


def _f(v: str) -> float:
    """Parse a numeric CSV cell that may be blank or ``None``."""
    if v is None:
        return 0.0
    v = v.strip()
    return float(v) if v else 0.0


def compute_daily(rows: list[dict]):
    """Return ``(daily_records, flows, meta)``.

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
    missing_basis = 0

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
            qty_sold = -shares              # shares negative on a sell
            lots = positions.get(symbol, [])
            remaining = qty_sold
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
            if remaining > 1e-9:
                missing_basis += 1          # opened before our data window
            proceeds = amount + fee         # gross, positive; sell fee netted
            rec = daily[date]
            rec["r"] += proceeds - cost_removed   # realized P&L, net of fees
            rec["f"] += fee
            rec["t"] += tax                 # capital-gains tax withheld (<=0)
            rec["n"] += 1

        elif typ in INCOME_TYPES:
            rec = daily[date]
            rec["i"] += amount              # dividend/interest cash
            rec["t"] += tax                 # withholding on the payout, if any

        elif typ == TAX_OPTIMIZATION:
            rec = daily[date]
            rec["t"] += tax                 # tax refund from loss offsetting (>=0)

        elif typ == TRANSFER_IN:
            flows_by_date[date]["dep"] += amount    # deposit (>=0)

        elif typ == TRANSFER_OUT:
            flows_by_date[date]["wd"] += amount     # withdrawal (<=0)

        # Transfers are tracked as funding flows only — they create no P&L day
        # record, so a pure transfer day never shows as a P&L cell.

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
        "min_date": all_dates[0] if all_dates else None,
        "max_date": all_dates[-1] if all_dates else None,
        "n_days": len(daily_records),
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
