"""Tests for the P&L analysis — the logic that actually matters.

Covers realized P&L via average cost, the fee/tax handling (including the
withheld-then-refunded case that nets to zero), income vs. transfers, and the
missing-cost-basis edge case.
"""

from analysis import _f, build_payload, compute_daily

COLS = ["datetime", "date", "type", "amount", "fee", "tax", "symbol", "shares"]


def row(**kw):
    """Build a transaction row with all columns present (blank unless given)."""
    r = {c: "" for c in COLS}
    r.update({k: str(v) for k, v in kw.items()})
    return r


def day(days, iso):
    return next(d for d in days if d["d"] == iso)


def test_f_parses_blanks_and_numbers():
    assert _f("") == 0.0
    assert _f(None) == 0.0
    assert _f("   ") == 0.0
    assert _f("-630.00") == -630.0


def test_round_trip_realized_pnl():
    # Buy 100 @ 6.30, sell 100 @ 6.81 same day; €1 fee each side.
    rows = [
        row(date="2026-01-05", type="BUY", symbol="X", shares="100", amount="-630", fee="-1"),
        row(date="2026-01-05", type="SELL", symbol="X", shares="-100", amount="681", fee="-1"),
    ]
    days, _flows, _meta = compute_daily(rows)
    d = day(days, "2026-01-05")
    assert d["r"] == 51.0     # 681 proceeds - 630 cost
    assert d["f"] == -2.0     # two €1 fees
    assert d["p"] == 49.0     # net after fees
    assert d["n"] == 2


def test_average_cost_basis():
    # Buy 100 @ 10 then 100 @ 12 (avg 11); sell 100 @ 13 -> (13-11)*100 = 200.
    rows = [
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1000"),
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1200"),
        row(date="2026-02-02", type="SELL", symbol="Y", shares="-100", amount="1300"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert round(day(days, "2026-02-02")["r"], 2) == 200.0


def test_tax_withheld_then_refunded_nets_to_zero():
    # €120 withheld on a winning sell, later refunded via TAX_OPTIMIZATION.
    rows = [
        row(date="2026-03-01", type="BUY", symbol="Z", shares="100", amount="-500", fee="-1"),
        row(date="2026-03-01", type="SELL", symbol="Z", shares="-100", amount="700", fee="-1", tax="-120"),
        row(date="2026-03-10", type="TAX_OPTIMIZATION", amount="0", tax="120"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert round(sum(d["t"] for d in days), 2) == 0.0
    assert day(days, "2026-03-01")["t"] == -120.0   # withheld on the sell day
    assert day(days, "2026-03-10")["t"] == 120.0    # refunded later


def test_income_counted_and_transfers_ignored():
    rows = [
        row(date="2026-04-01", type="INTEREST_PAYMENT", amount="5"),
        row(date="2026-04-01", type="DIVIDEND", amount="10", tax="-2"),
        row(date="2026-04-02", type="TRANSFER_INSTANT_INBOUND", amount="1000"),
        row(date="2026-04-03", type="TRANSFER_INSTANT_OUTBOUND", amount="-400"),
    ]
    days, flows, _meta = compute_daily(rows)
    apr1 = day(days, "2026-04-01")
    assert apr1["i"] == 15.0
    assert apr1["t"] == -2.0
    # transfer-only days never appear as P&L days...
    assert not any(d["d"] in ("2026-04-02", "2026-04-03") for d in days)
    # ...but they are captured as funding flows
    assert sum(f["dep"] for f in flows) == 1000.0
    assert sum(f["wd"] for f in flows) == -400.0


def test_missing_cost_basis_is_flagged():
    # A sell with no prior buy (position opened before the data window).
    rows = [row(date="2026-05-01", type="SELL", symbol="Q", shares="-10", amount="100")]
    _days, _flows, meta = compute_daily(rows)
    assert meta["missing_basis"] == 1


def test_build_payload_totals():
    rows = [
        row(date="2026-06-01", type="BUY", symbol="A", shares="100", amount="-100"),
        row(date="2026-06-01", type="SELL", symbol="A", shares="-100", amount="150"),
        row(date="2026-06-02", type="TRANSFER_INSTANT_INBOUND", amount="500"),
    ]
    payload = build_payload(rows)
    meta = payload["meta"]
    assert meta["total_pnl"] == 50.0
    assert meta["deposits"] == 500.0
    assert meta["net_deposited"] == 500.0
    assert meta["n_txns"] == 3
