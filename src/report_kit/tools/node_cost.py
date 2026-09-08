#!/usr/bin/env python3
"""node_cost.py — what the nodes cost during a window, on the same day.

    ./node_cost.py --start 2026-09-03T15:19:31Z --end 2026-09-03T15:57:48Z \\
        --nodepool apps-compute --prom-url http://localhost:9090
    ./node_cost.py --last 40m --nodepool apps-compute --format csv

**Provisional, and not a source of record.** The Cost and Usage Report is,
and it lands a day or more later — by which time the sweep has moved on and a
figure that looked wrong has no cheap way of being questioned. This gives a
number the same afternoon, to sanity-check the shape of a cost curve while
the runs are still fresh, and to catch an order-of-magnitude mistake before it
reaches a report. Reconcile against CUR before publishing.

How it prices a window that has already passed:

  kube_node_labels  → which nodes belonged to the nodepool, and when
  kube_node_info    → each node's provider_id, hence its EC2 instance-id
  describe-instances→ instance type, AZ, spot or on-demand
  Pricing / spot    → the hourly rate for that type at that moment

`provider_id` is a built-in kube-state-metrics label, not gated by
`metricLabelsAllowlist`, so this works on nodes that are already terminated
without any configuration change. The chain's real limit is EC2's own
visibility of terminated instances — roughly an hour — after which a node that
Prometheus still remembers can no longer be typed or priced.

Reports gross node cost. Savings Plans, Reserved Instances and any negotiated
discount are applied by AWS after the fact and are invisible here.

No figure this has produced has yet been compared against a real bill. The
arithmetic and the failure paths are covered by `report-kit selftest`; the prices
themselves are not. Treat the first run on a real account as unverified.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from report_kit import prometheus
from report_kit.clock import parse_instant, utcnow
from report_kit.cloud import aws
from report_kit.constants import ARROW, BAD, EXIT_CLEAN, OK, WARN, die
from report_kit.window import Window

DURATION = re.compile(r"^(\d+)([smhd])$")
UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    match = DURATION.match(text.strip())
    if not match:
        die(f"bad duration {text!r} — expected forms like 30s, 40m, 2h, 1d")
    return timedelta(**{UNITS[match.group(2)]: int(match.group(1))})


def node_lifecycle(prom_url: str, nodepools: list[str], window: Window,
                   step: str) -> list[dict]:
    """One row per node: name, nodepool, instance-id, and the interval it was
    alive, clipped to the window. A node that outlived the window is charged
    only for the part inside it — the rest belongs to whatever ran next."""
    pools = "|".join(nodepools)
    series = prometheus.prom_query_range(
        prom_url, f'kube_node_labels{{label_karpenter_sh_nodepool=~"{pools}"}}',
        window.start, window.end, step)

    timing: dict[str, dict] = {}
    for one in series:
        stamps = [float(v[0]) for v in one.get("values", [])]
        if not stamps:
            continue
        node = one["metric"].get("node", "?")
        timing[node] = {
            "nodepool": one["metric"].get("label_karpenter_sh_nodepool", "?"),
            "first_seen": max(window.start,
                              datetime.fromtimestamp(min(stamps), tz=timezone.utc)),
            "last_seen": min(window.end,
                             datetime.fromtimestamp(max(stamps), tz=timezone.utc)),
        }
    if not timing:
        return []

    provider: dict[str, str] = {}
    for one in prometheus.prom_query_range(prom_url, "kube_node_info",
                                           window.start, window.end, step):
        node = one["metric"].get("node", "?")
        if node in timing and node not in provider:
            provider[node] = one["metric"].get("provider_id", "")

    rows = []
    for node, seen in timing.items():
        if seen["last_seen"] < seen["first_seen"]:
            # Clipping inverts only when the samples lie outside the window
            # entirely. Left alone this becomes negative hours and a negative
            # cost, which is a number a report would carry without anyone
            # blinking. Drop the node and say so.
            print(f"{WARN} {node}: its samples fall outside the window — "
                  f"skipped, so the total below is short by whatever it cost",
                  file=sys.stderr)
            continue
        pid = provider.get(node, "")
        rows.append({"node": node,
                     "instance_id": pid.rsplit("/", 1)[-1] if pid else None,
                     **seen})
    return sorted(rows, key=lambda r: r["first_seen"])


def resolve_types(rows: list[dict]) -> None:
    """Fill instance_type / az / capacity_type in place. A node EC2 has already
    forgotten stays unresolved rather than being guessed at — it will show as
    unpriced, which is the honest outcome."""
    try:
        described = aws.describe_instances([r["instance_id"] for r in rows])
    except RuntimeError as e:
        print(f"{WARN} describe-instances failed ({e}) — nothing can be priced")
        described = {}
    for row in rows:
        inst = described.get(row["instance_id"] or "", {})
        row["instance_type"] = inst.get("InstanceType", "?")
        row["az"] = inst.get("Placement", {}).get("AvailabilityZone", "?")
        row["capacity_type"] = "spot" if inst.get("InstanceLifecycle") == "spot" \
            else ("on-demand" if inst else "?")


def hourly_rate(row: dict, region: str) -> float | None:
    if row["capacity_type"] == "spot":
        return aws.spot_hourly(row["instance_type"], row["az"], row["last_seen"])
    if row["capacity_type"] == "on-demand":
        return aws.ondemand_hourly(row["instance_type"], region)
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="report-kit node-cost",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nodepool", action="append", required=True,
                   help="Karpenter nodepool name; repeat for several")
    p.add_argument("--start", help="RFC3339; the point record's window start")
    p.add_argument("--end", help="RFC3339; defaults to now when --start is given")
    p.add_argument("--last", help="window ending now, e.g. 40m — instead of --start")
    p.add_argument("--step", default="1m", help="lifecycle resolution (default 1m)")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-1"))
    p.add_argument("--prom-url", default=os.environ.get("PROM_URL"))
    p.add_argument("--format", choices=["table", "csv"], default="table")
    args = p.parse_args(argv)

    if not args.prom_url:
        die("no Prometheus URL — pass --prom-url or set PROM_URL")
    if args.last:
        end = utcnow()
        window = Window(end - parse_duration(args.last), end)
    elif args.start:
        window = Window(parse_instant(args.start),
                        parse_instant(args.end) if args.end else utcnow())
    else:
        die("pass --last, or --start (with optional --end)")

    rows = node_lifecycle(args.prom_url.rstrip("/"), args.nodepool, window, args.step)
    if not rows:
        die(f"no nodes of {', '.join(args.nodepool)} seen in {window} — check the "
            f"nodepool names and that kube-state-metrics was scraped then")
    resolve_types(rows)

    print(f"{ARROW} {len(rows)} node(s) · {window}", file=sys.stderr)
    total, unpriced = 0.0, 0
    by_pool: dict[str, float] = defaultdict(float)
    for row in rows:
        row["hours"] = (row["last_seen"] - row["first_seen"]).total_seconds() / 3600
        rate = hourly_rate(row, args.region)
        if rate is None:
            unpriced += 1
            rate = 0.0
        row["rate"], row["cost"] = rate, row["hours"] * rate
        total += row["cost"]
        by_pool[row["nodepool"]] += row["cost"]

    if args.format == "csv":
        print("node,nodepool,instance_type,capacity_type,az,hours,rate,cost")
        for r in rows:
            print(f'{r["node"]},{r["nodepool"]},{r["instance_type"]},'
                  f'{r["capacity_type"]},{r["az"]},{r["hours"]:.4f},'
                  f'{r["rate"]:.4f},{r["cost"]:.4f}')
    else:
        for r in rows:
            flag = "  (unpriced)" if r["rate"] == 0 else ""
            print(f'  {r["node"]:<45} {r["instance_type"]:<12} '
                  f'{r["capacity_type"]:<10} {r["hours"]:>6.3f}h x '
                  f'${r["rate"]:.4f}/h = ${r["cost"]:.4f}{flag}')
        print()
        for pool, cost in sorted(by_pool.items()):
            print(f'  {pool:<20} ${cost:.4f}')
        print(f'  {"TOTAL":<20} ${total:.4f}   provisional — reconcile against CUR')

    if unpriced:
        print(f"\n{BAD} {unpriced} node(s) could not be priced: EC2 no longer "
              f"describes them, or the region has no entry in "
              f"cloud/aws.LOCATION_BY_REGION. The total above is short by "
              f"whatever they cost.", file=sys.stderr)
        return 2
    print(f"[{OK}] every node priced", file=sys.stderr)
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
