"""Analysis for the P&L dashboard.

Turns raw transaction rows into per-day P&L records and summary metadata.
Realized P&L uses a running average cost per instrument; dividends & interest
count as income; fees and capital-gains tax (withheld on sells, refunded via
"Tax Optimisation") are applied on their day; cash transfers are ignored.

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
        d = ISO date, p = net P&L, r = realized trading P&L, i = income
        (dividends + interest), f = fees (<=0), t = tax (signed: withheld <0,
        refunded >0), n = trade count.
    ``flows`` is a list of ``{d, dep, wd}`` for dates with cash movements:
        dep = deposits (>=0), wd = withdrawals (<=0).
    """
    # symbol -> {"qty": float, "cost": float}  (cost = money spent, positive)
    positions: dict[str, dict] = {}
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
            pos = positions.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
            pos["qty"] += shares            # shares positive on a buy
            pos["cost"] += -amount          # amount negative -> cost positive
            rec = daily[date]
            rec["f"] += fee                 # buy fee expensed on its day
            rec["t"] += tax
            rec["n"] += 1

        elif typ == TRADE_SELL:
            qty_sold = -shares              # shares negative on a sell
            pos = positions.get(symbol)
            if pos and pos["qty"] > 1e-9:
                avg = pos["cost"] / pos["qty"]
            else:
                avg = 0.0                   # opened before our data window
                missing_basis += 1
            cost_removed = avg * qty_sold
            proceeds = amount               # gross, positive
            rec = daily[date]
            rec["r"] += proceeds - cost_removed   # realized trading P&L (pre-tax)
            rec["f"] += fee
            rec["t"] += tax                 # capital-gains tax withheld (<=0)
            rec["n"] += 1
            if pos:
                pos["qty"] = max(0.0, pos["qty"] - qty_sold)
                pos["cost"] = max(0.0, pos["cost"] - cost_removed)

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
        p = v["r"] + v["i"] + v["f"] + v["t"]
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

    meta = {
        "missing_basis": missing_basis,
        "min_date": daily_records[0]["d"] if daily_records else None,
        "max_date": daily_records[-1]["d"] if daily_records else None,
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
