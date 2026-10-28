#!/usr/bin/env python3
"""export_metrics.py — snapshot a window's Prometheus series to .jsonl by hand.

    report-kit export-metrics --record data/api-r200.point.json
    report-kit export-metrics --run api-r200 --queries series.txt \
        --start 2026-09-04T10:00:00Z --end 2026-09-04T10:20:00Z
    report-kit export-metrics --run x --queries series.txt --last 30m

`--record` reads the run id, the window and the queries from the point
record a runner wrote before its own export; `--queries` reads a
`ref|promql` file, as an execution from before 0.4 keeps beside its runner.

The runners export automatically; this exists for the case that matters
most and happens least often: the run finished, the export didn't, and the
window is sitting in the point record with metrics retention counting down.
A window can only be re-exported, never re-measured — so this path stays
usable even when the rest of the toolkit isn't.

To keep that true it imports only prometheus/refs/shell/constants/window,
which are standard-library-only, and a point record is JSON. It does not read
env.yaml or metrics.yaml (those need PyYAML): pass --prom-url, or set PROM_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path

from report_kit import prometheus, refs
from report_kit.constants import EXIT_CLEAN, EXIT_EXPORT_GAP, die
from report_kit.clock import parse_instant, utcnow
from report_kit.window import Window

DURATION = re.compile(r"^(\d+)([smhd])$")
UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    match = DURATION.match(text.strip())
    if not match:
        die(f"bad duration {text!r} — expected forms like 30s, 10m, 2h, 1d")
    return timedelta(**{UNITS[match.group(2)]: int(match.group(1))})


def by_hand(args: argparse.Namespace) -> tuple[str, Window, list[list[str]]]:
    if not args.run or not args.queries:
        die("pass --record, or --run and --queries with a window")
    if args.last:
        end = utcnow()
        window = Window(end - parse_duration(args.last), end)
    elif args.start:
        window = Window(parse_instant(args.start),
                        parse_instant(args.end) if args.end else utcnow())
    else:
        die("pass --last, or --start (with optional --end)")
    return args.run, window, refs.read_ref_file(args.queries, 2)


def from_record(path: Path) -> tuple[str, Window, list[list[str]]]:
    """(run id, window, ref|promql rows) as the point record holds them."""
    try:
        record = json.loads(path.read_text())
        window = record["window"]
        queries = record["queries"]
        run_id = record["run"]
        span = Window(parse_instant(window["start"]), parse_instant(window["end"]))
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}")
    except (ValueError, KeyError, TypeError) as e:
        die(f"{path} is not a point record with run, window and queries ({e}) — "
            f"a record written before 0.4 has no queries: pass --queries "
            f"series.txt and the window instead")
    return run_id, span, [[ref, query] for ref, query in queries.items()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="report-kit export-metrics",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--record", type=Path,
                   help="a point record: its run id, window and queries")
    p.add_argument("--run", help="point id; names the output files")
    p.add_argument("--queries", type=Path,
                   help="series.txt (ref|promql), for an execution from before 0.4")
    p.add_argument("--start", help="RFC3339, e.g. 2026-09-04T10:00:00Z")
    p.add_argument("--end", help="RFC3339; defaults to now when --start is given")
    p.add_argument("--last", help="window ending now, e.g. 30m — instead of --start")
    p.add_argument("--step", default="15s")
    p.add_argument("--out-dir", type=Path, default=os.environ.get("OUT_DIR"),
                   help="default: beside the record, or the working directory")
    p.add_argument("--prom-url", default=os.environ.get("PROM_URL"))
    p.add_argument("--force", action="store_true", help="overwrite an existing export")
    args = p.parse_args(argv)

    if not args.prom_url:
        die("no Prometheus URL — pass --prom-url or set PROM_URL")
    if args.record:
        run_id, window, series = from_record(args.record)
        out_dir = Path(args.out_dir) if args.out_dir else args.record.parent
    else:
        run_id, window, series = by_hand(args)
        out_dir = Path(args.out_dir or ".")
    export = prometheus.export_range(
        args.prom_url.rstrip("/"), series, window,
        out_dir=out_dir, run_id=args.run or run_id, step=args.step, force=args.force)
    return EXIT_CLEAN if export.ok else EXIT_EXPORT_GAP


if __name__ == "__main__":
    sys.exit(main())
