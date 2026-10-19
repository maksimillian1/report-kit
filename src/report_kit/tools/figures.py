#!/usr/bin/env python3
"""figures.py — the report's numbers: resolve them, and fail when they drift.

    report-kit figures                    every figure, grouped
    report-kit figures block_b_total      one figure, bare value
    report-kit figures FD26               the same, by ref
    report-kit figures --group totals
    report-kit figures check [--strict]   retired values, coverage, ref identity,
                                          evidence
    report-kit figures pull [figure ...]  rewrite each value: from what its from:
                                          names in the run's data files
    report-kit figures add-point data/r1.point.json [--as LABEL] [--allow-invalid]
                                          append one run's figures from points:
    report-kit figures rename-point n08c n09
    report-kit figures delete-point n09 [--force]
                                          remove them, renumber, move the marks
    report-kit figures orphans report.md  currency tokens matching no figure
    report-kit figures validate           the registry's own rules
    report-kit figures retype d23_n25 E   change a kind, renumber every ref

Every number a report prints comes from `figures.yaml` as either a leaf — a
value with a source — or a formula over other figures. Arithmetic lives here
and nowhere else, least of all in prose. `formats.md` covers how a number is
written into a document and how a ref attaches to it.

A kind says where an error could originate: M measured, R recorded from an
authority, D derived, E estimated. A derived figure with an estimated input
prints as estimated — the weakest input decides.

A leaf may also say where its value lives in a run's committed data files
(`from:`, read by `report_kit.evidence`). `pull` writes that value in, and
`check` fails when the stored one no longer matches it.

The registry is found by walking up from the working directory, so the command
works from anywhere inside a report. `--path` names one explicitly, which is
also how you check a registry that is not the one you are standing in.

Everything above `cmd_list` is the model and prints nothing, so a caller that
wants a value rather than a page imports it and calls it directly. Every
failure that depends on what the registry says arrives as `FigureError`
rather than as whatever exception the parser happened to raise; a `from:`
that names no value is `evidence.EvidenceError`, reported per figure.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass, replace
from typing import Iterable, NamedTuple

import yaml

from report_kit import evidence, points


REGISTRY = "figures.yaml"

KINDS = ("M", "R", "D", "E")
MARK = {"M": "", "R": "ᴿ", "D": "ᴰ", "E": "ᴱ"}

DEFAULT_GROUP = "inputs"
DEFAULT_DECIMALS = 2
HOURS_DECIMALS = 0

# No zero padding and no F?0: the tool writes FD7, and `renumber` would
# rewrite a hand-typed FD07 into it — silently orphaning every mark in
# every document that points at the padded form. Caught here instead.
REF_RE = re.compile(r"^F([MRDE])([1-9]\d*)$")
MONEY = re.compile(r"\$\s?-?\d[\d,]*(?:\.\d+)?")

# Two marking forms, and both have to verify or the one nobody checks is the
# one that rots. The hidden form glues the ref to the digits inside a comment.
# The visible form is an anchor a reader can see — between the number and its
# ref only closing markup, a trust marker and whitespace may sit, never a
# word, because a ref separated from its number by prose would capture
# whatever number happened to come before it.
MARKED = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)<!--(F[MRDE]\d+)-->"
    r"|(-?\d[\d,]*(?:\.\d+)?)[*`_]{0,2}\s{0,2}[ᴿᴰᴱ]?\s{0,2}\((F[MRDE]\d+)\)")

# `formats.md`: fenced code blocks and inline code spans are skipped whole.
# Queries, commands and manifests are full of digits that mean nothing to the
# report, and a price quoted inside an example command is not a claim.
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
INLINE_CODE = re.compile(r"`[^`]*`")

# The rewriter's view of the file: a figure's name at two spaces, its keys at
# four. Anything else it cannot see, which `renumber` refuses rather than
# half-applies.
NAME_LINE = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$")
REFKIND_LINE = re.compile(r"^    (ref|kind):")
VALUE_LINE = re.compile(r"^    value:[ \t]*[^#\r\n]*?(?P<comment>[ \t]+#[^\r\n]*)?"
                        r"(?P<newline>\r?\n?)\Z")
POINT_LINE = re.compile(r"^    point:[ \t]*[^#\r\n]*?(?P<rest>(?:[ \t]+#[^\r\n]*)?"
                        r"\r?\n?)\Z")
FORMULA_LINE = re.compile(r"^    formula:(?P<expr>[^\r\n]*)(?P<newline>\r?\n?)\Z")
REPLACED_BY_LINE = re.compile(r"^(?P<lead>\s+(?:- )?replaced_by:[ \t]*)"
                              r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
                              r"(?P<rest>[^\r\n]*\r?\n?)\Z")
ANCHOR = re.compile(r"<!--(?P<hidden>F[MRDE]\d+)-->"
                    r"|(?P<space>[ \t]?)\((?P<visible>F[MRDE]\d+)\)")

_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


class FigureError(Exception):
    """Anything the registry's own contents make impossible.

    Callers catch this one type and report it; they never have to know that
    underneath sit a YAML parser, an AST walk and a pile of file I/O.
    """


class Pending:
    """A figure whose value does not exist yet.

    A singleton, and compared with `is` everywhere, so copying and pickling
    have to return the same object or a round-trip would produce a value that
    is pending and does not look it.
    """

    _instance: Pending | None = None

    def __new__(cls) -> Pending:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "pending"

    def __copy__(self) -> Pending:
        return self

    def __deepcopy__(self, memo: dict) -> Pending:
        return self

    def __reduce__(self) -> str:
        return "PENDING"


PENDING = Pending()

Value = float | Pending


# ----------------------------------------------------------------- the file

def find_registry(explicit: str | os.PathLike | None = None,
                  start: str | os.PathLike | None = None,
                  ) -> tuple[pathlib.Path, pathlib.Path]:
    """The report root and the registry file inside it. The root is whatever
    directory holds `figures.yaml`, because every `scan` entry and every
    `appears_in` path is relative to it."""
    if explicit:
        path = pathlib.Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FigureError(f"no such registry: {path}")
        return path.parent, path
    here = pathlib.Path(start or pathlib.Path.cwd()).expanduser().resolve()
    for folder in [here, *here.parents]:
        candidate = folder / REGISTRY
        if candidate.is_file():
            return folder, candidate
    raise FigureError(f"no {REGISTRY} in {here} or any parent — run this inside "
                      f"a report, or name one with --path")


class _UniqueKeyLoader(yaml.SafeLoader):
    """`safe_load` keeps the last of two equal keys, so a figure defined twice
    loses its first definition without a word. Merge keys (`<<`) may still be
    overridden; only keys written out twice are refused."""

    def construct_mapping(self, node, deep=False):
        line_of: dict = {}
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            line = key_node.start_mark.line + 1
            if key in line_of:
                raise yaml.constructor.ConstructorError(
                    None, None,
                    f"{key!r} appears twice, at lines {line_of[key]} and {line}",
                    key_node.start_mark)
            line_of[key] = line
        return super().construct_mapping(node, deep=deep)


def _parse(text: str, path: pathlib.Path) -> dict:
    try:
        doc = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise FigureError(f"{path} is not valid YAML: "
                          f"{str(exc).splitlines()[0]}") from exc
    if doc is None:
        raise FigureError(f"{path} is empty")
    if not isinstance(doc, dict):
        raise FigureError(f"{path} must be a mapping, not a "
                          f"{type(doc).__name__}")
    return doc


def _figures_of(doc: dict, path: pathlib.Path) -> dict[str, dict]:
    if "figures" not in doc:
        raise FigureError(f"{path} has no 'figures' mapping")
    figures = doc["figures"]
    if figures is None:
        raise FigureError(f"{path} has an empty 'figures' mapping")
    if not isinstance(figures, dict):
        raise FigureError(f"{path}: 'figures' must be a mapping of name to "
                          f"figure, not a {type(figures).__name__}")
    bad = [k for k in figures if not isinstance(k, str)]
    if bad:
        raise FigureError(f"{path}: figure names must be strings; found "
                          f"{bad[0]!r}")
    return {name: (spec if isinstance(spec, dict) else {})
            for name, spec in figures.items()}


def _sequence(doc: dict, key: str, path: pathlib.Path) -> tuple:
    value = doc.get(key) or []
    if not isinstance(value, list):
        raise FigureError(f"{path}: '{key}' must be a list, not a "
                          f"{type(value).__name__}")
    return tuple(value)


# ------------------------------------------------------------- the corpus

class Line(NamedTuple):
    """One line of a scanned document, in the two views the checks need.

    `text` is the line as written and is where marks are found — a mark inside
    an inline code span is still a mark, because a table cell often wraps the
    number in backticks. `prose` has those spans blanked and is where loose
    numbers are looked for, so a price inside `$0.75` is not mistaken for a
    claim. Both are empty for a line inside a fenced block.
    """

    number: int
    text: str
    prose: str


class Document(NamedTuple):
    path: pathlib.Path
    rel: str
    lines: tuple[Line, ...]


def split_lines(text: str) -> tuple[Line, ...]:
    """Number the lines and mark off the code.

    A fence opens on ``` or ~~~ and closes on the same character at least as
    long, which is what lets a block quoting a fence nest inside a longer one.
    """
    lines, fence = [], ""
    for number, raw in enumerate(text.splitlines(), 1):
        opening = FENCE.match(raw)
        if fence:
            if opening and opening.group(1)[0] == fence[0] \
                    and len(opening.group(1)) >= len(fence) \
                    and not opening.group(2):
                fence = ""
            lines.append(Line(number, "", ""))
            continue
        if opening:
            fence = opening.group(1)
            lines.append(Line(number, "", ""))
            continue
        lines.append(Line(number, raw, INLINE_CODE.sub(
            lambda m: " " * len(m.group()), raw)))
    return tuple(lines)


def read_document(path: pathlib.Path, root: pathlib.Path) -> Document:
    try:
        text = path.read_text()
    except OSError as exc:
        raise FigureError(f"cannot read {path}: {exc}") from exc
    return Document(path, relative(path, root), split_lines(text))


def relative(path: pathlib.Path, root: pathlib.Path) -> str:
    """How a document is named in the output, and in `allow` and
    `appears_in`.

    Both sides are resolved first: one of them reached here through a symlink
    — on macOS every temporary directory does — is enough to make
    `relative_to` fail, and a file then named by a chain of `..` matches no
    entry anybody wrote by hand.
    """
    path, root = pathlib.Path(path).resolve(), pathlib.Path(root).resolve()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return os.path.relpath(path, root)


# ------------------------------------------------------------- the registry

@dataclass(frozen=True)
class Registry:
    """A loaded `figures.yaml`, and everything derived from it.

    Constructed straight from a mapping for tests and for callers that build a
    registry in memory; `load()` is the file path in. `root` is what every
    relative path in the file is relative to, which is the directory the file
    itself sits in.
    """

    figures: dict[str, dict]
    root: pathlib.Path = pathlib.Path(".")
    path: pathlib.Path | None = None
    scan: tuple = ()
    allow: tuple = ()
    retired: tuple = ()
    points: object = None

    def __post_init__(self) -> None:
        # Resolved once, here, because every path the checks report is
        # `relative_to` this one. A root left as given — a relative path, or
        # anything under a symlinked directory, which on macOS is every
        # temporary directory — makes `relative_to` fail and each file is
        # then named by a chain of `..`, which `allow` entries and
        # `appears_in` paths no longer match.
        object.__setattr__(self, "root", pathlib.Path(self.root).resolve())

    @classmethod
    def load(cls, explicit: str | os.PathLike | None = None,
             start: str | os.PathLike | None = None) -> Registry:
        root, path = find_registry(explicit, start)
        doc = _parse(path.read_text(), path)
        return cls(figures=_figures_of(doc, path), root=root, path=path,
                   scan=_sequence(doc, "scan", path),
                   allow=_sequence(doc, "allow", path),
                   retired=_sequence(doc, "retired", path),
                   points=doc.get("points"))

    # -- figures ----------------------------------------------------------

    def spec(self, name: str) -> dict:
        if name not in self.figures:
            raise FigureError(f"unknown figure '{name}'")
        return self.figures[name]

    def resolve(self) -> dict[str, Value]:
        """Every figure's value, formulas included, in file order."""
        resolved: dict[str, Value] = {}
        for name in self.figures:
            _resolve_one(name, self.figures, resolved, [])
        return resolved

    def inputs(self, name: str) -> list[str]:
        """The figures a formula names, in the order it names them."""
        spec = self.spec(name)
        if "formula" not in spec:
            return []
        tree = _formula(name, spec["formula"])
        return [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]

    def effective_kind(self, name: str, _seen: tuple[str, ...] = ()) -> str:
        """The kind a figure prints as: the weakest input decides, so a
        derived figure with an estimate anywhere upstream prints ᴱ."""
        kind = self.spec(name).get("kind", "?")
        if kind != "D":
            return kind
        for source in self.inputs(name):
            if source in self.figures and source not in _seen:
                if self.effective_kind(source, _seen + (name,)) == "E":
                    return "E"
        return kind

    def by_ref(self) -> dict[str, str]:
        """Ref to figure name. A figure with no ref is simply not in here;
        `validate` is what complains about it."""
        index = {}
        for name, spec in self.figures.items():
            ref = spec.get("ref")
            if ref is not None:
                index.setdefault(str(ref), name)
        return index

    def display(self, name: str, value: Value) -> str:
        """The figure written out at its own precision."""
        if value is PENDING:
            return "pending"
        spec = self.figures.get(name) or {}
        default = (HOURS_DECIMALS if str(spec.get("unit", "")) == "hours"
                   else DEFAULT_DECIMALS)
        decimals = spec.get("display", default)
        if isinstance(decimals, bool) or not isinstance(decimals, int) \
                or decimals < 0:
            raise FigureError(f"figure '{name}': display must be a whole "
                              f"number of decimals, not {decimals!r}")
        return f"{value:,.{decimals}f}"

    def groups(self) -> dict[str, list[str]]:
        """Figures by group, in the order the file puts them: a fixed list
        here would bake one report's subjects into a general tool."""
        grouped: dict[str, list[str]] = {}
        for name, spec in self.figures.items():
            grouped.setdefault(str(spec.get("group", DEFAULT_GROUP)),
                               []).append(name)
        return grouped

    # -- documents --------------------------------------------------------

    def documents(self) -> list[Document]:
        """Every file `scan` names, each read once. Entries overlap freely,
        and a file counted twice would double the marked-number count, which
        is the one number that notices a ref orphaned by a delete."""
        seen, docs = set(), []
        for entry in self.scan:
            for path in self._match(str(entry)):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                docs.append(read_document(path, self.root))
        return docs

    def _match(self, entry: str) -> list[pathlib.Path]:
        direct = (self.root / entry).resolve()
        if direct.is_file():
            return [direct]
        try:
            return [p for p in sorted(self.root.glob(entry)) if p.is_file()]
        except (ValueError, IndexError) as exc:
            raise FigureError(f"scan entry {entry!r} is not a usable path or "
                              f"glob: {exc}") from exc

    def document(self, rel: str) -> Document | None:
        """One document by its path relative to the root, or None if absent."""
        path = self.root / rel
        return read_document(path, self.root) if path.is_file() else None

    def relative(self, path: pathlib.Path) -> str:
        return relative(path, self.root)


# ------------------------------------------------------------- arithmetic

def _formula(name: str, formula: object) -> ast.Expression:
    try:
        return ast.parse(str(formula), mode="eval")
    except SyntaxError as exc:
        raise FigureError(f"figure '{name}': {formula!r} is not an "
                          f"expression ({exc.msg})") from exc


def _eval(node: ast.AST, figures: dict[str, dict],
          resolved: dict[str, Value], stack: list[str]) -> Value:
    if isinstance(node, ast.Expression):
        return _eval(node.body, figures, resolved, stack)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FigureError(f"non-numeric constant {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        return _resolve_one(node.id, figures, resolved, stack)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _eval(node.operand, figures, resolved, stack)
        return PENDING if operand is PENDING else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        left = _eval(node.left, figures, resolved, stack)
        right = _eval(node.right, figures, resolved, stack)
        if left is PENDING or right is PENDING:
            return PENDING
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise FigureError("division by zero")
        return left / right
    raise FigureError(f"unsupported expression node {type(node).__name__}")


def _resolve_one(name: str, figures: dict[str, dict],
                 resolved: dict[str, Value], stack: list[str]) -> Value:
    if name in resolved:
        return resolved[name]
    if name not in figures:
        raise FigureError(f"unknown figure '{name}'")
    if name in stack:
        raise FigureError("cycle: " + " -> ".join(stack + [name]))
    spec = figures[name]
    if spec.get("pending"):
        resolved[name] = PENDING
        return PENDING
    if "value" in spec:
        raw = spec["value"]
        try:
            value: Value = float(raw)
        except (TypeError, ValueError) as exc:
            raise FigureError(f"figure '{name}': value {raw!r} is not a "
                              f"number") from exc
    elif "formula" in spec:
        value = _eval(_formula(name, spec["formula"]), figures, resolved,
                      stack + [name])
    elif "from" in spec:
        raise FigureError(f"figure '{name}' has a from: but no value yet — run "
                          f"`report-kit figures pull {name}`")
    else:
        raise FigureError(f"figure '{name}' has neither value nor formula")
    resolved[name] = value
    return value


def rounds_to(shown: str, value: Value) -> bool:
    """Does `value` print as `shown` at the precision `shown` chose?

    One figure has several legal renderings: prose prints $554, a table prints
    553.83, a rate keeps 0.0952. All are the same number rounded once at
    print, so the author's precision decides the comparison. Checking against
    a single stored `display` instead would reject correct numbers — most of a
    rate card, whose figures render to 2 decimals and are written with four.
    """
    bare = shown.replace(",", "")
    decimals = len(bare.split(".")[1]) if "." in bare else 0
    try:
        return f"{value:.{decimals}f}" == f"{float(bare):.{decimals}f}"
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------- checks

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
            raise FigureError(f"allow entries must be mappings, not "
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
            raise FigureError(f"every retired entry needs a 'pattern'; got "
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
    """Every ref written into a document must exist and carry that figure's
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
    """Figures the registry claims appear somewhere, checked where claimed."""
    rows, cache = [], {}
    for name, spec in registry.figures.items():
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
    """Currency tokens in one document that match no figure at any precision.

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


def validate(registry: Registry) -> tuple[list[str], list[str]]:
    """The registry's own rules: refs well-formed, unique, and agreeing with
    the kind they claim; every leaf carrying a source."""
    problems, notes = [], []
    refs = collections.Counter()
    for name, spec in registry.figures.items():
        ref, kind = spec.get("ref"), spec.get("kind")
        if not ref:
            problems.append(f"{name}: no ref")
        else:
            refs[str(ref)] += 1
            m = REF_RE.match(str(ref))
            if not m:
                problems.append(f"{name}: ref {ref!r} is not F<MRDE><n>")
            elif kind and m.group(1) != kind:
                problems.append(f"{name}: ref {ref} disagrees with kind {kind}")
        if kind not in KINDS:
            problems.append(f"{name}: kind {kind!r} is not one of {'/'.join(KINDS)}")
        if "formula" not in spec and not spec.get("source") \
                and "from" not in spec:
            problems.append(f"{name}: a leaf with no source")
        problems.extend(evidence_problems(name, spec))
        if kind == "D" and registry.effective_kind(name) == "E":
            notes.append(f"{name}: prints ᴱ — a formula, but one of its inputs "
                         f"is an estimate")
    for ref, count in refs.items():
        if count > 1:
            problems.append(f"ref {ref} used by {count} figures")
    if registry.points is not None:
        try:
            points.read_template(registry.points)
        except points.PointError as exc:
            problems.append(str(exc))
    return problems, notes


def evidence_problems(name: str, spec: dict) -> list[str]:
    if "from" not in spec:
        return []
    try:
        evidence_source(spec)
    except evidence.EvidenceError as exc:
        return [f"{name}: {exc}"]
    return []


def evidence_source(spec: dict) -> evidence.Source:
    if "formula" in spec:
        raise evidence.EvidenceError("from: and formula: together — a figure "
                                     "is read from data or computed, not both")
    return evidence.read_source(spec["from"])


def reading(registry: Registry, name: str) -> float:
    """What the data files say a figure's value is. Raises
    `evidence.EvidenceError`, `MissingEvidence` when the file is absent."""
    return evidence.reproduce(evidence_source(registry.spec(name)),
                              registry.root)


def stored_number(raw: object) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class EvidenceRow(NamedTuple):
    name: str
    status: str
    stored: object
    found: float | None
    why: str = ""


def check_evidence(registry: Registry) -> list[EvidenceRow]:
    """Every figure with a `from:`, its stored value against what its data
    reproduces at full precision."""
    rows = []
    for name, spec in registry.figures.items():
        if "from" not in spec:
            continue
        stored = spec.get("value")
        try:
            found = reading(registry, name)
        except evidence.MissingEvidence as exc:
            rows.append(EvidenceRow(name, "NO FILE", stored, None, str(exc)))
            continue
        except evidence.EvidenceError as exc:
            rows.append(EvidenceRow(name, "FAIL", stored, None, str(exc)))
            continue
        number = stored_number(stored)
        if number is None:
            status = "NO VALUE"
        else:
            status = "ok" if evidence.agrees(number, found) else "DIFFERS"
        rows.append(EvidenceRow(name, status, stored, found))
    return rows


# ---------------------------------------------------------- file surgery

def renumber(path: str | os.PathLike,
             kinds: dict[str, str] | None = None) -> dict[str, int]:
    """Rewrite every ref so the sequence per kind follows file order. `kinds`
    reclassifies in the same pass, which is how `retype` works.

    Refuses rather than half-applies: a figure the rewriter cannot see keeps
    its old ref while everything after it shifts, orphaning every mark that
    points at either one.
    """
    path = pathlib.Path(path)
    text, counts = renumbered(path.read_text(), path, kinds)
    path.write_text(text)
    return counts


def renumbered(text: str, path: pathlib.Path,
               kinds: dict[str, str] | None = None) -> tuple[str, dict[str, int]]:
    """`renumber` on text in memory: the new text and the count per kind."""
    figures = _figures_of(_parse(text, path), path)

    overrides = dict(kinds or {})
    for name, kind in overrides.items():
        if name not in figures:
            raise FigureError(f"unknown figure '{name}'")
        if kind not in KINDS:
            raise FigureError(f"kind must be one of {'/'.join(KINDS)}")

    lines = text.splitlines(keepends=True)
    start, end = figures_block(lines, path)

    counters: collections.Counter = collections.Counter()
    out, written = [], []
    for i, line in enumerate(lines):
        if start < i < end and REFKIND_LINE.match(line):
            continue
        out.append(line)
        if not start < i < end:
            continue
        m = NAME_LINE.match(line)
        if not m or m.group(1) not in figures:
            continue
        name = m.group(1)
        kind = overrides.get(name, figures[name].get("kind", "M"))
        if kind not in KINDS:
            raise FigureError(f"{name}: kind {kind!r} is not one of "
                              f"{'/'.join(KINDS)} — fix it before renumbering")
        counters[kind] += 1
        out.append(f"    ref: F{kind}{counters[kind]}\n")
        out.append(f"    kind: {kind}\n")
        written.append(name)

    unseen = [name for name in figures if name not in written]
    if unseen:
        raise FigureError(
            f"{path}: {len(unseen)} figure(s) the rewriter cannot see — "
            f"{', '.join(unseen[:5])}. A figure needs its name alone on a line "
            f"indented two spaces, its keys four; nothing was written")
    return "".join(out), dict(counters)


def retype(name: str, kind: str, path: str | os.PathLike) -> dict[str, int]:
    """Change one figure's kind and renumber every ref to match."""
    if kind not in KINDS:
        raise FigureError(f"kind must be one of {'/'.join(KINDS)}")
    return renumber(path, {name: kind})


def figures_block(lines: list[str], path: pathlib.Path) -> tuple[int, int]:
    """The `figures:` line and the first line after its block."""
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == "figures:"), None)
    if start is None:
        raise FigureError(
            f"{path}: no line reading 'figures:' on its own — the rewriter "
            f"edits the block as text and cannot rewrite an inline mapping")
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i][0].isspace():
            return start, i
    return start, len(lines)


def figure_spans(lines: list[str], path: pathlib.Path) -> dict[str, range]:
    """Each figure's lines, from its name to the line before the next."""
    start, end = figures_block(lines, path)
    names = [(i, m.group(1)) for i in range(start + 1, end)
             if (m := NAME_LINE.match(lines[i]))]
    stops = [i for i, _ in names[1:]] + [end]
    return {name: range(i, stop) for (i, name), stop in zip(names, stops)}


def value_text(value: float) -> str:
    """Full precision without the float noise: 0.0022 * 100 writes 0.22."""
    rounded = float(f"{value:.15g}")
    return str(int(rounded)) if rounded.is_integer() else repr(rounded)


def with_value(lines: list[str], span: range, text: str) -> list[str]:
    """`lines` with this figure's value line replaced, or inserted after its
    ref and kind when it has none."""
    for i in span:
        match = VALUE_LINE.match(lines[i])
        if match:
            comment, newline = match["comment"] or "", match["newline"] or "\n"
            line = f"    value: {text}{comment}{newline}"
            return lines[:i] + [line] + lines[i + 1:]
    after = max((i for i in span if REFKIND_LINE.match(lines[i])),
                default=span.start)
    return lines[:after + 1] + [f"    value: {text}\n"] + lines[after + 1:]


def rewrite_values(path: str | os.PathLike, texts: dict[str, str]) -> None:
    """Rewrite one `value:` line per figure and touch nothing else, so the
    file's comments and block scalars survive byte for byte. Refuses, and
    writes nothing, when a figure is not where the rewriter can see it."""
    path = pathlib.Path(path)
    lines = path.read_text().splitlines(keepends=True)
    for name, text in texts.items():
        span = figure_spans(lines, path).get(name)
        if span is None:
            raise FigureError(
                f"{path}: the rewriter cannot see '{name}' — a figure needs "
                f"its name alone on a line indented two spaces, its keys "
                f"four; nothing was written")
        lines = with_value(lines, span, text)
    rewritten = _figures_of(_parse("".join(lines), path), path)
    for name, text in texts.items():
        if stored_number(rewritten[name].get("value")) != float(text):
            raise FigureError(f"{path}: '{name}' did not read back as {text} "
                              f"after the rewrite; nothing was written")
    path.write_text("".join(lines))


class Pulled(NamedTuple):
    name: str
    old: object
    new: float


def pull_targets(registry: Registry, wanted: Iterable[str]) -> list[str]:
    wanted = list(wanted)
    if not wanted:
        return [name for name, spec in registry.figures.items()
                if "from" in spec]
    index = registry.by_ref()
    names = [index.get(item, item) for item in wanted]
    for name in names:
        if "from" not in registry.spec(name):
            raise FigureError(f"figure '{name}' has no from: to pull")
    return names


def pull(registry: Registry, wanted: Iterable[str] = ()
         ) -> tuple[list[Pulled], list[tuple[str, str]]]:
    """Fill each `value:` from what its `from:` reproduces. Returns what
    changed, and the figures with no reading — a gap is reported and its
    value left alone, never written as a zero."""
    if registry.path is None:
        raise FigureError("pull rewrites a registry file; this one has none")
    changed, unread = [], []
    for name in pull_targets(registry, wanted):
        try:
            found = reading(registry, name)
        except evidence.EvidenceError as exc:
            unread.append((name, str(exc)))
            continue
        old = registry.figures[name].get("value")
        stored = stored_number(old)
        if stored is None or not evidence.agrees(stored, found):
            changed.append(Pulled(name, old, found))
    if changed:
        rewrite_values(registry.path,
                       {item.name: value_text(item.new) for item in changed})
    return changed, unread


def flow(value: object) -> str:
    """One YAML value on one line, quoted where YAML needs it."""
    text = yaml.safe_dump(value, default_flow_style=True, sort_keys=False,
                          allow_unicode=True, width=1_000_000)
    return text.removesuffix("...\n").strip()


def figure_lines(name: str, spec: dict) -> list[str]:
    return ["\n", f"  {name}:\n"] + [
        f"    {key}: {value_text(value) if key == 'value' else flow(value)}\n"
        for key, value in spec.items()]


def appended(text: str, path: pathlib.Path, added: dict[str, dict]) -> str:
    """`text` with these figures after the last line of the figures block,
    so no existing ref moves."""
    lines = text.splitlines(keepends=True)
    start, end = figures_block(lines, path)
    last = max(i for i in range(start, end) if lines[i].strip())
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    block = [line for name, spec in added.items()
             for line in figure_lines(name, spec)]
    return "".join(lines[:last + 1] + block + lines[last + 1:])


def without_figures(text: str, path: pathlib.Path, names: list[str]) -> str:
    """`text` without these figures: each from its name through its last
    indented line, and the blank lines after it."""
    lines = text.splitlines(keepends=True)
    spans = figure_spans(lines, path)
    dropped: set[int] = set()
    for name in names:
        span = spans.get(name)
        if span is None:
            raise FigureError(f"{path}: the rewriter cannot see '{name}'; "
                              f"nothing was written")
        last = max(i for i in span
                   if i == span.start or lines[i].startswith("    "))
        stop = last + 1
        while stop < span.stop and not lines[stop].strip():
            stop += 1
        dropped.update(range(span.start, stop))
    return "".join(line for i, line in enumerate(lines) if i not in dropped)


def renamed_text(text: str, path: pathlib.Path, names: dict[str, str],
                 label: str) -> str:
    """Every member's name and `point:` line, every formula naming one, and
    every `replaced_by:` naming one, rewritten line by line."""
    lines = text.splitlines(keepends=True)
    start, end = figures_block(lines, path)
    for name, span in figure_spans(lines, path).items():
        if name in names:
            lines[span.start] = lines[span.start].replace(
                f"  {name}:", f"  {names[name]}:", 1)
        for i in span:
            point = POINT_LINE.match(lines[i])
            formula = FORMULA_LINE.match(lines[i])
            if point and name in names:
                lines[i] = f"    point: {flow(label)}{point['rest']}"
            elif formula:
                lines[i] = (f"    formula:{points.renamed_formula(formula['expr'], names)}"
                            f"{formula['newline']}")
    for i in [*range(start), *range(end, len(lines))]:
        replaced = REPLACED_BY_LINE.match(lines[i])
        if replaced and replaced["name"] in names:
            lines[i] = f"{replaced['lead']}{names[replaced['name']]}{replaced['rest']}"
    return "".join(lines)


def moved_anchor(match: re.Match, refs: dict[str, str | None]) -> str:
    ref = match["hidden"] or match["visible"]
    if ref not in refs:
        return match.group()
    new = refs[ref]
    if match["hidden"]:
        return "" if new is None else f"<!--{new}-->"
    return "" if new is None else f"{match['space']}({new})"


def rewrite_marks(text: str, refs: dict[str, str | None]) -> str:
    """Every anchor outside fenced code moved by an exact old -> new map; one
    that maps to None is removed. An anchor is the whole `<!--FM1-->` or
    `(FM1)`, so FM1 never matches inside FM12."""
    raw = text.splitlines(keepends=True)
    return "".join(
        ANCHOR.sub(lambda m: moved_anchor(m, refs), line) if view.text else line
        for line, view in zip(raw, split_lines(text)))


def write_all(texts: dict[pathlib.Path, str]) -> None:
    """Every file staged beside itself first, and only then moved into place,
    so a write that fails leaves every file as it was."""
    staged: dict[pathlib.Path, pathlib.Path] = {}
    try:
        for path, text in texts.items():
            staged[path] = path.with_name(f".{path.name}.report-kit")
            staged[path].write_text(text)
    except OSError as exc:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        raise FigureError(f"cannot write {exc.filename}: {exc.strerror}; "
                          f"nothing was changed") from exc
    for path, temporary in staged.items():
        os.replace(temporary, path)


def parsed(registry: Registry, text: str) -> Registry:
    doc = _parse(text, registry.path)
    return replace(registry, figures=_figures_of(doc, registry.path),
                   retired=_sequence(doc, "retired", registry.path))


def checked(registry: Registry, text: str) -> Registry:
    """The registry `text` would be. Refused when it does not resolve, or
    breaks a rule the current one keeps."""
    after = parsed(registry, text)
    after.resolve()
    broken = set(validate(after)[0]) - set(validate(registry)[0])
    if broken:
        raise FigureError("the change would break the registry: "
                          + "; ".join(sorted(broken)) + "; nothing was written")
    return after


def next_refs(figures: dict[str, dict], kinds: list[object]) -> list[str]:
    """Refs for new figures of these kinds, after the highest of each kind,
    so no ref already cited moves."""
    highest: collections.Counter = collections.Counter()
    for spec in figures.values():
        match = REF_RE.match(str(spec.get("ref", "")))
        if match:
            highest[match[1]] = max(highest[match[1]], int(match[2]))
    refs = []
    for kind in kinds:
        if kind not in KINDS:
            raise FigureError(f"points: every figure needs kind: "
                              f"{'/'.join(KINDS)}, not {kind!r}")
        highest[kind] += 1
        refs.append(f"F{kind}{highest[kind]}")
    return refs


class Added(NamedTuple):
    label: str
    figures: dict[str, dict]
    gaps: list[tuple[str, str]]


def point_record(path: str | os.PathLike) -> dict:
    try:
        record = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise FigureError(f"cannot read point record {path}: {exc}") from exc
    if not isinstance(record, dict):
        raise FigureError(f"{path} is not a point record")
    return record


def refuse_outside_grid(template: points.Template, record: dict, path: str,
                        allow_invalid: bool) -> None:
    invalid = points.validity_problems(record)
    if invalid and not allow_invalid:
        raise FigureError(f"{path} is not a valid point ({'; '.join(invalid)});"
                          f" pass --allow-invalid to register it anyway")
    held = points.held_mismatches(template, record)
    if held:
        raise FigureError(f"{path} is not a point of this grid: "
                          f"{'; '.join(held)}. A different grid is never a "
                          f"repeat of this one")


def point_label(registry: Registry, template: points.Template, record: dict,
                rel: str, wanted: str | None) -> str:
    def taken(label: str) -> bool:
        return label in points.labels_in_use(registry.figures) or any(
            name in registry.figures
            for name in points.expand(template, label, rel))

    if wanted is None:
        return points.free_label(points.base_label(template, record), taken)
    points.check_label(wanted)
    if taken(wanted):
        raise FigureError(f"label {wanted} is taken")
    return wanted


def with_readings(registry: Registry, added: dict[str, dict]
                  ) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """The figures as they are written — ref, kind, point, value, then the
    template's own keys — and every reading that failed."""
    refs = iter(next_refs(registry.figures,
                          [spec["kind"] for spec in added.values()]))
    written, gaps = {}, []
    for name, spec in added.items():
        figure = {"ref": next(refs), "kind": spec["kind"], "point": spec["point"]}
        if "from" in spec:
            try:
                figure["value"] = evidence.reproduce(evidence_source(spec),
                                                     registry.root)
            except evidence.EvidenceError as exc:
                gaps.append((name, str(exc)))
        written[name] = {**figure, **{key: value for key, value in spec.items()
                                      if key not in figure}}
    return written, gaps


def add_point(registry: Registry, path: str | os.PathLike,
              wanted: str | None = None, allow_invalid: bool = False) -> Added:
    """Expand `points:` for one run and append it, its values pulled. Writes
    nothing when a reading is a gap, or when the result would not resolve."""
    if registry.points is None or registry.path is None:
        raise FigureError("no points: block — add-point expands that template")
    template = points.read_template(registry.points)
    record, rel = point_record(path), registry.relative(pathlib.Path(path))
    refuse_outside_grid(template, record, str(path), allow_invalid)
    label = point_label(registry, template, record, rel, wanted)
    written, gaps = with_readings(registry,
                                  points.expand(template, label, rel))
    if gaps:
        return Added(label, {}, gaps)
    text = appended(registry.path.read_text(), registry.path, written)
    checked(registry, text)
    write_all({registry.path: text})
    return Added(label, written, [])


def point_members(registry: Registry, label: str) -> list[str]:
    names = points.members(registry.figures, label)
    if not names:
        raise FigureError(f"no figure carries point: {label}")
    return names


def rename_point(registry: Registry, old: str, new: str) -> dict[str, str]:
    """Rename every figure of point `old`, and every formula naming one.
    Refs stay, so no document changes. Returns old name -> new name."""
    points.check_label(new)
    names = {name: points.renamed(name, old, new)
             for name in point_members(registry, old)}
    clashes = [name for name in names.values()
               if name in registry.figures and name not in names]
    if new in points.labels_in_use(registry.figures) or clashes:
        raise FigureError(f"label {new} is taken"
                          + (f" ({', '.join(clashes)})" if clashes else ""))
    text = renamed_text(registry.path.read_text(), registry.path, names, new)
    expect_renamed(registry, parsed(registry, text), names, new)
    checked(registry, text)
    write_all({registry.path: text})
    return names


def expect_renamed(before: Registry, after: Registry, names: dict[str, str],
                   label: str) -> None:
    expected = {}
    for name, spec in before.figures.items():
        spec = dict(spec)
        if name in names:
            spec["point"] = label
        if isinstance(spec.get("formula"), str):
            spec["formula"] = points.renamed_formula(spec["formula"], names)
        expected[names.get(name, name)] = spec
    retired = [{**item, "replaced_by": names.get(item.get("replaced_by"),
                                                 item.get("replaced_by"))}
               if isinstance(item, dict) and "replaced_by" in item else item
               for item in before.retired]
    if list(after.figures.items()) != list(expected.items()) \
            or list(after.retired) != retired:
        raise FigureError(f"{before.path}: the rewriter could not rename every "
                          f"reference — one sits where it cannot see, such as "
                          f"a formula across lines; nothing was written")


class Deleted(NamedTuple):
    names: list[str]
    refs: dict[str, str | None]
    documents: list[str]


def formula_dependents(registry: Registry, names: list[str]) -> list[str]:
    gone = set(names)
    found = [name for name in registry.figures
             if name not in gone and gone & set(registry.inputs(name))]
    return found + [f"retired {item.get('pattern')!r}"
                    for item in registry.retired
                    if isinstance(item, dict) and item.get("replaced_by") in gone]


def cited_anchors(registry: Registry, names: list[str]) -> list[str]:
    refs = {str(registry.figures[name].get("ref")) for name in names}
    return [f"{ref} at {document.rel}:{line.number}"
            for document in registry.documents() for line in document.lines
            for match in ANCHOR.finditer(line.text)
            if (ref := match["hidden"] or match["visible"]) in refs]


def moved_refs(before: Registry, after: Registry,
               names: list[str]) -> dict[str, str | None]:
    refs: dict[str, str | None] = {str(before.figures[name].get("ref")): None
                                   for name in names}
    for name, spec in after.figures.items():
        old = str(before.figures[name].get("ref"))
        if old != str(spec.get("ref")):
            refs[old] = str(spec.get("ref"))
    return refs


def delete_point(registry: Registry, label: str, force: bool = False) -> Deleted:
    """Remove a point's figures, renumber, and move every shifted mark in
    every scanned document. Everything is computed before anything is
    written, and nothing is written unless all of it succeeds."""
    names = point_members(registry, label)
    dependents = formula_dependents(registry, names)
    if dependents:
        raise FigureError(f"point {label} is still used by "
                          f"{', '.join(dependents)}; nothing was deleted")
    cited = cited_anchors(registry, names)
    if cited and not force:
        raise FigureError(f"point {label} is cited — {', '.join(cited)}. Carry "
                          f"it as a row instead, or pass --force to delete it "
                          f"and remove those marks; nothing was deleted")
    text, _ = renumbered(without_figures(registry.path.read_text(),
                                         registry.path, names), registry.path)
    refs = moved_refs(registry, checked(registry, text), names)
    documents = {document.path: document.path.read_text()
                 for document in registry.documents()}
    moved = {path: rewrite_marks(original, refs)
             for path, original in documents.items()}
    changed = {path: rewritten for path, rewritten in moved.items()
               if rewritten != documents[path]}
    write_all({**changed, registry.path: text})
    return Deleted(names, refs, sorted(registry.relative(p) for p in changed))


# ---------------------------------------------------------------- the command

# Not `constants.EXIT_*`, which numbers what a runner did. These three are
# this command's own contract, and the report's CI reads them.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def cmd_list(registry: Registry, values: dict, args: argparse.Namespace) -> int:
    groups = registry.groups()
    for group, names in groups.items():
        if args.group and group != args.group:
            continue
        print(f"\n{group}")
        for name in names:
            spec = registry.figures[name]
            kind = registry.effective_kind(name)
            basis = spec.get("formula") or spec.get("source", "")
            print(f"  {registry.display(name, values[name]):>14} "
                  f"{MARK.get(kind, '?'):1} {str(spec.get('ref', '?')):>6}  "
                  f"{name:<28} {basis}")
    print()
    return EXIT_OK


def cmd_check(registry: Registry, values: dict, args: argparse.Namespace) -> int:
    documents = registry.documents()
    failed = False
    print(f"scanned {len(documents)} documents, {len(registry.figures)} figures\n")

    print("retired values")
    hits = check_retired(registry, documents)
    if hits:
        failed = True
        for hit in hits:
            new = (registry.display(hit.replaced_by, values[hit.replaced_by])
                   if hit.replaced_by in values else "?")
            print(f"  FAIL {hit.file}:{hit.line}  {hit.pattern} -> "
                  f"{hit.replaced_by} = {new}")
            print(f"       {hit.text[:120]}")
    else:
        print("  none")

    seen, problems = check_marks(registry, values, documents)
    print(f"\nmarked numbers: {seen} checked")
    for problem in problems:
        failed = True
        print(f"  FAIL {problem.file}:{problem.line}  {problem.ref}: "
              f"{problem.why}")

    rows = check_coverage(registry, values)
    missing = [row for row in rows if row.status != "ok"]
    print(f"\ncoverage: {len(rows) - len(missing)}/{len(rows)} figures present "
          f"where declared")
    for row in missing:
        print(f"  {row.status:<8} {row.name:<28} {row.wanted:>12}  expected in "
              f"{row.file}")
    if missing and args.strict:
        failed = True

    failed = report_evidence(registry, args.strict) or failed
    print()
    return EXIT_FAILED if failed else EXIT_OK


def report_evidence(registry: Registry, strict: bool) -> bool:
    """Prints the evidence section of `check`; True when it fails."""
    rows = check_evidence(registry)
    off = [row for row in rows if row.status != "ok"]
    print(f"\nevidence: {len(rows) - len(off)}/{len(rows)} figures agree with "
          f"the data their from: names")
    for row in off:
        detail = row.why or (f"stores {row.stored}, its data gives "
                             f"{value_text(row.found)}")
        print(f"  {row.status:<8} {row.name:<28} {detail}")
    absent = [row for row in off if row.status == "NO FILE"]
    return len(off) > len(absent) or bool(absent and strict)


def cmd_pull(registry: Registry, wanted: list[str]) -> int:
    changed, unread = pull(registry, wanted)
    for item in changed:
        old = "(none)" if item.old is None else item.old
        print(f"  {item.name:<28} {old} -> {value_text(item.new)}")
    for name, why in unread:
        print(f"  FAIL {name:<28} {why}")
    print(f"\n{len(changed)} value(s) rewritten, {len(unread)} with no reading")
    return EXIT_FAILED if unread else EXIT_OK


def cmd_add_point(registry: Registry, rest: list[str],
                  opts: argparse.Namespace) -> int:
    if len(rest) != 2:
        return usage("add-point <run.point.json> [--as LABEL] [--allow-invalid]")
    added = add_point(registry, rest[1], opts.as_label, opts.allow_invalid)
    for name, why in added.gaps:
        print(f"  FAIL {name:<28} {why}")
    if added.gaps:
        print(f"\npoint {added.label}: {len(added.gaps)} figure(s) with no "
              f"reading; nothing was written")
        return EXIT_FAILED
    print(f"added point {added.label}")
    for name, spec in added.figures.items():
        shown = (value_text(spec["value"]) if "value" in spec
                 else spec.get("formula", ""))
        print(f"  {spec['ref']:>6}  {name:<28} {shown}")
    return EXIT_OK


def cmd_rename_point(registry: Registry, rest: list[str],
                     opts: argparse.Namespace) -> int:
    if len(rest) != 3:
        return usage("rename-point <old label> <new label>")
    names = rename_point(registry, rest[1], rest[2])
    print(f"point {rest[1]} is now {rest[2]}; refs unchanged")
    for old, new in names.items():
        print(f"  {old} -> {new}")
    return EXIT_OK


def cmd_delete_point(registry: Registry, rest: list[str],
                     opts: argparse.Namespace) -> int:
    if len(rest) != 2:
        return usage("delete-point <label> [--force]")
    deleted = delete_point(registry, rest[1], opts.force)
    print(f"deleted point {rest[1]}: {', '.join(deleted.names)}")
    for old, new in deleted.refs.items():
        print(f"  {old} -> {new or '(deleted)'}")
    print(f"marks moved in: {', '.join(deleted.documents) or 'no document'}")
    return EXIT_OK


POINT_COMMANDS = {"add-point": cmd_add_point, "rename-point": cmd_rename_point,
                  "delete-point": cmd_delete_point}


def cmd_validate(registry: Registry, values: dict,
                 args: argparse.Namespace) -> int:
    problems, notes = validate(registry)
    for line in problems:
        print(f"  FAIL {line}")
    for line in notes:
        print(f"  note {line}")
    print(f"\n{len(registry.figures)} figures, {len(problems)} problems, "
          f"{len(notes)} notes")
    return EXIT_FAILED if problems else EXIT_OK


def cmd_orphans(registry: Registry, values: dict, rel: str) -> int:
    orphans = check_orphans(registry, values, rel)
    print(f"orphan currency tokens in {rel}")
    if orphans is None:
        print("  no such file")
    elif not orphans:
        print("  none")
    else:
        for token in sorted(orphans, key=lambda t: -len(orphans[t])):
            lines = ", ".join(str(n) for n in orphans[token][:6])
            print(f"  ${token:<12} lines {lines}")
    return EXIT_OK


def cmd_one(registry: Registry, values: dict, wanted: str) -> int:
    name = registry.by_ref().get(wanted, wanted)
    if name not in values:
        print(f"unknown figure or ref '{wanted}'", file=sys.stderr)
        return EXIT_USAGE
    print(registry.display(name, values[name]))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit figures", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path", help=f"a {REGISTRY} other than the one above this "
                                  f"working directory")
    p.add_argument("--group", help="list one group only")
    p.add_argument("--strict", action="store_true",
                   help="check: missing coverage and missing data files fail "
                        "too")
    p.add_argument("--as", dest="as_label", metavar="LABEL",
                   help="add-point: this label instead of the template's")
    p.add_argument("--allow-invalid", action="store_true",
                   help="add-point: register a point whose guards failed or "
                        "whose export has gaps")
    p.add_argument("--force", action="store_true",
                   help="delete-point: delete a cited point, removing its marks")
    p.add_argument("args", nargs="*", metavar="<command|figure>")
    return p


def usage(message: str) -> int:
    print(f"usage: report-kit figures {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_intermixed_args(argv)
    rest = opts.args
    command = rest[0] if rest else "list"

    try:
        registry = Registry.load(opts.path)

        # These rewrite the file and never need a value, so they run before
        # resolution — a registry with a figure that does not resolve is
        # exactly one you may still want to renumber, or pull a value into.
        if command == "pull":
            return cmd_pull(registry, rest[1:])
        if command in POINT_COMMANDS:
            return POINT_COMMANDS[command](registry, rest, opts)
        if command == "retype":
            if len(rest) != 3:
                return usage("retype <figure> <M|R|D|E>")
            counts = retype(rest[1], rest[2], registry.path)
            print(f"{rest[1]} is now {rest[2]}; refs renumbered: {counts}")
            return EXIT_OK
        if command == "renumber":
            print(f"refs renumbered: {renumber(registry.path)}")
            return EXIT_OK

        values = registry.resolve()

        if command == "validate":
            return cmd_validate(registry, values, opts)
        if command == "check":
            return cmd_check(registry, values, opts)
        if command == "orphans":
            if len(rest) != 2:
                return usage("orphans <file>")
            return cmd_orphans(registry, values, rest[1])
        if command != "list":
            return cmd_one(registry, values, command)
        return cmd_list(registry, values, opts)
    except (FigureError, points.PointError) as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
