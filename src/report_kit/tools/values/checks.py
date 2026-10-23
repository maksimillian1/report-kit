"""What `report-kit values check` and `validate` assert about a registry."""

from __future__ import annotations

import collections
import re
from typing import Iterable, NamedTuple

from . import evidence, points
from .errors import RegistryError
from .registry import KINDS, PENDING, REF_RE, Registry, Value
from .corpus import Document, MARKED
from .links import METRIC, letter_of, metric_of
from .readings import evidence_source


MONEY = re.compile(r"\$\s?-?\d[\d,]*(?:\.\d+)?")


class RetiredHit(NamedTuple):
    file: str
    line: int
    pattern: str
    replaced_by: str
    text: str


class MarkProblem(NamedTuple):
    file: str
    line: int
    ref: str
    why: str


class CoverageRow(NamedTuple):
    name: str
    file: str
    status: str
    wanted: str


def allowed(registry: Registry, pattern: str, rel: str, line: str) -> bool:
    for item in registry.allow:
        if not isinstance(item, dict):
            raise RegistryError(f"allow entries must be mappings, not "
                              f"{type(item).__name__}")
        if str(item.get("pattern")) != pattern:
            continue
        if item.get("file") and str(item["file"]) != rel:
            continue
        if item.get("must_contain") and str(item["must_contain"]) not in line:
            continue
        return True
    return False


def check_retired(registry: Registry,
                  documents: Iterable[Document]) -> list[RetiredHit]:
    """Values the report has superseded, still sitting in a document."""
    patterns = []
    for item in registry.retired:
        if not isinstance(item, dict) or "pattern" not in item:
            raise RegistryError(f"every retired entry needs a 'pattern'; got "
                              f"{item!r}")
        patterns.append((str(item["pattern"]), str(item.get("replaced_by", ""))))
    hits = []
    for document in documents:
        for line in document.lines:
            if not line.prose:
                continue
            for pattern, replaced_by in patterns:
                if pattern in line.prose and not allowed(
                        registry, pattern, document.rel, line.prose):
                    hits.append(RetiredHit(document.rel, line.number, pattern,
                                           replaced_by, line.text.strip()))
    return hits


def check_marks(registry: Registry, values: dict[str, Value],
                documents: Iterable[Document]) -> tuple[int, list[MarkProblem]]:
    """Every ref written into a document must exist and carry that value's
    current value. This is the only check that verifies identity rather than
    presence, and it is what marking a number buys."""
    index = registry.by_ref()
    problems, seen = [], 0
    for document in documents:
        for line in document.lines:
            if not line.text:
                continue
            for match in MARKED.finditer(line.text):
                shown = match.group(1) or match.group(3)
                ref = match.group(2) or match.group(4)
                seen += 1
                name = index.get(ref)
                if name is None:
                    problems.append(MarkProblem(document.rel, line.number, ref,
                                                "no such ref"))
                    continue
                value = values[name]
                if value is PENDING:
                    problems.append(MarkProblem(
                        document.rel, line.number, ref,
                        f"shows {shown}, {name} is pending"))
                elif not rounds_to(shown, value):
                    problems.append(MarkProblem(
                        document.rel, line.number, ref,
                        f"shows {shown}, {name} is "
                        f"{registry.display(name, value)}"))
    return seen, problems


def check_coverage(registry: Registry,
                   values: dict[str, Value]) -> list[CoverageRow]:
    """Values the registry claims appear somewhere, checked where claimed."""
    rows, cache = [], {}
    for name, spec in registry.entries.items():
        declared = spec.get("appears_in") or []
        if isinstance(declared, str):
            declared = [declared]
        for rel in declared:
            rel = str(rel)
            if rel not in cache:
                cache[rel] = registry.document(rel)
            document = cache[rel]
            wanted = registry.display(name, values[name])
            if document is None:
                rows.append(CoverageRow(name, rel, "NO FILE", wanted))
            elif any(wanted in line.prose for line in document.lines):
                rows.append(CoverageRow(name, rel, "ok", wanted))
            else:
                rows.append(CoverageRow(name, rel, "MISSING", wanted))
    return rows


def check_orphans(registry: Registry, values: dict[str, Value],
                  rel: str) -> dict[str, list[int]] | None:
    """Currency tokens in one document that match no value at any precision.

    None means the file is not there, which is a different answer from an
    empty mapping — that one means the document is clean.
    """
    document = registry.document(rel)
    if document is None:
        return None
    numeric = [v for v in values.values() if v is not PENDING]
    known = {registry.display(n, v) for n, v in values.items()}
    for decimals in range(0, 7):
        known |= {f"{v:,.{decimals}f}" for v in numeric}
        known |= {f"{v:.{decimals}f}" for v in numeric}
    orphans: dict[str, list[int]] = {}
    for line in document.lines:
        for token in MONEY.findall(line.prose):
            bare = token.replace("$", "").strip()
            if bare not in known:
                orphans.setdefault(bare, []).append(line.number)
    return orphans


def rounds_to(shown: str, value: Value) -> bool:
    """Does `value` print as `shown` at the precision `shown` chose?

    One value has several legal renderings: prose prints 412 ms, a table
    prints 411.7, a rate keeps 23.97. All are the same number rounded once at
    print, so the author's precision decides the comparison. Checking against
    a single stored `display` instead would reject correct numbers — most of a
    rate card, whose entries render to 2 decimals and are written with four.
    """
    bare = shown.replace(",", "")
    decimals = len(bare.split(".")[1]) if "." in bare else 0
    try:
        return f"{value:.{decimals}f}" == f"{float(bare):.{decimals}f}"
    except (ValueError, TypeError):
        return False


def validate(registry: Registry) -> tuple[list[str], list[str]]:
    """The registry's own rules: refs well-formed, unique, and agreeing with
    the kind they claim; every leaf carrying a source."""
    problems, notes = [], []
    refs = collections.Counter()
    for name, spec in registry.entries.items():
        ref, kind = spec.get("ref"), spec.get("kind")
        if not ref:
            problems.append(f"{name}: no ref")
        else:
            refs[str(ref)] += 1
            m = REF_RE.match(str(ref))
            if not m:
                problems.append(f"{name}: ref {ref!r} is not V<MRDE><n>")
            elif kind and m.group(1) != kind:
                problems.append(f"{name}: ref {ref} disagrees with kind {kind}")
        if kind not in KINDS:
            problems.append(f"{name}: kind {kind!r} is not one of {'/'.join(KINDS)}")
        if "formula" not in spec and not spec.get("source") \
                and "from" not in spec:
            problems.append(f"{name}: a leaf with no source")
        problems.extend(evidence_problems(name, spec))
        problems.extend(metric_problems(name, spec))
        if kind == "D" and registry.effective_kind(name) == "E":
            notes.append(f"{name}: prints ᴱ — a formula, but one of its inputs "
                         f"is an estimate")
    for ref, count in refs.items():
        if count > 1:
            problems.append(f"ref {ref} used by {count} values")
    if registry.points is not None:
        try:
            template = points.read_template(registry.points)
        except points.PointError as exc:
            problems.append(str(exc))
        else:
            problems += [f"points: held: {field} names {name}, which is not a "
                         f"value" for field, name in template.held.items()
                         if name not in registry.entries]
    return problems, notes


def metric_problems(name: str, spec: dict) -> list[str]:
    """A value is the kind of the ref it measures: one read from D9 is
    derived wherever it is printed, and its mark says so."""
    metric = metric_of(spec)
    if metric is None:
        return []
    if not METRIC.match(metric):
        return [f"{name}: metric {metric!r} is not a ref such as M1 or "
                f"00-baseline/M1"]
    kind, letter = spec.get("kind"), letter_of(metric)
    if kind in KINDS and kind != letter:
        return [f"{name}: kind {kind}, but it measures {metric} — a value is "
                f"the kind of the ref it measures, so it is {letter}"]
    return []


def evidence_problems(name: str, spec: dict) -> list[str]:
    if "from" not in spec:
        return []
    try:
        evidence_source(spec)
    except evidence.EvidenceError as exc:
        return [f"{name}: {exc}"]
    return []
