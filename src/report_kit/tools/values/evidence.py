"""evidence.py — a reported value, read back out of the data files a run committed.

A `from:` in `report-values.yaml` names one of two shapes, and nothing else:

    {file: data/r1.point.json, path: client.p95_ms, scale: 1}
    {file: data/r1.jsonl, ref: M7, per: M5, where: "M5 > 1", reduce: mean, scale: 1000}
    {file: data/r1.jsonl, ref: M3, across: max, reduce: max}
    {file: data/r1.jsonl, ref: M5, settle_on: M4, until: generator_window.end, reduce: mean}

`templates/formats.md` has the rules; this module only reads.
"""

from __future__ import annotations

import json
import math
import operator
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from report_kit import jsonl
from report_kit.strict_yaml import unknown_keys

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

POINT_KEYS = frozenset({"file", "path", "scale"})
EXPORT_KEYS = frozenset({"file", "ref", "reduce", "across", "per", "where",
                         "scale", "settle_on", "until"})
RECORD_SUFFIX = ".point.json"
EXPORT_SUFFIX = ".jsonl"

RELATIVE_TOLERANCE = 1e-9
ABSOLUTE_TOLERANCE = 1e-12


class EvidenceError(Exception):
    """A `from:` that names no value: malformed, unreadable, or a gap."""


class MissingEvidence(EvidenceError):
    """The data file a `from:` names is not there."""


@dataclass(frozen=True)
class Mask:
    ref: str
    op: str
    bound: float

    def __str__(self) -> str:
        return f"{self.ref} {self.op} {self.bound:g}"


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


Source = PointSource | ExportSource


def read_source(raw: object) -> Source:
    if not isinstance(raw, dict):
        raise EvidenceError(f"from: must be a mapping, not "
                            f"{type(raw).__name__}")
    if "path" in raw and "ref" in raw:
        raise EvidenceError("from: names both path: and ref: — a point "
                            "record or an export, not both")
    if "path" in raw:
        return point_source(raw)
    if "ref" in raw:
        return export_source(raw)
    raise EvidenceError("from: needs path: (a point record) or ref: (an export)")


def point_source(raw: dict) -> PointSource:
    refuse_unknown_keys(raw, POINT_KEYS)
    return PointSource(file=required_text(raw, "file"),
                       path=required_text(raw, "path"),
                       scale=scale_of(raw))


def export_source(raw: dict) -> ExportSource:
    refuse_unknown_keys(raw, EXPORT_KEYS)
    reduce = required_text(raw, "reduce")
    if reduce not in REDUCTIONS:
        raise EvidenceError(f"from: reduce {reduce!r} is not one of "
                            f"{'/'.join(REDUCTIONS)}")
    per = raw.get("per")
    return ExportSource(file=required_text(raw, "file"),
                        ref=required_text(raw, "ref"),
                        reduce=reduce,
                        per=None if per is None else required_text(raw, "per"),
                        where=mask_of(raw.get("where")),
                        scale=scale_of(raw),
                        across=across_of(raw),
                        settle_on=optional_text(raw, "settle_on"),
                        until=optional_text(raw, "until"))


def optional_text(raw: dict, key: str) -> str | None:
    return None if raw.get(key) is None else required_text(raw, key)


def across_of(raw: dict) -> str | None:
    if raw.get("across") is None:
        return None
    across = required_text(raw, "across")
    if across not in COMBINATIONS:
        raise EvidenceError(f"from: across {across!r} is not one of "
                            f"{'/'.join(COMBINATIONS)}")
    return across


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


def mask_of(raw: object) -> Mask | None:
    if raw is None:
        return None
    match = MASK.match(str(raw))
    if not match:
        raise EvidenceError(f"from: where {raw!r} is not '<ref> <op> <number>' "
                            f"with op one of {' '.join(COMPARISONS)}")
    ref, op, bound = match.groups()
    try:
        return Mask(ref, op, float(bound))
    except ValueError as exc:
        raise EvidenceError(f"from: where {raw!r} compares with "
                            f"{bound!r}, not a number") from exc


def reproduce(source: Source, root: Path) -> float:
    """What the data says, at full precision, scale applied."""
    path = Path(root) / source.file
    if not path.is_file():
        raise MissingEvidence(f"{source.file}: no such data file")
    if isinstance(source, PointSource):
        return point_value(path, source) * source.scale
    return export_value(path, source) * source.scale


def agrees(stored: float, reproduced: float) -> bool:
    return math.isclose(stored, reproduced, rel_tol=RELATIVE_TOLERANCE,
                        abs_tol=ABSOLUTE_TOLERANCE)


def point_value(path: Path, source: PointSource) -> float:
    node = record_field(path, source.file, source.path)
    return number_at(node, f"{source.file}: {source.path}")


def record_field(path: Path, file: str, dotted: str) -> object:
    try:
        node = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"{file}: not readable JSON ({exc})") from exc
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            raise EvidenceError(f"{file}: no {dotted} (nothing at {key!r})")
        node = node[key]
    return node


def number_at(node: object, where: str) -> float:
    if node is None:
        raise EvidenceError(f"{where} is null — a gap, not a zero")
    if isinstance(node, bool) or not isinstance(node, (int, float, str)):
        raise EvidenceError(f"{where} is a {type(node).__name__}, not a number")
    try:
        value = float(node)
    except ValueError as exc:
        raise EvidenceError(f"{where} is {node!r}, not a number") from exc
    if not math.isfinite(value):
        raise EvidenceError(f"{where} is {node!r}, not a finite number")
    return value


def export_value(path: Path, source: ExportSource) -> float:
    exported = series_by_ref(path, source.file)
    samples = combined(exported, source.ref, source)
    if source.where:
        samples = masked(samples, combined(exported, source.where.ref, source),
                         source.where)
    if source.per:
        samples = divided(samples, combined(exported, source.per, source),
                          source)
    samples = segment(samples, exported, path, source)
    if not samples:
        raise EvidenceError(f"{source.file}: {describe(source)} has no "
                            f"samples — a gap, not a zero")
    in_time_order = [samples[timestamp] for timestamp in sorted(samples)]
    return REDUCTIONS[source.reduce](in_time_order)


def series_by_ref(path: Path, file: str) -> dict[str, list]:
    try:
        lines = jsonl.read_lines(path)
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"{file}: {exc}") from exc
    return {str(line.get("metric")): line.get("result") or []
            for line in lines if isinstance(line, dict)}


def combined(exported: dict[str, list], ref: str,
             source: ExportSource) -> dict[float, float]:
    """One sample per timestamp: the ref's only series, or its series
    combined by `across:`. Several series and no `across:` is refused."""
    if ref not in exported:
        raise EvidenceError(f"{source.file}: the export holds no ref {ref}")
    series = [one for one in exported[ref] if isinstance(one, dict)]
    if len(series) > 1 and source.across is None:
        labels = "; ".join(jsonl.label_summary(one.get("metric") or {})
                           for one in series[:3])
        raise EvidenceError(f"{source.file}: {ref} holds {len(series)} series "
                            f"({labels}{'; …' if len(series) > 3 else ''}) — "
                            f"say how to combine them with across: "
                            f"{'|'.join(COMBINATIONS)}")
    at: dict[float, list[float]] = {}
    for one in series:
        for timestamp, value in jsonl.parse_values(one.get("values", [])):
            at.setdefault(timestamp, []).append(value)
    combine = COMBINATIONS[source.across or "sum"]
    return {timestamp: combine(values) for timestamp, values in at.items()}


def segment(samples: dict[float, float], exported: dict[str, list], path: Path,
            source: ExportSource) -> dict[float, float]:
    """The samples from the instant `settle_on` last changed — a window holds
    the system reacting, then settled, and a mean across both describes
    neither — up to the instant `until` names in the run's point record."""
    start = settle_instant(exported, source) if source.settle_on else None
    end = until_instant(path, source) if source.until else None
    return {timestamp: value for timestamp, value in samples.items()
            if (start is None or timestamp >= start)
            and (end is None or timestamp <= end)}


def settle_instant(exported: dict[str, list], source: ExportSource) -> float | None:
    """None when `settle_on` never changed: the window holds one regime."""
    series = combined(exported, source.settle_on, source)
    instants = jsonl.changes(sorted(series.items()))
    return max(instants) if instants else None


def until_instant(path: Path, source: ExportSource) -> float:
    record = path.with_name(path.name.removesuffix(EXPORT_SUFFIX) + RECORD_SUFFIX)
    file = str(Path(source.file).with_name(record.name))
    if not record.is_file():
        raise EvidenceError(f"{file}: no point record beside the export, so "
                            f"until: {source.until} has nothing to read")
    node = record_field(record, file, source.until)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    try:
        return datetime.fromisoformat(str(node).replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise EvidenceError(f"{file}: {source.until} is {node!r}, not an "
                            f"instant") from None


def masked(samples: dict[float, float], by: dict[float, float],
           mask: Mask) -> dict[float, float]:
    keep = COMPARISONS[mask.op]
    return {timestamp: value for timestamp, value in samples.items()
            if timestamp in by and keep(by[timestamp], mask.bound)}


def divided(samples: dict[float, float], by: dict[float, float],
            source: ExportSource) -> dict[float, float]:
    ratios = {}
    for timestamp, value in samples.items():
        if timestamp not in by:
            continue
        if by[timestamp] == 0:
            raise EvidenceError(f"{source.file}: {source.per} is 0 at "
                                f"{timestamp} — exclude it with where:")
        ratios[timestamp] = value / by[timestamp]
    return ratios


def describe(source: ExportSource) -> str:
    text = source.ref if source.across is None else \
        f"{source.ref} ({source.across} across series)"
    if source.per:
        text += f" per {source.per}"
    if source.where:
        text += f" where {source.where}"
    if source.settle_on:
        text += f" once {source.settle_on} settled"
    if source.until:
        text += f" until {source.until}"
    return text
