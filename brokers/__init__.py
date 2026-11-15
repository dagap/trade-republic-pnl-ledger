"""Broker readers: one small module per broker.

Each reader recognises its own export files and converts them into the common
row format that :mod:`analysis` understands (Trade Republic's CSV columns —
``datetime``, ``date``, ``type``, ``symbol``, ``shares``, ``amount``, ``fee``,
``tax``, ``transaction_id`` … — plus a ``broker`` id). The P&L logic and the
dashboard only ever see that common format, so adding a broker means adding one
module here and listing it in ``READERS``.

A reader module provides:

    ID, NAME        short id ("tr") and display name ("Trade Republic")
    WITHHOLDS_TAX   True if the broker deducts capital-gains tax at source; if
                    not, the dashboard can show an estimate of the tax owed
    detect(path, head) -> bool   is this file ours? ``head`` is the first 4 KB
    read(path) -> list[dict]     rows in the common format
"""

from __future__ import annotations

from . import capital, traderepublic

READERS = (traderepublic, capital)


class SkipFile(Exception):
    """A recognised file that deliberately contributes no rows; the message says why."""


def _head(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(4096)


def reader_for(path: str):
    """Return the reader module that recognises ``path``, or ``None``."""
    head = _head(path)
    return next((r for r in READERS if r.detect(path, head)), None)


def info(broker_id: str) -> dict:
    """Display metadata for a broker id (unknown ids get neutral defaults)."""
    for r in READERS:
        if r.ID == broker_id:
            return {"id": r.ID, "name": r.NAME, "withholds_tax": r.WITHHOLDS_TAX}
    return {"id": broker_id, "name": broker_id, "withholds_tax": True}
