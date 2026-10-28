#!/usr/bin/env python3
"""jobs_point.py — one measurement point for an ASYNCHRONOUS (queue/worker)
workload: enqueue a batch of work, then measure the system draining it.

    ./jobs_point.py --run jobs-n50 --n 50 --count 12000
    ./jobs_point.py --run x --n 4 --preflight-only
    ./jobs_point.py --reset-only          # between points
    ./jobs_point.py --set-freeze

A TEMPLATE, copied into an execution's scripts/ by `report-kit new-point`.
What a point is run with — its settings, the hold, the image freeze, the
instant the guards are read as of — is the execution's execution.yaml, under
`point:`; a key it leaves out takes DEFAULTS below. What is read is its
metrics.yaml, and addresses are env.yaml: every queue under `sqs:` has to
drain, `nodepool_workers` selects the worker pool. What stays in this file is
what only a queue/worker system knows — how its state is read, what a reset
clears, which losses put a point in doubt — and the order of a run, top to
bottom in main(). Everything after the window closes is `report-kit point
finish`, run here in the same process.

The one thing that must not be simplified away: the producer runs
CONCURRENTLY with the watch loop, not before it. Filling the queue first and
then starting to watch measures a system draining a queue that is already
full — a different experiment with a different answer, and the arrival
pattern that produced the backlog is gone from the data.

The window opens when the producer starts and closes once every queue is
empty, the worker pool is back to zero, and every deployment in
window_closes_when_back_to_idle is back at its idle_replicas — all three
held together, because any one of them alone reads "done" while work is
still in flight. The instant the queues first read empty is kept as the
event `queues_empty`, for a D ref to measure the drain from.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from report_kit import cluster, finish, launch, point as points, watch
from report_kit.clock import utcnow
from report_kit.cloud import aws
from report_kit.constants import ARROW, BAD, EXIT_CLEAN, EXIT_TIMEOUT, OK, WARN
from report_kit.dbs import qdrant
from report_kit.env import Env
from report_kit.execution_config import PointPlan, Setting
from report_kit.preflight import Preflight

HERE = Path(__file__).resolve().parent

# The hold outlasts eventual consistency: a queue reads zero while messages
# are still in flight, a pool reads zero between two node claims.
DEFAULTS = PointPlan(settings=(Setting("n"), Setting("count")),
                     load="background", hold_seconds=90, guards_at="window_end")
RESET_HOLD_SECONDS = 30


def queue_depths(env: Env) -> dict[str, int]:
    """Visible and in-flight, for every queue env.yaml lists — see aws.sqs_depth."""
    return {label: aws.sqs_depth(url) for label, url in env.need("sqs").items()}


def worker_nodes(env: Env) -> dict[str, str]:
    return cluster.nodes_by_selector(env.need("nodepool_workers"))


def node_losses(env: Env) -> Callable[[dict[str, str]], list[str]]:
    """Tells a node that vanished while it had pods on it from one the
    autoscaler retired because it was already empty. Only the first kind
    threatens the measurement."""
    seen: dict[str, str] = {}
    workload: dict[str, int] = {}
    lost: list[str] = []

    def lost_with_work(nodes: dict[str, str]) -> list[str]:
        pods = cluster.pods_by_node(env.namespace, env.need("worker_selector"))
        for name in nodes:
            workload[name] = max(workload.get(name, 0), len(pods.get(name, [])))
        for gone in sorted(set(seen) - set(nodes)):
            if workload.get(gone, 0) > 0 and gone not in lost:
                lost.append(gone)
                print(f"{WARN} node {gone} disappeared while it had "
                      f"{workload[gone]} pod(s) on it")
        seen.clear()
        seen.update(nodes)
        return list(lost)

    return lost_with_work


def system_state(point: points.Point,
                 losses: Callable[[dict[str, str]], list[str]] | None = None) -> dict:
    """One read of everything the close condition depends on."""
    nodes = worker_nodes(point.env)
    state = {"queues": queue_depths(point.env), "worker_nodes": len(nodes),
             "tiers": points.tier_replicas(point)}
    if losses:
        state["nodes_lost_with_work"] = losses(nodes)
    return state


def queues_empty(state: dict) -> bool:
    return sum(state["queues"].values()) == 0


def at_rest(point: points.Point, state: dict) -> bool:
    """Empty, at zero and back at idle — all three."""
    return (queues_empty(state) and state["worker_nodes"] == 0
            and points.tiers_at_rest(point, state["tiers"]))


def system_checks(point: points.Point, pre: Preflight) -> None:
    """A point that starts dirty measures the previous point's leftovers."""
    try:
        depths = queue_depths(point.env)
        pre.check("queues empty", sum(depths.values()) == 0,
                  " ".join(f"{k}={v}" for k, v in sorted(depths.items())))
    except RuntimeError as exc:
        pre.fail("queues unreadable", str(exc))
    try:
        nodes = worker_nodes(point.env)
        pre.check("worker pool at zero", not nodes, f"{len(nodes)} node(s)")
    except RuntimeError as exc:
        pre.fail("worker pool unreadable", str(exc))


def reset(env: Env, dry_run: bool = False) -> None:
    """EDIT THIS for your system — each step is skipped when its env.yaml key
    is absent. Order matters: stop the inflow, drop what is queued, clear the
    sink. Reversed, work still in flight refills what was just cleared."""
    bucket, prefix = env.get("s3.bucket"), env.get("s3.prefix")
    if bucket:
        print(f"{ARROW} wiping s3://{bucket}/{prefix or ''}")
        if not dry_run:
            try:
                print(f"[{OK}] removed {aws.s3_rm_recursive(bucket, prefix or '')} object(s)")
            except RuntimeError as exc:
                print(f"{WARN} s3 wipe failed, continuing: {exc}")
    for label, url in (env.get("sqs") or {}).items():
        print(f"{ARROW} purging queue {label}")
        if not dry_run:
            requested = aws.sqs_purge(url)
            print(f"[{OK}] purge {'requested' if requested else 'already in progress'}")
    url, collection = env.get("qdrant.url"), env.get("qdrant.collection")
    if url and collection:
        print(f"{ARROW} clearing collection {collection!r}")
        if not dry_run:
            try:
                emptied = qdrant.delete_collection_if_nonempty(url, collection)
                print(f"[{OK if emptied else BAD}] "
                      f"{'collection empty' if emptied else 'delete failed'}")
            except RuntimeError as exc:
                print(f"{WARN} qdrant unreachable, leaving it: {exc}")


def reset_between_points(point: points.Point) -> int:
    """Purges are asynchronous and scale-in is not instant — the reset is only
    finished when the system reads idle and stays that way."""
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


def forced_interruptions(since) -> list[str]:
    """Karpenter's and EC2's own account of why nodes went away. Event TTL is
    short, so silence here proves nothing — it can only confirm."""
    return [event for event in cluster.interrupt_events(since)
            if event.split(" · ")[0] in cluster.FORCED_REASONS]


def doubts(load: launch.Load, observations: dict) -> list[str]:
    """A node lost while it held work invalidates the window; ordinary
    consolidation of an idle node does not."""
    found = [f"node {name} lost while it held work"
             for name in observations["nodes_lost_with_work"]]
    found += observations["forced_interruptions"]
    if load.exit_code is None:
        found.append("producer outlived the drain — this point measures the "
                     "producer's speed, not the system's")
    elif load.exit_code != 0:
        found.append(f"producer exited {load.exit_code} — the work this point "
                     f"claims to have measured was not all enqueued")
    return found


def reset_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reset-only", action="store_true",
                        help="reset the system for the next point and exit")
    parser.add_argument("--reset-after", action="store_true",
                        help="reset once this point's files are written")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --reset-only: print what would be reset")


def main() -> int:
    point = points.open_point(HERE, "jobs", DEFAULTS, __doc__, flags=reset_flags)
    with points.port_forwards(point, "prometheus", "qdrant") as forwards:
        if point.args.reset_only:
            return reset_between_points(point)
        if point.args.set_freeze:
            return points.record_freeze(point)
        pre = points.preflight(point, lambda pre: system_checks(point, pre))
        if point.args.preflight_only:
            return points.verdict(pre)
        pre.finish()
        points.require_settings(point)

        losses = node_losses(point.env)
        with launch.start_load(point, "producer") as producer:
            watched = watch.watch(
                point, lambda: system_state(point, losses),
                lambda state: at_rest(point, state), start=producer.started_at,
                events={"queues_empty": queues_empty}, keep_alive=forwards.ensure_alive)
            load = launch.load_of(producer)
        observations = {
            "nodes_lost_with_work": watched.state.get("nodes_lost_with_work", []),
            "forced_interruptions": forced_interruptions(producer.started_at)}
        code = finish.close_point(point, pre, watched, load, observations,
                                  doubts(load, observations))
        if point.args.reset_after:
            print()
            reset_between_points(point)
    return code


if __name__ == "__main__":
    sys.exit(main())
