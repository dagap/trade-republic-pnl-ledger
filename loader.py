"""Data access for the P&L dashboard.

Finds, reads, merges and de-dupes the source transaction CSVs. This module is
pure data access — it holds no business logic and does no analysis, so it can
be reused and tested on its own.
"""

from __future__ import annotations

import csv
import glob
import os

# Bundled sample data. It's used only when no real export is present, so a fresh
# clone renders a populated dashboard out of the box — but the moment you drop
# your own CSV into data/, the demo steps aside.
DEMO_FILE = "demo.csv"


def find_csv_files(data_dir: str) -> list[str]:
    """Return the CSV files to load from ``data_dir``, sorted by name.

    If any real export is present, ``demo.csv`` is ignored; if the demo is all
    that's there, it's used on its own.
    """
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    real = [f for f in files if os.path.basename(f) != DEMO_FILE]
    return real or files


def load_transactions(data_dir: str) -> list[dict]:
    """Load and merge every CSV in ``data_dir``.

    Rows are de-duped by ``transaction_id`` (rows without one are always kept)
    and returned in chronological order — ordering matters because the analysis
    layer accounts for positions using a running average cost.
    """
    files = find_csv_files(data_dir)
    if not files:
        raise SystemExit(f"No CSV files found in {data_dir}")

    seen: set[str] = set()
    rows: list[dict] = []
    for path in files:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                tid = (row.get("transaction_id") or "").strip()
                if tid:
                    if tid in seen:
                        continue
                    seen.add(tid)
                rows.append(row)

    rows.sort(key=lambda r: (r.get("datetime") or r.get("date") or ""))
    return rows
