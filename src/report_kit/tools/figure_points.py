"""figure_points.py — `report-kit figures add-point`, `rename-point` and
`delete-point`: one run's figures added, renamed and removed as a set.

What a point is, its label and which figures belong to it is `report_kit.points`;
this module edits the registry and the scanned documents as text, the way
`renumber` does, and writes nothing unless every step succeeded.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import re
from typing import NamedTuple

import yaml

from report_kit import evidence, points
from report_kit.tools import figures
from report_kit.tools.figures import FigureError, Registry


POINT_LINE = re.compile(r"^    point:[ \t]*[^#\r\n]*?(?P<rest>(?:[ \t]+#[^\r\n]*)?"
                        r"\r?\n?)\Z")
FORMULA_LINE = re.compile(r"^    formula:(?P<expr>[^\r\n]*)(?P<newline>\r?\n?)\Z")
REPLACED_BY_LINE = re.compile(r"^(?P<lead>\s+(?:- )?replaced_by:[ \t]*)"
                              r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
                              r"(?P<rest>[^\r\n]*\r?\n?)\Z")
ANCHOR = re.compile(r"<!--(?P<hidden>F[MRDE]\d+)-->"
                    r"|(?P<space>[ \t]?)\((?P<visible>F[MRDE]\d+)\)")


def flow(value: object) -> str:
    """One YAML value on one line, quoted where YAML needs it."""
    text = yaml.safe_dump(value, default_flow_style=True, sort_keys=False,
                          allow_unicode=True, width=1_000_000)
    return text.removesuffix("...\n").strip()


def figure_lines(name: str, spec: dict) -> list[str]:
    return ["\n", f"  {name}:\n"] + [
        f"    {key}: {figures.value_text(value) if key == 'value' else flow(value)}\n"
        for key, value in spec.items()]


def appended(text: str, path: pathlib.Path, added: dict[str, dict]) -> str:
    """`text` with these figures after the last line of the figures block,
    so no existing ref moves."""
    lines = text.splitlines(keepends=True)
    start, end = figures.figures_block(lines, path)
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
    spans = figures.figure_spans(lines, path)
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
    start, end = figures.figures_block(lines, path)
    for name, span in figures.figure_spans(lines, path).items():
        if name in names:
            lines[span.start] = lines[span.start].replace(
                f"  {name}:", f"  {names[name]}:", 1)
        for i in span:
            point = POINT_LINE.match(lines[i])
            formula = FORMULA_LINE.match(lines[i])
            if point and name in names:
                lines[i] = f"    point: {flow(label)}{point['rest']}"
            elif formula:
                expr = points.renamed_formula(formula["expr"], names)
                lines[i] = f"    formula:{expr}{formula['newline']}"
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
        for line, view in zip(raw, figures.split_lines(text)))


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


def checked(registry: Registry, text: str) -> Registry:
    """The registry `text` would be. Refused when it does not resolve, or
    breaks a rule the current one keeps."""
    after = figures.parsed(registry, text)
    after.resolve()
    broken = (set(figures.validate(after)[0])
              - set(figures.validate(registry)[0]))
    if broken:
        raise FigureError("the change would break the registry: "
                          + "; ".join(sorted(broken)) + "; nothing was written")
    return after


def next_refs(existing: dict[str, dict], kinds: list[object]) -> list[str]:
    """Refs for new figures of these kinds, after the highest of each kind,
    so no ref already cited moves."""
    highest: collections.Counter = collections.Counter()
    for spec in existing.values():
        match = figures.REF_RE.match(str(spec.get("ref", "")))
        if match:
            highest[match[1]] = max(highest[match[1]], int(match[2]))
    refs = []
    for kind in kinds:
        if kind not in figures.KINDS:
            raise FigureError(f"points: every figure needs kind: "
                              f"{'/'.join(figures.KINDS)}, not {kind!r}")
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


def refuse_registered_run(registry: Registry, rel: str) -> None:
    """A run file registered twice is one measurement printed as two, so no
    flag lifts this: a real repeat is always another run file."""
    users = points.readers(registry.figures, rel)
    if users:
        raise FigureError(f"{rel} is already registered — {', '.join(users)} "
                          f"read it. A repeat is a new run with its own file; "
                          f"nothing was written")


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
                figure["value"] = evidence.reproduce(
                    figures.evidence_source(spec), registry.root)
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
    refuse_registered_run(registry, rel)
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
    expect_renamed(registry, figures.parsed(registry, text), names, new)
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
    remaining = without_figures(registry.path.read_text(), registry.path, names)
    text, _ = figures.renumbered(remaining, registry.path)
    refs = moved_refs(registry, checked(registry, text), names)
    documents = {document.path: document.path.read_text()
                 for document in registry.documents()}
    moved = {path: rewrite_marks(original, refs)
             for path, original in documents.items()}
    changed = {path: rewritten for path, rewritten in moved.items()
               if rewritten != documents[path]}
    write_all({**changed, registry.path: text})
    return Deleted(names, refs, sorted(registry.relative(p) for p in changed))


def cmd_add_point(registry: Registry, rest: list[str],
                  opts: argparse.Namespace) -> int:
    if len(rest) != 2:
        return figures.usage("add-point <run.point.json> [--as LABEL] "
                             "[--allow-invalid]")
    added = add_point(registry, rest[1], opts.as_label, opts.allow_invalid)
    for name, why in added.gaps:
        print(f"  FAIL {name:<28} {why}")
    if added.gaps:
        print(f"\npoint {added.label}: {len(added.gaps)} figure(s) with no "
              f"reading; nothing was written")
        return figures.EXIT_FAILED
    print(f"added point {added.label}")
    for name, spec in added.figures.items():
        shown = (figures.value_text(spec["value"]) if "value" in spec
                 else spec.get("formula", ""))
        print(f"  {spec['ref']:>6}  {name:<28} {shown}")
    return figures.EXIT_OK


def cmd_rename_point(registry: Registry, rest: list[str],
                     opts: argparse.Namespace) -> int:
    if len(rest) != 3:
        return figures.usage("rename-point <old label> <new label>")
    names = rename_point(registry, rest[1], rest[2])
    print(f"point {rest[1]} is now {rest[2]}; refs unchanged")
    for old, new in names.items():
        print(f"  {old} -> {new}")
    return figures.EXIT_OK


def cmd_delete_point(registry: Registry, rest: list[str],
                     opts: argparse.Namespace) -> int:
    if len(rest) != 2:
        return figures.usage("delete-point <label> [--force]")
    deleted = delete_point(registry, rest[1], opts.force)
    print(f"deleted point {rest[1]}: {', '.join(deleted.names)}")
    for old, new in deleted.refs.items():
        print(f"  {old} -> {new or '(deleted)'}")
    print(f"marks moved in: {', '.join(deleted.documents) or 'no document'}")
    return figures.EXIT_OK


COMMANDS = {"add-point": cmd_add_point, "rename-point": cmd_rename_point,
            "delete-point": cmd_delete_point}
