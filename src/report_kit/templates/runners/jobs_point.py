#!/usr/bin/env python3
"""jobs_point.py — one measurement point for an ASYNCHRONOUS (queue/worker)
workload: enqueue a batch of work, then measure the system draining it.

    ./jobs_point.py --run jobs-n50 --n 50 --count 12000
    ./jobs_point.py --run x --n 4 --preflight-only
    ./jobs_point.py --reset-only          # between points
    ./jobs_point.py --set-freeze

This is a TEMPLATE. Copy it per project and edit the CONSTANTS block below.

The one thing that must not be simplified away: the producer runs
CONCURRENTLY with the watch loop, not before it. Filling the queue first and
then starting to watch measures a system draining a queue that is already
full — a different experiment with a different answer, and the arrival
pattern that produced the backlog is gone from the data.

The window opens when the producer starts and closes once every queue is
empty, the worker pool is back to zero, and the shared tier is at its floor
— all three held together, because any one of them alone reads "done" while
work is still in flight.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from report_kit import cluster, poll, prometheus, refs, reporting
from report_kit.cloud import aws
from report_kit.dbs import qdrant
from report_kit.constants import (ARROW, BAD, EXIT_CLEAN, EXIT_EXPORT_GAP,
                                  OK, WARN, die)
from report_kit.env import Env
from report_kit.clock import hms, utcnow
from report_kit.portforward import PortForwards, forward_spec
from report_kit.preflight import Preflight
from report_kit.proc import Background
from report_kit.text import fill
from report_kit.window import Window

# --------------------------------------------------------------------- CONSTANTS

# env.yaml keys holding the queue URLs this point watches. All must reach
# zero — visible *and* in-flight, see aws.sqs_depth.
QUEUES = ["work", "retry"]

# env.yaml key for the label selector matching worker nodes. The pool
# returning to zero is what says the work is finished and the cost stopped.
WORKER_POOL_KEY = "nodepool_workers"

# Always-on tiers the workers lean on: these scale up under load but must
# come back down for the window to close.
SHARED_TIERS = [
    {"deployment": "embeddings", "floor": 1},
]

# The close condition must hold this long. Queue purges and scale-in are
# eventually consistent — a queue reads zero while messages are still
# in-flight, a pool reads zero between two node claims.
HOLD_SECONDS = 90

FREEZE = ["deployment/worker", "deployment/embeddings"]

STEP = "15s"
# ------------------------------------------------------------------------------


def queue_depths(env: Env) -> dict[str, int]:
    return {label: aws.sqs_depth(env.need(f"sqs.{label}")) for label in QUEUES}


def worker_nodes(env: Env) -> dict[str, str]:
    return cluster.nodes_by_selector(env.need(WORKER_POOL_KEY))


def tier_replicas(env: Env) -> dict[str, int]:
    return {t["deployment"]: cluster.deployment_replicas(
        env.namespace_for(t["deployment"]), t["deployment"]) for t in SHARED_TIERS}


def system_state(env: Env) -> dict:
    """One read of everything the close condition depends on."""
    return {"depths": queue_depths(env), "nodes": worker_nodes(env),
            "tiers": tier_replicas(env)}


def is_idle(state: dict) -> bool:
    """Empty, at zero and at floor — all three. Any one of them alone reads
    "done" while work is still in flight somewhere else."""
    return (sum(state["depths"].values()) == 0
            and not state["nodes"]
            and all(state["tiers"][t["deployment"]] <= t["floor"]
                    for t in SHARED_TIERS))


def render_state(state: dict) -> str:
    depths = " ".join(f"{k}={v}" for k, v in sorted(state["depths"].items()))
    tiers = " ".join(f"{k}={v}" for k, v in sorted(state["tiers"].items()))
    return f"q[{depths}] nodes={len(state['nodes']):<3} {tiers}"


# --------------------------------------------------------------------- reset
# Between points, not a separate script: resetting needs exactly the constants
# above, and a second file holding its own copy of them is a second file to
# keep in sync. EDIT THIS for your system — each step is skipped when its
# env.yaml key is absent, so a project without an S3 inflow or a vector store
# just doesn't configure one.
#
# Order matters: stop the inflow first, then drop what is already queued, then
# clear the sink. Reversed, work still in flight refills what you just cleared.

def reset(env: Env, dry_run: bool = False) -> None:
    bucket, prefix = env.get("s3.bucket"), env.get("s3.prefix")
    if bucket:
        print(f"{ARROW} wiping s3://{bucket}/{prefix or ''}")
        if not dry_run:
            try:
                print(f"[{OK}] removed "
                      f"{aws.s3_rm_recursive(bucket, prefix or '')} object(s)")
            except RuntimeError as e:
                print(f"{WARN} s3 wipe failed, continuing: {e}")

    for label in QUEUES:
        url = env.get(f"sqs.{label}")
        if not url:
            continue
        print(f"{ARROW} purging queue {label}")
        if not dry_run:
            requested = aws.sqs_purge(url)
            print(f"[{OK}] purge "
                  f"{'requested' if requested else 'already in progress'}")

    url, collection = env.get("qdrant.url"), env.get("qdrant.collection")
    if url and collection:
        print(f"{ARROW} clearing collection {collection!r}")
        if not dry_run:
            try:
                ok = qdrant.delete_collection_if_nonempty(url, collection)
                print(f"[{OK if ok else BAD}] "
                      f"{'collection empty' if ok else 'delete failed'}")
            except RuntimeError as e:
                print(f"{WARN} qdrant unreachable, leaving it: {e}")


def wait_for_idle(env: Env, hold_seconds: float) -> bool:
    """Purges are asynchronous and scale-in is not instant — the reset is only
    finished when the system reads idle and stays that way."""
    state: dict = {}

    def idle() -> bool:
        state.update(system_state(env))
        return is_idle(state)

    print()
    print(f"{ARROW} waiting for idle (timeout {hms(env.max_wait_seconds)})")
    return poll.wait_until_stable(
        idle, hold_seconds=hold_seconds, poll_seconds=env.poll_seconds,
        max_wait_seconds=env.max_wait_seconds,
        on_tick=lambda ok, held: print(f"    {render_state(state)}"
                                       f"{f' · held {int(held)}s' if ok else ''}")
    ) is not None


def build_producer(env: Env, args, log_path: Path) -> tuple[list[str], dict]:
    """Whatever puts work in the queue — an uploader, a publisher, a seeding
    script. Named by env.yaml so this file stays project-independent."""
    values = {"run": args.run, "n": args.n, "count": args.count,
              "log": str(log_path)}
    try:
        cmd = [fill(part, values) for part in env.need("producer.command")]
        env_extra = {k: fill(str(v), values)
                     for k, v in (env.get("producer.env") or {}).items()}
    except KeyError as e:
        die(f"producer template references unknown placeholder '{e.args[0]}' — "
            f"jobs_point.py fills {sorted(values)}")
    return cmd, env_extra


def preflight(env: Env, freeze_file: Path) -> Preflight:
    """A point that starts dirty measures the previous point's leftovers."""
    pre = Preflight("preflight")

    try:
        depths = queue_depths(env)
        pre.check("queues empty", sum(depths.values()) == 0,
                  " ".join(f"{k}={v}" for k, v in sorted(depths.items())))
    except RuntimeError as e:
        pre.fail("queues unreadable", str(e))

    try:
        nodes = worker_nodes(env)
        pre.check("worker pool at zero", not nodes, f"{len(nodes)} node(s)")
    except RuntimeError as e:
        pre.fail("worker pool unreadable", str(e))

    for tier in SHARED_TIERS:
        name, floor = tier["deployment"], tier["floor"]
        try:
            replicas = cluster.deployment_replicas(env.namespace_for(name), name)
            pre.check(f"{name} at floor", replicas <= floor,
                      f"{replicas} replica(s), floor {floor}")
        except RuntimeError as e:
            pre.fail(f"{name} unreadable", str(e))

    down = prometheus.prom_targets_down(env.prom_url)
    pre.check("prometheus targets up", not down, ", ".join(down[:5]))

    images = reporting.frozen_images(env, FREEZE)
    for problem in reporting.check_freeze(freeze_file, images):
        pre.fail("image freeze", problem)
    pre.record(images=images, **reporting.git_facts())
    return pre


def watch(env: Env, pf: PortForwards, producer: Background) -> tuple[Window | None, dict]:
    """Watch the drain. Returns (window, observations).

    Tracks which nodes hold work, so a node vanishing while it had pods can
    be told apart from a node the autoscaler retired because it was already
    empty. Only the first kind threatens the measurement."""
    # The window opens with the producer, not with this loop: the few
    # milliseconds between them are the runner's, not the system's.
    started = producer.started_at or utcnow()
    seen_busy = False
    seen_nodes: dict[str, str] = {}
    node_workload: dict[str, int] = {}
    lost_with_work: list[str] = []
    peak_nodes = 0
    state: dict = {}

    print()
    print(f"{ARROW} watching the drain — hold {HOLD_SECONDS}s, "
          f"poll {env.poll_seconds}s, timeout {hms(env.max_wait_seconds)}")

    def drained() -> bool:
        nonlocal peak_nodes, seen_busy
        for notice in pf.ensure_alive():
            print(f"{WARN} {notice}")

        current = system_state(env)
        nodes = current["nodes"]

        pods = cluster.pods_by_node(env.namespace, env.need("worker_selector"))
        for name in nodes:
            node_workload[name] = max(node_workload.get(name, 0),
                                       len(pods.get(name, [])))
        for gone in set(seen_nodes) - set(nodes):
            if node_workload.get(gone, 0) > 0 and gone not in lost_with_work:
                lost_with_work.append(gone)
                print(f"{WARN} node {gone} disappeared while it had "
                      f"{node_workload[gone]} pod(s) on it")
        seen_nodes.clear()
        seen_nodes.update(nodes)
        peak_nodes = max(peak_nodes, len(nodes))

        state.update(current)
        state["producer"] = "running" if producer.running else "done"

        # An untouched system satisfies every clause of is_idle(): the queues
        # are empty, the pool is at zero, every shared tier is at its floor.
        # That is true at the *first* poll, before the producer has enqueued
        # anything — so a producer slower to start than HOLD_SECONDS (an
        # upload, a seeding pass, an image pull) closes a zero-length window
        # over a system that never did any work, and the point reads clean.
        # The window cannot close until the system has been seen busy once.
        idle = is_idle(current)
        seen_busy = seen_busy or not idle
        return seen_busy and idle

    def tick(ok: bool, held: float) -> None:
        held_note = f" · held {int(held)}s/{HOLD_SECONDS}s" if ok else ""
        print(f"    {render_state(state)} producer={state['producer']}{held_note}")

    settled_at = poll.wait_until_stable(
        drained, hold_seconds=HOLD_SECONDS, poll_seconds=env.poll_seconds,
        max_wait_seconds=env.max_wait_seconds, on_tick=tick)

    # Karpenter/EC2's own account of why nodes went away. Event TTL is short,
    # so silence here proves nothing — it can only confirm, never clear.
    events = cluster.interrupt_events(started)
    forced = [e for e in events if e.split(" · ")[0] in cluster.FORCED_REASONS]

    observations = {
        "peak_worker_nodes": peak_nodes,
        "nodes_lost_with_work": lost_with_work,
        "forced_interruptions": forced,
    }
    if settled_at is None:
        return None, observations
    return Window(started, settled_at), observations


def point_block(args, window: Window, facts: dict, observations: dict,
                guard_failures: list[str], producer_rc: int | None) -> str:
    start, end = window.rfc3339
    rows = [
        ("run", f"`{args.run}`"),
        ("profile", "jobs (async)"),
        ("concurrency", str(args.n)),
        ("units", str(args.count)),
        ("window", f"`{start}` .. `{end}` ({window.hms})"),
        ("commit", f"`{facts.get('commit', '?')[:12]}`"
                   f"{' (dirty)' if facts.get('dirty') else ''}"),
        ("peak worker nodes", str(observations["peak_worker_nodes"])),
        ("producer exit", "still running" if producer_rc is None else str(producer_rc)),
        ("guards", "clean" if not guard_failures else ", ".join(guard_failures)),
    ]
    if observations["nodes_lost_with_work"]:
        rows.append(("nodes lost with work",
                     ", ".join(observations["nodes_lost_with_work"])))
    if observations["forced_interruptions"]:
        rows.append(("forced interruptions",
                     str(len(observations["forced_interruptions"]))))
    return "\n".join(reporting.md_table(rows))


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="point id, e.g. jobs-n50")
    p.add_argument("--n", help="concurrency / parallelism under test")
    p.add_argument("--count", help="units of work to enqueue")
    p.add_argument("--env", type=Path)
    p.add_argument("--series", type=Path)
    p.add_argument("--guards", type=Path)
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--freeze-file", type=Path)
    p.add_argument("--step", default=STEP)
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--reset-only", action="store_true",
                   help="reset the system for the next point and exit")
    p.add_argument("--reset-after", action="store_true",
                   help="reset once this point's files are written")
    p.add_argument("--dry-run", action="store_true",
                   help="with --reset-only: print what would be reset")
    p.add_argument("--set-freeze", action="store_true")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    here = Path(__file__).resolve().parent
    env = Env(args.env or here / "env.yaml")
    out_dir = args.out_dir or here / "data"
    freeze_file = args.freeze_file or here / "image-freeze.json"

    forwards = [forward_spec(env, "prometheus"), forward_spec(env, "qdrant")]
    with PortForwards(forwards, enabled=not args.no_port_forward) as pf:
        if args.reset_only:
            reset(env, args.dry_run)
            if args.dry_run:
                return EXIT_CLEAN
            if not wait_for_idle(env, hold_seconds=min(HOLD_SECONDS, 30)):
                print(f"{BAD} still not idle — check the autoscaler by hand")
                return 4
            print(f"[{OK}] ready for the next point")
            return EXIT_CLEAN

        if args.set_freeze:
            images = reporting.frozen_images(env, FREEZE)
            freeze_file.parent.mkdir(parents=True, exist_ok=True)
            freeze_file.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
            print(f"[{OK}] freeze written to {freeze_file}")
            return EXIT_CLEAN

        pre = preflight(env, freeze_file)
        if args.preflight_only:
            return EXIT_CLEAN if pre.finish(exit_on_fail=False) else 1
        pre.finish()

        if not args.run or not args.n:
            die("--run and --n are required for a measured point")

        log_path = Path(out_dir) / f"{args.run}.producer.log"
        cmd, env_extra = build_producer(env, args, log_path)
        print()
        print(f"{ARROW} producer (background) · {' '.join(cmd)}")

        with Background(cmd, log_path, env_extra=env_extra, cwd=here) as producer:
            window, observations = watch(env, pf, producer)
            producer_rc = producer.poll()
            if producer_rc is None:
                print(f"{WARN} the queues drained while the producer is still "
                      f"running — it is slower than the workers, so this point "
                      f"measures the producer, not the system")
            elif producer_rc != 0:
                print(f"{BAD} producer exited {producer_rc} — tail:")
                for line in producer.tail():
                    print(f"         {line}")

        if window is None:
            print(f"{BAD} never drained within {hms(env.max_wait_seconds)} — "
                  f"nothing exported")
            return 4
        print()
        print(f"[{OK}] window {window}")

        pf.ensure_alive()
        series = refs.read_ref_file(args.series or here / "series.txt", 2)
        export = prometheus.export_range(
            env.prom_url, series, window, out_dir=out_dir, run_id=args.run,
            step=args.step, force=args.force)

        guards = refs.load_guards(args.guards or here / "guards.txt",
                                  {"n": args.n, "count": args.count or 0})
        print()
        # As of the drain, not now: the export sits between the two.
        guard_failures = prometheus.check_guards(env.prom_url, guards,
                                                 at=window.end)

    record = {
        "run": args.run,
        "profile": "jobs",
        "n": args.n,
        "count": args.count,
        "window": window.to_dict(),
        "producer_exit": producer_rc,
        "guard_failures": guard_failures,
        "export": {"path": str(export.path), "series": export.series,
                   "points": export.points, "empty_refs": export.empty},
        **observations,
        **pre.facts,
    }
    markdown = point_block(args, window, pre.facts, observations,
                           guard_failures, producer_rc)
    path = reporting.write_point(out_dir, args.run, markdown, record)
    print()
    print(f"[{OK}] {path}")

    if args.reset_after:
        print()
        reset(env)
        wait_for_idle(env, hold_seconds=min(HOLD_SECONDS, 30))

    if not export.ok:
        print(f"{WARN} export gaps: {', '.join(export.empty)} — the window is "
              f"recorded, re-export with tools/export_metrics.py before "
              f"retention drops it")
        return EXIT_EXPORT_GAP

    # A node lost while it held work invalidates the window; ordinary
    # consolidation of an idle node does not.
    doubts = observations["nodes_lost_with_work"] + observations["forced_interruptions"]
    if producer_rc not in (0, None):
        doubts.append(f"producer exited {producer_rc} — the work this point "
                      f"claims to have measured was not all enqueued")
    if producer_rc is None:
        doubts.append("producer outlived the drain — this point measures the "
                      "producer's speed, not the system's")
    return reporting.report_validity(doubts, guard_failures)


if __name__ == "__main__":
    sys.exit(main())
