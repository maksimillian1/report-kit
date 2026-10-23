"""An exported ref reduced to one number.

`ref`, `across`, `per`, `where`, `settle_on`, `until` and `reduce` are the
whole vocabulary, shared by a D ref's `series:` in `metrics.yaml` and by an
export `from:` in `report-values.yaml`. `templates/formats.md` has the rules.
"""

from __future__ import annotations

import math
import operator
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from . import jsonl, records

REDUCTIONS = {
    "max": max,
    "min": min,
    "mean": statistics.fmean,
    "last": lambda samples: samples[-1],
}
COMBINATIONS = {
    "sum": math.fsum,
    "max": max,
    "min": min,
    "mean": statistics.fmean,
}
COMPARISONS = {">": operator.gt, ">=": operator.ge,
               "<": operator.lt, "<=": operator.le}
MASK = re.compile(r"^\s*(\S+?)\s*(>=|<=|>|<)\s*(\S+)\s*$")
SERIES_KEYS = frozenset({"ref", "reduce", "across", "per", "where",
                         "settle_on", "until"})

Samples = dict[float, float]


class SeriesError(ValueError):
    """A reduction that is malformed, or that the export cannot answer."""


@dataclass(frozen=True)
class Mask:
    ref: str
    op: str
    bound: float

    def __str__(self) -> str:
        return f"{self.ref} {self.op} {self.bound:g}"


@dataclass(frozen=True)
class Series:
    ref: str
    reduce: str
    per: str | None = None
    where: Mask | None = None
    across: str | None = None
    settle_on: str | None = None
    until: str | None = None

    @property
    def refs(self) -> list[str]:
        """Every exported ref the reduction reads."""
        named = [self.ref, self.per, self.where and self.where.ref, self.settle_on]
        return [ref for ref in named if ref]


def read_series(raw: object, also: frozenset = frozenset()) -> Series:
    """`also` names keys the caller handles itself, such as a `from:`'s file."""
    if not isinstance(raw, dict):
        raise SeriesError(f"must be a mapping, not {type(raw).__name__}")
    unknown = sorted(str(key) for key in raw if key not in SERIES_KEYS | also)
    if unknown:
        raise SeriesError(f"does not take {', '.join(unknown)} here; it takes "
                          f"{', '.join(sorted(SERIES_KEYS | also))}")
    reduce = text(raw, "reduce")
    if reduce not in REDUCTIONS:
        raise SeriesError(f"reduce {reduce!r} is not one of {'/'.join(REDUCTIONS)}")
    return Series(ref=text(raw, "ref"), reduce=reduce,
                  per=optional(raw, "per"), where=mask_of(raw.get("where")),
                  across=across_of(raw), settle_on=optional(raw, "settle_on"),
                  until=optional(raw, "until"))


def text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if value is None or isinstance(value, (dict, list)) or not str(value).strip():
        raise SeriesError(f"needs {key}:")
    return str(value).strip()


def optional(raw: dict, key: str) -> str | None:
    return None if raw.get(key) is None else text(raw, key)


def across_of(raw: dict) -> str | None:
    across = optional(raw, "across")
    if across is not None and across not in COMBINATIONS:
        raise SeriesError(f"across {across!r} is not one of {'/'.join(COMBINATIONS)}")
    return across


def mask_of(raw: object) -> Mask | None:
    if raw is None:
        return None
    match = MASK.match(str(raw))
    if not match:
        raise SeriesError(f"where {raw!r} is not '<ref> <op> <number>' with op "
                          f"one of {' '.join(COMPARISONS)}")
    ref, op, bound = match.groups()
    try:
        return Mask(ref, op, float(bound))
    except ValueError as exc:
        raise SeriesError(f"where {raw!r} compares with {bound!r}, not a "
                          f"number") from exc


def value(export: Path, spec: Series, file: str) -> float:
    """What the export says, at full precision. `file` is how messages name it."""
    exported = series_by_ref(export, file)
    samples = combined(exported, spec.ref, spec, file)
    if spec.where:
        samples = masked(samples, combined(exported, spec.where.ref, spec, file),
                         spec.where)
    if spec.per:
        samples = divided(samples, combined(exported, spec.per, spec, file),
                          spec, file)
    samples = segment(samples, exported, export, spec, file)
    if not samples:
        raise SeriesError(f"{file}: {describe(spec)} has no samples — a gap, "
                          f"not a zero")
    in_time_order = [samples[timestamp] for timestamp in sorted(samples)]
    return REDUCTIONS[spec.reduce](in_time_order)


def series_by_ref(export: Path, file: str) -> dict[str, list]:
    try:
        lines = jsonl.read_lines(export)
    except (OSError, ValueError) as exc:
        raise SeriesError(f"{file}: {exc}") from exc
    return {str(line.get("metric")): line.get("result") or []
            for line in lines if isinstance(line, dict)}


def combined(exported: dict[str, list], ref: str, spec: Series,
             file: str) -> Samples:
    """One sample per timestamp: the ref's only series, or its series
    combined by `across:`. Several series and no `across:` is refused."""
    if ref not in exported:
        raise SeriesError(f"{file}: the export holds no ref {ref}")
    series = [one for one in exported[ref] if isinstance(one, dict)]
    if len(series) > 1 and spec.across is None:
        labels = "; ".join(jsonl.label_summary(one.get("metric") or {})
                           for one in series[:3])
        raise SeriesError(f"{file}: {ref} holds {len(series)} series "
                          f"({labels}{'; …' if len(series) > 3 else ''}) — "
                          f"say how to combine them with across: "
                          f"{'|'.join(COMBINATIONS)}")
    at: dict[float, list[float]] = {}
    for one in series:
        for timestamp, sample in jsonl.parse_values(one.get("values", [])):
            at.setdefault(timestamp, []).append(sample)
    combine = COMBINATIONS[spec.across or "sum"]
    return {timestamp: combine(samples) for timestamp, samples in at.items()}


def segment(samples: Samples, exported: dict[str, list], export: Path,
            spec: Series, file: str) -> Samples:
    """The samples from the instant `settle_on` last changed — a window holds
    the system reacting, then settled, and a mean across both describes
    neither — up to the instant `until` names in the run's point record."""
    start = settle_instant(exported, spec, file) if spec.settle_on else None
    end = until_instant(export, spec, file) if spec.until else None
    return {timestamp: sample for timestamp, sample in samples.items()
            if (start is None or timestamp >= start)
            and (end is None or timestamp <= end)}


def settle_instant(exported: dict[str, list], spec: Series, file: str) -> float | None:
    """None when `settle_on` never changed: the window holds one regime."""
    series = combined(exported, spec.settle_on, spec, file)
    instants = jsonl.changes(sorted(series.items()))
    return max(instants) if instants else None


def until_instant(export: Path, spec: Series, file: str) -> float:
    record = records.record_beside(export)
    label = str(Path(file).with_name(record.name))
    if not record.is_file():
        raise SeriesError(f"{label}: no point record beside the export, so "
                          f"until: {spec.until} has nothing to read")
    try:
        node = records.field(records.read_record(record, label), spec.until, label)
        return records.instant_at(node, f"{label}: {spec.until}")
    except records.RecordError as exc:
        raise SeriesError(str(exc)) from exc


def masked(samples: Samples, by: Samples, mask: Mask) -> Samples:
    keep = COMPARISONS[mask.op]
    return {timestamp: sample for timestamp, sample in samples.items()
            if timestamp in by and keep(by[timestamp], mask.bound)}


def divided(samples: Samples, by: Samples, spec: Series, file: str) -> Samples:
    ratios = {}
    for timestamp, sample in samples.items():
        if timestamp not in by:
            continue
        if by[timestamp] == 0:
            raise SeriesError(f"{file}: {spec.per} is 0 at {timestamp} — "
                              f"exclude it with where:")
        ratios[timestamp] = sample / by[timestamp]
    return ratios


def describe(spec: Series) -> str:
    text = spec.ref if spec.across is None else \
        f"{spec.ref} ({spec.across} across series)"
    if spec.per:
        text += f" per {spec.per}"
    if spec.where:
        text += f" where {spec.where}"
    if spec.settle_on:
        text += f" once {spec.settle_on} settled"
    if spec.until:
        text += f" until {spec.until}"
    return text


def formula_text(spec: Series) -> str:
    """The reduction as one readable phrase: `mean of M7 per M5 where M5 > 1`."""
    return f"{spec.reduce} of {describe(spec)}"
