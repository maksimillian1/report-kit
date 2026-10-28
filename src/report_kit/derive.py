"""A register ref's number for one run, worked out of the run's committed data:
a field of its point record (`record:`), a reduction of its export
(`series:`), or arithmetic over both (`formula:`). Returned with the steps
that produced it, so a reader can follow a number back to its readings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import arith, records, series
from .register import METRIC_REF, Metric, Register


class DeriveError(ValueError):
    """A ref the run's data cannot answer: a gap, or a definition with no data."""


@dataclass(frozen=True)
class Derivation:
    """`name` is a ref or a record field; `how` is its definition as written."""

    name: str
    value: float
    how: str
    inputs: tuple[Derivation, ...] = ()


@dataclass(frozen=True)
class Run:
    register: Register
    path: Path
    record: dict
    file: str


def derive(register: Register, ref: str, record_path: Path, file: str = "") -> float:
    return explain(register, ref, record_path, file).value


def explain(register: Register, ref: str, record_path: Path,
            file: str = "") -> Derivation:
    """`file` is how messages name the record; its path when not given."""
    label = file or str(record_path)
    try:
        record = records.read_record(Path(record_path), label)
    except records.RecordError as exc:
        raise DeriveError(str(exc)) from exc
    return explained(Run(register, Path(record_path), record, label), ref, ())


def explained(run: Run, ref: str, trail: tuple[str, ...]) -> Derivation:
    metric = run.register.by_ref.get(ref)
    if metric is None:
        raise DeriveError(f"{run.register.path.name} defines no {ref}")
    if ref in trail:
        raise DeriveError("cycle: " + " -> ".join((*trail, ref)))
    if metric.record is not None:
        return Derivation(ref, field_number(run, metric.record),
                          f"record {metric.record}")
    if metric.series is not None:
        return Derivation(ref, reduced(run, metric.series),
                          f"{series.formula_text(metric.series)}, "
                          f"{records.export_beside(run.path).name}")
    if metric.formula is not None:
        return computed(run, metric, (*trail, ref))
    raise DeriveError(no_data(metric))


def computed(run: Run, metric: Metric, trail: tuple[str, ...]) -> Derivation:
    steps: dict[str, Derivation] = {}

    def resolve(name: str) -> float:
        if name not in steps:
            steps[name] = (explained(run, name, trail) if METRIC_REF.match(name)
                           else Derivation(name, field_number(run, name), "record"))
        return steps[name].value

    try:
        value = arith.evaluate(arith.parse(metric.formula), resolve, dotted=True)
    except arith.ArithError as exc:
        raise DeriveError(f"{metric.ref}: {exc}") from exc
    return Derivation(metric.ref, value, metric.formula, tuple(steps.values()))


def field_number(run: Run, dotted: str) -> float:
    try:
        node = records.field(run.record, dotted, run.file)
        return records.number_at(node, f"{run.file}: {dotted}")
    except records.RecordError as exc:
        raise DeriveError(str(exc)) from exc


def reduced(run: Run, spec: series.Series) -> float:
    export = records.export_beside(run.path)
    label = str(Path(run.file).with_name(export.name))
    if not export.is_file():
        raise DeriveError(f"{label}: no export beside the point record")
    try:
        return series.value(export, spec, label)
    except series.SeriesError as exc:
        raise DeriveError(str(exc)) from exc


def no_data(metric: Metric) -> str:
    if metric.promql is not None:
        return (f"{metric.ref} is a series exported at every point — a number "
                f"for one run is a D ref with series: over it")
    return (f"{metric.ref} is written by hand ({metric.source}) — no run's data "
            f"holds it")
