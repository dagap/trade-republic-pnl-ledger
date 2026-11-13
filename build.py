#!/usr/bin/env python3
"""Build the self-contained P&L calendar dashboard.

Thin orchestrator that wires the pieces together:

    loader.load_transactions  ->  analysis.build_payload  ->  web/ template

It reads every ``*.csv`` in ``./data`` and assembles the front-end sources in
``web/`` (HTML shell + stylesheet + scripts) with the data baked in, producing a
single self-contained ``dashboard.html`` you can open in any browser.

``render_report`` assembles the printable one-day page that ``report.py`` turns
into a PDF.

    uv run python build.py      # reads ./data/*.csv -> dashboard.html

Pure standard library. No dependencies.
"""

from __future__ import annotations

import json
import os

from analysis import build_payload
from loader import find_csv_files, load_transactions

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
WEB_DIR = os.path.join(HERE, "web")
OUT_FILE = os.path.join(HERE, "dashboard.html")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _inline(template: str, web_dir: str, styles: str, scripts: dict, data: str) -> str:
    """Swap each ``/*__NAME__*/`` placeholder for its source file, then the data.

    The data goes in last: ``core.js`` carries the ``/*__DATA__*/`` slot.
    """
    html = template.replace("/*__STYLES__*/", _read(os.path.join(web_dir, styles)))
    for slot, name in scripts.items():
        html = html.replace(f"/*__{slot}__*/", _read(os.path.join(web_dir, name)))
    return html.replace("/*__DATA__*/", data)


def render(payload: dict, web_dir: str) -> str:
    """Assemble the self-contained dashboard.

    Inlines the stylesheet and scripts into the HTML shell and bakes the data in
    as JSON, so the output is one portable file with no external requests.
    """
    return _inline(
        _read(os.path.join(web_dir, "template.html")), web_dir, "styles.css",
        {"CORE": "core.js", "APP": "app.js", "DAYCORE": "day-core.js", "DAY": "day.js"},
        json.dumps(payload, separators=(",", ":")),
    )


def day_payload(payload: dict, date: str) -> dict:
    """Cut the payload down to one day: its day record and the trades closed on it."""
    meta = dict(payload["meta"])
    meta["trades"] = [t for t in meta.get("trades", []) if t["d"] == date]
    return {
        "days": [d for d in payload["days"] if d["d"] == date],
        "flows": [],
        "meta": meta,
    }


def render_report(payload: dict, date: str, generated: str, web_dir: str) -> str:
    """Assemble the printable report page for one day (see ``web/report.html``).

    Only that day's data is baked in. ``generated`` is an ISO timestamp shown in
    the report footer.
    """
    html = _inline(
        _read(os.path.join(web_dir, "report.html")), web_dir, "report.css",
        {"CORE": "core.js", "DAYCORE": "day-core.js", "REPORT": "report.js"},
        json.dumps(day_payload(payload, date), separators=(",", ":")),
    )
    report_meta = json.dumps({"date": date, "generated": generated})
    return html.replace("/*__REPORT_META__*/", report_meta)


def load_payload(data_dir: str = DATA_DIR) -> dict:
    """Read every CSV in ``data_dir`` and return the analysed payload."""
    payload = build_payload(load_transactions(data_dir))
    payload["meta"]["n_files"] = len(find_csv_files(data_dir))
    return payload


def main() -> None:
    payload = load_payload()
    meta = payload["meta"]

    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(render(payload, WEB_DIR))

    print(f"Loaded {meta['n_txns']} txns from {meta['n_files']} file(s).")
    print(f"Days with activity: {meta['n_days']}  "
          f"({meta['min_date']} -> {meta['max_date']})")
    print(f"All-time net P&L: {meta['total_pnl']:+,.2f} EUR")
    print(f"Funding: {meta['deposits']:+,.2f} in, {meta['withdrawals']:+,.2f} out, "
          f"net {meta['net_deposited']:+,.2f} EUR")
    if meta["missing_basis"]:
        print(f"Note: {meta['missing_basis']} sell(s) had no prior cost basis "
              "in the data (treated as zero cost).")
    if meta["unknown_types"]:
        listing = ", ".join(f"{t} ({n})" for t, n in meta["unknown_types"].items())
        print(f"Warning: unrecognised transaction type(s) excluded: {listing}")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
