#!/usr/bin/env python3
"""Build the self-contained P&L calendar dashboard.

Thin orchestrator that wires the pieces together:

    loader.load_transactions  ->  analysis.build_payload  ->  web/ template

It reads every ``*.csv`` in ``./data`` and assembles the front-end sources in
``web/`` (HTML shell + stylesheet + script) with the data baked in, producing a
single self-contained ``dashboard.html`` you can open in any browser.

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


def render(payload: dict, web_dir: str) -> str:
    """Assemble the self-contained dashboard.

    Inlines the stylesheet and script into the HTML shell and bakes the data in
    as JSON, so the output is one portable file with no external requests.
    """
    template = _read(os.path.join(web_dir, "template.html"))
    styles = _read(os.path.join(web_dir, "styles.css"))
    app = _read(os.path.join(web_dir, "app.js"))
    data_json = json.dumps(payload, separators=(",", ":"))

    html = template.replace("/*__STYLES__*/", styles).replace("/*__APP__*/", app)
    return html.replace("/*__DATA__*/", data_json)


def main() -> None:
    rows = load_transactions(DATA_DIR)
    payload = build_payload(rows)
    meta = payload["meta"]
    meta["n_files"] = len(find_csv_files(DATA_DIR))

    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(render(payload, WEB_DIR))

    print(f"Loaded {meta['n_txns']} txns from {meta['n_files']} file(s).")
    print(f"Days with activity: {meta['n_days']}  "
          f"({meta['min_date']} -> {meta['max_date']})")
    print(f"All-time net P&L: {meta['total_pnl']:+,.2f} EUR")
    if meta["missing_basis"]:
        print(f"Note: {meta['missing_basis']} sell(s) had no prior cost basis "
              "in the data (treated as zero cost).")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
