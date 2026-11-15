"""Capital.com: the PDF "Client Daily Statement".

Capital.com's CSV transaction export leaves the instrument, trade id and
quantity blank, so the statement is the useful source. It holds, among others:

* **KO / CFD Deal confirmation** — every open and close, with its Trade ID;
  the *Open* rows tell us when a position was entered.
* **KO Closed trades / CFD Closed positions** — one row per (partial) close
  with Capital.com's own realised P&L in EUR. We take that figure as-is rather
  than recomputing it: it's the number the broker reports, and the ledger cash
  ties out to it.
* **Ledger movement** — every cash movement: deposits, withdrawals, overnight
  funding, knock-out fees. Buys and sells also appear here but are already
  covered by the closed trades, so they're skipped.

The PDF has no ruled tables, so it is read from word positions: a section
starts at its heading, the bold header row gives the column positions, and the
wrapped lines of a row (long Trade IDs, two-line underlier names) are grouped
around the row's date. Times on the statement are UTC.

Capital.com is a Cyprus-regulated broker and doesn't withhold German tax.

Needs ``pdfplumber`` (installed automatically by ``uv run``); it's imported only
when a Capital.com statement is actually present.
"""

from __future__ import annotations

import re
from collections import defaultdict

ID = "capital"
NAME = "Capital.com"
WITHHOLDS_TAX = False

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_TITLE_SIZE = 10      # section headings are 11pt; table text is 6–6.5pt
_BODY = (6.2, 7.5)    # data rows are 6.5pt (small print 5pt, page header 8pt)
_PAD = 10             # a value may sit a little left of its (left-aligned) header


def detect(path: str, head: bytes) -> bool:
    low = path.lower()
    if low.endswith(".pdf"):
        # PDF text is compressed, so the head can't tell whose statement this is;
        # read() checks the first page and skips a PDF that isn't Capital.com's.
        return head.startswith(b"%PDF")
    if low.endswith(".csv"):
        first = head.decode("utf-8", "replace").splitlines()[0] if head else ""
        return "Trade Id" in first and "Account type" in first
    return False


def read(path: str) -> list[dict]:
    from . import SkipFile

    if path.lower().endswith(".csv"):
        raise SkipFile("Capital.com transaction CSV skipped — it has no instrument or "
                       "trade id; drop the PDF statement into data/ instead")
    try:
        import pdfplumber
    except ImportError as exc:   # pragma: no cover - environment dependent
        raise SkipFile("Capital.com statements need pdfplumber: "
                       "run with `uv run`, or `pip install pdfplumber`") from exc

    with pdfplumber.open(path) as pdf:
        pages = [p.extract_words(extra_attrs=["size", "fontname"]) for p in pdf.pages]
    text = " ".join(w["text"] for w in (pages[0] if pages else []))
    if "Capital.com" not in text and "Capital Com" not in text:
        raise SkipFile("PDF not recognised as a Capital.com statement")
    return statement_rows(parse_sections(pages))


# ---------------------------------------------------------------- PDF layout --

def _cluster_header(words: list[dict]) -> list[dict]:
    """Group header words into columns by horizontal overlap / small gaps."""
    cols: list[dict] = []
    for w in sorted(words, key=lambda w: w["x0"]):
        if cols and w["x0"] <= cols[-1]["x1"] + 4.5:
            c = cols[-1]
            c["words"].append(w)
            c["x1"] = max(c["x1"], w["x1"])
        else:
            cols.append({"x0": w["x0"], "x1": w["x1"], "words": [w]})
    for c in cols:
        ws = sorted(c["words"], key=lambda w: (round(w["top"]), w["x0"]))
        c["name"] = " ".join(w["text"] for w in ws)
    return cols


def _column(cols: list[dict], w: dict) -> str:
    centre = (w["x0"] + w["x1"]) / 2
    name = cols[0]["name"]
    for c in cols:
        if c["x0"] - _PAD <= centre:
            name = c["name"]
    return name


def _join(parts: list[str]) -> str:
    out = ""
    for p in parts:
        out += p if (not out or out.endswith("-")) else " " + p
    return out


def parse_sections(pages: list[list[dict]]) -> dict[str, list[dict]]:
    """Return ``{section title: [ {column name: cell text}, ... ]}``.

    A section runs from its heading to the next one, across page breaks; a page
    that continues a table without repeating its header reuses the columns.
    """
    sections: dict[str, list[dict]] = defaultdict(list)
    title = None
    cols: list[dict] = []

    for words in pages:
        lines: dict[float, list[dict]] = defaultdict(list)
        for w in words:
            lines[round(w["top"], 1)].append(w)
        # Walk the page top to bottom, splitting it into (title, header, body) runs.
        runs: list[tuple[str | None, list[dict], list[dict]]] = []
        cur_title, header, body = title, [], []
        for top in sorted(lines):
            lw = lines[top]
            if all(w["size"] >= _TITLE_SIZE for w in lw):
                runs.append((cur_title, header, body))
                cur_title, header, body = " ".join(w["text"] for w in lw), [], []
            elif all("Bold" in w["fontname"] for w in lw) and not body:
                header.extend(lw)
            elif all(_BODY[0] <= w["size"] < _BODY[1] for w in lw) and \
                    not any("Bold" in w["fontname"] for w in lw):
                body.extend(lw)
        runs.append((cur_title, header, body))

        for run_title, header, body in runs:
            if run_title != title:
                title, cols = run_title, []
            if header:
                cols = _cluster_header(header)
            if not (title and cols and body):
                continue
            first = cols[0]["name"]
            anchors = sorted({w["top"] for w in body
                              if _DATE.match(w["text"]) and _column(cols, w) == first})
            if not anchors:
                continue
            rows: dict[float, dict[str, list[dict]]] = {a: defaultdict(list) for a in anchors}
            for w in body:
                a = min(anchors, key=lambda a: abs(a - w["top"]))
                rows[a][_column(cols, w)].append(w)
            for a in anchors:
                cells = {k: _join([w["text"] for w in sorted(v, key=lambda w: (round(w["top"]), w["x0"]))])
                         for k, v in rows[a].items()}
                sections[title].append(cells)
    return dict(sections)


# ------------------------------------------------------------ to common rows --

def _num(s: str | None) -> float:
    s = (s or "").replace("€", "").replace(",", "").replace("$", "").strip()
    if s in ("", "-"):
        return 0.0
    neg = s.startswith("-") or s.startswith("−")
    v = float(s.lstrip("-−"))
    return -v if neg else v


def _when(cell: str) -> tuple[str, str]:
    """``"14/11/2026 13:15:57"`` -> (``"2026-11-14T13:15:57Z"``, ``"2026-11-14"``)."""
    parts = (cell or "").split()
    m = _DATE.match(parts[0]) if parts else None
    if not m:
        return "", ""
    d, mo, y = m.groups()
    t = next((p for p in parts[1:] if _TIME.match(p)), "00:00:00")
    return f"{y}-{mo}-{d}T{t}Z", f"{y}-{mo}-{d}"


def _get(row: dict, *names: str) -> str:
    """First cell whose column name starts with one of ``names``."""
    for n in names:
        for k, v in row.items():
            if k.startswith(n):
                return v
    return ""


_SIDE = {"PUT": "Short", "SELL": "Short", "CALL": "Long", "BUY": "Long"}


def _closed_trade(row: dict, kind: str) -> dict | None:
    dt, date = _when(_get(row, "Date"))
    tid = _get(row, "Trade ID", "Position ID")
    if not date or not tid:
        return None
    cur = _get(row, "Currency")                    # "USD/0.9071775891" or "EUR"
    ccy, _, rate = cur.partition("/")
    fx = float(rate) if rate else 1.0
    qty = _num(_get(row, "Quantity"))
    pnl = _num(_get(row, "Realised P&L"))
    direction = _get(row, "Direction").upper()
    ko = _get(row, "KO level")
    # A KO option's premium is the gap between the KO level and the price —
    # "KO value" on the statement, in the instrument currency, for the whole
    # quantity. That's the cash at risk, so it's the entry cost.
    cost = _num(_get(row, "KO value")) * fx if kind == "KO" else 0.0
    trigger = _get(row, "Trigger").upper()
    return {
        "broker": ID,
        "type": "CLOSED_TRADE",
        "datetime": dt,
        "date": date,
        "symbol": tid,
        "shares": str(qty),
        "pnl": pnl,
        "cost": round(cost, 2),
        "underlying": _get(row, "Underlier"),
        "side": _SIDE.get(direction, ""),
        "ko": f"{ko} {ccy}".strip() if ko and ko != "-" else "",
        "product": "KO option" if kind == "KO" else "CFD",
        "how": "ko" if ("KO" in trigger or "KNOCK" in trigger) else "",
        "transaction_id": f"{ID}:{tid}:close:{dt}:{qty}:{_get(row, 'Close price')}",
    }


def _opened(row: dict) -> dict | None:
    if _get(row, "Status").strip().lower() != "open":
        return None
    dt, date = _when(_get(row, "Date"))
    tid = _get(row, "Trade ID", "Position ID")
    if not date or not tid:
        return None
    return {"broker": ID, "type": "POSITION_OPEN", "datetime": dt, "date": date,
            "symbol": tid, "transaction_id": f"{ID}:{tid}:open"}


def _ledger(row: dict) -> dict | None:
    dt, date = _when(_get(row, "Date"))
    kind = (_get(row, "Ledger transaction type") or "").upper()
    desc = _get(row, "Description")
    amount = _num(_get(row, "Amount, EUR", "Amount"))
    both = f"{desc} {kind}".upper()
    if not date:
        return None
    if re.search(r"_(BUY|SELL)$", kind) or kind in {"TRADE", "BUY", "SELL"}:
        return None                      # covered by the closed-trade rows
    if "DEPOSIT" in kind:
        typ = "TRANSFER_INBOUND"
    elif "WITHDRAW" in kind:
        typ = "TRANSFER_OUTBOUND"
    elif "OVERNIGHT" in both or "SWAP" in both or "FUNDING" in both:
        typ = "INTEREST_PAYMENT"         # financing charge / credit
    elif "DIVIDEND" in kind:
        typ = "DIVIDEND"
    elif "COMMISSION" in kind or "FEE" in kind:
        typ = "FEE"                      # e.g. the knock-out fee
    else:
        typ = f"CAPITAL:{kind or 'UNKNOWN'}"
    tid = _get(row, "Transaction ID")
    return {"broker": ID, "type": typ, "datetime": dt, "date": date,
            "amount": str(amount), "description": desc,
            "transaction_id": f"{ID}:ledger:{tid}" if tid else ""}


def statement_rows(sections: dict[str, list[dict]]) -> list[dict]:
    """Convert parsed statement sections into common rows."""
    out: list[dict] = []
    for title, rows in sections.items():
        t = title.lower()
        for row in rows:
            if t.startswith(("ko closed", "cfd closed")):
                r = _closed_trade(row, "KO" if t.startswith("ko") else "CFD")
            elif "deal confirmation" in t and t.startswith(("ko", "cfd")):
                r = _opened(row)
            elif t.startswith("ledger"):
                r = _ledger(row)
            else:
                r = None
            if r:
                out.append(r)
    return out
