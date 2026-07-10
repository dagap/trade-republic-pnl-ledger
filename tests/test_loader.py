"""Tests for the loader — file discovery, demo precedence, and de-duplication."""

import os

from loader import find_csv_files, load_transactions

HEADER = "datetime,date,type,amount,transaction_id\n"


def _write(path, *lines):
    path.write_text(HEADER + "".join(lines), encoding="utf-8")


def test_real_data_takes_precedence_over_demo(tmp_path):
    (tmp_path / "demo.csv").write_text(HEADER)
    (tmp_path / "transactions.csv").write_text(HEADER)
    names = [os.path.basename(f) for f in find_csv_files(str(tmp_path))]
    assert names == ["transactions.csv"]


def test_demo_used_when_it_is_the_only_file(tmp_path):
    (tmp_path / "demo.csv").write_text(HEADER)
    files = find_csv_files(str(tmp_path))
    assert len(files) == 1 and os.path.basename(files[0]) == "demo.csv"


def test_load_dedupes_by_transaction_id(tmp_path):
    _write(tmp_path / "a.csv",
           "2026-01-01T00:00:00Z,2026-01-01,BUY,-100,tid-1\n")
    _write(tmp_path / "b.csv",
           "2026-01-02T00:00:00Z,2026-01-02,SELL,150,tid-1\n",   # duplicate id -> dropped
           "2026-01-03T00:00:00Z,2026-01-03,SELL,120,tid-2\n")
    rows = load_transactions(str(tmp_path))
    ids = [r["transaction_id"] for r in rows]
    assert ids == ["tid-1", "tid-2"]   # de-duped and chronologically sorted
