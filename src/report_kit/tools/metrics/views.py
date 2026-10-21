"""What `metrics.yaml` renders: the register table, between two marker lines in
the one document beside it that holds them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from report_kit.register import REGISTER, Register, RegisterError

TABLE_HEADER = ("| Ref | What it measures | Source | Status | Notes |",
                "| :--- | :--- | :--- | :--- | :--- |")
BEGIN = f"<!-- report-kit metrics: generated from {REGISTER}, edit that file -->"
BEGIN_RE = re.compile(r"^<!-- report-kit metrics: .*-->\s*$")
END = "<!-- /report-kit metrics -->"


@dataclass(frozen=True)
class View:
    path: Path
    text: str

    def is_current(self) -> bool:
        try:
            return self.path.read_text(encoding="utf-8") == self.text
        except OSError:
            return False


def table_lines(register: Register) -> list[str]:
    rows = [table_row(m.ref, m.what, m.source or f"`{m.promql}`", m.status, m.notes)
            for m in register.metrics]
    return [*TABLE_HEADER, *rows]


def table_row(*cells: str) -> str:
    return "|" + "|".join(f" {escape(cell)} " if cell else " " for cell in cells) + "|"


def escape(cell: str) -> str:
    return cell.replace("|", r"\|")


def table_document(register: Register) -> Path:
    """The one document beside the register that holds the marked block.
    Moving the block is how the table moves, from `index.md` to `metrics.md`."""
    marked = [doc for doc in sorted(register.directory.glob("*.md"))
              if any(BEGIN_RE.match(line) for line in read_lines(doc))]
    if not marked:
        raise RegisterError(f"no document beside {register.path} holds the marked "
                            f"block — put these two lines where the table goes:\n"
                            f"    {BEGIN}\n    {END}")
    if len(marked) > 1:
        names = ", ".join(doc.name for doc in marked)
        raise RegisterError(f"{names} each hold a marked block; the register "
                            f"renders into one")
    return marked[0]


def spliced(document: Path, block: list[str]) -> str:
    lines = read_lines(document)
    begins = [i for i, line in enumerate(lines) if BEGIN_RE.match(line)]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise RegisterError(f"{document}: expected one '{BEGIN}' followed by one "
                            f"'{END}'")
    kept = lines[:begins[0]] + [BEGIN, "", *block, "", END] + lines[ends[0] + 1:]
    return "\n".join(kept) + "\n"


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def table_view(register: Register) -> View:
    document = table_document(register)
    return View(document, spliced(document, table_lines(register)))


def write_table(register: Register) -> Path | None:
    """The document, when its table had to be rewritten."""
    view = table_view(register)
    if view.is_current():
        return None
    view.path.write_text(view.text, encoding="utf-8")
    return view.path
