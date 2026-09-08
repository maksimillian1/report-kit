#!/usr/bin/env python3
"""inspect_metrics.py — look at what a point's export actually captured.

    ./inspect_metrics.py --file data/api-r200.jsonl
    ./inspect_metrics.py --file data/api-r200.jsonl --ref M9
    ./inspect_metrics.py --file data/api-r200.jsonl --csv out.csv

Worth running once per point before trusting a number: an export can succeed
and still be useless — a ref with one series where you expected twelve, or a
metric that flatlines because the query matched the wrong label.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


from report_kit.clock import parse_instant
from report_kit.constants import EXIT_CLEAN, WARN, die
from report_kit.jsonl import (changes, label_summary, load_lines,
                              parse_values, split)


def settle_instant(lines: list[dict], ref: str) -> float | None:
    """The last time `ref` changed — after it, the system stopped reacting.

    Returns None when it never changed (nothing to split) or when the ref is
    absent. A ref that changes at its very last sample never settled inside
    the window at all, which is itself worth seeing."""
    instants: list[float] = []
    for entry in lines:
        if entry.get("metric") != ref:
            continue
        for series in entry.get("result", []):
            instants += changes(parse_values(series.get("values", [])))
    return max(instants) if instants else None


def describe(values: list[tuple[float, float]], label: str, indent: str = "  ") -> None:
    numbers = [v for _, v in values]
    if not numbers:
        print(f"{indent}{label}: no numeric samples")
        return
    print(f"{indent}{label}: n={len(numbers)} min={min(numbers):.4g} "
          f"max={max(numbers):.4g} avg={statistics.fmean(numbers):.4g} "
          f"last={numbers[-1]:.4g}")


def print_summary(lines: list[dict], only_ref: str | None,
                  settle: float | None = None,
                  until: float | None = None) -> None:
    for entry in lines:
        ref = entry.get("metric", "?")
        if only_ref and ref != only_ref:
            continue
        query = entry.get("query", "")
        result = entry.get("result", [])
        print(f"\n{ref} · {query[:100]}{'...' if len(query) > 100 else ''}")
        print(f"  series: {len(result)}")
        if not result:
            print("  NO DATA — a gap, not a zero")
            continue
        for series in result:
            points = parse_values(series.get("values", []))
            label = label_summary(series.get("metric", {}))
            describe(points, label)
            if settle is None or not points:
                continue
            before, after = split(points, settle)
            if until is not None:
                after = [p for p in after if p[0] <= until]
            if not after:
                # Saying nothing here would leave the whole-window mean looking
                # like a steady-state figure, which is the error this flag
                # exists to prevent.
                print(f"      no settled samples: the system was still reacting "
                      f"when the load ended, or the export step is too coarse "
                      f"to see the plateau")
                continue
            if not before:
                print(f"      no transient: it was already settled when the "
                      f"window opened")
                continue
            describe(before, "while still reacting", indent="      ")
            describe(after, "once settled" + (" and still loaded" if until else ""),
                     indent="      ")


def write_csv(lines: list[dict], only_ref: str | None, out_path: Path) -> tuple[int, int, int]:
    """Long format — one row per sample, so a spreadsheet can pivot it."""
    refs = series = rows = 0
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ref", "query", "series_labels", "timestamp_utc",
                         "timestamp_epoch", "value"])
        for entry in lines:
            ref = entry.get("metric", "?")
            if only_ref and ref != only_ref:
                continue
            query = entry.get("query", "")
            refs += 1
            for one in entry.get("result", []):
                label = label_summary(one.get("metric", {}))
                series += 1
                for timestamp, value in parse_values(one.get("values", [])):
                    iso = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
                    writer.writerow([ref, query, label, iso, timestamp, value])
                    rows += 1
    return refs, series, rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="report-kit inspect-metrics",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", required=True, type=Path, help="the point's .jsonl")
    p.add_argument("--ref", help="only this ref, e.g. M9")
    p.add_argument("--settle-on", metavar="REF",
                   help="split every ref at the last change of this one — the "
                        "autoscaler's replica count is the usual choice")
    p.add_argument("--until", metavar="RFC3339",
                   help="end the settled segment here. Use the moment the load "
                        "stopped (the point record's generator end): a settling "
                        "series says when the system stopped reacting, not when "
                        "the load stopped, so without this the steady state is "
                        "mixed with the wind-down after it")
    p.add_argument("--csv", type=Path, help="also write a long-format CSV here")
    args = p.parse_args(argv)

    lines = load_lines(args.file)
    if not lines:
        die(f"{args.file}: no entries")
    if args.ref and not any(line.get("metric") == args.ref for line in lines):
        available = ", ".join(sorted(line.get("metric", "?") for line in lines))
        die(f"no ref {args.ref!r} in {args.file} — available: {available}")

    settle = settle_instant(lines, args.settle_on) if args.settle_on else None
    if args.settle_on and settle is None:
        print(f"{WARN} {args.settle_on} never changed inside this window — "
              f"nothing to split on, which means the window holds one regime")
    until = parse_instant(args.until).timestamp() if args.until else None
    print_summary(lines, args.ref, settle, until)

    empty = [line.get("metric", "?") for line in lines if not line.get("result")]
    if empty and not args.ref:
        print()
        print(f"{WARN} {len(empty)} ref(s) captured nothing: {', '.join(empty)}")

    if args.csv:
        refs, series, rows = write_csv(lines, args.ref, args.csv)
        print(f"\n-> {refs} ref(s), {series} series, {rows} rows -> {args.csv}")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
