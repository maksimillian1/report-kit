"""results.py — the shared tier the workers lean on.

Always on, autoscaled, and capped below what the worker pool can offer it.
It exists so the example has the thing that makes an async grid interesting:
a component that does *not* scale with the workers, and therefore decides
where adding workers stops paying.

It is also what the close condition's third clause is about — the window does
not close until this is back at its floor, because a tier still scaled out is
a tier still working.
"""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POD = os.environ.get("POD_NAME", "unknown")
BURN_MS = int(os.environ.get("BURN_MS", "25"))

lock = threading.Lock()
ingested = 0
seconds = 0.0


def burn(ms: int) -> None:
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path.startswith("/metrics"):
            with lock:
                body = (
                    "# TYPE results_ingested_total counter\n"
                    f'results_ingested_total{{pod="{POD}"}} {ingested}\n'
                    "# TYPE results_seconds_total counter\n"
                    f'results_seconds_total{{pod="{POD}"}} {seconds:.6f}\n'
                ).encode()
            self.respond(200, body, "text/plain; version=0.0.4")
            return
        self.respond(200, b"ok")

    def do_POST(self):
        global ingested, seconds
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        started = time.perf_counter()
        burn(BURN_MS)
        with lock:
            ingested += 1
            seconds += time.perf_counter() - started
        self.respond(200, b'{"ok":true}', "application/json")

    def respond(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("", 8080), Handler).serve_forever()
