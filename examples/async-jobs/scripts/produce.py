#!/usr/bin/env python3
"""produce.py — puts work in the queue, at a steady rate, while the system drains it.

    ./produce.py --count 400 --rate 40

Runs in the background for the whole of a point (`point.py` starts it with
`report_kit.proc.Background`), which is the one thing about this profile that
must not be simplified away: filling the queue first and then watching would
measure a system draining a backlog that already exists, and the arrival
pattern that produced the backlog would be gone from the data.

The rate is offered on a schedule, not paced by how fast the queue drains —
the same open-model choice as the api example's k6 scenario, for the same
reason. A producer that waited for the workers could never build a backlog,
and a backlog is what this profile measures.
"""

from __future__ import annotations

import argparse
import sys
import time

from resp import Redis


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--redis", default="localhost:6380", help="host:port")
    p.add_argument("--queue", default="jobs:work")
    p.add_argument("--enqueued-key", default="jobs:enqueued")
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--rate", type=float, default=40.0, help="units per second")
    args = p.parse_args()

    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    started = time.monotonic()
    print(f"enqueueing {args.count} unit(s) at {args.rate}/s into {args.queue}",
          flush=True)

    with Redis.from_address(args.redis) as redis:
        for unit in range(1, args.count + 1):
            # Counted before it is pushed, never after: the exporter derives
            # in-flight work as enqueued - completed - depth, and incrementing
            # afterwards would make that briefly negative on every unit.
            redis.call("INCR", args.enqueued_key)
            redis.call("RPUSH", args.queue, f"{unit}|0")
            if unit % 100 == 0:
                print(f"  {unit}/{args.count} · {time.monotonic() - started:.1f}s",
                      flush=True)
            # Wall-clock schedule rather than a fixed sleep, so the offered
            # rate does not drift by however long each RPUSH took.
            target = started + unit * interval
            slack = target - time.monotonic()
            if slack > 0:
                time.sleep(slack)

    elapsed = time.monotonic() - started
    print(f"done · {args.count} unit(s) in {elapsed:.1f}s "
          f"({args.count / elapsed:.1f}/s offered)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
