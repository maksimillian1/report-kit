#!/usr/bin/env python3
"""jobs_point.py — one measurement point for an ASYNCHRONOUS (queue/worker)
workload: enqueue a batch of work, then measure the system draining it.

    ./jobs_point.py --run n02-long --n 2 --count 1200
    ./jobs_point.py --run x --n 4 --count 1 --preflight-only
    ./jobs_point.py --reset-only          # after a point that did not finish
    ./jobs_point.py --set-freeze

Copied by `report-kit new-point --profile jobs` and edited for this example:
the queues are Redis lists rather than SQS, the pool that has to reach zero is
the worker pods KEDA scales rather than a node pool, and the axis — the pool
ceiling — is patched into the ScaledObject at the start of every point. What a
point is run with is ../execution.yaml under `point:`, what is read is
../metrics.yaml, and addresses are env.yaml. Everything after the window
closes is `report-kit point finish`, run here in the same process.

The one thing that must not be simplified away: the producer runs
CONCURRENTLY with the watch loop, not before it. Filling the queue first and
then starting to watch measures a system draining a queue that is already
full — a different experiment with a different answer, and the arrival
pattern that produced the backlog is gone from the data.

The window opens when the producer starts and closes once both queues are
empty, the worker pool is back to zero, and the shared tier is back at its
idle_replicas — all three held together, because any one of them alone reads
"done" while work is still in flight. Two instants are kept as events:
`queues_empty`, and `drained`, the first poll at which every unit enqueued
has been completed — the end of the drain D8 measures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_kit import cluster, finish, launch, point as points, shell, watch
from report_kit.clock import utcnow
from report_kit.constants import ARROW, BAD, EXIT_CLEAN, EXIT_TIMEOUT, OK
from report_kit.env import Env
from report_kit.execution_config import PointPlan, Setting
from report_kit.preflight import Preflight

from resp import Redis

HERE = Path(__file__).resolve().parent

DEFAULTS = PointPlan(settings=(Setting("n"), Setting("count")),
                     load="background", hold_seconds=90, guards_at="window_end")
RESET_HOLD_SECONDS = 30


def redis(env: Env) -> Redis:
    """A connection per read: the port-forward under it can be restarted
    between two polls, and a socket opened before that is dead after it."""
    return Redis.from_address(env.need("redis.address"))


def queue_depths(env: Env) -> dict[str, int]:
    """What is waiting, read straight from the queue rather than from
    Prometheus — a close condition should not run a scrape interval behind
    the thing it is closing on."""
    with redis(env) as r:
        return {label: int(r.call("LLEN", key)) for label, key in env.need("queues").items()}


def counters(env: Env) -> dict[str, int]:
    with redis(env) as r:
        return {label: int(r.call("GET", key) or 0)
                for label, key in env.need("counters").items()}


def worker_pods(env: Env) -> int:
    """Running worker pods. The same read the real profile makes against a node
    pool, and what makes "the pool is at zero" a fact about pods rather than
    about the deployment's spec.replicas."""
    by_node = cluster.pods_by_node(env.namespace, env.need("worker.selector"))
    return sum(len(pods) for pods in by_node.values())


def system_state(point: points.Point) -> dict:
    """One read of everything the close condition depends on, plus the
    counters, which it deliberately does not — see at_rest()."""
    counts = counters(point.env)
    return {"queues": queue_depths(point.env), "workers": worker_pods(point.env),
            "tiers": points.tier_replicas(point),
            "outstanding": counts["enqueued"] - counts["completed"], "counters": counts}


def queues_empty(state: dict) -> bool:
    return sum(state["queues"].values()) == 0


def drained(state: dict) -> bool:
    return state["counters"]["enqueued"] > 0 and state["outstanding"] == 0


def at_rest(point: points.Point, state: dict) -> bool:
    """Empty, at zero and back at idle — all three. `outstanding` is not in
    here: it never returns to zero when a worker is killed holding a unit, so
    closing on it would hang on exactly the point whose record matters most.
    Conservation is a guard (G1) that fails the point instead of losing it."""
    return (queues_empty(state) and state["workers"] == 0
            and points.tiers_at_rest(point, state["tiers"]))


def system_checks(point: points.Point, pre: Preflight) -> None:
    """A point that starts dirty measures the previous point's leftovers."""
    try:
        depths = queue_depths(point.env)
        pre.check("queues empty", sum(depths.values()) == 0,
                  " ".join(f"{k}={v}" for k, v in sorted(depths.items())))
    except (OSError, RuntimeError) as exc:
        pre.fail("queues unreadable", str(exc))
    try:
        pods = worker_pods(point.env)
        pre.check("worker pool at zero", pods == 0, f"{pods} pod(s)")
    except RuntimeError as exc:
        pre.fail("worker pool unreadable", str(exc))


def set_ceiling(point: points.Point) -> None:
    """The axis, patched into the ScaledObject before the load, so the run and
    the record cannot disagree about what was measured."""
    n = point.settings["n"]
    shell.sh(["kubectl", "-n", point.env.namespace, "patch", "scaledobject",
              point.env.need("worker.scaledobject"), "--type=merge",
              "-p", f'{{"spec":{{"maxReplicaCount":{n}}}}}'])
    print(f"[{OK}] worker pool ceiling set to {n}")


def reset(env: Env, dry_run: bool = False) -> None:
    """Drop the queues and the counters. The counters are a point's
    accumulators: G1 and G2 are meaningless against a total carried over from
    the point before, so this also runs at the start of every point."""
    keys = list(env.need("queues").values()) + list(env.need("counters").values())
    print(f"{ARROW} clearing {', '.join(keys)}")
    if not dry_run:
        with redis(env) as r:
            print(f"[{OK}] cleared {int(r.call('DEL', *keys))} key(s)")


def reset_between_points(point: points.Point) -> int:
    """Scale-in is not instant — the reset is only finished when the system
    reads idle and stays that way."""
    reset(point.env, point.args.dry_run)
    if point.args.dry_run:
        return EXIT_CLEAN
    idle = watch.watch(point, lambda: system_state(point),
                       lambda state: at_rest(point, state), start=utcnow(),
                       require_busy=False, label="the reset",
                       hold_seconds=min(point.plan.hold_seconds, RESET_HOLD_SECONDS))
    if idle.window is None:
        print(f"{BAD} still not idle — check the autoscaler by hand")
        return EXIT_TIMEOUT
    print(f"[{OK}] ready for the next point")
    return EXIT_CLEAN


def doubts(load: launch.Load) -> list[str]:
    if load.exit_code is None:
        return ["producer outlived the drain — this point measures the "
                "producer's speed, not the system's"]
    if load.exit_code != 0:
        return [f"producer exited {load.exit_code} — the work this point "
                f"claims to have measured was not all enqueued"]
    return []


def reset_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reset-only", action="store_true",
                        help="clear the queues and counters, wait for idle, and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --reset-only: print what would be cleared")


def main() -> int:
    point = points.open_point(HERE, "jobs", DEFAULTS, __doc__, flags=reset_flags)
    with points.port_forwards(point, "prometheus", "redis") as forwards:
        if point.args.reset_only:
            return reset_between_points(point)
        if point.args.set_freeze:
            return points.record_freeze(point)
        pre = points.preflight(point, lambda pre: system_checks(point, pre))
        if point.args.preflight_only:
            return points.verdict(pre)
        pre.finish()
        points.require_settings(point)

        set_ceiling(point)
        reset(point.env)
        with launch.start_load(point, "producer") as producer:
            watched = watch.watch(
                point, lambda: system_state(point), lambda state: at_rest(point, state),
                start=producer.started_at,
                events={"queues_empty": queues_empty, "drained": drained},
                keep_alive=forwards.ensure_alive)
            load = launch.load_of(producer)
        observations = {"final_counters": watched.state.get("counters", {}),
                        "units_outstanding_at_close": watched.state.get("outstanding")}
        return finish.close_point(point, pre, watched, load, observations, doubts(load))


if __name__ == "__main__":
    sys.exit(main())
