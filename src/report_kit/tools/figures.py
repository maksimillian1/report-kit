#!/usr/bin/env python3
"""figures.py — the report's numbers: resolve them, and fail when they drift.

    report-kit figures                    every figure, grouped
    report-kit figures block_b_total      one figure, bare value
    report-kit figures FD26               the same, by ref
    report-kit figures --group totals
    report-kit figures check [--strict]   retired values, coverage, ref identity
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

The registry is found by walking up from the working directory, so the command
works from anywhere inside a report. `--path` names one explicitly, which is
also how you check a registry that is not the one you are standing in.

Everything above `cmd_list` is the model and prints nothing, so a caller that
wants a value rather than a page imports it and calls it directly. Every
failure that depends on what the registry says arrives as `FigureError`
rather than as whatever exception the parser happened to raise.
"""

from __future__ import annotations

import argparse
import ast
import collections
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Iterable, NamedTuple

import yaml


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
    """The report root and the registry file inside it.

    The root is whatever directory holds `figures.yaml`, because every `scan`
    entry and every `appears_in` path is written relative to it. Deriving it
    from this file's own location on disk would work only while the tool lived
    inside the report it checked; installed as a command it has to be found.
    """
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


def _parse(text: str, path: pathlib.Path) -> dict:
    try:
        doc = yaml.safe_load(text)
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
                   retired=_sequence(doc, "retired", path))

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
        """The kind a figure prints as — the weakest input decides.

        A derived figure with an estimate anywhere upstream prints ᴱ however
        many steps sit between, so nobody has to remember to downgrade a mark
        by hand.
        """
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
        """Figures by group, groups in the order they first appear.

        The file's order is the author's, and a fixed list here would bake one
        report's subjects — a floor, a sweep, a campaign — into a tool meant
        for any of them.
        """
        grouped: dict[str, list[str]] = {}
        for name, spec in self.figures.items():
            grouped.setdefault(str(spec.get("group", DEFAULT_GROUP)),
                               []).append(name)
        return grouped

    # -- documents --------------------------------------------------------

    def documents(self) -> list[Document]:
        """Every file `scan` names, read once, each one only once.

        Entries overlap freely — `report.md` beside `*.md` is the obvious
        case — and a file counted twice would double the marked-number count,
        which is the one number that notices a ref orphaned by a delete.
        """
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
        if "formula" not in spec and not spec.get("source"):
            problems.append(f"{name}: a leaf with no source")
        if kind == "D" and registry.effective_kind(name) == "E":
            notes.append(f"{name}: prints ᴱ — a formula, but one of its inputs "
                         f"is an estimate")
    for ref, count in refs.items():
        if count > 1:
            problems.append(f"ref {ref} used by {count} figures")
    return problems, notes


# ---------------------------------------------------------- file surgery

def renumber(path: str | os.PathLike,
             kinds: dict[str, str] | None = None) -> dict[str, int]:
    """Rewrite every ref so the sequence per kind follows file order.

    Refs are assigned by the tool precisely so that changing a kind stays
    cheap. `kinds` reclassifies figures in the same pass, which is how
    `retype` works — the ref and kind lines are emitted from the parsed
    registry rather than edited in place, so a figure whose `kind:` is
    missing, commented or oddly spaced is handled like any other.

    Refuses rather than half-applies: a figure the rewriter cannot see keeps
    its old ref while everything after it shifts, which silently orphans every
    mark pointing at either one.
    """
    path = pathlib.Path(path)
    text = path.read_text()
    figures = _figures_of(_parse(text, path), path)

    overrides = dict(kinds or {})
    for name, kind in overrides.items():
        if name not in figures:
            raise FigureError(f"unknown figure '{name}'")
        if kind not in KINDS:
            raise FigureError(f"kind must be one of {'/'.join(KINDS)}")

    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == "figures:"), None)
    if start is None:
        raise FigureError(
            f"{path}: no line reading 'figures:' on its own — the rewriter "
            f"edits the block as text and cannot renumber an inline mapping")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i][0].isspace():
            end = i
            break

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
    path.write_text("".join(out))
    return dict(counters)


def retype(name: str, kind: str, path: str | os.PathLike) -> dict[str, int]:
    """Change one figure's kind and renumber every ref to match."""
    if kind not in KINDS:
        raise FigureError(f"kind must be one of {'/'.join(KINDS)}")
    return renumber(path, {name: kind})


# ---------------------------------------------------------------- the command

# `constants.EXIT_*` numbers what a *runner* did — a preflight refusal, an
# export gap — and says nothing about a checker. These three are this
# command's own contract, and the report's CI reads them.
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

    print()
    return EXIT_FAILED if failed else EXIT_OK


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
                   help="check: missing coverage fails too")
    p.add_argument("args", nargs="*", metavar="<command|figure>")
    return p


def usage(message: str) -> int:
    print(f"usage: report-kit figures {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    rest = opts.args
    command = rest[0] if rest else "list"

    try:
        registry = Registry.load(opts.path)

        # These two rewrite the file and never need a value, so they run
        # before resolution — a registry with a figure that does not resolve
        # is exactly one you may still want to renumber.
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
    except FigureError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
