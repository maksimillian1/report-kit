"""exporter.py — the queue, as Prometheus can see it.

Reads Redis and republishes it: two depths, three counters, and the one
number that is not directly observable anywhere else.

    jobs_inflight = enqueued - completed - depth(work) - depth(retry)

A unit that has been popped but not finished is in no queue and in no
counter. `BRPOP` is destructive, so nothing on the Redis side knows it exists
— which is the whole reason "the queue is empty" is not the same claim as
"the work is done", and why the runner's close condition also waits for the
worker pool to reach zero.
"""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from resp import Redis

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
WORK_QUEUE = os.environ.get("WORK_QUEUE", "jobs:work")
RETRY_QUEUE = os.environ.get("RETRY_QUEUE", "jobs:retry")
ENQUEUED_KEY = os.environ.get("ENQUEUED_KEY", "jobs:enqueued")
DONE_KEY = os.environ.get("DONE_KEY", "jobs:done")
RETRIED_KEY = os.environ.get("RETRIED_KEY", "jobs:retried")
INTERVAL = float(os.environ.get("SAMPLE_SECONDS", "1"))

state = {"work": 0, "retry": 0, "enqueued": 0, "done": 0, "retried": 0}
lock = threading.Lock()


def counter(redis: Redis, key: str) -> int:
    raw = redis.call("GET", key)
    return int(raw) if raw else 0


def sample() -> None:
    redis = Redis(REDIS_HOST, 6379, timeout=10)
    while True:
        try:
            fresh = {"work": redis.call("LLEN", WORK_QUEUE),
                     "retry": redis.call("LLEN", RETRY_QUEUE),
                     "enqueued": counter(redis, ENQUEUED_KEY),
                     "done": counter(redis, DONE_KEY),
                     "retried": counter(redis, RETRIED_KEY)}
        except (RuntimeError, OSError) as e:
            print(f"redis read failed ({e}) — reconnecting", flush=True)
            redis.close()
            time.sleep(1)
            redis = Redis(REDIS_HOST, 6379, timeout=10)
            continue
        with lock:
            state.update(fresh)
        time.sleep(INTERVAL)


class Metrics(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        with lock:
            s = dict(state)
        inflight = max(0, s["enqueued"] - s["done"] - s["work"] - s["retry"])
        body = (
            "# TYPE jobs_queue_depth gauge\n"
            f'jobs_queue_depth{{queue="work"}} {s["work"]}\n'
            f'jobs_queue_depth{{queue="retry"}} {s["retry"]}\n'
            "# TYPE jobs_inflight gauge\n"
            f"jobs_inflight {inflight}\n"
            "# TYPE jobs_enqueued_total counter\n"
            f'jobs_enqueued_total {s["enqueued"]}\n'
            "# TYPE jobs_completed_total counter\n"
            f'jobs_completed_total {s["done"]}\n'
            "# TYPE jobs_retried_total counter\n"
            f'jobs_retried_total {s["retried"]}\n'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    threading.Thread(target=sample, daemon=True).start()
    ThreadingHTTPServer(("", 8080), Metrics).serve_forever()
