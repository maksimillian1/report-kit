"""The documents a registry scans: their lines, the code in them, and the marks."""

from __future__ import annotations

import os
import pathlib
import re
from typing import NamedTuple

from .errors import RegistryError


# Two marking forms, and both have to verify or the one nobody checks is the
# one that rots. The hidden form glues the ref to the digits inside a comment.
# The visible form is an anchor a reader can see — between the number and its
# ref only closing markup, a trust marker and whitespace may sit, never a
# word, because a ref separated from its number by prose would capture
# whatever number happened to come before it.
MARKED = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)<!--(V[MRDE]\d+)-->"
    r"|(-?\d[\d,]*(?:\.\d+)?)[*`_]{0,2}\s{0,2}[ᴿᴰᴱ]?\s{0,2}\((V[MRDE]\d+)\)")


# `formats.md`: fenced code blocks and inline code spans are skipped whole.
# Queries, commands and manifests are full of digits that mean nothing to the
# report, and a number quoted inside an example command is not a claim.
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
INLINE_CODE = re.compile(r"`[^`]*`")
ANCHOR = re.compile(r"<!--(?P<hidden>V[MRDE]\d+)-->"
                    r"|(?P<space>[ \t]?)\((?P<visible>V[MRDE]\d+)\)")


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
        raise RegistryError(f"cannot read {path}: {exc}") from exc
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


def moved_anchor(match: re.Match, refs: dict[str, str | None]) -> str:
    ref = match["hidden"] or match["visible"]
    if ref not in refs:
        return match.group()
    new = refs[ref]
    if match["hidden"]:
        return "" if new is None else f"<!--{new}-->"
    return "" if new is None else f"{match['space']}({new})"


def rewrite_marks(text: str, refs: dict[str, str | None],
                  anchor: re.Pattern = ANCHOR) -> str:
    """Every anchor outside fenced code moved by an exact old -> new map; one
    that maps to None is removed. An anchor is the whole `<!--VM1-->` or
    `(VM1)`, so VM1 never matches inside VM12."""
    raw = text.splitlines(keepends=True)
    return "".join(
        anchor.sub(lambda m: moved_anchor(m, refs), line) if view.text else line
        for line, view in zip(raw, split_lines(text)))
