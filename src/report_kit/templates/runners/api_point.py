#!/usr/bin/env python3
"""api_point.py — one measurement point for a SYNCHRONOUS (request/response)
workload: drive a fixed load at an API, then measure what it cost to serve.

    ./api_point.py --run api-r200 --rate 200 --duration 10m
    ./api_point.py --run x --rate 50 --preflight-only
    ./api_point.py --set-freeze

This is a TEMPLATE. Copy it per project and edit the CONSTANTS block below;
everything under it should need no changes. Addresses live in env.yaml, what
is under test lives here — that split is the point: env.yaml can differ
between clusters, this file may not differ between points of one sweep.

The window opens when the generator starts and closes once every gated
deployment is back at its floor and has stayed there — scale-in is caused by
the load and is billed to this point, so it belongs inside the window.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from report_kit import cluster, poll, prometheus, refs, reporting
from report_kit.constants import (ARROW, BAD, EXIT_CLEAN, EXIT_EXPORT_GAP,
                                  OK, WARN, die)
from report_kit.env import Env
from report_kit.clock import hms, utcnow
from report_kit.portforward import PortForwards, forward_spec
from report_kit.preflight import Preflight
from report_kit.proc import run_logged
from report_kit.text import fill
from report_kit.window import Window

# --------------------------------------------------------------------- CONSTANTS
# What must not move across the sweep. Changing anything here starts a new
# sweep; it does not produce another point of the current one.

# Deployments whose scaling this point measures. `floor` is the idle replica
# count the window must return to; `ceiling` is the configured max — reaching
# it means the point measured the limit, not the system.
GATES = [
    {"deployment": "api", "floor": 1, "ceiling": 10},
]

# The close condition must hold this long before the window is called closed.
# Shorter than one scaling decision interval and a momentary dip at floor
# closes the window early.
HOLD_SECONDS = 60

# Container images frozen for the sweep, as kind/name.
FREEZE = ["deployment/api"]

# Prometheus range-query resolution for the export.
STEP = "15s"
# ------------------------------------------------------------------------------


def build_generator(env: Env, args, log_path: Path) -> tuple[list[str], dict]:
    """The load generator is named by env.yaml, not by this file — k6, vegeta,
    locust or a script are all fine as long as the run is one process that
    exits when the load stops. {run} {rate} {duration} are filled in."""
    # {summary} lets a generator write its own structured result next to the
    # point. On a serving path that file usually holds the headline numbers —
    # what the caller was served and waited — which Prometheus does not see.
    values = {"run": args.run, "rate": args.rate, "duration": args.duration,
              "log": str(log_path),
              "summary": str(log_path.with_name(f"{args.run}.summary.json"))}
    command = env.need("generator.command")
    try:
        cmd = [fill(part, values) for part in command]
        env_extra = {k: fill(str(v), values)
                     for k, v in (env.get("generator.env") or {}).items()}
    except KeyError as e:
        die(f"generator template references unknown placeholder '{e.args[0]}' — "
            f"api_point.py fills {sorted(values)}")
    return cmd, env_extra


def preflight(env: Env, freeze_file: Path) -> Preflight:
    pre = Preflight("preflight")

    for gate in GATES:
        name, floor = gate["deployment"], gate["floor"]
        try:
            replicas = gate_replicas(env, name)
        except RuntimeError as e:
            pre.fail(f"{name} replicas unreadable", str(e))
            continue
        pre.check(f"{name} at floor", replicas <= floor,
                  f"{replicas} replica(s), floor {floor}")

    down = prometheus.prom_targets_down(env.prom_url)
    pre.check("prometheus targets up", not down, ", ".join(down[:5]))

    images = reporting.frozen_images(env, FREEZE)
    for problem in reporting.check_freeze(freeze_file, images):
        pre.fail("image freeze", problem)
    pre.record(images=images, **reporting.git_facts())
    return pre


def gate_replicas(env: Env, name: str) -> int:
    return cluster.deployment_replicas(env.namespace_for(name), name)


def wait_for_scale_in(env: Env) -> tuple[Window | None, dict]:
    """Closes when every gate is back at its floor and has held there.

    Returns (window, observations). A None window means it never settled —
    the point is a timeout, and nothing is exported: an unclosed window has
    no defined end to export."""
    floors = {g["deployment"]: g["floor"] for g in GATES}
    ceilings = {g["deployment"]: g["ceiling"] for g in GATES}
    peak = {name: 0 for name in floors}
    ceiling_hits: list[str] = []
    state: dict = {}
    started = utcnow()

    print()
    print(f"{ARROW} waiting for scale-in — hold {HOLD_SECONDS}s, "
          f"poll {env.poll_seconds}s, timeout {hms(env.max_wait_seconds)}")

    def at_floor() -> bool:
        current = {name: gate_replicas(env, name) for name in floors}
        for name, value in current.items():
            peak[name] = max(peak[name], value)
            if value >= ceilings[name] and name not in ceiling_hits:
                ceiling_hits.append(name)
                print(f"{WARN} {name} hit its ceiling ({ceilings[name]}) — this "
                      f"point measures the ceiling, not the system")
        state["current"] = current
        return all(current[n] <= floor for n, floor in floors.items())

    def tick(ok: bool, held: float) -> None:
        replicas = " ".join(f"{n}={v}" for n, v in sorted(state["current"].items()))
        held_note = f" · held {int(held)}s/{HOLD_SECONDS}s" if ok else ""
        print(f"    {replicas}{held_note}")

    settled_at = poll.wait_until_stable(
        at_floor, hold_seconds=HOLD_SECONDS, poll_seconds=env.poll_seconds,
        max_wait_seconds=env.max_wait_seconds, on_tick=tick)

    observations = {"peak_replicas": peak, "ceiling_hits": ceiling_hits}
    if settled_at is None:
        return None, observations
    # t_end is when it settled, not when the hold confirmed it: the buffer is
    # confirmation that nothing moved, not part of what the load caused.
    return Window(started, settled_at), observations


def point_block(args, window: Window, facts: dict, observations: dict,
                guard_failures: list[str], generator_rc: int) -> str:
    start, end = window.rfc3339
    rows = [
        ("run", f"`{args.run}`"),
        ("profile", "api (sync)"),
        ("rate", str(args.rate)),
        ("duration", args.duration),
        ("window", f"`{start}` .. `{end}` ({window.hms})"),
        ("commit", f"`{facts.get('commit', '?')[:12]}`"
                   f"{' (dirty)' if facts.get('dirty') else ''}"),
        ("peak replicas", ", ".join(f"{k}={v}" for k, v in
                                    sorted(observations["peak_replicas"].items()))),
        ("generator exit", str(generator_rc)),
        ("guards", "clean" if not guard_failures else ", ".join(guard_failures)),
    ]
    if observations["ceiling_hits"]:
        rows.append(("ceiling reached", ", ".join(observations["ceiling_hits"])))
    return "\n".join(reporting.md_table(rows))


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="point id, e.g. api-r200")
    p.add_argument("--rate", help="offered load, passed to the generator")
    p.add_argument("--duration", default="10m", help="generator run length")
    p.add_argument("--env", type=Path, help="env.yaml (default: next to this file)")
    p.add_argument("--series", type=Path, help="series.txt of ref|promql")
    p.add_argument("--guards", type=Path, help="guards.txt of ref|bound|promql")
    p.add_argument("--out-dir", type=Path, help="where the point's files land")
    p.add_argument("--freeze-file", type=Path, help="image-freeze.json")
    p.add_argument("--step", default=STEP, help=f"export step (default {STEP})")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-freeze", action="store_true",
                   help="record the current images as the freeze and exit")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing export for this run id")
    args = p.parse_args()

    here = Path(__file__).resolve().parent
    env = Env(args.env or here / "env.yaml")
    out_dir = args.out_dir or here / "data"
    freeze_file = args.freeze_file or here / "image-freeze.json"

    forwards = [forward_spec(env, "prometheus"), forward_spec(env, "api")]
    with PortForwards(forwards, enabled=not args.no_port_forward) as pf:
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

        if not args.run or not args.rate:
            die("--run and --rate are required for a measured point")

        log_path = Path(out_dir) / f"{args.run}.generator.log"
        cmd, env_extra = build_generator(env, args, log_path)
        print()
        print(f"{ARROW} generator · {' '.join(cmd)}")
        # cwd is the runner's directory: a generator command naming a script
        # next to it (load.js, a locustfile) must not depend on where the
        # operator happened to be standing when they invoked this.
        generated = run_logged(cmd, log_path, env_extra=env_extra, cwd=here)
        print(f"[{OK if generated.ok else BAD}] generator exit {generated.returncode} "
              f"· {generated.window.hms} · {log_path}")

        pf.ensure_alive()
        window, observations = wait_for_scale_in(env)
        if window is None:
            print(f"{BAD} never returned to floor within "
                  f"{hms(env.max_wait_seconds)} — nothing exported")
            return 4

        # The window starts with the load, not with the wait.
        window = Window(generated.window.start, window.end)
        print()
        print(f"[{OK}] window {window}")

        pf.ensure_alive()
        series = refs.read_ref_file(args.series or here / "series.txt", 2)
        export = prometheus.export_range(
            env.prom_url, series, window, out_dir=out_dir, run_id=args.run,
            step=args.step, force=args.force)

        guards = refs.load_guards(args.guards or here / "guards.txt",
                                  {"rate": args.rate})
        print()
        # As of the generator's end, not now: scale-in and the export sit
        # between the two, and a rate guard checked after them sees dead air.
        guard_failures = prometheus.check_guards(env.prom_url, guards,
                                                 at=generated.window.end)

    record = {
        "run": args.run,
        "profile": "api",
        "rate": args.rate,
        "duration": args.duration,
        "window": window.to_dict(),
        "generator_exit": generated.returncode,
        "generator_window": generated.window.to_dict(),
        "guard_failures": guard_failures,
        "export": {"path": str(export.path), "series": export.series,
                   "points": export.points, "empty_refs": export.empty},
        **observations,
        **pre.facts,
    }
    markdown = point_block(args, window, pre.facts, observations,
                           guard_failures, generated.returncode)
    path = reporting.write_point(out_dir, args.run, markdown, record)
    print()
    print(f"[{OK}] {path}")

    if not export.ok:
        print(f"{WARN} export gaps: {', '.join(export.empty)} — the window is "
              f"recorded, re-export with tools/export_metrics.py before "
              f"retention drops it")
        return EXIT_EXPORT_GAP

    # A generator that failed did not offer the load this point claims to have
    # measured, so the point is suspect even when every guard passes.
    doubts = ([] if generated.ok else
              [f"generator exited {generated.returncode} — offered load is not "
               f"what this point claims; see {log_path.name}"])
    return reporting.report_validity(doubts, guard_failures)


if __name__ == "__main__":
    sys.exit(main())
