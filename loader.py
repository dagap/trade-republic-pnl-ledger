"""Data access for the P&L dashboard.

Finds the broker exports in ``data/``, hands each to the broker reader that
recognises it (see :mod:`brokers`), and merges and de-dupes the resulting rows.
This module is pure data access — it holds no business logic and does no
analysis, so it can be reused and tested on its own.
"""

from __future__ import annotations

import glob
import os

import brokers

# Bundled sample data. It's used only when no real export is present, so a fresh
# clone renders a populated dashboard out of the box — but the moment you drop
# your own export into data/, the demo steps aside.
DEMO_FILE = "demo.csv"
EXTENSIONS = (".csv", ".pdf")


def find_data_files(data_dir: str) -> list[str]:
    """Return the export files (CSV / PDF) to load from ``data_dir``, sorted by name.

    If any real export is present, ``demo.csv`` is ignored; if the demo is all
    that's there, it's used on its own.
    """
    files = sorted(f for f in glob.glob(os.path.join(data_dir, "*"))
                   if f.lower().endswith(EXTENSIONS) and os.path.isfile(f))
    real = [f for f in files if os.path.basename(f) != DEMO_FILE]
    return real or files


# Kept for callers written before PDFs were supported.
find_csv_files = find_data_files


def load(data_dir: str) -> tuple[list[dict], list[str]]:
    """Load and merge every export in ``data_dir``.

    Returns ``(rows, notes)``. Each row carries a ``broker`` id. Rows are de-duped
    per broker by ``transaction_id`` (rows without one are always kept), so
    overlapping exports or statements can sit side by side, and returned in
    chronological order — ordering matters because the analysis matches sells
    against earlier buys. ``notes`` lists files that were skipped, and why.
    """
    files = find_data_files(data_dir)
    if not files:
        raise SystemExit(f"No CSV or PDF files found in {data_dir}")

    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    notes: list[str] = []
    for path in files:
        name = os.path.basename(path)
        reader = brokers.reader_for(path)
        if reader is None:
            notes.append(f"{name}: not a recognised broker export, skipped")
            continue
        try:
            file_rows = reader.read(path)
        except brokers.SkipFile as exc:
            notes.append(f"{name}: {exc}")
            continue
        for row in file_rows:
            row.setdefault("broker", reader.ID)
            tid = (row.get("transaction_id") or "").strip()
            if tid:
                key = (row["broker"], tid)
                if key in seen:
                    continue
                seen.add(key)
            rows.append(row)

    rows.sort(key=lambda r: (r.get("datetime") or r.get("date") or ""))
    return rows, notes


def load_transactions(data_dir: str) -> list[dict]:
    """Like :func:`load`, rows only."""
    return load(data_dir)[0]
