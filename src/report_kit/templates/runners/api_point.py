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

import sys
from pathlib import Path

from report_kit import finish, launch, point as points, watch
from report_kit.constants import die
from report_kit.execution_config import WINDOW, PointPlan, Setting

HERE = Path(__file__).resolve().parent

DEFAULTS = PointPlan(settings=(Setting("rate"), Setting("duration", "10m")),
                     load="foreground", hold_seconds=60, guards_at="load_end")


def doubts(load: launch.Load) -> list[str]:
    """A generator that failed did not offer the load this point claims, so
    the point is suspect even when every guard passes. k6 exits 99 when a
    threshold is breached — the system failing, which is the finding — and
    which one a non-zero exit was is yours to decide in the copy."""
    if load.exit_code == 0:
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
        return finish.close_point(point, pre, watched, load, {}, doubts(load))


if __name__ == "__main__":
    sys.exit(main())
