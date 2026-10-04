"""What `--check` says about charts, without drawing any."""

from __future__ import annotations

from pathlib import Path

from . import stamp
from .canvas import svg_name
from .errors import Skip
from .kinds import NO_AXIS
from .render import leftovers
from .spec import CHART_DIR, SPEC, Entry, Spec, read_spec
from .table import read, sha256, with_axis

EXIT_OK = 0
EXIT_FAILED = 1


def inspect(path: Path, kind: str | None) -> tuple[list[str], list[str]]:
    """(problems, notes). A problem means the file cannot be drawn."""
    try:
        data = read(path)
    except Skip as exc:
        return [f"{path.name}: {exc}"], []
    notes = [f"{path.name}: {data.rows} rows, {len(data.labels)} label column(s), "
             f"{len(data.groups)} unit group(s)"]
    if kind is None or kind in NO_AXIS:
        return [], notes
    try:
        with_axis(data)
    except Skip as exc:
        return [f"{path.name}: {exc}"], notes
    return [], notes


def report(problems: list[str], notes: list[str], files: int) -> int:
    for line in problems:
        print(line)
    for line in notes:
        print(f"note: {line}")
    print(f"\n{len(problems)} problem(s) across {files} file(s)")
    return EXIT_FAILED if problems else EXIT_OK


def check_files(paths: list[Path], kind: str | None) -> int:
    problems, notes = [], []
    for path in paths:
        found, said = inspect(path, kind)
        problems.extend(found)
        notes.extend(said)
    return report(problems, notes, len(paths))


def freshness(entry: Entry, theme_name: str, colours: dict, out: Path):
    svg = out / svg_name(entry.name, theme_name)
    if not svg.exists():
        return f"{entry.name}: not drawn on {theme_name} — run --all"
    drawn = stamp.read(svg)
    if drawn is None:
        return f"{svg.name}: no report-kit stamp, so nothing says what drew it — run --all"
    if not entry.path.exists():
        return None
    csv, spec = drawn
    if csv != sha256(entry.path):
        return f"{entry.name}: {entry.path.name} changed since {svg.name} was drawn — run --all"
    if spec != stamp.spec_hash(entry.kind, entry.marks, colours):
        return f"{entry.name}: {SPEC.name} changed since {svg.name} was drawn — run --all"
    return None


def stale(spec: Spec, out: Path) -> list[str]:
    if not list(out.glob("*.svg")):
        return [f"nothing drawn yet in {out}/ — run --all"]
    found = [line for entry, name, colours in spec.pairs()
             if (line := freshness(entry, name, colours, out))]
    found.extend(f"{svg.name}: no entry or theme of {SPEC.name} draws it — "
                 f"--all removes it" for svg in leftovers(out, spec.svgs()))
    return found


def unnamed(spec: Spec) -> list[str]:
    named = {entry.path.resolve() for entry in spec.entries}
    return [f"{path.name}: no entry in {SPEC.name}, so --all never draws it"
            for path in sorted(CHART_DIR.glob("*.csv")) if path.resolve() not in named]


def check_spec() -> int:
    spec = read_spec()
    problems, notes = [], []
    for entry in spec.entries:
        found, said = inspect(entry.path, entry.kind)
        problems.extend(found)
        notes.extend(said)
    problems.extend(unnamed(spec))
    problems.extend(stale(spec, CHART_DIR))
    return report(problems, notes, len(spec.entries))
