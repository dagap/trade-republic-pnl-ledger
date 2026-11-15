#!/usr/bin/env python3
"""Serve the dashboard locally so the day view can save PDF reports.

``dashboard.html`` on its own is a static file and can't write to disk; served
from here, the day view's *Generate report* button asks this server to write
``reports/daily_report_<date>.pdf``.

    uv run python serve.py              # http://127.0.0.1:8765
    uv run python serve.py --port 9000 --no-open

The CSVs in ``./data`` are re-read on every page load, so dropping in a fresh
export only needs a browser refresh. Binds to localhost only.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import report
from build import HERE, WEB_DIR, load_payload, render


class Handler(BaseHTTPRequestHandler):
    server_version = "PnLLedger"

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path.split("?")[0] not in ("/", "/index.html", "/dashboard.html"):
            self._send(404, b"Not found", "text/plain")
            return
        html = render(load_payload(), WEB_DIR)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/report":
            self._json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            date = str(body.get("date", ""))
            theme = str(body.get("theme") or "light")
            view = body.get("view")
        except (ValueError, AttributeError):
            self._json(400, {"error": "Expected a JSON body like {\"date\": \"YYYY-MM-DD\"}"})
            return
        try:
            out = report.generate(load_payload(), date, theme=theme, view=view)
        except report.ReportError as exc:
            self._json(400, {"error": str(exc)})
            return
        rel = os.path.relpath(out, HERE)
        self.log_message("wrote %s", rel)
        self._json(200, {"path": rel})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Serve the P&L dashboard with PDF report saving.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    args = ap.parse_args(argv)

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving the dashboard at {url}  (Ctrl+C to stop)")
    if not report.find_browser():
        print("Note: no Chrome/Chromium/Edge found; set CHROME_PATH to enable PDF reports.")
    if not args.no_open:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
