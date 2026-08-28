"""Tests for the P&L analysis — the logic that actually matters.

Covers realized P&L via FIFO lots net of fees, the fee/tax handling (including the
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
    assert d["r"] == 49.0     # 681 proceeds - 630 cost - two €1 fees
    assert d["f"] == -2.0     # two €1 fees (informational, already in r)
    assert d["p"] == 49.0
    assert d["n"] == 2


def test_first_lot_consumed_first():
    # Buy 100 @ 10 then 100 @ 12; sell 100 @ 13 -> FIFO takes the @10 lot: 300.
    rows = [
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1000"),
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1200"),
        row(date="2026-02-02", type="SELL", symbol="Y", shares="-100", amount="1300"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert round(day(days, "2026-02-02")["r"], 2) == 300.0


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


def test_fifo_lot_matching():
    # Buy 100 @ 40.03 then 100 @ 39.29; sell 100 @ 41.11 must consume the
    # FIRST lot (German § 20 Abs. 4 S. 7 EStG), not the average.
    rows = [
        row(date="2026-08-26", type="BUY", symbol="G", shares="100", amount="-4003"),
        row(date="2026-08-26", type="BUY", symbol="G", shares="100", amount="-3929"),
        row(date="2026-08-26", type="SELL", symbol="G", shares="-100", amount="4111"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert day(days, "2026-08-26")["r"] == 108.0   # 4111 - 4003, not 145


def test_fifo_partial_lot_consumption():
    # Sell 150 out of lots 100@10 and 100@12: 100 from lot 1, 50 from lot 2.
    rows = [
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1000"),
        row(date="2026-02-01", type="BUY", symbol="Y", shares="100", amount="-1200"),
        row(date="2026-02-02", type="SELL", symbol="Y", shares="-150", amount="1950"),
        row(date="2026-02-03", type="SELL", symbol="Y", shares="-50", amount="650"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert day(days, "2026-02-02")["r"] == 350.0   # 1950 - (1000 + 600)
    assert day(days, "2026-02-03")["r"] == 50.0    # 650 - 600


def test_realized_is_net_of_fees_and_not_double_counted():
    # TR nets the €1 buy fee and €1 sell fee into the gain: 51 gross -> 49.
    rows = [
        row(date="2026-01-05", type="BUY", symbol="X", shares="100", amount="-630", fee="-1"),
        row(date="2026-01-05", type="SELL", symbol="X", shares="-100", amount="681", fee="-1"),
    ]
    d = day(compute_daily(rows)[0], "2026-01-05")
    assert d["r"] == 49.0
    assert d["f"] == -2.0     # still reported for the Fees tile...
    assert d["p"] == 49.0     # ...but not deducted a second time


def test_buy_fee_is_realized_when_the_lot_is_sold():
    # Buy fee is an acquisition cost: it hits P&L on the sell day, not the buy day.
    rows = [
        row(date="2026-01-05", type="BUY", symbol="X", shares="100", amount="-630", fee="-1"),
        row(date="2026-01-06", type="SELL", symbol="X", shares="-100", amount="681", fee="-1"),
    ]
    days, _flows, _meta = compute_daily(rows)
    assert day(days, "2026-01-05")["p"] == 0.0
    assert day(days, "2026-01-05")["f"] == -1.0
    assert day(days, "2026-01-06")["r"] == 49.0
    assert day(days, "2026-01-06")["p"] == 49.0


def test_real_export_tax_reconciles_with_fifo_net_gain():
    """Trade Republic withholds 26.375% (Abgeltungsteuer + Soli) on the
    FIFO, fee-net gain of each profitable sell — so the export's ``tax`` column
    is an independent oracle for the realized figure. Skipped without a real
    export."""
    import os

    import pytest

    from loader import load_transactions

    path = os.path.join(os.path.dirname(__file__), "..", "data", "transactions.csv")
    if not os.path.exists(path):
        pytest.skip("no real export in data/")
    rows = load_transactions(os.path.dirname(path))
    day_rows = [r for r in rows if r["date"] == "2026-08-26" and r["type"] in ("BUY", "SELL")]
    if not day_rows:
        pytest.skip("26 Aug 2026 not in export")
    d = day(compute_daily(rows)[0], "2026-08-26")
    # Sells that day: (124-2) + (25-3) + (108-2) - (9+2) = 239
    assert d["r"] == 239.0
    withheld = sum(_f(r["tax"]) for r in day_rows)
    assert abs(withheld - (-(122 + 22 + 106) * 0.26375)) < 0.05


def test_date_window_includes_transfer_only_days():
    """A deposit on a day with no trades must still fall inside the data window,
    otherwise the dashboard's "All-time" funding total silently drops it."""
    rows = [
        {"date": "2026-05-17", "type": "TRANSFER_INSTANT_INBOUND", "amount": "975"},
        {"date": "2026-05-18", "type": "BUY", "symbol": "X", "shares": "1", "amount": "-100", "fee": "0", "tax": "0"},
        {"date": "2026-05-19", "type": "SELL", "symbol": "X", "shares": "-1", "amount": "110", "fee": "0", "tax": "0"},
        {"date": "2026-05-20", "type": "TRANSFER_INSTANT_OUTBOUND", "amount": "-50"},
    ]
    meta = build_payload(rows)["meta"]
    assert meta["min_date"] == "2026-05-17"
    assert meta["max_date"] == "2026-05-20"
    assert meta["deposits"] == 975.0
