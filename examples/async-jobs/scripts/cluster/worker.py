"""worker.py — one queue consumer. Runs in the cluster; KEDA decides how many.

Pops a unit, spends CPU on it, hands the result to the shared tier, and
counts it in Redis. Every knob is an environment variable so the manifest
holds the numbers and this file holds the shape.

Two details exist for the measurement rather than for the workload:

* **The failure is deterministic** — unit `n` is retried when `n %
  RETRY_EVERY == 0`, not at random. Every point on the grid must do the same
  work, or the grid measures the dice.
* **The counters live in Redis, not here.** A worker pool that scales to zero
  takes its `/metrics` with it, and a counter that vanishes at the end of the
  window cannot be checked at the end of the window. See `scripts/README.md`.
"""

from __future__ import annotations

import os
import signal
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from resp import Redis

POD = os.environ.get("POD_NAME", "unknown")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
WORK_QUEUE = os.environ.get("WORK_QUEUE", "jobs:work")
RETRY_QUEUE = os.environ.get("RETRY_QUEUE", "jobs:retry")
DONE_KEY = os.environ.get("DONE_KEY", "jobs:done")
RETRIED_KEY = os.environ.get("RETRIED_KEY", "jobs:retried")
BURN_MS = int(os.environ.get("BURN_MS", "150"))
RETRY_EVERY = int(os.environ.get("RETRY_EVERY", "20"))
RESULTS_URL = os.environ.get("RESULTS_URL", "http://results/ingest")

stopping = threading.Event()
busy = 0
jobs_here = 0
lock = threading.Lock()


def burn(ms: int) -> None:
    """Real CPU, so the autoscalers have something to react to."""
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        pass


class Metrics(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        with lock:
            body = (
                "# TYPE worker_busy gauge\n"
                f'worker_busy{{pod="{POD}"}} {busy}\n'
                "# TYPE worker_jobs_total counter\n"
                f'worker_jobs_total{{pod="{POD}"}} {jobs_here}\n'
            ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def handle(unit: int, attempt: int, redis: Redis) -> None:
    global busy, jobs_here
    with lock:
        busy = 1
    try:
        burn(BURN_MS)
        # A transient failure, decided by the unit's number so that every point
        # on the grid retries exactly the same units.
        if attempt == 0 and unit % RETRY_EVERY == 0:
            redis.call("RPUSH", RETRY_QUEUE, f"{unit}|1")
            redis.call("INCR", RETRIED_KEY)
            return
        try:
            urllib.request.urlopen(
                urllib.request.Request(RESULTS_URL, data=b"{}",
                                       headers={"Content-Type": "application/json"}),
                timeout=30).read()
        except (urllib.error.URLError, OSError) as e:
            # The shared tier being unreachable is a finding, not a reason to
            # drop the unit: push it back so the conservation guard can see it.
            redis.call("RPUSH", RETRY_QUEUE, f"{unit}|{attempt}")
            print(f"results unreachable ({e}) — unit {unit} requeued", flush=True)
            return
        redis.call("INCR", DONE_KEY)
        with lock:
            jobs_here += 1
    finally:
        with lock:
            busy = 0


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    threading.Thread(
        target=ThreadingHTTPServer(("", 8080), Metrics).serve_forever,
        daemon=True).start()

    redis = Redis(REDIS_HOST, 6379, timeout=30)
    print(f"worker {POD} up · burn {BURN_MS}ms · retry every {RETRY_EVERY}",
          flush=True)
    while not stopping.is_set():
        # Work before retries, so a requeued unit waits for the backlog to
        # clear — which is what makes the retry queue refill after the work
        # queue has already read empty.
        popped = redis.call("BRPOP", WORK_QUEUE, RETRY_QUEUE, 2)
        if popped is None:
            continue
        unit, _, attempt = popped[1].decode().partition("|")
        handle(int(unit), int(attempt or 0), redis)
    print(f"worker {POD} stopping after {jobs_here} unit(s)", flush=True)


if __name__ == "__main__":
    main()
