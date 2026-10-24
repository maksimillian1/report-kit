#!/usr/bin/env python3
"""api_point.py — one measurement point for a SYNCHRONOUS (request/response)
workload: drive a fixed load at an API, then measure what it cost to serve.

    ./api_point.py --run api-r200 --rate 200 --duration 10m
    ./api_point.py --run x --rate 50 --preflight-only
    ./api_point.py --set-freeze

A TEMPLATE, copied into an execution's scripts/ by `report-kit new-point`.
What a point is run with — its settings, the hold, the image freeze, the
instant the guards are read as of — is the execution's execution.yaml, under
`point:`; a key it leaves out takes DEFAULTS below. What is read is its
metrics.yaml, and addresses are env.yaml. What stays in this file is what
only this profile knows, and the order of a run, top to bottom in main().
Everything after the window closes is `report-kit point finish`, run here in
the same process.

The window opens when the generator starts and closes once every deployment
in window_closes_when_back_to_idle is back at its idle_replicas and has
stayed there — scale-in is caused by the load and is billed to this point,
so it belongs inside the window.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from report_kit import finish, launch, point as points, watch
from report_kit.constants import die
from report_kit.execution_config import WINDOW, PointPlan, Setting

HERE = Path(__file__).resolve().parent

DEFAULTS = PointPlan(settings=(Setting("rate"), Setting("duration", "10m")),
                     load="foreground", hold_seconds=60, guards_at="load_end")

K6_THRESHOLD_BREACHED = 99


def client_summary(point: points.Point) -> dict:
    """What the caller saw, from k6's --summary-export, unrounded: on a
    serving path that is the measurement, and Prometheus the second opinion.
    metrics.yaml reads it as observations.client.*."""
    path = point.out_dir / f"{point.run}.summary.json"
    if not path.is_file():
        return {}
    metrics = json.loads(path.read_text()).get("metrics", {})
    reqs, duration = metrics.get("http_reqs", {}), metrics.get("http_req_duration", {})
    return {"served_per_second": reqs.get("rate", 0),
            "requests": reqs.get("count", 0),
            "p95_ms": duration.get("p(95)", 0),
            "failed_share": metrics.get("http_req_failed", {}).get("value", 0),
            "dropped_iterations": metrics.get("dropped_iterations", {}).get("count", 0)}


def doubts(load: launch.Load) -> list[str]:
    """A generator that failed did not offer the load this point claims, so
    the point is suspect even when every guard passes. k6 exits 99 when a
    threshold is breached — the system failing to serve, which is the
    finding, not a reason to doubt the load."""
    if load.exit_code in (0, K6_THRESHOLD_BREACHED):
        return []
    return [f"generator exited {load.exit_code} — offered load is not what "
            f"this point claims; see {load.log.name}"]


def main() -> int:
    point = points.open_point(HERE, "api", DEFAULTS, __doc__)
    if not point.execution.window_closes_when_back_to_idle:
        die(f"{point.execution.path} names no deployment under {WINDOW}, so "
            f"the window has nothing to wait for")
    with points.port_forwards(point, "prometheus", "api") as forwards:
        if point.args.set_freeze:
            return points.record_freeze(point)
        pre = points.preflight(point)
        if point.args.preflight_only:
            return points.verdict(pre)
        pre.finish()
        points.require_settings(point)

        load = launch.run_load(point, "generator")
        watched = watch.watch(
            point, lambda: {"tiers": points.tier_replicas(point)},
            lambda state: points.tiers_at_rest(point, state["tiers"]),
            start=load.started, keep_alive=forwards.ensure_alive)
        return finish.close_point(point, pre, watched, load,
                                  {"client": client_summary(point)}, doubts(load))


if __name__ == "__main__":
    sys.exit(main())
