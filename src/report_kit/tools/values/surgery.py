"""`report-values.yaml` edited as text, a line at a time, so its comments and
block scalars survive."""

from __future__ import annotations

import collections
import os
import pathlib
import re
from dataclasses import replace

import yaml

from . import points
from .errors import RegistryError
from .registry import (
    KINDS, Registry, entries_of, parse_registry, sequence_of, stored_number)


# The rewriter's view of the file: a value's name at two spaces, its keys at
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


def renumbered(text: str, path: pathlib.Path,
               kinds: dict[str, str] | None = None) -> tuple[str, dict[str, int]]:
    """Every ref rewritten so the sequence per kind follows file order: the new
    text and the count per kind. `kinds` reclassifies in the same pass.

    Refuses rather than half-applies: a value the rewriter cannot see would
    keep its old ref while everything after it shifts, orphaning every mark
    that points at either one.
    """
    entries = entries_of(parse_registry(text, path), path)

    overrides = dict(kinds or {})
    for name, kind in overrides.items():
        if name not in entries:
            raise RegistryError(f"unknown value '{name}'")
        if kind not in KINDS:
            raise RegistryError(f"kind must be one of {'/'.join(KINDS)}")

    lines = text.splitlines(keepends=True)
    start, end = entries_block(lines, path)

    counters: collections.Counter = collections.Counter()
    out, written = [], []
    for i, line in enumerate(lines):
        if start < i < end and REFKIND_LINE.match(line):
            continue
        out.append(line)
        if not start < i < end:
            continue
        m = NAME_LINE.match(line)
        if not m or m.group(1) not in entries:
            continue
        name = m.group(1)
        kind = overrides.get(name, entries[name].get("kind", "M"))
        if kind not in KINDS:
            raise RegistryError(f"{name}: kind {kind!r} is not one of "
                              f"{'/'.join(KINDS)} — fix it before renumbering")
        counters[kind] += 1
        out.append(f"    ref: V{kind}{counters[kind]}\n")
        out.append(f"    kind: {kind}\n")
        written.append(name)

    unseen = [name for name in entries if name not in written]
    if unseen:
        raise RegistryError(
            f"{path}: {len(unseen)} value(s) the rewriter cannot see — "
            f"{', '.join(unseen[:5])}. A value needs its name alone on a line "
            f"indented two spaces, its keys four; nothing was written")
    return "".join(out), dict(counters)


def entries_block(lines: list[str], path: pathlib.Path) -> tuple[int, int]:
    """The `values:` line and the first line after its block."""
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == "values:"), None)
    if start is None:
        raise RegistryError(
            f"{path}: no line reading 'values:' on its own — the rewriter "
            f"edits the block as text and cannot rewrite an inline mapping")
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i][0].isspace():
            return start, i
    return start, len(lines)


def entry_spans(lines: list[str], path: pathlib.Path) -> dict[str, range]:
    """Each value's lines, from its name to the line before the next."""
    start, end = entries_block(lines, path)
    names = [(i, m.group(1)) for i in range(start + 1, end)
             if (m := NAME_LINE.match(lines[i]))]
    stops = [i for i, _ in names[1:]] + [end]
    return {name: range(i, stop) for (i, name), stop in zip(names, stops)}


def value_text(value: float) -> str:
    """Full precision without the float noise: 0.0022 * 100 writes 0.22."""
    rounded = float(f"{value:.15g}")
    return str(int(rounded)) if rounded.is_integer() else repr(rounded)


def with_value(lines: list[str], span: range, text: str) -> list[str]:
    """`lines` with this entry's `value:` line replaced, or inserted after its
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
    """Rewrite one `value:` line per value and touch nothing else, so the
    file's comments and block scalars survive byte for byte. Refuses, and
    writes nothing, when a value is not where the rewriter can see it."""
    path = pathlib.Path(path)
    lines = path.read_text().splitlines(keepends=True)
    for name, text in texts.items():
        span = entry_spans(lines, path).get(name)
        if span is None:
            raise RegistryError(
                f"{path}: the rewriter cannot see '{name}' — a value needs "
                f"its name alone on a line indented two spaces, its keys "
                f"four; nothing was written")
        lines = with_value(lines, span, text)
    rewritten = entries_of(parse_registry("".join(lines), path), path)
    for name, text in texts.items():
        if stored_number(rewritten[name].get("value")) != float(text):
            raise RegistryError(f"{path}: '{name}' did not read back as {text} "
                              f"after the rewrite; nothing was written")
    path.write_text("".join(lines))


def parsed(registry: Registry, text: str) -> Registry:
    doc = parse_registry(text, registry.path)
    return replace(registry, entries=entries_of(doc, registry.path),
                   retired=sequence_of(doc, "retired", registry.path))


def flow(value: object) -> str:
    """One YAML value on one line, quoted where YAML needs it."""
    text = yaml.safe_dump(value, default_flow_style=True, sort_keys=False,
                          allow_unicode=True, width=1_000_000)
    return text.removesuffix("...\n").strip()


def entry_lines(name: str, spec: dict) -> list[str]:
    return ["\n", f"  {name}:\n"] + [
        f"    {key}: {value_text(value) if key == 'value' else flow(value)}\n"
        for key, value in spec.items()]


def appended(text: str, path: pathlib.Path, added: dict[str, dict]) -> str:
    """`text` with these entries after the last line of the entries block,
    so no existing ref moves."""
    lines = text.splitlines(keepends=True)
    start, end = entries_block(lines, path)
    last = max(i for i in range(start, end) if lines[i].strip())
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    block = [line for name, spec in added.items()
             for line in entry_lines(name, spec)]
    return "".join(lines[:last + 1] + block + lines[last + 1:])


def without_entries(text: str, path: pathlib.Path, names: list[str]) -> str:
    """`text` without these entries: each from its name through its last
    indented line, and the blank lines after it."""
    lines = text.splitlines(keepends=True)
    spans = entry_spans(lines, path)
    dropped: set[int] = set()
    for name in names:
        span = spans.get(name)
        if span is None:
            raise RegistryError(f"{path}: the rewriter cannot see '{name}'; "
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
    start, end = entries_block(lines, path)
    for name, span in entry_spans(lines, path).items():
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


def with_point_key(lines: list[str], span: range, label: str) -> list[str]:
    after = max((i for i in span if REFKIND_LINE.match(lines[i])),
                default=span.start)
    return (lines[:after + 1] + [f"    point: {flow(label)}\n"]
            + lines[after + 1:])


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
        raise RegistryError(f"cannot write {exc.filename}: {exc.strerror}; "
                          f"nothing was changed") from exc
    for path, temporary in staged.items():
        os.replace(temporary, path)
