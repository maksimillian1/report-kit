"""A run's point record read back: a field by its dotted path, as a number or
as an instant. `reporting.py` writes the record; this only reads it."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

RECORD_SUFFIX = ".point.json"
EXPORT_SUFFIX = ".jsonl"


class RecordError(ValueError):
    """A record, or a field in it, that holds no usable number."""


def read_record(path: Path, file: str) -> dict:
    """`file` is how messages name the record: the path a reader wrote."""
    try:
        record = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RecordError(f"{file}: not readable JSON ({exc})") from exc
    return record if isinstance(record, dict) else {}


def field(record: dict, dotted: str, file: str) -> object:
    node: object = record
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            raise RecordError(f"{file}: no {dotted} (nothing at {key!r})")
        node = node[key]
    return node


def number_at(node: object, where: str) -> float:
    """A number stored as a string ("24") counts; null is a gap, never a zero."""
    if node is None:
        raise RecordError(f"{where} is null — a gap, not a zero")
    if isinstance(node, bool) or not isinstance(node, (int, float, str)):
        raise RecordError(f"{where} is a {type(node).__name__}, not a number")
    try:
        value = float(node)
    except ValueError as exc:
        raise RecordError(f"{where} is {node!r}, not a number") from exc
    if not math.isfinite(value):
        raise RecordError(f"{where} is {node!r}, not a finite number")
    return value


def instant_at(node: object, where: str) -> float:
    """Seconds since the epoch, from a number or an RFC 3339 string."""
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    try:
        return datetime.fromisoformat(str(node).replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise RecordError(f"{where} is {node!r}, not an instant") from None


def export_beside(record: Path) -> Path:
    return record.with_name(record.name.removesuffix(RECORD_SUFFIX) + EXPORT_SUFFIX)


def record_beside(export: Path) -> Path:
    return export.with_name(export.name.removesuffix(EXPORT_SUFFIX) + RECORD_SUFFIX)
