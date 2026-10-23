#!/usr/bin/env python3
"""metrics — an execution's metric register: one YAML file, every view generated.

    report-kit metrics write           render the register table
    report-kit metrics check           fail when a view no longer matches the register,
                                       or the register names a ref nothing defines
    report-kit metrics check --all     every metrics.yaml under the working directory
    report-kit metrics check --strict  a D ref defined in prose alone fails too
    report-kit metrics import          build metrics.yaml from a hand-kept table,
                                       series.txt and guards.txt (before 0.4)

`metrics.yaml` sits beside the execution's `index.md`. A runner reads it for
what to export, what to guard and which deployments its window waits for, and
this command renders its register table between two marker lines in whichever
document beside it holds them. The register is found by walking up from the
working directory; `--path` names one explicitly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_kit import shell
from report_kit.constants import BAD, OK, WARN

from .legacy import GUARDS_FILE, SERIES_FILE, find_table, imported
from .mentions import mention_problems
from report_kit.execution_config import (
    EXECUTION, WINDOW, ExecutionError, parse_execution, read_execution)
from report_kit.register import (
    REGISTER, RegisterError, find_register, parse_register, read_register)
from .views import table_lines, table_view, write_table

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def registers_below(directory: Path) -> list[Path]:
    """Every register under `directory` that git does not ignore — a build
    directory holds copies of the templates' — or, outside a repository,
    every one not under a hidden directory."""
    try:
        listed = shell.sh(["git", "ls-files", "--cached", "--others",
                           "--exclude-standard", "--", f"*{REGISTER}"])
        found = [directory / line for line in listed.splitlines()]
    except (RuntimeError, OSError):
        found = list(directory.rglob(REGISTER))
    return sorted(path for path in found
                  if path.name == REGISTER and path.is_file()
                  and not any(part.startswith(".")
                              for part in path.relative_to(directory).parts))


def registers(opts: argparse.Namespace) -> list[Path]:
    if opts.all:
        found = registers_below(Path.cwd())
        if not found:
            raise RegisterError(f"no {REGISTER} under {Path.cwd()}")
        return found
    if opts.path:
        path = Path(opts.path)
        return [path / REGISTER if path.is_dir() else path]
    found = find_register(Path.cwd())
    if found is None:
        raise RegisterError(f"no {REGISTER} here or above — pass --path")
    return [found]


def shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def cmd_write(paths: list[Path]) -> int:
    for path in paths:
        written = write_table(read_register(path))
        print(f"[{OK}] {shown(path)}: "
              f"{shown(written) if written else 'nothing changed'}")
    return EXIT_OK


def cmd_check(paths: list[Path], strict: bool = False) -> int:
    failed = 0
    for path in paths:
        register = read_register(path)
        view = table_view(register)
        stale = not view.is_current()
        dangling = mention_problems(register) + execution_problems(register)
        if strict:
            dangling += prose_problems(register)
        if stale:
            print(f"[{BAD}] {shown(path)}: the table in {shown(view.path)} no "
                  f"longer matches — run report-kit metrics write")
        for problem in dangling:
            print(f"[{BAD}] {shown(path)}: {problem}")
        if not stale and not dangling:
            print(f"[{OK}] {shown(path)}: the table matches, every ref it names "
                  f"is defined, and {EXECUTION} beside it reads")
        failed += bool(stale or dangling)
    return EXIT_FAILED if failed else EXIT_OK


def prose_problems(register) -> list[str]:
    """A D ref nothing can work out: its formula lives in a sentence."""
    return [f"{metric.ref} is derived in prose only — give it formula:, series: "
            f"or record:, so every run's data produces it"
            for metric in register.metrics
            if metric.ref.startswith("D") and not metric.derived_from_data]


def execution_problems(register) -> list[str]:
    """execution.yaml beside the register, read against it: a guard's metric:
    has to be one of its exported refs."""
    path = register.directory / EXECUTION
    if not path.is_file():
        return []
    try:
        read_execution(path, register)
    except ExecutionError as exc:
        return [str(exc)]
    return []


def cmd_import(opts: argparse.Namespace) -> int:
    directory = Path(opts.path or ".")
    target = directory / REGISTER
    execution_target = directory / EXECUTION
    for existing in (target, execution_target):
        if existing.exists() and not opts.force:
            raise RegisterError(f"{existing} exists — pass --force to replace it")
    document = Path(opts.document) if opts.document else table_holder(directory)
    original = document.read_text(encoding="utf-8").splitlines()
    register_text, execution_text, marked = imported(
        document, directory / SERIES_FILE, directory / GUARDS_FILE)
    register = parse_register(register_text, target)
    execution = parse_execution(execution_text, execution_target, register)
    table = find_table(original, document)
    reworded = sum(1 for old, new in zip(original[table.start:table.end],
                                         table_lines(register)) if old != new)

    target.write_text(register_text, encoding="utf-8")
    execution_target.write_text(execution_text, encoding="utf-8")
    document.write_text(marked, encoding="utf-8")
    write_table(read_register(target))

    print(f"[{OK}] {shown(target)} — {len(register.metrics)} metrics")
    print(f"[{OK}] {shown(execution_target)} — "
          f"{len(execution.point_validity_guards)} guards")
    print(f"    {SERIES_FILE} and {GUARDS_FILE} stay: the runner already copied here "
          f"reads them. One from report-kit new-point reads {REGISTER} and "
          f"{EXECUTION} instead, and needs {WINDOW} added by hand")
    if reworded:
        print(f"{WARN} {reworded} table line(s) now read the way the register renders them")
    return EXIT_OK


def table_holder(directory: Path) -> Path:
    holders = [doc for doc in sorted(directory.glob("*.md"))
               if "| Ref | What it measures |" in doc.read_text(encoding="utf-8")]
    if len(holders) != 1:
        raise RegisterError(f"{len(holders)} documents in {directory} hold a register "
                            f"table — name one with --document")
    return holders[0]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit metrics", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["write", "check", "import"])
    p.add_argument("--path", help=f"a {REGISTER}, or the execution directory holding it")
    p.add_argument("--all", action="store_true",
                   help=f"every {REGISTER} under the working directory")
    p.add_argument("--document", help="import: the document holding the table")
    p.add_argument("--force", action="store_true",
                   help=f"import: replace an existing {REGISTER}")
    p.add_argument("--strict", action="store_true",
                   help="check: a D ref with no formula, series or record fails")
    return p


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    try:
        if opts.command == "import":
            return cmd_import(opts)
        paths = registers(opts)
        if opts.command == "write":
            return cmd_write(paths)
        return cmd_check(paths, opts.strict)
    except (RegisterError, ExecutionError) as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
