"""`metrics.yaml`: an execution's metric register — what is read and from
where, each ref defined once. A runner exports every M ref with a promql;
`derive.py` works out every ref a run's data holds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import arith, series
from .strict_yaml import UniqueKeyLoader, unknown_keys

REGISTER = "metrics.yaml"
SECTIONS = ("metrics",)

METRIC_REF = re.compile(r"^([MDRE])([1-9]\d*)$")
MEASURED_STATUS = re.compile(r"^(confirmed \d{4}-\d{2}-\d{2}|unconfirmed)$")

DEFINITIONS = {"M": ("promql", "record", "source"),
               "D": ("formula", "series", "record", "source"),
               "R": ("record", "source"),
               "E": ("source",)}
DEFINING_KEYS = ("promql", "formula", "series", "record", "source")
METRIC_KEYS = frozenset({"what", "status", "notes", *DEFINING_KEYS})
TEXT_KEYS = METRIC_KEYS - {"series"}


class RegisterError(Exception):
    """Anything the register's own contents make impossible."""


@dataclass(frozen=True)
class Metric:
    ref: str
    what: str
    status: str
    notes: str = ""
    promql: str | None = None
    source: str | None = None
    formula: str | None = None
    series: series.Series | None = None
    record: str | None = None

    @property
    def derived_from_data(self) -> bool:
        """A number for one run can be worked out of its committed data."""
        return any(key is not None for key in (self.formula, self.series, self.record))

    @property
    def inputs(self) -> list[str]:
        """The refs of this register its definition reads."""
        if self.series is not None:
            return self.series.refs
        if self.formula is None:
            return []
        return [name for name in arith.names(arith.parse(self.formula), dotted=True)
                if METRIC_REF.match(name)]


@dataclass(frozen=True)
class Register:
    path: Path
    metrics: tuple[Metric, ...]

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def exported(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if m.promql is not None)

    @property
    def by_ref(self) -> dict[str, Metric]:
        return {metric.ref: metric for metric in self.metrics}


def read_register(path: Path) -> Register:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegisterError(f"cannot read {path}: {exc.strerror}") from None
    return parse_register(text, path)


def parse_register(text: str, path: Path) -> Register:
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise RegisterError(f"{path}: {exc}") from None
    if not isinstance(doc, dict):
        raise RegisterError(f"{path}: expected a mapping with metrics")
    unknown = sorted(set(doc) - set(SECTIONS))
    if unknown:
        raise RegisterError(f"{path}: unknown section {unknown[0]!r} — a register "
                            f"holds only metrics; when a window closes and what "
                            f"makes a point valid are execution.yaml's")
    metrics = tuple(metric_of(ref, spec) for ref, spec in section(doc, "metrics", path))
    register = Register(path, metrics)
    check_numbering(register)
    check_definitions(register)
    if not register.exported:
        raise RegisterError(f"{path}: no metric has a promql — a runner exports "
                            f"those and refuses a register with none")
    return register


def section(doc: dict, name: str, path: Path) -> list[tuple[str, dict]]:
    entries = doc.get(name)
    if not isinstance(entries, dict) or not entries:
        raise RegisterError(f"{path}: '{name}' must be a mapping of ref to entry, "
                            f"with at least one entry")
    for ref, spec in entries.items():
        if not isinstance(spec, dict):
            raise RegisterError(f"{path}: {name}.{ref} must be a mapping")
    return [(str(ref), spec) for ref, spec in entries.items()]


def metric_of(ref: str, spec: dict) -> Metric:
    found = METRIC_REF.match(ref)
    if not found:
        raise RegisterError(f"metric {ref!r} is not M, D, R or E followed by a number")
    refuse_unknown_keys(ref, spec, METRIC_KEYS)
    text = {key: one_line(ref, key, spec[key]) for key in TEXT_KEYS if key in spec}
    for key in ("what", "status"):
        if not text.get(key):
            raise RegisterError(f"{ref}: '{key}' is required")
    check_definition(ref, found.group(1), spec)
    if found.group(1) == "M" and not MEASURED_STATUS.match(text["status"]):
        raise RegisterError(f"{ref}: status {text['status']!r} — an M ref is "
                            f"'confirmed YYYY-MM-DD' or 'unconfirmed'")
    return Metric(ref=ref, what=text["what"], status=text["status"],
                  notes=text.get("notes", ""), promql=text.get("promql"),
                  source=text.get("source"), formula=formula_of(ref, text.get("formula")),
                  series=series_of(ref, spec.get("series")), record=text.get("record"))


def check_definition(ref: str, letter: str, spec: dict) -> None:
    """One key says how a ref is had, and the letter decides which keys may."""
    given = [key for key in DEFINING_KEYS if key in spec]
    allowed = DEFINITIONS[letter]
    takes = f"a {letter} ref takes {' or '.join(allowed)}"
    if "promql" in given and letter != "M":
        raise RegisterError(f"{ref}: only an M ref is a query; {takes}")
    stray = [key for key in given if key not in allowed]
    if stray:
        raise RegisterError(f"{ref}: {stray[0]} is not for it; {takes}")
    if len(given) != 1:
        raise RegisterError(f"{ref}: give exactly one of {', '.join(allowed)} — "
                            f"how a number for it is had")


def formula_of(ref: str, formula: str | None) -> str | None:
    if formula is not None:
        try:
            arith.check(arith.parse(formula), dotted=True)
        except arith.ArithError as exc:
            raise RegisterError(f"{ref}: formula {exc}") from None
    return formula


def series_of(ref: str, raw: object) -> series.Series | None:
    if raw is None:
        return None
    try:
        return series.read_series(raw)
    except series.SeriesError as exc:
        raise RegisterError(f"{ref}: series {exc}") from None


def one_line(ref: str, key: str, value: object) -> str:
    if not isinstance(value, str):
        raise RegisterError(f"{ref}: {key} must be text — quote it")
    if "\n" in value.strip():
        raise RegisterError(f"{ref}: {key} spans lines, and every view of it is one line")
    return value.strip()


def refuse_unknown_keys(ref: str, spec: dict, allowed: frozenset[str]) -> None:
    unknown = unknown_keys(spec, allowed)
    if unknown:
        raise RegisterError(f"{ref}: unknown key {unknown[0]!r} — expected "
                            f"{', '.join(sorted(allowed))}")


def check_numbering(register: Register) -> None:
    """methodology.md: one sequence per execution, never one counter per
    letter, so a mistyped letter fails to resolve instead of landing on a
    second live metric."""
    previous = 0
    for metric in register.metrics:
        number = int(METRIC_REF.match(metric.ref).group(2))
        if number <= previous:
            raise RegisterError(f"{register.path}: {metric.ref} comes after number "
                                f"{previous} — one sequence across M, D, R and E, "
                                f"in file order, no number twice")
        previous = number


def check_definitions(register: Register) -> None:
    """Every ref a definition reads is one this register can answer for a run:
    a series reads exported refs, a formula reads refs worked out of data."""
    known = register.by_ref
    for metric in register.metrics:
        for name in metric.inputs:
            problem = unreadable(metric, known.get(name))
            if problem:
                raise RegisterError(f"{register.path}: {metric.ref} reads {name}, {problem}")
    for metric in register.metrics:
        refuse_cycle(metric.ref, known, ())


def unreadable(reader: Metric, metric: Metric | None) -> str | None:
    if metric is None:
        return "which this register does not define"
    if reader.series is not None:
        return None if metric.promql else "which is not an M ref with a promql"
    if metric.promql is not None:
        return "a series — reduce it in a D ref's series: and read that instead"
    if not metric.derived_from_data:
        return "which is written by hand, so no run's data holds it"
    return None


def refuse_cycle(ref: str, known: dict[str, Metric], trail: tuple[str, ...]) -> None:
    if ref in trail:
        raise RegisterError("cycle: " + " -> ".join((*trail, ref)))
    for name in known[ref].inputs if known[ref].formula else []:
        refuse_cycle(name, known, (*trail, ref))


def find_register(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / REGISTER
        if candidate.is_file():
            return candidate
    return None


def register_above(path: Path, root: Path) -> Path | None:
    """The first register in `path` or a directory above it, no higher than
    `root`: the execution a run's data belongs to."""
    root, start = root.resolve(), path.resolve()
    if root not in (start, *start.parents):
        return None
    for directory in (start, *start.parents):
        if (directory / REGISTER).is_file():
            return directory / REGISTER
        if directory == root:
            break
    return None


def series_rows(register: Register) -> list[list[str]]:
    """The refs a runner exports, as `prometheus.export_range` takes them."""
    return [[metric.ref, metric.promql] for metric in register.exported]
