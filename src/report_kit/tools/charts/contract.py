"""What a chart CSV may contain, how a row is read, whether one file keeps it.

The CSVs are the consumer's, so `required` is the shortest list a chart can
draw anything from and everything else is a note rather than a failure.
Whether a cell still agrees with the report is the registry's question — see
`charts.md`, which also covers the two open schemas and the note/problem line.
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from .errors import Skip


WORKLOADS = "*workloads"            # `derived` sources taken from the header
REPLICAS_RE = re.compile(r"^replicas_([A-Za-z0-9][\w-]*)$")
PLACEHOLDER = re.compile(r"⟨[^⟩]*⟩")

SCHEMA = {
    "frontier-jobs.csv": {
        "serves": "report §3.2 chart and §3.3 · the execution's run matrix",
        "required": ["n_set", "throughput"],
        "optional": ["run", "unit", "period", "n_reached", "n_peak",
                     "usd_per_1m_units", "duration", "compute_usd",
                     "other_usd", "usd_per_run", "unit_count", "mark",
                     "dominated", "note"],
        "derived": [("usd_per_1m_units", ("usd_per_run", "unit_count"),
                     lambda run, units: run / units * 1e6,
                     "usd_per_1m_units = usd_per_run / unit_count * 1e6")],
        "tolerance": 0.005,
    },
    "frontier-api.csv": {
        "serves": "report §3.2 chart · the execution's run matrix",
        "required": ["offered_rps", "p95_ms"],
        "optional": ["run", "unit", "served_rps", "converge_s", "p50_ms",
                     "p95_converged_ms", "error_pct", "error_converged_pct",
                     "usd_per_1k_units", "reference_ms", "reference_note",
                     "mark", "excluded", "note"],
        "series": "replicas",
        "derived": [],
        "tolerance": 0.005,
    },
    "split-jobs.csv": {
        "serves": "report §4.2 · the execution's split-cost table",
        "required": ["n_set"],
        "optional": ["unused_fleet", "workload_total", "mark", "note"],
        "workloads": True,
        "derived": [("workload_total", WORKLOADS, lambda *parts: sum(parts),
                     "workload_total = every workload column added up")],
        "tolerance": 0.005,
    },
    "floor-blocks.csv": {
        "serves": "report §4.1 Floor",
        "required": ["block", "usd_per_month"],
        "optional": ["label", "mark", "note"],
        "derived": [],
        "tolerance": 0.005,
    },
    "amortization.csv": {
        "serves": "report §4.3",
        "required": ["unit", "volume", "effective_usd_per_unit"],
        "optional": ["floor_share_pct", "crossover_volume"],
        "derived": [],
        "tolerance": 0.005,
    },
}

# Named rather than measured, so `--check` does not ask them to be numbers.
NAMING = frozenset({"block", "unit", "run", "label", "mark", "note",
                    "reference_note"})

def read_table(path: Path) -> tuple[list[str], list[dict]]:
    """A CSV as (header, rows). The header comes back even with no rows, so a
    scaffolded file can be told its columns are placeholders and not only that
    nobody has filled it in yet."""
    if not path.exists():
        raise Skip(f"no such file: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def read_rows(path: Path) -> list[dict]:
    return read_table(path)[1]


def num(row: dict, key: str):
    raw = (row.get(key) or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def cell(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def flag(row: dict, key: str) -> bool:
    return cell(row, key).lower() in {"1", "true", "yes"}


def header_of(rows: list[dict]) -> list[str]:
    return list(rows[0].keys()) if rows else []


def declared(spec: dict) -> set[str]:
    return set(spec["required"]) | set(spec["optional"])


def placeholders(header: list[str]) -> list[str]:
    return [c for c in header if c and PLACEHOLDER.search(c)]


def workload_columns(spec: dict, header: list[str]) -> list[str]:
    if not spec.get("workloads"):
        return []
    known = declared(spec) | set(placeholders(header))
    return [c for c in header if c and c not in known]


def series_columns(spec: dict, header: list[str]) -> list[tuple[str, str]]:
    if spec.get("series") != "replicas":
        return []
    matches = (REPLICAS_RE.match(c) for c in header if c)
    return [(m.group(0), m.group(1)) for m in matches if m]


# Both are file-level and read from the first row, so `charts all` needs no
# flags: what a row counts, and the denominator it counts per, are properties
# of the data rather than of one invocation.
def split_workloads(header: list[str]) -> list[str]:
    return workload_columns(SCHEMA["split-jobs.csv"], header)


def replica_series(header: list[str]) -> list[tuple[str, str]]:
    return series_columns(SCHEMA["frontier-api.csv"], header)


def unit_of(rows: list[dict], default: str = "unit") -> str:
    return cell(rows[0], "unit") or default if rows else default


def period_of(rows: list[dict], default: str = "min") -> str:
    return cell(rows[0], "period") or default if rows else default


def singular(unit: str) -> str:
    if unit.endswith("ies"):
        return f"{unit[:-3]}y"
    return unit[:-1] if unit.endswith("s") else unit


def sources_of(spec: dict, sources, header: list[str]) -> list[str]:
    if sources == WORKLOADS:
        return workload_columns(spec, header)
    return [s for s in sources if s in header]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def check_columns(name: str, spec: dict,
                  header: list[str]) -> tuple[list[str], list[str]]:
    """Required and absent is a problem; unknown is a note, named once in case
    it is a typo and then left alone."""
    problems, notes = [], []
    for missing in sorted(set(spec["required"]) - set(header)):
        problems.append(f"{name}: required column absent — {missing}")
    left = placeholders(header)
    known = declared(spec) | set(workload_columns(spec, header)) | set(left)
    known |= {col for col, _ in series_columns(spec, header)}
    for extra in sorted(set(header) - known - {None, ""}):
        notes.append(f"{name}: {extra} is not a column this tool reads")
    for column in left:
        notes.append(f"{name}: {column} is still the template's placeholder "
                     f"— name the column after what it holds")
    if spec.get("workloads") and not workload_columns(spec, header) and not left:
        notes.append(f"{name}: no workload column yet — every column beyond "
                     f"{', '.join(spec['required'])} is one workload's cost")
    return problems, notes


def check_numeric(name: str, spec: dict, rows: list[dict],
                  header: list[str]) -> list[str]:
    problems = []
    for index, row in enumerate(rows, start=2):
        for col in spec["required"]:
            if col not in header or col in NAMING or not cell(row, col):
                continue
            if num(row, col) is None:
                problems.append(f"{name}:{index}: {col} is not a number — "
                                f"{cell(row, col)!r}")
    return problems


def check_derived(name: str, spec: dict, rows: list[dict],
                  header: list[str]) -> list[str]:
    problems = []
    for target, sources, fn, rule in spec["derived"]:
        if target not in header:
            continue
        columns = sources_of(spec, sources, header)
        for index, row in enumerate(rows, start=2):
            stated = num(row, target)
            parts = [num(row, c) for c in columns]
            if stated is None or None in parts or not parts:
                continue
            try:
                computed = fn(*parts)
            except ZeroDivisionError:
                continue
            if computed == 0:
                continue
            gap = abs(computed - stated) / abs(computed)
            if gap > spec["tolerance"]:
                problems.append(
                    f"{name}:{index}: {target} states {stated:,.6g}, "
                    f"{rule} gives {computed:,.6g} ({gap * 100:.1f}% apart)")
    return problems


def validate(path: Path) -> tuple[list[str], list[str]]:
    """One CSV against its schema, as (problems, notes). A problem means the
    file cannot produce its chart or contradicts itself; a note costs no exit
    code, because a file nobody has filled in yet is a first revision."""
    spec = SCHEMA.get(path.name)
    if spec is None:
        return [], [f"{path.name}: no schema — this tool draws nothing from it"]
    try:
        header, rows = read_table(path)
    except Skip:
        return [], [f"{path.name}: absent, so nothing is drawn from it"]

    problems, notes = check_columns(path.name, spec, header)
    if not rows:
        return problems, notes + [f"{path.name}: header only, no rows yet"]
    problems += check_numeric(path.name, spec, rows, header)
    problems += check_derived(path.name, spec, rows, header)
    return problems, notes
