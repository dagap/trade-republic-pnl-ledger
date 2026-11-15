"""Tests for multi-broker support: the Capital.com statement reader, broker-
reported closed trades in the analysis, per-broker payloads and loader dispatch."""

import os

from analysis import build_payload, compute_by_broker, compute_daily
from brokers import capital, info
from loader import find_data_files, load

# ---------------------------------------------------------------- PDF layout --


def _w(text, x0, top, size=6.5, bold=False, width=None):
    """A word as pdfplumber's extract_words returns it."""
    width = width if width is not None else len(text) * size * 0.5
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "size": size,
            "fontname": "Roboto-Bold" if bold else "Roboto-Regular"}


def _ko_closed_page():
    """A cut-down 'KO Closed trades' table laid out like Capital.com's statement:
    a wrapped Trade ID and underlier, right-aligned numbers, 5pt small print."""
    words = [_w(t, x, 46.4, size=11) for t, x in (("KO", 34), ("Closed", 53), ("trades", 92.8))]
    header = [("Date", 36), ("/", 49.9), ("Time", 53.6), ("Trade", 116.1), ("ID", 133.3),
              ("Underlier", 204.5), ("Direction", 347.4), ("Quantity", 383.7),
              ("KO", 507.6), ("level", 517.1), ("KO", 547), ("value", 556.5),
              ("Realised", 627.2), ("P&L", 651.9), ("Trigger", 786.1)]
    words += [_w(t, x, 76.7, size=6, bold=True) for t, x in header]
    words += [_w("Currency", 311.3, 72.7, size=6, bold=True), _w("/", 337.2, 72.7, size=6, bold=True),
              _w("Conversion", 296.7, 80.7, size=6, bold=True), _w("rate", 328.8, 80.7, size=6, bold=True)]
    row = [("14/11/2026", 36), ("21:40:16", 72.1), ("USD/0.9071775891", 282.6), ("PUT", 359.7),
           ("6.00", 393.8), ("1,929.91", 504.9), ("616.44", 551), ("€209.52", 643), ("EXPLICIT", 780)]
    words += [_w("00945508-0001-54c4-0000-", 116.1, 97.8), _w("Ethereum", 204.5, 97.8),
              _w("to", 233.9, 97.8), _w("US", 241.3, 97.8)]
    words += [_w(t, x, 102.1) for t, x in row]
    words += [_w("00008032174b", 116.1, 106.4), _w("Dollar", 204.5, 106.4)]
    words += [_w("Capital.com", 36, 545, size=5), _w("is", 70, 545, size=5)]   # small print
    return words


def test_parse_sections_rebuilds_wrapped_rows():
    sections = capital.parse_sections([_ko_closed_page()])
    (row,) = sections["KO Closed trades"]
    assert row["Trade ID"] == "00945508-0001-54c4-0000-00008032174b"
    assert row["Underlier"] == "Ethereum to US Dollar"
    assert row["Currency / Conversion rate"] == "USD/0.9071775891"
    assert row["Date / Time"] == "14/11/2026 21:40:16"
    assert row["Realised P&L"] == "€209.52"
    assert row["Quantity"] == "6.00"
    assert row["Trigger"] == "EXPLICIT"


def test_section_continues_on_next_page_without_header():
    page1 = _ko_closed_page()
    page2 = [_w("Trading", 104, 18.4, size=8), _w("Statement", 133, 18.4, size=8)]  # page header
    page2 += [_w(t, x, 60) for t, x in (("14/11/2026", 36), ("22:00:00", 72.1), ("€5.00", 643))]
    sections = capital.parse_sections([page1, page2])
    rows = sections["KO Closed trades"]
    assert len(rows) == 2
    assert rows[1]["Realised P&L"] == "€5.00"
    assert "Trading" not in " ".join(rows[1].values())


# ----------------------------------------------------- statement -> common rows --

CLOSED = {"Date / Time": "14/11/2026 13:15:57", "Trade ID": "T1",
          "Underlier": "Ethereum to US Dollar", "Currency / Conversion rate": "USD/0.9",
          "Direction": "PUT", "Quantity": "5.00", "Open price": "1,902.97",
          "Close price": "1,895.00", "KO level": "2,284.36", "KO value": "1,906.95",
          "Realised P&L": "€36.02", "Trigger": "SL"}


def _rows(sections):
    return capital.statement_rows(sections)


def test_closed_trade_row():
    (r,) = _rows({"KO Closed trades": [CLOSED]})
    assert r["type"] == "CLOSED_TRADE" and r["broker"] == "capital"
    assert r["datetime"] == "2026-11-14T13:15:57Z" and r["date"] == "2026-11-14"
    assert r["pnl"] == 36.02
    assert r["cost"] == round(1906.95 * 0.9, 2)       # KO value converted to EUR
    assert r["side"] == "Short" and r["ko"] == "2,284.36 $" and r["how"] == ""


def test_negative_pnl_and_knock_out_trigger():
    row = {**CLOSED, "Realised P&L": "-€120.50", "Trigger": "KO"}
    (r,) = _rows({"KO Closed trades": [row]})
    assert r["pnl"] == -120.50 and r["how"] == "ko"


def test_ledger_mapping():
    ledger = [
        {"Date / Time": "14/11/2026 09:03:20", "Transaction ID": "1", "Description": "-",
         "Ledger transaction type": "DEPOSIT", "Amount, EUR": "€2,000.00"},
        {"Date / Time": "14/11/2026 12:42:13", "Transaction ID": "2",
         "Ledger transaction type": "KO_OPTION_BUY", "Amount, EUR": "-€1,730.07"},
        {"Date / Time": "14/11/2026 22:01:59", "Transaction ID": "3",
         "Description": "Ethereum to US Dollar KO", "Ledger transaction type": "OVERNIGHT FEE",
         "Amount, EUR": "€1.10"},
        {"Date / Time": "15/11/2026 10:00:00", "Transaction ID": "4",
         "Ledger transaction type": "TRADE_COMMISSION", "Amount, EUR": "-€3.00"},
        {"Date / Time": "15/11/2026 11:00:00", "Transaction ID": "5",
         "Ledger transaction type": "WITHDRAWAL", "Amount, EUR": "-€500.00"},
        {"Date / Time": "15/11/2026 12:00:00", "Transaction ID": "6",
         "Ledger transaction type": "SOMETHING_NEW", "Amount, EUR": "€1.00"},
    ]
    types = [(r["type"], float(r["amount"])) for r in _rows({"Ledger movement": ledger})]
    assert types == [("TRANSFER_INBOUND", 2000.0), ("INTEREST_PAYMENT", 1.1), ("FEE", -3.0),
                     ("TRANSFER_OUTBOUND", -500.0), ("CAPITAL:SOMETHING_NEW", 1.0)]


def test_open_rows_from_deal_confirmation():
    deals = [{"Date / Time": "14/11/2026 12:42:13", "Trade ID": "T1", "Status": "Open"},
             {"Date / Time": "14/11/2026 13:15:57", "Trade ID": "T1", "Status": "Close"}]
    (r,) = _rows({"KO Deal confirmation": deals})
    assert r["type"] == "POSITION_OPEN" and r["symbol"] == "T1"


# ------------------------------------------------------------------ analysis --

def _capital_day():
    return [
        {"broker": "capital", "type": "TRANSFER_INBOUND", "date": "2026-11-14",
         "datetime": "2026-11-14T09:00:00Z", "amount": "2000"},
        {"broker": "capital", "type": "POSITION_OPEN", "date": "2026-11-14",
         "datetime": "2026-11-14T12:42:13Z", "symbol": "T1"},
        {"broker": "capital", "type": "CLOSED_TRADE", "date": "2026-11-14",
         "datetime": "2026-11-14T13:15:57Z", "symbol": "T1", "shares": "5", "pnl": 36.02,
         "cost": 1729.94, "underlying": "Ethereum to US Dollar", "side": "Short",
         "ko": "2,284.36 USD", "product": "KO option", "how": ""},
        {"broker": "capital", "type": "INTEREST_PAYMENT", "date": "2026-11-14",
         "datetime": "2026-11-14T22:01:59Z", "amount": "1.10"},
        {"broker": "capital", "type": "FEE", "date": "2026-11-14",
         "datetime": "2026-11-14T22:30:00Z", "amount": "-3.00"},
    ]


def test_broker_reported_trade_is_realized_as_is():
    days, flows, meta = compute_daily(_capital_day())
    (d,) = days
    assert d["r"] == round(36.02 - 3.00, 2)       # trade P&L + knock-out fee
    assert d["f"] == -3.00
    assert d["i"] == 1.10
    assert d["p"] == round(36.02 - 3.00 + 1.10, 2)
    assert d["n"] == 2                            # open + close, like a buy + sell
    assert flows == [{"d": "2026-11-14", "dep": 2000.0, "wd": 0.0}]
    (t,) = meta["trades"]
    assert t["o"] == "2026-11-14T12:42:13Z" and t["c"] == "2026-11-14T13:15:57Z"
    assert t["u"] == "Ethereum to US Dollar" and t["side"] == "Short" and t["prod"] == "KO option"
    assert t["cost"] == 1729.94 and t["p"] == 36.02
    assert t["ep"] == round(1729.94 / 5, 4) and t["xp"] == round((1729.94 + 36.02) / 5, 4)


def test_brokers_kept_apart_and_merged():
    tr = [
        {"broker": "tr", "type": "BUY", "date": "2026-11-14", "datetime": "2026-11-14T08:00:00Z",
         "symbol": "X", "shares": "10", "amount": "-100", "fee": "-1"},
        {"broker": "tr", "type": "SELL", "date": "2026-11-14", "datetime": "2026-11-14T09:00:00Z",
         "symbol": "X", "shares": "-10", "amount": "150", "fee": "-1"},
    ]
    days, flows, meta, per = compute_by_broker(tr + _capital_day())
    assert set(per) == {"tr", "capital"}
    assert per["tr"]["days"][0]["p"] == 48.0
    assert days[0]["p"] == round(48.0 + 36.02 - 3.00 + 1.10, 2)
    assert days[0]["n"] == 4
    assert {t["b"] for t in meta["trades"]} == {"tr", "capital"}


def test_same_symbol_at_two_brokers_does_not_cross_match():
    rows = [
        {"broker": "a", "type": "BUY", "date": "2026-01-01", "symbol": "X", "shares": "1",
         "amount": "-100"},
        {"broker": "b", "type": "SELL", "date": "2026-01-02", "symbol": "X", "shares": "-1",
         "amount": "150"},
    ]
    _days, _flows, meta, _per = compute_by_broker(rows)
    assert meta["missing_basis"] == 1             # broker b never bought X


def test_payload_lists_brokers_with_tax_flag():
    payload = build_payload(_capital_day(), info)
    assert payload["meta"]["brokers"] == [
        {"id": "capital", "name": "Capital.com", "withholds_tax": False}]
    assert payload["brokers"]["capital"]["days"] == payload["days"]


# -------------------------------------------------------------------- loader --

def test_loader_dispatches_and_skips_with_notes(tmp_path):
    (tmp_path / "tr.csv").write_text(
        "datetime,date,type,amount,transaction_id\n"
        "2026-01-01T00:00:00Z,2026-01-01,INTEREST_PAYMENT,1,tid-1\n", encoding="utf-8")
    (tmp_path / "capital_transactions.csv").write_text(
        "Id,Balance,Amount,Currency,Type,Quantity,Status,Modified (UTC),Trade Id,ISIN,"
        "Instrument Symbol,Instrument Name,Commission,Regulatory fees,Taxes,Account type\n",
        encoding="utf-8")
    (tmp_path / "other.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    names = [os.path.basename(f) for f in find_data_files(str(tmp_path))]
    assert names == ["capital_transactions.csv", "other.csv", "tr.csv"]
    rows, notes = load(str(tmp_path))
    assert [(r["broker"], r["transaction_id"]) for r in rows] == [("tr", "tid-1")]
    assert any(n.startswith("capital_transactions.csv:") for n in notes)
    assert any(n.startswith("other.csv:") for n in notes)


def test_common_format_csv_keeps_each_rows_broker(tmp_path):
    (tmp_path / "mixed.csv").write_text(
        "datetime,date,type,amount,transaction_id,broker\n"
        "2026-01-01T00:00:00Z,2026-01-01,INTEREST_PAYMENT,1,a-1,tr\n"
        "2026-01-02T00:00:00Z,2026-01-02,TRANSFER_INBOUND,500,c-1,capital\n"
        "2026-01-03T00:00:00Z,2026-01-03,INTEREST_PAYMENT,2,x-1,\n", encoding="utf-8")
    rows, notes = load(str(tmp_path))
    assert [r["broker"] for r in rows] == ["tr", "capital", "common"] and notes == []


def test_bundled_demo_has_both_brokers():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # read the demo file directly: data/ may also hold real exports
    from brokers import common
    demo = common.read(os.path.join(here, "data", "demo.csv"))
    payload = build_payload(demo, info)
    assert [b["id"] for b in payload["meta"]["brokers"]] == ["tr", "capital"]
    assert payload["meta"]["unknown_types"] == {}
