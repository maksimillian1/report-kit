"""The frozen CSV format, read into the one shape every chart kind draws from."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import Skip

LABEL_UNIT = "label"
ASIDE_SUFFIX = " aside"
LINEAR_MAX_SPAN = 25.0
LOG_Y_MIN_SPAN = 10.0
TOLERANCE = 0.005


@dataclass(frozen=True)
class Column:
    name: str
    unit: str
    values: tuple


@dataclass(frozen=True)
class Group:
    unit: str
    columns: tuple
    aside: bool

    @property
    def title(self) -> str:
        return self.unit[:-len(ASIDE_SUFFIX)] if self.aside else self.unit


@dataclass(frozen=True)
class Table:
    path: Path
    labels: tuple
    x: Column | None
    series: tuple
    groups: tuple
    rows: int

    @property
    def panels(self) -> tuple:
        return tuple(g for g in self.groups if not g.aside)

    @property
    def aside(self) -> tuple:
        return tuple(g for g in self.groups if g.aside)

    def label_at(self, row: int) -> str:
        return self.labels[0].values[row] if self.labels else ""


def as_number(raw: str):
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def read(path: Path) -> Table:
    if not path.exists():
        raise Skip(f"no such file: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise Skip("needs a header, a units row and at least one row of data")

    names = [c.strip() for c in rows[0]]
    units = [c.strip() for c in rows[1]]
    body = rows[2:]
    if not body:
        raise Skip("header and units only, no rows yet")
    if len(units) != len(names) or any(not u for u in units):
        raise Skip("line 2 must give a unit for every column, "
                   f"got {len(units)} for {len(names)}")
    if all(as_number(u) is not None for u in units if u):
        raise Skip("line 2 must be the units row, and it reads as data")

    labels, series = [], []
    for index, (name, unit) in enumerate(zip(names, units)):
        raw = [r[index].strip() if index < len(r) else "" for r in body]
        numbers = tuple(as_number(v) if v else None for v in raw)
        if unit == LABEL_UNIT or all(n is None for n in numbers):
            labels.append(Column(name, LABEL_UNIT, tuple(raw)))
        else:
            series.append(Column(name, unit, numbers))
    if not series:
        raise Skip("no numeric column to draw")

    return Table(path=path, labels=tuple(labels), x=None,
                 series=tuple(series), groups=group(series), rows=len(body))


def group(columns) -> tuple:
    """Columns sharing a unit share a panel, or a stack, in header order."""
    grouped: dict[str, list] = {}
    for column in columns:
        grouped.setdefault(column.unit, []).append(column)
    return tuple(Group(unit, tuple(cols), unit.endswith(ASIDE_SUFFIX))
                 for unit, cols in grouped.items())


def with_axis(table: Table) -> Table:
    """The first series column becomes the x axis. Kinds without one skip this.

    Panels are then ordered by the first column of each unit that is left, so
    the header decides which panel is on top.
    """
    first = table.series[0]
    rest = [c for c in table.series if c is not first]
    if not rest:
        raise Skip(f"{first.name} is the only numeric column, so nothing is "
                   f"left to plot against it")
    return Table(path=table.path, labels=table.labels, x=first,
                 series=tuple(rest), groups=group(rest), rows=table.rows)


def span(values) -> float:
    present = [v for v in values if v is not None and v > 0]
    if len(present) < 2:
        return 1.0
    return max(present) / min(present)


def log_x(table: Table) -> bool:
    return table.x is not None and span(table.x.values) > LINEAR_MAX_SPAN


def log_y(table: Table, group: Group) -> bool:
    """Per panel: one wide panel must not drag a narrow neighbour onto a log axis."""
    widest = max((span(c.values) for c in group.columns), default=1.0)
    return log_x(table) and widest > LOG_Y_MIN_SPAN


def subtotals(values) -> tuple:
    """Which rows of a waterfall restate the running total rather than add to it.

    A subtotal is a row whose value is what the steps before it already sum to,
    so the format needs no column to mark one.
    """
    marks, running = [], 0.0
    for value in values:
        if value is None:
            marks.append(False)
            continue
        if running and abs(value - running) <= abs(running) * TOLERANCE:
            marks.append(True)
        else:
            marks.append(False)
            running += value
    return tuple(marks)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
