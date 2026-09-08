#!/usr/bin/env python3
"""export_metrics.py — snapshot a window's Prometheus series to .jsonl by hand.

    ./export_metrics.py --run api-r200 --queries series.txt \
        --start 2026-09-04T10:00:00Z --end 2026-09-04T10:20:00Z
    ./export_metrics.py --run x --queries series.txt --last 30m

The runners export automatically; this exists for the case that matters
most and happens least often: the run finished, the export didn't, and the
window is sitting in the point record with metrics retention counting down.
A window can only be re-exported, never re-measured — so this path stays
usable even when the rest of the toolkit isn't.

To keep that true it imports only prometheus/refs/shell/constants/window,
which are standard-library-only. It does not read env.yaml (that needs
PyYAML): pass --prom-url, or set PROM_URL.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="report-kit export-metrics",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True, help="point id; names the output files")
    p.add_argument("--queries", required=True, type=Path, help="series.txt (ref|promql)")
    p.add_argument("--start", help="RFC3339, e.g. 2026-09-04T10:00:00Z")
    p.add_argument("--end", help="RFC3339; defaults to now when --start is given")
    p.add_argument("--last", help="window ending now, e.g. 30m — instead of --start")
    p.add_argument("--step", default="15s")
    p.add_argument("--out-dir", type=Path, default=Path(os.environ.get("OUT_DIR", ".")))
    p.add_argument("--prom-url", default=os.environ.get("PROM_URL"))
    p.add_argument("--force", action="store_true", help="overwrite an existing export")
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

    series = refs.read_ref_file(args.queries, 2)
    export = prometheus.export_range(
        args.prom_url.rstrip("/"), series, window,
        out_dir=args.out_dir, run_id=args.run, step=args.step, force=args.force)
    return EXIT_CLEAN if export.ok else EXIT_EXPORT_GAP


if __name__ == "__main__":
    sys.exit(main())
