#!/usr/bin/env python3
"""charts — render the report's charts as SVG, one CSV per chart.

    report-kit charts --list                 the column contract, every CSV
    report-kit charts --check                what is drawable, and what is not
    report-kit charts all --out assets
    report-kit charts all --theme navy --out assets
    report-kit charts api-frontier --data charts/frontier-api.csv

This package holds no numbers. Every figure comes from a CSV under `charts/`,
whose contract is `contract.SCHEMA` and whose rules — what may go in one, what
`--check` fails on, what the renderer will not let you override — are
`charts.md`. Drift is the registry's question: put `charts/*.csv` in
`figures.yaml`'s `scan`.

Charts, and the section of the report template each one serves:

  jobs-frontier   §3.2  concurrency vs throughput and unit cost, two panels
  jobs-tradeoff   §3.3  throughput bought vs unit cost paid, points labelled
  jobs-split      §4.2  per-workload cost at each step, against unused capacity
  api-frontier    §3.2  offered rate vs p95 and replicas, two panels
  floor           §4.1  the dedicated block against the shared one
  amortization    §4.3  effective unit cost against monthly volume
  all                   every chart above

## Module map

This module is the command: the parser, the three `cmd_*` functions, and the
table wiring a chart name to the function that draws it. Everything below it
prints nothing, so `from report_kit.tools.charts import validate` gets a script
an answer rather than a page.

| | |
| :--- | :--- |
| `contract.py` | what a CSV may hold, how a row is read, whether one file keeps the contract |
| `canvas.py` | the surface: size, type, palette, axis helpers — and matplotlib's entry point |
| `labels.py` | where a label goes, decided by measuring rather than by guessing |
| `frontier.py` | report §3 — what throughput costs, on either profile |
| `cost.py` | report §4 — the split, the floor, the amortization |
| `errors.py` | `Skip` (one chart) against `ChartError` (the run) |

The dependency order is that list. `errors` imports nothing of this package;
`contract` and `canvas` import only it; `labels` sits on `canvas`; and the two
drawing modules on all four. Nothing imports this module, and nothing in the
package imports `report_kit.tools.figures`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cost, frontier
from .canvas import THEMES, configure, load_backend
from .contract import SCHEMA, read_rows, sha256, validate
from .errors import ChartError, Skip

# Re-exported, not used below, so an importing caller need not know which
# submodule a name moved to.
from .canvas import new_figure
from .contract import (num, period_of, read_table, replica_series,
                       series_columns, singular, split_workloads, unit_of,
                       workload_columns)
from .cost import split_segments
from .frontier import jobs_axis
from .labels import place_label, renderer_for, rule_obstacle, within

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

CHART_DIR = "charts"
ASSET_DIR = "assets"

# One table, so a chart's CSV and the function that draws it cannot drift
# apart. Adding a chart is a schema entry in `contract.py`, a function in
# `frontier.py` or `cost.py`, and a row here.
CHART = {
    "jobs-frontier": ("frontier-jobs.csv", frontier.jobs_frontier),
    "jobs-tradeoff": ("frontier-jobs.csv", frontier.jobs_tradeoff),
    "jobs-split": ("split-jobs.csv", cost.jobs_split),
    "api-frontier": ("frontier-api.csv", frontier.api_frontier),
    "floor": ("floor-blocks.csv", cost.floor_blocks),
    "amortization": ("amortization.csv", cost.amortization),
}

# `all` is a command word, not a chart.
CHARTS = list(CHART) + ["all"]
SOURCES = {name: csv_name for name, (csv_name, _) in CHART.items()}


def chosen(chart: str) -> list[str]:
    return list(CHART) if chart == "all" else [chart]


def paths_for(charts: list[str], data: str | None,
              root: Path) -> dict[str, Path]:
    if data:
        return {c: Path(data) for c in charts}
    return {c: root / CHART_DIR / CHART[c][0] for c in charts}


def cmd_list() -> int:
    for name, spec in SCHEMA.items():
        print(f"\n{name}   — {spec['serves']}")
        print(f"  required  {', '.join(spec['required'])}")
        print(f"  optional  {', '.join(spec['optional']) or '—'}")
        if spec.get("workloads"):
            print("  open      every further column is one workload's cost")
        if spec.get("series") == "replicas":
            print("  open      replicas_<name> is one autoscaled tier")
        for _target, _sources, _fn, rule in spec["derived"]:
            print(f"  derived   {rule}")
    print("\nflags: dominated, excluded — 1/true/yes marks the row")
    print("mark: M/R/D/E provenance, carried for the caption, not drawn")
    print("unit, period: read from the first row, for the axis labels")
    print("\nA column not listed is ignored, not rejected, and which panels a "
          "chart has\ndepends on the columns it was given — so `required` is "
          "the shortest list it\ncan draw anything from.")
    print("\nWhether a cell still matches the report is figures.yaml's "
          "question, not this\ntool's: add charts/*.csv to its `scan` and run "
          "report-kit figures check.")
    return EXIT_OK


def cmd_check(paths: list[Path]) -> int:
    """Only a problem costs an exit code; a note is said and let go."""
    problems, notes = [], []
    for path in paths:
        found, said = validate(path)
        problems.extend(found)
        notes.extend(said)

    for line in problems:
        print(line)
    for line in notes:
        print(f"note: {line}")
    print(f"\n{len(problems)} problem(s) and {len(notes)} note(s) across "
          f"{len(paths)} file(s)")
    return EXIT_FAILED if problems else EXIT_OK


def render(chart: str, path: Path, theme: dict, out: Path,
           theme_name: str) -> list[Path]:
    return CHART[chart][1](read_rows(path), theme, out, theme_name)


def cmd_render(charts: list[str], sources: dict[str, Path], theme_name: str,
               out: Path) -> int:
    load_backend()
    theme = THEMES[theme_name]
    configure(theme)

    manifest, skipped = [], []
    for chart in charts:
        path = sources[chart]
        try:
            written = render(chart, path, theme, out, theme_name)
        except Skip as exc:
            skipped.append(f"{chart}: {exc}")
            continue
        for out_path in written:
            print(out_path)
            manifest.append({
                "chart": chart,
                "svg": out_path.name,
                "theme": theme_name,
                "source": str(path),
                "source_sha256_12": sha256(path),
            })

    if manifest:
        out.mkdir(parents=True, exist_ok=True)
        index = out / f"manifest-{theme_name}.json"
        index.write_text(json.dumps(manifest, indent=2) + "\n",
                         encoding="utf-8")
        print(index)

    for line in skipped:
        print(f"skipped — {line}", file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit charts", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("chart", nargs="?", choices=CHARTS, default="all")
    p.add_argument("--data", help="one CSV path; defaults by chart")
    p.add_argument("--root", default=".",
                   help=f"the report root holding {CHART_DIR}/ (default: .)")
    p.add_argument("--out", help=f"where the SVGs go (default: <root>/{ASSET_DIR})")
    p.add_argument("--theme", choices=list(THEMES), default="light",
                   help="light for a document, navy for a slide")
    p.add_argument("--check", action="store_true",
                   help="say what is drawable and what is not; render nothing")
    p.add_argument("--list", action="store_true",
                   help="print the column contract for every CSV and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    if opts.list:
        return cmd_list()

    root = Path(opts.root)
    charts = chosen(opts.chart)
    if opts.chart == "all" and opts.data:
        print("usage: --data names one CSV, so it cannot be combined with 'all'",
              file=sys.stderr)
        return EXIT_USAGE

    sources = paths_for(charts, opts.data, root)
    try:
        if opts.check:
            return cmd_check(sorted(set(sources.values())))
        out = Path(opts.out) if opts.out else root / ASSET_DIR
        return cmd_render(charts, sources, opts.theme, out)
    except ChartError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
