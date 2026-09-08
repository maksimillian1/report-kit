#!/usr/bin/env python3
"""point.py — the smallest thing that measures a point, built from report_kit.

    ./point.py --run demo-r20 --rate 20 --duration 30s

Every step of the lifecycle is here, in order, in about seventy lines. This
is what `runners/api_point.py` looks like with the image freeze, git facts,
ceiling tracking, exit-code contract and point-block rendering removed — read
this one to see the shape, copy that one to actually run a sweep.

Requires the example cluster: see README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from report_kit import cluster, poll, prometheus, refs, reporting
from report_kit.constants import ARROW, BAD, OK
from report_kit.env import Env
from report_kit.portforward import PortForwards, forward_spec
from report_kit.preflight import Preflight
from report_kit.proc import run_logged
from report_kit.text import fill
from report_kit.window import Window

def read_k6_summary(path: Path) -> dict:
    """The headline of a serving point: offered vs served, and what the caller
    waited. k6's shape, so it lives here rather than in the kit."""
    if not path.is_file():
        return {}
    metrics = json.loads(path.read_text()).get("metrics", {})
    reqs, duration = metrics.get("http_reqs", {}), metrics.get("http_req_duration", {})
    return {"served_per_second": round(reqs.get("rate", 0), 2),
            "requests": reqs.get("count", 0),
            "p95_ms": round(duration.get("p(95)", 0), 1),
            "failed_share": round(metrics.get("http_req_failed", {}).get("value", 0), 4)}


HERE = Path(__file__).resolve().parent
DEPLOYMENT = "mock-api"
FLOOR = 1
HOLD_SECONDS = 20


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", default="demo")
    p.add_argument("--rate", default="20", help="requests per second")
    p.add_argument("--duration", default="30s")
    args = p.parse_args()

    env = Env(HERE / "env.yaml")
    out_dir = HERE / "data"

    with PortForwards([forward_spec(env, "prometheus"),
                       forward_spec(env, "api")]) as pf:
        # 1. preflight — is the system in the state this point assumes?
        pre = Preflight()
        replicas = cluster.deployment_replicas(env.namespace, DEPLOYMENT)
        pre.check(f"{DEPLOYMENT} at floor", replicas <= FLOOR, f"{replicas} replica(s)")
        down = prometheus.prom_targets_down(env.prom_url)
        pre.check("prometheus targets up", not down, ", ".join(down))
        pre.finish()

        # 2. load — a subprocess, timed
        summary_path = out_dir / f"{args.run}.summary.json"
        cmd = [fill(part, {"rate": args.rate, "duration": args.duration,
                           "run": args.run, "log": str(out_dir),
                           "summary": str(summary_path)})
               for part in env.need("generator.command")]
        print()
        print(f"{ARROW} generator · {' '.join(cmd)}")
        generated = run_logged(cmd, out_dir / f"{args.run}.generator.log", cwd=HERE)
        print(f"[{OK if generated.ok else BAD}] generator exit "
              f"{generated.returncode} · {generated.window.hms}")

        # 3. watch — until the system has been back at its floor for a while,
        #    not merely touched it once
        print()
        print(f"{ARROW} waiting for scale-in (hold {HOLD_SECONDS}s)")
        settled = poll.wait_until_stable(
            lambda: cluster.deployment_replicas(env.namespace, DEPLOYMENT) <= FLOOR,
            hold_seconds=HOLD_SECONDS, poll_seconds=env.poll_seconds,
            max_wait_seconds=env.max_wait_seconds,
            on_tick=lambda ok, held: print(
                f"    replicas={cluster.deployment_replicas(env.namespace, DEPLOYMENT)}"
                f"{f' · held {int(held)}s' if ok else ''}"))
        if settled is None:
            print(f"{BAD} never returned to floor — nothing exported")
            return 4

        window = Window(generated.window.start, settled)
        print()
        print(f"[{OK}] window {window}")

        # 4. export — the series, for this window
        pf.ensure_alive()
        export = prometheus.export_range(
            env.prom_url, refs.read_ref_file(HERE / "series.txt", 2), window,
            out_dir=out_dir, run_id=args.run, force=True)

        # 5. guards — as of when the load stopped, not now
        print()
        failures = prometheus.check_guards(
            env.prom_url, refs.load_guards(HERE / "guards.txt", {"rate": args.rate}),
            at=generated.window.end)

    # 6. record. The client-side numbers come from the generator's own summary,
    #    not from Prometheus: on a serving path what the caller saw is the
    #    measurement, and the server's view is the second opinion.
    record = {"run": args.run, "rate": args.rate, "window": window.to_dict(),
              "guard_failures": failures, "empty_refs": export.empty,
              "generator_exit": generated.returncode,
              "generator_window": generated.window.to_dict(),
              "client": read_k6_summary(summary_path)}
    markdown = "\n".join(reporting.md_table([
        ("run", f"`{args.run}`"),
        ("rate", args.rate),
        ("window", f"{window} "),
        ("series exported", f"{export.series} ({export.points} points)"),
        ("guards", "clean" if not failures else ", ".join(failures)),
    ]))
    print()
    print(f"[{OK}] {reporting.write_point(out_dir, args.run, markdown, record)}")
    # k6 exits 99 when a threshold is breached — the system failed, not the
    # generator, and that is the measurement rather than a reason to doubt it.
    # Any other non-zero exit means the offered load was not what is claimed.
    K6_THRESHOLD_BREACHED = 99
    doubts = ([] if generated.ok or generated.returncode == K6_THRESHOLD_BREACHED
              else [f"generator exited {generated.returncode}"])
    return reporting.report_validity(doubts, failures)


if __name__ == "__main__":
    sys.exit(main())
