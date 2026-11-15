"""Trade Republic: the "CSV export for tracking tools".

The export already *is* the common row format, so reading it is just tagging
each row with the broker id.
"""

from __future__ import annotations

import csv

ID = "tr"
NAME = "Trade Republic"
WITHHOLDS_TAX = True   # German broker: Abgeltungsteuer is withheld on every sale


def detect(path: str, head: bytes) -> bool:
    if not path.lower().endswith(".csv"):
        return False
    first = head.decode("utf-8", "replace").splitlines()[0] if head else ""
    cols = {c.strip().strip('"') for c in first.split(",")}
    return {"type", "transaction_id"} <= cols


def read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [{**row, "broker": ID} for row in csv.DictReader(fh)]
