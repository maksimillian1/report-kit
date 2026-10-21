"""`metrics.yaml`: an execution's metric register — what is read and from
where, each ref defined once. A runner exports every M ref with a promql."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .strict_yaml import UniqueKeyLoader, unknown_keys

REGISTER = "metrics.yaml"
SECTIONS = ("metrics",)

METRIC_REF = re.compile(r"^([MDRE])([1-9]\d*)$")
MEASURED_STATUS = re.compile(r"^(confirmed \d{4}-\d{2}-\d{2}|unconfirmed)$")

METRIC_KEYS = frozenset({"what", "promql", "source", "status", "notes"})


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
    text = {key: one_line(ref, key, spec[key]) for key in METRIC_KEYS if key in spec}
    for key in ("what", "status"):
        if not text.get(key):
            raise RegisterError(f"{ref}: '{key}' is required")
    if ("promql" in text) == ("source" in text):
        raise RegisterError(f"{ref}: give exactly one of promql (exported at every "
                            f"point) and source (anything else)")
    if found.group(1) == "M" and not MEASURED_STATUS.match(text["status"]):
        raise RegisterError(f"{ref}: status {text['status']!r} — an M ref is "
                            f"'confirmed YYYY-MM-DD' or 'unconfirmed'")
    if "promql" in text and found.group(1) != "M":
        raise RegisterError(f"{ref}: only an M ref is a query; a {found.group(1)} "
                            f"ref is written over other refs, in source")
    return Metric(ref=ref, what=text["what"], status=text["status"],
                  notes=text.get("notes", ""), promql=text.get("promql"),
                  source=text.get("source"))


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


def find_register(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / REGISTER
        if candidate.is_file():
            return candidate
    return None


def series_rows(register: Register) -> list[list[str]]:
    """The refs a runner exports, as `prometheus.export_range` takes them."""
    return [[metric.ref, metric.promql] for metric in register.exported]
