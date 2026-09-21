#!/usr/bin/env python3
"""point.py — the smallest thing that measures an ASYNC point, built from report_kit.

    ./point.py --run n02-long --n 2 --count 1200
    ./point.py --reset                      # after a point that did not finish

An async point is not a load test with a different verb. Four things make it
its own profile:

1. **The producer runs while the watch loop watches.** Filling the queue first
   measures a system draining a backlog that already exists — a different
   experiment, and the arrival pattern that built the backlog is gone.
2. **The window closes on a composite condition, held.** Queues empty, worker
   pool at zero, shared tier back at its floor. Any one of them alone reads
   "done" while work is still in flight somewhere else — and all three
   together are also what an untouched system looks like, which is why the
   watch loop will not close on a system it has never seen busy.
3. **What proves the point is valid outlives the pods.** The worker pool
   scales to zero at the end of every run and takes its `/metrics` with it,
   so the counters that say whether every unit was actually completed live in
   Redis and are read back through the exporter.
4. **There are two windows, and they answer different questions.** The drain
   ends when the last unit is completed; the measured window runs on until
   the pool has gone away, because scale-in is caused by the load. A rate
   averaged over the second one is averaged over the tail of dead air too.

This is `runners/jobs_point.py` with the image freeze, git facts, node-loss
tracking, cost pass and exit-code contract removed — read this one to see the
shape, copy that one to actually run a sweep.

Requires the example cluster: see README.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_kit import cluster, poll, prometheus, refs, reporting, shell
from report_kit.clock import hms, utcnow
from report_kit.constants import ARROW, BAD, OK, WARN
from report_kit.env import Env
from report_kit.portforward import PortForwards, forward_spec
from report_kit.preflight import Preflight
from report_kit.proc import Background
from report_kit.text import fill
from report_kit.window import Window

from resp import Redis

HERE = Path(__file__).resolve().parent

# Above the ScaledObject's cooldownPeriod (20s), or the hold completes while
# the pool is still winding down and the window closes early. The two numbers
# are coupled; keda/scaledobject.yaml says so from its side.
HOLD_SECONDS = 30

# The scrape interval, not the kit's 15s default: a drain is a minute or two,
# and a queue-depth curve sampled six times is not a curve.
STEP = "5s"


def queue_depths(env: Env, redis: Redis) -> dict[str, int]:
    """What is waiting. Read straight from the queue rather than from
    Prometheus — a close condition should not run a scrape interval behind
    the thing it is closing on."""
    return {label: int(redis.call("LLEN", key))
            for label, key in env.need("queues").items()}


def counters(env: Env, redis: Redis) -> dict[str, int]:
    keys = env.need("counters")
    out = {}
    for label, key in keys.items():
        raw = redis.call("GET", key)
        out[label] = int(raw) if raw else 0
    return out


def worker_pods(env: Env) -> list[str]:
    """Running worker pods, flattened out of pods_by_node(). One node here, so
    the grouping buys nothing — but it is the same call the real profile makes
    against a node pool, and it is what makes "the pool is at zero" a fact
    about pods rather than about the deployment's `spec.replicas`."""
    by_node = cluster.pods_by_node(env.namespace, env.need("worker.selector"))
    return sorted(pod for pods in by_node.values() for pod in pods)


def tier_replicas(env: Env) -> dict[str, int]:
    return {tier["deployment"]: cluster.deployment_replicas(
        env.namespace_for(tier["deployment"]), tier["deployment"])
        for tier in env.need("tiers")}


def system_state(env: Env, redis: Redis) -> dict:
    """One read of everything the close condition depends on, plus the
    counters, which it deliberately does not — see is_idle()."""
    counts = counters(env, redis)
    return {"depths": queue_depths(env, redis),
            "workers": worker_pods(env),
            "tiers": tier_replicas(env),
            "outstanding": counts["enqueued"] - counts["completed"],
            "counters": counts}


def is_idle(env: Env, state: dict) -> bool:
    """Empty, at zero, and at floor — all three.

    `outstanding` is not in here, and that is a choice rather than an
    oversight. It is the exact count of units enqueued and not yet completed,
    so closing on it would be tighter than closing on these three. It is also
    the one number that never comes back to zero when a worker is killed
    holding a unit: closing on it would hang until the timeout on exactly the
    point whose record you most want. So the window closes on three conditions
    that are always reachable, and conservation is a guard (G1) that fails the
    point instead of losing it.
    """
    return (sum(state["depths"].values()) == 0
            and not state["workers"]
            and all(state["tiers"][tier["deployment"]] <= tier["floor"]
                    for tier in env.need("tiers")))


def render_state(state: dict) -> str:
    depths = " ".join(f"{k}={v}" for k, v in sorted(state["depths"].items()))
    tiers = " ".join(f"{k}={v}" for k, v in sorted(state["tiers"].items()))
    return (f"q[{depths}] workers={len(state['workers']):<2} {tiers} "
            f"outstanding={state['outstanding']:<4}")


def reset(env: Env, redis: Redis) -> None:
    """Drop the queues and the counters. Order matters in the real profile —
    stop the inflow, then clear what is queued — but here the producer is a
    process the runner owns, so it is already gone."""
    keys = list(env.need("queues").values()) + list(env.need("counters").values())
    removed = int(redis.call("DEL", *keys))
    print(f"[{OK}] cleared {removed} key(s): {', '.join(keys)}")


def watch(env: Env, pf: PortForwards, redis: Redis, producer: Background):
    """Watch the drain, from the instant the producer started."""
    started = producer.started_at
    state: dict = {}
    peak_workers = 0
    drained_at = None

    print()
    print(f"{ARROW} watching the drain — hold {HOLD_SECONDS}s, "
          f"poll {env.poll_seconds}s, timeout {hms(env.max_wait_seconds)}")

    def drained() -> bool:
        nonlocal peak_workers, drained_at
        for notice in pf.ensure_alive():
            print(f"{WARN} {notice}")
        state.update(system_state(env, redis))
        state["producer"] = "running" if producer.running else "done"
        peak_workers = max(peak_workers, len(state["workers"]))

        arrived = state["counters"]["enqueued"] > 0
        if arrived and state["outstanding"] == 0 and drained_at is None:
            drained_at = utcnow()
        # An untouched system satisfies every clause of is_idle(): empty
        # queues, no workers, tier at its floor. That is true at the first
        # poll, before the producer has pushed anything — so a producer
        # slower to start than HOLD_SECONDS would close a window over a
        # system that never did any work, and the point would look clean.
        # This clause is why `poll.wait_until_stable` takes a closure.
        return arrived and is_idle(env, state)

    settled = poll.wait_until_stable(
        drained, hold_seconds=HOLD_SECONDS, poll_seconds=env.poll_seconds,
        max_wait_seconds=env.max_wait_seconds,
        on_tick=lambda ok, held: print(
            f"    {render_state(state)} producer={state['producer']}"
            f"{f' · held {int(held)}s/{HOLD_SECONDS}s' if ok else ''}"))

    observations = {"peak_worker_pods": peak_workers,
                    "final_counters": state.get("counters", {}),
                    "units_outstanding_at_close": state.get("outstanding")}
    # Two windows, and they answer different questions. The drain window ends
    # when the last unit was completed; the measurement window runs on until
    # the pool has actually gone away, because scale-in is caused by the load
    # and is billed to the point that caused it. Averaging a rate over the
    # second one averages it over the tail of dead air as well — the same
    # mistake the api example makes visible with --settle-on.
    drain = Window(started, drained_at) if drained_at else None
    return (Window(started, settled) if settled else None), drain, observations


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default="demo")
    p.add_argument("--n", type=int, default=2, help="worker pool ceiling")
    p.add_argument("--count", type=int, default=400, help="units to enqueue")
    p.add_argument("--rate", default="40", help="units per second offered")
    p.add_argument("--reset", action="store_true",
                   help="clear the queues and counters, then exit")
    args = p.parse_args()

    env = Env(HERE / "env.yaml")
    out_dir = HERE / "data"

    with PortForwards([forward_spec(env, "prometheus"),
                       forward_spec(env, "redis")]) as pf, \
            Redis.from_address(env.need("redis.address")) as redis:
        if args.reset:
            reset(env, redis)
            return 0

        # 0. the axis — the pool ceiling this point is about. Set before
        #    preflight so the run and the record cannot disagree about it.
        shell.sh(["kubectl", "-n", env.namespace, "patch", "scaledobject",
                  env.need("worker.scaledobject"), "--type=merge",
                  "-p", f'{{"spec":{{"maxReplicaCount":{args.n}}}}}'])

        # 1. preflight — is the system in the state this point assumes?
        pre = Preflight()
        state = system_state(env, redis)
        dirty = sum(state["depths"].values())
        pre.check("queues empty", dirty == 0,
                  " ".join(f"{k}={v}" for k, v in sorted(state["depths"].items()))
                  + (" — run --reset" if dirty else ""))
        pre.check("worker pool at zero", not state["workers"],
                  f"{len(state['workers'])} pod(s)")
        for tier in env.need("tiers"):
            name = tier["deployment"]
            pre.check(f"{name} at floor",
                      state["tiers"][name] <= tier["floor"],
                      f"{state['tiers'][name]} replica(s), floor {tier['floor']}")
        down = prometheus.prom_targets_down(env.prom_url)
        pre.check("prometheus targets up", not down, ", ".join(down))
        pre.finish()

        # The counters are this point's accumulators, not the system's state:
        # arming them is part of starting the run, and G1/G2 are meaningless
        # against a total carried over from the point before.
        print(f"{ARROW} arming counters")
        reset(env, redis)

        # 2. producer + watch, together. This is the profile.
        log_path = out_dir / f"{args.run}.producer.log"
        cmd = [fill(part, {"run": args.run, "n": args.n, "count": args.count,
                           "rate": args.rate, "log": str(log_path)})
               for part in env.need("producer.command")]
        print()
        print(f"{ARROW} producer (background) · {' '.join(cmd)}")
        with Background(cmd, log_path, cwd=HERE) as producer:
            window, drain, observations = watch(env, pf, redis, producer)
            producer_rc = producer.poll()
        if producer_rc is None:
            print(f"{WARN} the queues drained while the producer was still "
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

        # 3. export — the series, for this window
        pf.ensure_alive()
        export = prometheus.export_range(
            env.prom_url, refs.read_ref_file(HERE / "series.txt", 2), window,
            out_dir=out_dir, run_id=args.run, step=STEP, force=True)

        # 4. guards — as of the close, not now: the export sits between them
        print()
        failures = prometheus.check_guards(
            env.prom_url,
            refs.load_guards(HERE / "guards.txt", {"count": args.count}),
            at=window.end)

    # 5. record. The headline of an async point is a duration and a rate the
    #    system sustained, both derived from the window rather than reported
    #    by any one component.
    completed = observations["final_counters"].get("completed", 0)
    drained_per_second = (round(completed / drain.seconds, 2)
                          if drain and drain.seconds else None)
    record = {"run": args.run, "profile": "jobs", "n": args.n,
              "count": args.count, "offered_rate": args.rate,
              "window": window.to_dict(),
              "drain_window": drain.to_dict() if drain else None,
              "guard_failures": failures,
              "empty_refs": export.empty, "producer_exit": producer_rc,
              "drained_per_second": drained_per_second,
              **observations}
    markdown = "\n".join(reporting.md_table([
        ("run", f"`{args.run}`"),
        ("profile", "jobs (async)"),
        ("pool ceiling", str(args.n)),
        ("units", str(args.count)),
        ("window", f"{window} "),
        ("drain", f"{drain.hms} " if drain else "never"),
        ("peak worker pods", str(observations["peak_worker_pods"])),
        ("completed", str(completed)),
        ("drained/s", str(drained_per_second)),
        ("series exported", f"{export.series} ({export.points} points)"),
        ("guards", "clean" if not failures else ", ".join(failures)),
    ]))
    print()
    print(f"[{OK}] {reporting.write_point(out_dir, args.run, markdown, record)}")

    doubts = [] if producer_rc == 0 else [
        "producer outlived the drain — this point measures the producer's "
        "speed, not the system's" if producer_rc is None
        else f"producer exited {producer_rc} — not every unit this point "
             f"claims to have measured was enqueued"]
    return reporting.report_validity(doubts, failures)


if __name__ == "__main__":
    sys.exit(main())
