"""The common row format itself, as a CSV with a ``broker`` column.

Any CSV whose header has ``broker`` and ``type`` columns is read as-is: each row
already names its broker and uses the column names :mod:`analysis` expects
(see :mod:`brokers`). The bundled ``data/demo.csv`` uses it to hold sample data
for several brokers in one file, and it's a way to bring in a broker that has
no reader yet — convert its export to this format once.
"""

from __future__ import annotations

import csv

ID = "common"
NAME = "Other"
WITHHOLDS_TAX = True


def detect(path: str, head: bytes) -> bool:
    if not path.lower().endswith(".csv"):
        return False
    first = head.decode("utf-8", "replace").splitlines()[0] if head else ""
    cols = {c.strip().strip('"') for c in first.split(",")}
    return {"broker", "type"} <= cols


def read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [{**row, "broker": (row.get("broker") or "").strip() or ID}
                for row in csv.DictReader(fh)]
