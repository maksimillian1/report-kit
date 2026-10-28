"""evidence.py — a reported value, read back out of the data files a run committed.

A `from:` in `report-values.yaml` names one of three shapes, and nothing else:

    {file: data/r1.point.json, path: client.p95_ms, scale: 1}
    {file: data/r1.jsonl, ref: M7, per: M5, where: "M5 > 1", reduce: mean, scale: 1000}
    {file: data/r1.jsonl, ref: M3, across: max, reduce: max}
    {file: data/r1.jsonl, ref: M5, settle_on: M4, until: generator_window.end, reduce: mean}
    {file: data/r1.point.json, metric: D9, scale: 1}

The last works the value out the way the execution's `metrics.yaml` defines
that ref, so the definition is written once and every value of it follows.
`templates/formats.md` has the rules; this module only reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from report_kit import derive, records, series
from report_kit.register import METRIC_REF, RegisterError, read_register, register_above
from report_kit.series import Mask
from report_kit.strict_yaml import unknown_keys

POINT_KEYS = frozenset({"file", "path", "scale"})
EXPORT_KEYS = frozenset({"file", "scale"})
METRIC_KEYS = frozenset({"file", "metric", "scale"})
SHAPES = ("path", "metric", "ref")
RECORD_SUFFIX = records.RECORD_SUFFIX
EXPORT_SUFFIX = records.EXPORT_SUFFIX

RELATIVE_TOLERANCE = 1e-9
ABSOLUTE_TOLERANCE = 1e-12


class EvidenceError(Exception):
    """A `from:` that names no value: malformed, unreadable, or a gap."""


class MissingEvidence(EvidenceError):
    """The data file a `from:` names is not there."""


@dataclass(frozen=True)
class PointSource:
    file: str
    path: str
    scale: float = 1.0


@dataclass(frozen=True)
class ExportSource:
    file: str
    ref: str
    reduce: str
    per: str | None = None
    where: Mask | None = None
    scale: float = 1.0
    across: str | None = None
    settle_on: str | None = None
    until: str | None = None

    @property
    def series(self) -> series.Series:
        return series.Series(ref=self.ref, reduce=self.reduce, per=self.per,
                             where=self.where, across=self.across,
                             settle_on=self.settle_on, until=self.until)


@dataclass(frozen=True)
class MetricSource:
    file: str
    metric: str
    scale: float = 1.0


Source = PointSource | ExportSource | MetricSource


def read_source(raw: object) -> Source:
    if not isinstance(raw, dict):
        raise EvidenceError(f"from: must be a mapping, not "
                            f"{type(raw).__name__}")
    named = [key for key in SHAPES if key in raw]
    if len(named) > 1:
        raise EvidenceError(f"from: names both {named[0]}: and {named[1]}: — "
                            f"one place a value is read from, not both")
    if "path" in raw:
        return point_source(raw)
    if "metric" in raw:
        return metric_source(raw)
    if "ref" in raw:
        return export_source(raw)
    raise EvidenceError("from: needs path: (a point record), metric: (a register "
                        "ref) or ref: (an export)")


def point_source(raw: dict) -> PointSource:
    refuse_unknown_keys(raw, POINT_KEYS)
    return PointSource(file=required_text(raw, "file"),
                       path=required_text(raw, "path"),
                       scale=scale_of(raw))


def export_source(raw: dict) -> ExportSource:
    try:
        spec = series.read_series(raw, also=EXPORT_KEYS)
    except series.SeriesError as exc:
        raise EvidenceError(f"from: {exc}") from exc
    return ExportSource(file=required_text(raw, "file"), ref=spec.ref,
                        reduce=spec.reduce, per=spec.per, where=spec.where,
                        scale=scale_of(raw), across=spec.across,
                        settle_on=spec.settle_on, until=spec.until)


def metric_source(raw: dict) -> MetricSource:
    refuse_unknown_keys(raw, METRIC_KEYS)
    file, metric = required_text(raw, "file"), required_text(raw, "metric")
    if not METRIC_REF.match(metric):
        raise EvidenceError(f"from: metric {metric!r} is not a ref of the run's "
                            f"own register, such as D9")
    if not file.endswith(RECORD_SUFFIX):
        raise EvidenceError(f"from: metric: reads a run's {RECORD_SUFFIX}, "
                            f"not {file}")
    return MetricSource(file=file, metric=metric, scale=scale_of(raw))


def refuse_unknown_keys(raw: dict, allowed: frozenset) -> None:
    unknown = unknown_keys(raw, allowed)
    if unknown:
        raise EvidenceError(f"from: does not take {', '.join(unknown)} here; "
                            f"it takes {', '.join(sorted(allowed))}")


def required_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if value is None or isinstance(value, (dict, list)) or not str(value).strip():
        raise EvidenceError(f"from: needs {key}:")
    return str(value).strip()


def scale_of(raw: dict) -> float:
    scale = raw.get("scale", 1)
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        raise EvidenceError(f"from: scale must be a number, not {scale!r}")
    return float(scale)


def reproduce(source: Source, root: Path) -> float:
    """What the data says, at full precision, scale applied."""
    path = Path(root) / source.file
    if not path.is_file():
        raise MissingEvidence(f"{source.file}: no such data file")
    try:
        if isinstance(source, PointSource):
            found = point_value(path, source)
        elif isinstance(source, MetricSource):
            found = metric_value(path, source, Path(root))
        else:
            found = series.value(path, source.series, source.file)
    except (records.RecordError, series.SeriesError, derive.DeriveError) as exc:
        raise EvidenceError(str(exc)) from exc
    return found * source.scale


def agrees(stored: float, reproduced: float) -> bool:
    return math.isclose(stored, reproduced, rel_tol=RELATIVE_TOLERANCE,
                        abs_tol=ABSOLUTE_TOLERANCE)


def point_value(path: Path, source: PointSource) -> float:
    node = records.field(records.read_record(path, source.file), source.path,
                         source.file)
    return records.number_at(node, f"{source.file}: {source.path}")


def metric_register(path: Path, source: MetricSource, root: Path):
    """The register of the execution the run belongs to: the first above it."""
    found = register_above(path.parent, root)
    if found is None:
        raise EvidenceError(f"{source.file}: no metrics.yaml between it and the "
                            f"report root, so nothing defines {source.metric}")
    try:
        return read_register(found)
    except RegisterError as exc:
        raise EvidenceError(str(exc)) from exc


def metric_value(path: Path, source: MetricSource, root: Path) -> float:
    register = metric_register(path, source, root)
    return derive.derive(register, source.metric, path, source.file)


def describe(source: ExportSource) -> str:
    return series.describe(source.series)
