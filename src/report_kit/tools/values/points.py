"""points.py — what one run contributes to `report-values.yaml`, and which entries
belong to it.

A `points:` block is a template: the entries one point adds, with `{point}`
where its label goes. A value that came from a point carries `point: <label>`,
and that key is the only thing membership is read from. `templates/formats.md`
has the rules; this module only computes.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Callable

from report_kit.records import EXPORT_SUFFIX, RECORD_SUFFIX

PLACEHOLDER = "{point}"
REPEAT_LETTERS = "bcdefghijklmnopqrstuvwxyz"
LABEL = re.compile(r"^[A-Za-z0-9_]+$")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
IDENTIFIER = re.compile(r"(?<![\w.])[A-Za-z_]\w*")
TEMPLATE_KEYS = frozenset({"axis", "label", "held", "values"})
FILLED_BY_ADD = ("ref", "value", "point")


class PointError(Exception):
    """A template, a point record or a label that cannot be used."""


@dataclass(frozen=True)
class Template:
    axis: str
    label: str
    held: dict
    entries: dict


def read_template(raw: object) -> Template:
    if not isinstance(raw, dict):
        raise PointError("points: must be a mapping")
    unknown = sorted(str(key) for key in raw if key not in TEMPLATE_KEYS)
    if unknown:
        raise PointError(f"points: does not take {', '.join(unknown)}")
    axis, held, entries = raw.get("axis"), raw.get("held") or {}, raw.get("values")
    if not isinstance(axis, str) or not axis:
        raise PointError("points: needs axis:, the point record field that "
                         "names a point")
    if not isinstance(held, dict) or not all(
            isinstance(name, str) and NAME.match(name) for name in held.values()):
        raise PointError("points: held: maps a point record field to the registered "
                         "value holding its number, so the number is written once")
    if not isinstance(entries, dict) or not entries:
        raise PointError("points: needs values:, what one point adds")
    for pattern, spec in entries.items():
        check_entry_template(str(pattern), spec)
    return Template(axis, str(raw.get("label") or f"{axis}{{{axis}}}"),
                    held, entries)


def check_entry_template(pattern: str, spec: object) -> None:
    if PLACEHOLDER not in pattern:
        raise PointError(f"points: {pattern} has no {PLACEHOLDER} in its name")
    if not isinstance(spec, dict):
        raise PointError(f"points: {pattern} must be a mapping")
    present = [key for key in FILLED_BY_ADD if key in spec]
    if present:
        raise PointError(f"points: {pattern} sets {', '.join(present)}, which "
                         f"add-point fills in")
    source = spec.get("from")
    if source is not None and (not isinstance(source, dict) or "file" in source):
        raise PointError(f"points: {pattern} from: must be a mapping without "
                         f"file:, which add-point fills in")


def record_fields(record: dict) -> dict:
    """The record's top-level fields and its settings, a number stored as a
    string ("24") turned back into one."""
    settings = record.get("settings") if isinstance(record.get("settings"), dict) else {}
    return {key: as_number(value) for key, value in {**settings, **record}.items()}


def as_number(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        number = float(value)
    except ValueError:
        return value
    return number if math.isfinite(number) else value


def base_label(template: Template, record: dict) -> str:
    fields = record_fields(record)
    if template.axis not in fields:
        raise PointError(f"the point record has no {template.axis}, the axis "
                         f"points: names")
    try:
        label = template.label.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        raise PointError(f"points: label {template.label!r} does not format "
                         f"with this record ({exc})") from exc
    check_label(label)
    return label


def check_label(label: str) -> None:
    if not LABEL.match(label):
        raise PointError(f"label {label!r} may hold only letters, digits and _")


def free_label(base: str, taken: Callable[[str], bool]) -> str:
    """`base`, or the first of base+b … base+z nobody has: n08, n08b, n08c."""
    for candidate in [base] + [base + letter for letter in REPEAT_LETTERS]:
        if not taken(candidate):
            return candidate
    raise PointError(f"{base} through {base}z are all taken; name this point "
                     f"with --as")


def labels_in_use(entries: dict[str, dict]) -> set[str]:
    return {str(spec["point"]) for spec in entries.values() if "point" in spec}


def members(entries: dict[str, dict], label: str) -> list[str]:
    return [name for name, spec in entries.items()
            if str(spec.get("point")) == label]


def validity_problems(record: dict) -> list[str]:
    export = record.get("export") if isinstance(record.get("export"), dict) else {}
    prices = record.get("prices") if isinstance(record.get("prices"), dict) else {}
    found = {"guard_failures": record.get("guard_failures"),
             "empty_refs": record.get("empty_refs") or export.get("empty_refs"),
             "doubts": record.get("doubts"),
             "price doubts": prices.get("doubts")}
    return [f"{field}: {', '.join(str(item) for item in items)}"
            for field, items in found.items() if items]


def held_mismatches(template: Template, record: dict,
                    held: dict[str, float]) -> list[str]:
    """`held` is the number of each value `held:` names, by name."""
    fields = record_fields(record)
    return [f"{field} is {fields.get(field, 'absent')!r}, the grid holds "
            f"{held[name]:g} ({name})" for field, name in template.held.items()
            if fields.get(field) != held[name]]


def expand(template: Template, label: str, point_file: str) -> dict[str, dict]:
    """The entries one point adds, `{point}` filled in and every `from:`
    pointed at the point's own record, or the export beside it."""
    added = {}
    for pattern, spec in template.entries.items():
        name = filled(str(pattern), label)
        if not NAME.match(name):
            raise PointError(f"{pattern} with label {label} gives {name!r}, "
                             f"not a value name")
        entry = {key: filled(value, label) for key, value in spec.items()}
        if "from" in entry:
            entry["from"] = {"file": data_file(point_file, entry["from"]),
                              **entry["from"]}
        added[name] = {"kind": entry.pop("kind", None), "point": label,
                       **entry}
    return added


def filled(value: object, label: str) -> object:
    if isinstance(value, str):
        return value.replace(PLACEHOLDER, label)
    if isinstance(value, dict):
        return {key: filled(item, label) for key, item in value.items()}
    return value


def run_files(point_file: str) -> set[str]:
    """The point record and the export beside it, as `from: file` names them."""
    files = {point_file}
    if point_file.endswith(RECORD_SUFFIX):
        files.add(point_file[:-len(RECORD_SUFFIX)] + EXPORT_SUFFIX)
    return {os.path.normpath(name) for name in files}


def readers(entries: dict[str, dict], point_file: str) -> list[str]:
    """The values whose `from:` already reads this run's record or export."""
    files = run_files(point_file)
    return [name for name, spec in entries.items()
            if isinstance(spec.get("from"), dict)
            and os.path.normpath(str(spec["from"].get("file"))) in files]


def data_file(point_file: str, source: dict) -> str:
    if "ref" not in source:
        return point_file
    if not point_file.endswith(RECORD_SUFFIX):
        raise PointError(f"{point_file} is not a <run>{RECORD_SUFFIX}, so there "
                         f"is no export beside it for ref: {source['ref']}")
    return point_file[:-len(RECORD_SUFFIX)] + EXPORT_SUFFIX


def renamed(name: str, old: str, new: str) -> str:
    """A member's name with its label replaced where it stands alone between
    underscores — n08 in drain_n08, never inside drain_n08b."""
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])")
    if not pattern.search(name):
        raise PointError(f"{name} carries point: {old} but its name does not "
                         f"contain {old}; rename it by hand")
    return pattern.sub(new, name)


def renamed_formula(formula: str, names: dict[str, str]) -> str:
    return IDENTIFIER.sub(lambda m: names.get(m.group(), m.group()), formula)
