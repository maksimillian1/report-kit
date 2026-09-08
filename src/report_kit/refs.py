from __future__ import annotations

import re
from pathlib import Path

from .constants import die
from .text import fill


def read_ref_file(path: Path, fields: int) -> list[list[str]]:
    """Shared parser for series.txt and guards.txt. Pipe-separated, '#' comments
    and blanks ignored. Refs are unique within a file — which is why the same ref
    exported as a series and checked as a guard lives in two files."""
    if not path.is_file():
        die(f"file not found: {path}")
    rows: list[list[str]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", fields - 1)]
        if len(parts) != fields:
            die(f"{path}:{lineno} expected {fields} '|'-separated fields, "
                f"got {len(parts)}")
        if any(not p for p in parts):
            die(f"{path}:{lineno} empty field")
        rows.append(parts)
    if not rows:
        die(f"{path} holds no entries")
    refs = [row[0] for row in rows]
    dupes = {r for r in refs if refs.count(r) > 1}
    if dupes:
        die(f"{path}: duplicate refs: {', '.join(sorted(dupes))}")
    return rows


BOUND_TOKEN = re.compile(r"(min|max)\s+(\S+)")


def _substitute(value: str, subs: dict, path: Path, ref: str) -> str:
    """text.fill(), with the file and ref named in the error — a missing
    substitution is a mistake in a frozen file, and the message should say
    which line of which file to go fix."""
    try:
        return fill(value, subs)
    except KeyError as e:
        die(f"{path}: guard {ref} references unknown substitution '{e.args[0]}'")


def load_guards(path: Path, substitutions: dict | None = None) -> list[dict]:
    """ref|bound|promql. Bound is one or both of 'min <v>' and 'max <v>'.
    Substitutions fill {name} placeholders in bounds and queries — the only
    place a per-point value is allowed into a frozen file."""
    subs = substitutions or {}
    guards = []
    for ref, bound, query in read_ref_file(path, 3):
        bound = _substitute(bound, subs, path, ref)
        query = _substitute(query, subs, path, ref)
        found = BOUND_TOKEN.findall(bound)
        if not found:
            die(f"{path}: guard {ref} has no bound — expected 'min <v>' or "
                f"'max <v>', got {bound!r}")
        entry: dict = {"ref": ref, "query": query}
        for kind, value in found:
            try:
                entry[kind] = float(value)
            except ValueError:
                die(f"{path}: guard {ref} bound {kind} is not a number: {value!r}")
        guards.append(entry)
    return guards
