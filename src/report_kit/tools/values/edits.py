"""Edits that span the registry and the documents citing it: points added,
adopted, renamed and removed. Each is computed in full before anything is
written, and nothing is written unless all of it succeeds."""

from __future__ import annotations

import ast
import collections
import json
import os
import pathlib
from dataclasses import replace
from typing import NamedTuple

from . import evidence, points
from .errors import RegistryError
from .registry import KINDS, REF_RE, Registry
from .corpus import ANCHOR, rewrite_marks
from .checks import validate
from .readings import evidence_source
from .surgery import (
    appended, entry_spans, flow, parsed, renamed_text, renumbered,
    with_point_key, without_entries, write_all)


def checked(registry: Registry, text: str) -> Registry:
    """The registry `text` would be. Refused when it does not resolve, or
    breaks a rule the current one keeps."""
    after = parsed(registry, text)
    after.resolve()
    refuse_breaking(registry, after)
    return after


def refuse_breaking(before: Registry, after: Registry) -> None:
    broken = set(validate(after)[0]) - set(validate(before)[0])
    if broken:
        raise RegistryError("the change would break the registry: "
                          + "; ".join(sorted(broken)) + "; nothing was written")


def next_refs(existing: dict[str, dict], kinds: list[object]) -> list[str]:
    """Refs for new entries of these kinds, after the highest of each kind,
    so no ref already cited moves."""
    highest: collections.Counter = collections.Counter()
    for spec in existing.values():
        match = REF_RE.match(str(spec.get("ref", "")))
        if match:
            highest[match[1]] = max(highest[match[1]], int(match[2]))
    refs = []
    for kind in kinds:
        if kind not in KINDS:
            raise RegistryError(f"points: every value needs kind: "
                              f"{'/'.join(KINDS)}, not {kind!r}")
        highest[kind] += 1
        refs.append(f"V{kind}{highest[kind]}")
    return refs


class Added(NamedTuple):
    label: str
    entries: dict[str, dict]
    gaps: list[tuple[str, str]]


def point_record(path: str | os.PathLike) -> dict:
    try:
        record = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RegistryError(f"cannot read point record {path}: {exc}") from exc
    if not isinstance(record, dict):
        raise RegistryError(f"{path} is not a point record")
    return record


def refuse_registered_run(registry: Registry, rel: str) -> None:
    """A run file registered twice is one measurement printed as two, so no
    flag lifts this: a real repeat is always another run file."""
    users = points.readers(registry.entries, rel)
    if users:
        raise RegistryError(f"{rel} is already registered — {', '.join(users)} "
                          f"read it. A repeat is a new run with its own file; "
                          f"nothing was written")


def refuse_outside_grid(registry: Registry, template: points.Template,
                        record: dict, path: str, allow_invalid: bool) -> None:
    invalid = points.validity_problems(record)
    if invalid and not allow_invalid:
        raise RegistryError(f"{path} is not a valid point ({'; '.join(invalid)});"
                          f" pass --allow-invalid to register it anyway")
    values = {name: registry.value(name) for name in template.held.values()}
    held = points.held_mismatches(template, record, values)
    if held:
        raise RegistryError(f"{path} is not a point of this grid: "
                          f"{'; '.join(held)}. A different grid is never a "
                          f"repeat of this one")


def point_label(registry: Registry, template: points.Template, record: dict,
                rel: str, wanted: str | None) -> str:
    def taken(label: str) -> bool:
        return label in points.labels_in_use(registry.entries) or any(
            name in registry.entries
            for name in points.expand(template, label, rel))

    if wanted is None:
        return points.free_label(points.base_label(template, record), taken)
    points.check_label(wanted)
    if taken(wanted):
        raise RegistryError(f"label {wanted} is taken")
    return wanted


def with_readings(registry: Registry, added: dict[str, dict]
                  ) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """The entries as they are written — ref, kind, point, value, then the
    template's own keys — and every reading that failed."""
    refs = iter(next_refs(registry.entries,
                          [spec["kind"] for spec in added.values()]))
    written, gaps = {}, []
    for name, spec in added.items():
        entry = {"ref": next(refs), "kind": spec["kind"], "point": spec["point"]}
        if "from" in spec:
            try:
                entry["value"] = evidence.reproduce(
                    evidence_source(spec), registry.root)
            except evidence.EvidenceError as exc:
                gaps.append((name, str(exc)))
        written[name] = {**entry, **{key: value for key, value in spec.items()
                                      if key not in entry}}
    return written, gaps


def point_template(registry: Registry) -> points.Template:
    if registry.points is None or registry.path is None:
        raise RegistryError("no points: block — the point commands expand that "
                          "template")
    return points.read_template(registry.points)


def add_point(registry: Registry, path: str | os.PathLike,
              wanted: str | None = None, allow_invalid: bool = False) -> Added:
    """Expand `points:` for one run and append it, its values pulled. Writes
    nothing when a reading is a gap, or when the result would not resolve."""
    template = point_template(registry)
    record, rel = point_record(path), registry.relative(pathlib.Path(path))
    refuse_registered_run(registry, rel)
    refuse_outside_grid(registry, template, record, str(path), allow_invalid)
    label = point_label(registry, template, record, rel, wanted)
    written, gaps = with_readings(registry,
                                  points.expand(template, label, rel))
    if gaps:
        return Added(label, {}, gaps)
    text = appended(registry.path.read_text(), registry.path, written)
    checked(registry, text)
    write_all({registry.path: text})
    return Added(label, written, [])


def same_source(stored: object, expected: object) -> bool:
    if stored is None or expected is None:
        return stored is expected
    try:
        one, other = evidence.read_source(stored), evidence.read_source(expected)
    except evidence.EvidenceError:
        return stored == expected
    return (replace(one, file=os.path.normpath(one.file))
            == replace(other, file=os.path.normpath(other.file)))


def same_formula(stored: object, expected: object) -> bool:
    if stored is None or expected is None:
        return stored is expected
    try:
        return (ast.dump(ast.parse(str(stored), mode="eval"))
                == ast.dump(ast.parse(str(expected), mode="eval")))
    except SyntaxError:
        return str(stored).strip() == str(expected).strip()


def adoption_problems(registry: Registry, name: str, expected: dict,
                      label: str) -> list[str]:
    """Why an existing value is not what the template makes of this run.
    Only kind, from:, formula and metric decide; the prose keys are the
    author's."""
    stored = registry.entries.get(name)
    if stored is None:
        return [f"{name} is missing"]
    problems = []
    if "point" in stored and str(stored["point"]) != label:
        problems.append(f"{name} already belongs to point {stored['point']}")
    if str(stored.get("kind")) != str(expected.get("kind")):
        problems.append(f"{name} is kind {stored.get('kind')}, the template "
                        f"makes it {expected.get('kind')}")
    if not same_source(stored.get("from"), expected.get("from")):
        problems.append(f"{name} reads {flow(stored.get('from'))}, the template "
                        f"reads {flow(expected.get('from'))}")
    if not same_formula(stored.get("formula"), expected.get("formula")):
        problems.append(f"{name} computes {stored.get('formula')}, the template "
                        f"computes {expected.get('formula')}")
    if stored.get("metric") != expected.get("metric"):
        problems.append(f"{name} names metric {stored.get('metric')}, the "
                        f"template names {expected.get('metric')}")
    return problems


def refuse_bound_elsewhere(registry: Registry, rel: str, label: str) -> None:
    bound = sorted({str(registry.entries[name]["point"])
                    for name in points.readers(registry.entries, rel)
                    if "point" in registry.entries[name]} - {label})
    if bound:
        raise RegistryError(f"{rel} is already bound to point "
                          f"{', '.join(bound)}; nothing was written")


def adopt_point(registry: Registry, label: str, path: str | os.PathLike,
                allow_invalid: bool = False) -> list[str]:
    """Bind entries written before the template to point `label`: every
    value the template makes of this run must exist and agree, or nothing
    is written. Refs never move, so no document changes. Returns the names
    that gained a `point:` key."""
    template = point_template(registry)
    record, rel = point_record(path), registry.relative(pathlib.Path(path))
    refuse_outside_grid(registry, template, record, str(path), allow_invalid)
    points.check_label(label)
    refuse_bound_elsewhere(registry, rel, label)
    expected = points.expand(template, label, rel)
    problems = [problem for name, spec in expected.items()
                for problem in adoption_problems(registry, name, spec, label)]
    problems += [f"{name} carries point: {label} but the template does not "
                 f"make it" for name in points.members(registry.entries, label)
                 if name not in expected]
    if problems:
        raise RegistryError(f"cannot adopt {rel} as {label}: "
                          f"{'; '.join(problems)}; nothing was written")
    unbound = [name for name in expected if "point" not in registry.entries[name]]
    lines = registry.path.read_text().splitlines(keepends=True)
    for name in unbound:
        lines = with_point_key(lines, entry_spans(lines, registry.path)[name],
                               label)
    text = "".join(lines)
    expect_bound(registry, parsed(registry, text), unbound, label)
    checked(registry, text)
    write_all({registry.path: text})
    return unbound


def expect_bound(before: Registry, after: Registry, names: list[str],
                 label: str) -> None:
    expected = {name: {**spec, "point": label} if name in names else spec
                for name, spec in before.entries.items()}
    if list(after.entries.items()) != list(expected.items()):
        raise RegistryError(f"{before.path}: the rewriter could not add point: "
                          f"{label} where it can see; nothing was written")


def point_members(registry: Registry, label: str) -> list[str]:
    names = points.members(registry.entries, label)
    if not names:
        raise RegistryError(f"no value carries point: {label}")
    return names


def rename_point(registry: Registry, old: str, new: str) -> dict[str, str]:
    """Rename every value of point `old`, and every formula naming one.
    Refs stay, so no document changes. Returns old name -> new name."""
    points.check_label(new)
    names = {name: points.renamed(name, old, new)
             for name in point_members(registry, old)}
    clashes = [name for name in names.values()
               if name in registry.entries and name not in names]
    if new in points.labels_in_use(registry.entries) or clashes:
        raise RegistryError(f"label {new} is taken"
                          + (f" ({', '.join(clashes)})" if clashes else ""))
    text = renamed_text(registry.path.read_text(), registry.path, names, new)
    expect_renamed(registry, parsed(registry, text), names, new)
    checked(registry, text)
    write_all({registry.path: text})
    return names


def expect_renamed(before: Registry, after: Registry, names: dict[str, str],
                   label: str) -> None:
    expected = {}
    for name, spec in before.entries.items():
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
    if list(after.entries.items()) != list(expected.items()) \
            or list(after.retired) != retired:
        raise RegistryError(f"{before.path}: the rewriter could not rename every "
                          f"reference — one sits where it cannot see, such as "
                          f"a formula across lines; nothing was written")


class Deleted(NamedTuple):
    names: list[str]
    refs: dict[str, str | None]
    documents: list[str]


def formula_dependents(registry: Registry, names: list[str]) -> list[str]:
    gone = set(names)
    found = [name for name in registry.entries
             if name not in gone and gone & set(registry.inputs(name))]
    return found + [f"retired {item.get('pattern')!r}"
                    for item in registry.retired
                    if isinstance(item, dict) and item.get("replaced_by") in gone]


def cited_anchors(registry: Registry, names: list[str]) -> list[str]:
    refs = {str(registry.entries[name].get("ref")) for name in names}
    return [f"{ref} at {document.rel}:{line.number}"
            for document in registry.documents() for line in document.lines
            for match in ANCHOR.finditer(line.text)
            if (ref := match["hidden"] or match["visible"]) in refs]


def moved_refs(before: Registry, after: Registry,
               names: list[str]) -> dict[str, str | None]:
    refs: dict[str, str | None] = {str(before.entries[name].get("ref")): None
                                   for name in names}
    for name, spec in after.entries.items():
        old = str(before.entries[name].get("ref"))
        if old != str(spec.get("ref")):
            refs[old] = str(spec.get("ref"))
    return refs


def delete_point(registry: Registry, label: str, force: bool = False) -> Deleted:
    """Remove a point's values, renumber, and move every shifted mark in
    every scanned document. Everything is computed before anything is
    written, and nothing is written unless all of it succeeds."""
    names = point_members(registry, label)
    dependents = formula_dependents(registry, names)
    if dependents:
        raise RegistryError(f"point {label} is still used by "
                          f"{', '.join(dependents)}; nothing was deleted")
    cited = cited_anchors(registry, names)
    if cited and not force:
        raise RegistryError(f"point {label} is cited — {', '.join(cited)}. Carry "
                          f"it as a row instead, or pass --force to delete it "
                          f"and remove those marks; nothing was deleted")
    remaining = without_entries(registry.path.read_text(), registry.path, names)
    text, _ = renumbered(remaining, registry.path)
    refs = moved_refs(registry, checked(registry, text), names)
    changed = with_marks_moved(registry, refs)
    write_all({**changed, registry.path: text})
    return Deleted(names, refs, sorted(registry.relative(p) for p in changed))


def with_marks_moved(registry: Registry,
                     refs: dict[str, str | None]) -> dict[pathlib.Path, str]:
    """Every scanned document whose marks the map moves, rewritten."""
    documents = {document.path: document.path.read_text()
                 for document in registry.documents()}
    moved = {path: rewrite_marks(original, refs)
             for path, original in documents.items()}
    return {path: rewritten for path, rewritten in moved.items()
            if rewritten != documents[path]}


class Renumbered(NamedTuple):
    counts: dict[str, int]
    refs: dict[str, str | None]
    documents: list[str]


def unheld_anchors(registry: Registry) -> list[str]:
    held = set(registry.by_ref())
    return [f"{ref} at {document.rel}:{line.number}"
            for document in registry.documents() for line in document.lines
            for match in ANCHOR.finditer(line.text)
            if (ref := match["hidden"] or match["visible"]) not in held]


def renumber(registry: Registry, kinds: dict[str, str] | None = None) -> Renumbered:
    """Refs back in file order, and every mark in every scanned document moved
    with its value. `kinds` reclassifies in the same pass, which is `retype`.

    A mark that no value holds is refused first: renumbering could hand its
    ref to another value, and the mark would then verify a number it never
    meant. The registry need not resolve, so one with a value still waiting
    for its value can be renumbered."""
    if registry.path is None:
        raise RegistryError("renumber rewrites a registry file; this one has none")
    unheld = unheld_anchors(registry)
    if unheld:
        raise RegistryError(f"marked, but no value holds the ref: "
                          f"{', '.join(unheld)}. Renumbering could give it to "
                          f"another value; fix those marks first; nothing was "
                          f"written")
    text, counts = renumbered(registry.path.read_text(), registry.path, kinds)
    after = parsed(registry, text)
    refuse_breaking(registry, after)
    refs = moved_refs(registry, after, [])
    changed = with_marks_moved(registry, refs)
    write_all({**changed, registry.path: text})
    return Renumbered(counts, refs, sorted(registry.relative(p) for p in changed))


def retype(registry: Registry, name: str, kind: str) -> Renumbered:
    """Change one value's kind, renumber every ref, and move the marks."""
    if kind not in KINDS:
        raise RegistryError(f"kind must be one of {'/'.join(KINDS)}")
    return renumber(registry, {name: kind})
