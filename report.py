#!/usr/bin/env python3
"""Save a trading day as a PDF report: ``reports/daily_report_<date>.pdf``.

The report is an HTML page (``web/report.html`` + ``report.css`` + ``report.js``)
that reuses the day view's numbers and charts. It is assembled by
``build.render_report`` and printed to A4 PDF by a headless Chrome / Chromium /
Edge already installed on the machine, so there is still no Python dependency.

    uv run python report.py 2026-11-12          # one-off, from the shell
    uv run python report.py 2026-11-12 --theme dark
    uv run python serve.py                      # or the dashboard's day view button

Set ``CHROME_PATH`` if the browser isn't found automatically.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build import HERE, WEB_DIR, load_payload, render_report

REPORTS_DIR = os.path.join(HERE, "reports")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
THEMES = ("light", "dark")

_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             "chrome", "msedge", "microsoft-edge")
_BROWSER_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


class ReportError(Exception):
    """A report couldn't be produced; the message is safe to show the user."""


def find_browser() -> str | None:
    """Locate a Chromium-based browser: ``$CHROME_PATH``, then PATH, then the usual installs."""
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    for name in _BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return next((p for p in _BROWSER_PATHS if os.path.exists(p)), None)


def report_filename(date: str) -> str:
    return f"daily_report_{date}.pdf"


def _validate(payload: dict, date: str) -> None:
    if not DATE_RE.match(date):
        raise ReportError(f"Not a date (expected YYYY-MM-DD): {date!r}")
    try:
        dt.date.fromisoformat(date)
    except ValueError as exc:
        raise ReportError(f"Not a valid date: {date}") from exc
    if not any(t["d"] == date for t in payload["meta"].get("trades", [])):
        raise ReportError(f"No closed trades on {date}, so there is nothing to report.")


def print_to_pdf(html: str, out_path: str, browser: str | None = None,
                 timeout: float = 60) -> None:
    """Render ``html`` with headless Chrome and write it to ``out_path`` as a PDF."""
    browser = browser or find_browser()
    if not browser:
        raise ReportError("No Chrome, Chromium or Edge found. Install one, or set CHROME_PATH.")
    with tempfile.TemporaryDirectory(prefix="pnl-report-") as tmp:
        page = Path(tmp, "report.html")
        page.write_text(html, encoding="utf-8")
        partial = Path(tmp, "out.pdf")
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions",
            # A throwaway profile, so this never touches (or hands off to) a running browser.
            f"--user-data-dir={Path(tmp, 'profile')}",
            "--no-pdf-header-footer", "--window-size=1200,1600",
            f"--print-to-pdf={partial}", page.as_uri(),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ReportError(f"The browser took longer than {timeout:.0f}s to print the report.") \
                from exc
        except OSError as exc:
            raise ReportError(f"Couldn't start the browser ({browser}): {exc}") from exc
        if not partial.exists() or partial.stat().st_size == 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["no output"]
            raise ReportError(f"The browser didn't produce a PDF ({detail[0]}).")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.move(str(partial), out_path)


def generate(payload: dict, date: str, reports_dir: str = REPORTS_DIR,
             browser: str | None = None, theme: str = "light") -> str:
    """Write ``reports_dir/daily_report_<date>.pdf`` (overwriting) and return its path.

    ``theme`` is ``"light"`` (the default) or ``"dark"``.
    """
    _validate(payload, date)
    if theme not in THEMES:
        raise ReportError(f"Unknown theme {theme!r} (expected one of: {', '.join(THEMES)}).")
    generated = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    html = render_report(payload, date, generated, WEB_DIR, theme)
    out = os.path.join(reports_dir, report_filename(date))
    print_to_pdf(html, out, browser)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Save one trading day as a PDF report.")
    ap.add_argument("date", help="the trading day, YYYY-MM-DD")
    ap.add_argument("--theme", choices=THEMES, default="light", help="colour theme (default: light)")
    args = ap.parse_args(argv)
    try:
        out = generate(load_payload(), args.date, theme=args.theme)
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {os.path.relpath(out, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
