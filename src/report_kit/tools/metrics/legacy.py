"""Building `metrics.yaml` from what came before it: a hand-kept register table
beside `series.txt` and `guards.txt`. Where the table and a pipe file disagree
about a query, that is the drift the register exists to end, and it is
reported rather than settled."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from report_kit.refs import BOUND_TOKEN

from report_kit.register import RegisterError
from report_kit.execution_config import GUARDS as GUARDS_SECTION

from .views import BEGIN, BEGIN_RE, END, TABLE_HEADER

SERIES_FILE = Path("scripts") / "series.txt"
GUARDS_FILE = Path("scripts") / "guards.txt"

UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
ONE_CODE_SPAN = re.compile(r"^`([^`]+)`$")
ROW_REF = re.compile(r"^[MDRE][1-9]\d*$")
REGISTER_HEADER = [
    "# The metric register: every ref this execution defines, once. A runner",
    "# reads it; `report-kit metrics write` renders the register table from it.",
]
EXECUTION_HEADER = [
    "# How a point of this execution is run and judged. Imported from",
    "# guards.txt; add window_closes_when_back_to_idle, the deployments the",
    "# window waits for, before a runner from report-kit new-point reads it.",
]


@dataclass(frozen=True)
class PipeEntry:
    fields: tuple[str, ...]
    comments: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    start: int
    end: int
    rows: tuple[tuple[str, ...], ...]


def read_pipe_file(path: Path, fields: int) -> tuple[list[str], dict[str, PipeEntry]]:
    """(the comments above the first entry, ref -> entry with the comments
    directly above it). `refs.read_ref_file` drops comments; an import keeps
    them, because they explain the queries they sit on."""
    header: list[str] = []
    pending: list[str] = []
    entries: dict[str, PipeEntry] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            pending.append(line.lstrip("#").strip())
            continue
        if not line:
            if pending and not entries:
                header += pending + [""]
                pending = []
            continue
        parts = tuple(p.strip() for p in line.split("|", fields - 1))
        if len(parts) != fields:
            raise RegisterError(f"{path}: expected {fields} '|'-separated fields in {line!r}")
        entries[parts[0]] = PipeEntry(parts, tuple(pending))
        pending = []
    return trimmed(header), entries


def trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[-1]:
        lines.pop()
    return lines


def find_table(lines: list[str], path: Path) -> Table:
    starts = [i for i, line in enumerate(lines) if line.strip() == TABLE_HEADER[0]]
    if len(starts) != 1:
        raise RegisterError(f"{path}: expected one register table headed "
                            f"'{TABLE_HEADER[0]}', found {len(starts)}")
    start = starts[0]
    end = start + 2
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    rows = tuple(cells(line) for line in lines[start + 2:end])
    return Table(start, end, rows)


def cells(line: str) -> tuple[str, ...]:
    inner = line.strip()[1:-1]
    return tuple(cell.strip().replace(r"\|", "|") for cell in UNESCAPED_PIPE.split(inner))


def metric_entries(table: Table, series: dict[str, PipeEntry],
                   path: Path) -> list[tuple[str, dict, tuple[str, ...]]]:
    conflicts, out = [], []
    for row in table.rows:
        if len(row) != 5 or not ROW_REF.match(row[0]):
            raise RegisterError(f"{path}: cannot read register row {' | '.join(row)}")
        ref, what, source, status, notes = row
        spec = {"what": what}
        exported = series.get(ref)
        if exported is None:
            spec["source"] = source
        else:
            shown = ONE_CODE_SPAN.match(source)
            query = exported.fields[1]
            if not shown or shown.group(1) != query:
                conflicts.append(f"{ref}: the table shows {source!r}, "
                                 f"series.txt exports {query!r}")
            spec["promql"] = query
        spec["status"] = status
        if notes:
            spec["notes"] = notes
        out.append((ref, spec, exported.comments if exported else ()))
    missing = sorted(set(series) - {ref for ref, _, _ in out})
    if missing:
        conflicts.append(f"series.txt exports {', '.join(missing)}, which the "
                         f"register table does not define")
    if conflicts:
        raise RegisterError("the table and series.txt disagree — settle each, "
                            "then import again:\n  " + "\n  ".join(conflicts))
    return out


def guard_entries(guards: dict[str, PipeEntry],
                  series: dict[str, PipeEntry]) -> list[tuple[str, dict, tuple[str, ...]]]:
    """A guard whose query an exported metric already holds names that metric
    instead of copying the query."""
    exported = {entry.fields[1]: ref for ref, entry in series.items()}
    out = []
    for ref, entry in guards.items():
        _, bound, query = entry.fields
        spec: dict = dict(BOUND_TOKEN.findall(bound))
        if query in exported:
            spec["metric"] = exported[query]
        else:
            spec["promql"] = query
        out.append((ref, spec, entry.comments))
    return out


def scalar(value: str) -> str:
    """Plain when YAML reads it back unchanged, single-quoted otherwise."""
    try:
        plain = yaml.safe_load(f"k: {value}")
    except yaml.YAMLError:
        plain = None
    if isinstance(plain, dict) and plain.get("k") == value and value == value.strip():
        return value
    return "'" + value.replace("'", "''") + "'"


def bound_scalar(value: str) -> str:
    try:
        float(value)
        return value
    except ValueError:
        return scalar(value)


def yaml_section(name: str, header: list[str],
                 entries: list[tuple[str, dict, tuple[str, ...]]]) -> list[str]:
    lines = [f"# {line}".rstrip() for line in header]
    lines.append(f"{name}:")
    for ref, spec, comments in entries:
        lines += [f"  # {line}".rstrip() for line in comments]
        lines.append(f"  {ref}:")
        for key, value in spec.items():
            text = bound_scalar(value) if key in ("min", "max") else scalar(value)
            lines.append(f"    {key}: {text}")
    return lines


def imported(document: Path, series_file: Path,
             guards_file: Path) -> tuple[str, str, str]:
    """(metrics.yaml's text, execution.yaml's text, the document with its
    table wrapped in the markers). Nothing is written here."""
    lines = document.read_text(encoding="utf-8").splitlines()
    if any(BEGIN_RE.match(line) for line in lines):
        raise RegisterError(f"{document} already holds the marked block — "
                            f"this register was imported before")
    table = find_table(lines, document)
    series_header, series = read_pipe_file(series_file, 2)
    guards_header, guards = read_pipe_file(guards_file, 3)
    register = (REGISTER_HEADER + [""]
                + yaml_section("metrics", series_header,
                               metric_entries(table, series, document)))
    execution = (EXECUTION_HEADER + [""]
                 + yaml_section(GUARDS_SECTION, guards_header, guard_entries(guards, series)))
    marked = (lines[:table.start] + [BEGIN, ""] + lines[table.start:table.end]
              + ["", END] + lines[table.end:])
    return ("\n".join(register) + "\n", "\n".join(execution) + "\n",
            "\n".join(marked) + "\n")
