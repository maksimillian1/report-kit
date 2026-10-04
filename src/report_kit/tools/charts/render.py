"""Drawing: one chart on one theme, every chart on every theme, and the leftovers."""

from __future__ import annotations

import sys
from pathlib import Path

from . import stamp
from .canvas import configure, load_backend
from .errors import Skip
from .kinds import KINDS
from .spec import SPEC, Entry
from .table import read


def draw(entry: Entry, theme_name: str, colours: dict, out: Path) -> None:
    for svg in KINDS[entry.kind](read(entry.path), colours, out, theme_name,
                                 entry.marks):
        stamp.write(svg, entry.path, entry.kind, entry.marks, colours)
        print(svg)


def render(entries, theme_name: str, colours: dict, out: Path) -> None:
    load_backend()
    configure(colours)
    for entry in entries:
        try:
            draw(entry, theme_name, colours, out)
        except Skip as exc:
            print(f"skipped — {entry.path.name}: {exc}", file=sys.stderr)


def leftovers(out: Path, wanted: set) -> list[Path]:
    return [svg for svg in sorted(out.glob("*.svg")) if svg.name not in wanted]


def prune(out: Path, wanted: set) -> None:
    for svg in leftovers(out, wanted):
        svg.unlink()
        print(f"removed {svg}, which no entry or theme of {SPEC.name} draws")
