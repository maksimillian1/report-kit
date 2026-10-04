#!/usr/bin/env python3
"""charts — draw a CSV. Four shapes, two surfaces, no knowledge of your report.

    report-kit charts --format                   the CSV format, frozen
    report-kit charts new --kind waterfall       charts/waterfall.csv to fill, and its entry
    report-kit charts --check charts/*.csv       is this drawable
    report-kit charts charts/failover.csv --kind line --mark-x 20 primary lost
    report-kit charts charts/floor.csv --kind parts --theme navy
    report-kit charts --all                      every chart in charts/charts.yaml
    report-kit charts --check                    the spec, stale SVGs, missed CSVs

What goes on which axis comes from the file. The shape is the one thing the data
cannot say, so `--kind` says it. Worked files for every shape are under
`examples/tenant-platform/`; why a chart CSV may hold what it holds is `formats.md`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import canvas, kinds, labels, spec, stamp
from .canvas import DEFAULT_THEMES
from .check import EXIT_FAILED, EXIT_OK, check_files, check_spec
from .errors import ChartError, Skip
from .kinds import KINDS, Marks
from .render import prune, render
from .spec import CHART_DIR, SPEC, Entry, available_themes, checked, read_spec

EXIT_USAGE = 2

FORMAT = """\
the format
  line 1   column names
  line 2   a unit for every column, always
  line 3+  the data

  tier,compute,database,standby
  label,$/tenant/month,$/tenant/month,$/tenant/month aside
  pro,12,8,6

what the units row decides
  label        this column names the points; it is not drawn as a series
  anything     a unit. Columns sharing one share a panel, or a stack
  "<u> aside"  its own bar beside the stack, not inside it (--kind bars)

what the file decides on its own
  the x axis   the first numeric column that is not a label
  log scales   an x wider than 25x goes log; each panel's y follows past 10x
  a subtotal   a waterfall row restating the running total
  a gap        an empty cell; a line breaks there rather than bridging it

  Put only what is drawn in the file. A column kept for a caption becomes a
  panel nobody wanted.

the four shapes
  line       one panel per unit on a shared x axis
  bars       stacked bars per step, with an ` aside` unit beside them
  parts      one horizontal bar: the rows are the parts, there is no axis
  waterfall  ordered steps, each starting where the last ended

what a table cannot carry, on --kind line only
  --rule 300 p99 target            a horizontal threshold line
  --mark-x 100 break-even          a vertical line at one x, on every panel
  --points                         the marks without the line joining them,
                                   for points that are not a sequence

charts/charts.yaml, one entry per chart, so a report renders with one command
  themes:                          optional; without it, every built-in theme
    light: {}                      a built-in as it is
    print: {ink: "#000000", ...}   a new one needs every colour key
  failover:                        draws charts/failover.csv
    kind: line
    rule: {at: 300, text: p99 target}
    mark_x: {at: 20, text: primary lost}
    points: false
  floor:
    kind: parts
    themes: [light]                only these of the spec's themes

  --all draws every entry on every listed theme, or on its own themes: list. --check with no file named
  fails on an entry or theme it cannot read, a CSV it cannot draw, a CSV no
  entry names, an SVG missing or older than its CSV, its entry or its theme,
  and an SVG nothing draws.
"""

EPILOG = """\
output
  charts/<name>.svg beside charts/<name>.csv, and charts/<name>-<theme>.svg
  for every theme but light. The SVG's first lines say it is generated, from
  which CSV, with hashes of that CSV and of what drew it: that stamp is all
  --check needs. --all owns the SVGs in its output directory: one no entry or
  theme produces is deleted, so keep hand-drawn images elsewhere.

  Each SVG is authored at 1620 x 1000 units, so a font size is a pixel on an
  1800px slide and scales down to an article without dropping below a readable
  label. Text stays text, so the fonts resolve wherever the file is opened.

themes
  light and navy are built in. The themes: key of charts/charts.yaml picks
  which ones --all draws, overrides their colours, or adds one. --theme draws
  just one of them.

three rules the renderer does not let you override
  No chart carries two y-scales: a second unit goes in a second panel sharing
  the x axis, because two scales on one frame let the author choose where the
  lines cross. Series colours are steps of one hue ordered by magnitude, so
  adjacent segments stay apart for a colour-blind reader. And no label sits at a
  fixed offset: every one is measured against the frame and against what is
  already placed.

  So change the CSV rather than the renderer.
"""

SKELETON = {
    "line": "point,x,measure,cost\nlabel,x unit,measure unit,$\nfirst,1,10,100\n",
    "bars": "step,part_a,part_b,spare\nlabel,$,$,$ aside\nfirst,1.0,2.0,4.0\n",
    "parts": "part,amount\nlabel,$/month\nfirst,100\n",
    "waterfall": "step,amount\nlabel,$\ngross,10\nless something,-2\nnet,8\n",
}


def cmd_format() -> int:
    print(FORMAT)
    return EXIT_OK


def cmd_new(kind: str) -> int:
    if kind not in SKELETON:
        raise ChartError(f"unknown kind {kind!r} — have {', '.join(KINDS)}")
    path = CHART_DIR / f"{kind}.csv"
    if path.exists():
        print(f"{path} already exists, left alone")
        return EXIT_OK
    CHART_DIR.mkdir(exist_ok=True)
    path.write_text(SKELETON[kind], encoding="utf-8")
    with SPEC.open("a", encoding="utf-8") as handle:
        handle.write(f"{path.stem}:\n  kind: {kind}\n")
    print(path)
    print(f"{SPEC}: + {path.stem}")
    return EXIT_OK


def add_mark_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rule", nargs="+", metavar=("VALUE", "TEXT"),
                   help="a threshold line, e.g. --rule 300 p99 target")
    p.add_argument("--mark-x", nargs="+", metavar=("VALUE", "TEXT"),
                   help="a vertical line at one x, e.g. --mark-x 100 break-even")
    p.add_argument("--points", action="store_true",
                   help="draw the marks without joining them")


def parse_mark(flag: str, given: list[str] | None):
    if not given:
        return None
    value, *text = given
    try:
        return float(value), " ".join(text)
    except ValueError as exc:
        raise ChartError(f"{flag} wants a number first, got {value!r}") from exc


def build_marks(kind: str | None, opts) -> Marks:
    return checked(kind, Marks(rule=parse_mark("--rule", opts.rule),
                               mark_x=parse_mark("--mark-x", opts.mark_x),
                               join=not opts.points))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit charts", description=__doc__, epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="*", type=Path,
                   help="one or more CSVs, or the word `new`")
    p.add_argument("--kind", choices=list(KINDS), help="which shape to draw")
    p.add_argument("--out", type=Path,
                   help=f"where the SVGs go (default {CHART_DIR}/, beside the CSVs)")
    p.add_argument("--theme",
                   help=f"{' or '.join(DEFAULT_THEMES)}, or a theme {SPEC} "
                        f"adds (default light; every listed theme with --all)")
    add_mark_flags(p)
    p.add_argument("--all", action="store_true",
                   help=f"draw every chart {SPEC} names")
    p.add_argument("--check", action="store_true",
                   help="say whether each CSV is drawable; draw nothing. "
                        f"With no CSV, check {SPEC} and every SVG it draws")
    p.add_argument("--format", action="store_true",
                   help="print the CSV format and exit")
    return p


def pick(themes: dict, wanted: str | None) -> dict:
    if wanted is None:
        return themes
    if wanted not in themes:
        raise ChartError(f"unknown theme {wanted!r} — have "
                         f"{', '.join(sorted(themes))}")
    return {wanted: themes[wanted]}


def run_all(opts) -> int:
    if opts.csv or opts.kind or opts.rule or opts.mark_x or opts.points:
        raise ChartError(f"--all takes its files, kinds and marks from {SPEC}")
    given = read_spec()
    out = opts.out or CHART_DIR
    for name, colours in pick(given.themes, opts.theme).items():
        render([entry for entry, theme_name, _ in given.pairs() if theme_name == name],
               name, colours, out)
    prune(out, given.svgs())
    return EXIT_OK


def run_named(opts) -> int:
    if not opts.kind:
        raise ChartError(f"--kind is the one thing the file cannot say — "
                         f"{', '.join(KINDS)}")
    (name, colours), = pick(available_themes(), opts.theme or "light").items()
    marks = build_marks(opts.kind, opts)
    render([Entry(path, opts.kind, marks) for path in opts.csv], name, colours,
           opts.out or CHART_DIR)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    try:
        if opts.format:
            return cmd_format()
        if opts.csv and str(opts.csv[0]) == "new":
            if not opts.kind:
                raise ChartError("new needs --kind")
            return cmd_new(opts.kind)
        if opts.all:
            return run_all(opts)
        if opts.check:
            return check_files(opts.csv, opts.kind) if opts.csv else check_spec()
        if not opts.csv:
            raise ChartError("name at least one CSV, or --all, or --format")
        return run_named(opts)
    except ChartError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
