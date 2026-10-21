"""`report-kit values migrate`: a report from before 0.4 — `figures.yaml`, refs
`FM9` — moved to `report-values.yaml` and refs `VM9`, every mark in every
scanned document with it. Written all at once, or not at all."""

from __future__ import annotations

import pathlib
import re
from typing import NamedTuple

from .corpus import rewrite_marks
from .errors import RegistryError
from .registry import REGISTRY, Registry, parse_registry, sequence_of
from .surgery import write_all

OLD_REGISTRY = "figures.yaml"
OLD_REF_LINE = re.compile(r"^(?P<lead>    ref:[ \t]*)F(?P<ref>[MRDE][1-9]\d*)(?P<rest>[^\r\n]*\r?\n?)\Z")
OLD_ANCHOR = re.compile(r"<!--(?P<hidden>F[MRDE]\d+)-->"
                        r"|(?P<space>[ \t]?)\((?P<visible>F[MRDE]\d+)\)")


class Migrated(NamedTuple):
    path: pathlib.Path
    refs: int
    documents: list[str]


def find_old_registry(explicit: str | None, start: pathlib.Path) -> pathlib.Path:
    if explicit:
        path = pathlib.Path(explicit).expanduser().resolve()
        if path.name != OLD_REGISTRY or not path.is_file():
            raise RegistryError(f"{path} is not a {OLD_REGISTRY} to migrate")
        return path
    for folder in (start, *start.parents):
        if (folder / OLD_REGISTRY).is_file():
            return folder / OLD_REGISTRY
    raise RegistryError(f"no {OLD_REGISTRY} in {start} or any parent — nothing to migrate")


def renamed_text(text: str) -> tuple[str, int]:
    """The registry with `figures:` read as `values:` — the top-level block and
    the one inside `points:` — and every `ref: F…` as `ref: V…`."""
    out, refs = [], 0
    for line in text.splitlines(keepends=True):
        if line.rstrip() == "figures:":
            line = line.replace("figures:", "values:", 1)
        elif line.rstrip() == "  figures:":
            line = line.replace("  figures:", "  values:", 1)
        found = OLD_REF_LINE.match(line)
        if found:
            line = f"{found['lead']}V{found['ref']}{found['rest']}"
            refs += 1
        out.append(line)
    return "".join(out), refs


def migrate(explicit: str | None = None,
            start: pathlib.Path | None = None) -> Migrated:
    old = find_old_registry(explicit, (start or pathlib.Path.cwd()).resolve())
    new = old.with_name(REGISTRY)
    if new.exists():
        raise RegistryError(f"{new} already exists; nothing was migrated")
    text, refs = renamed_text(old.read_text())
    doc = parse_registry(text, new)
    if "values" not in doc:
        raise RegistryError(f"{old} has no line reading 'figures:' on its own; "
                            f"nothing was migrated")
    registry = Registry(entries={}, root=old.parent, path=new,
                        scan=sequence_of(doc, "scan", new))
    moved = {}
    for document in registry.documents():
        original = document.path.read_text()
        rewritten = rewrite_marks(original, every_old_ref(original), OLD_ANCHOR)
        if rewritten != original:
            moved[document.path] = rewritten
    write_all({**moved, new: text})
    old.unlink()
    return Migrated(new, refs, sorted(registry.relative(path) for path in moved))


def every_old_ref(text: str) -> dict[str, str]:
    return {ref: "V" + ref[1:] for found in OLD_ANCHOR.finditer(text)
            if (ref := found["hidden"] or found["visible"])}
