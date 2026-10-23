#!/usr/bin/env python3
"""values — the report's numbers: resolve them, and fail when they drift.

    report-kit values                    every value, grouped
    report-kit values served_r24         one value, its number alone
    report-kit values VM9                the same, by ref
    report-kit values --group served_share
    report-kit values check [--strict]   retired values, coverage, ref identity,
                                          evidence
    report-kit values pull [value ...]   rewrite each value: from what its from:
                                          names in the run's data files
    report-kit values add-point data/r1.point.json [--as LABEL] [--allow-invalid]
                                          append one run's values from points:
    report-kit values adopt-point n08 data/n08.point.json [--allow-invalid]
                                          bind values written by hand to it
    report-kit values rename-point n08c n09
    report-kit values delete-point n09 [--force]
                                          remove them, renumber, move the marks
    report-kit values trace rate_n08     where a value is printed, how it is had,
                                          down to the run data that produce it
    report-kit values orphans report.md  currency tokens matching no value
    report-kit values validate           the registry's own rules
    report-kit values retype served_r24 E
                                          change a kind, renumber every ref, move the marks
    report-kit values renumber           refs back in file order, marks moved with them
    report-kit values migrate            figures.yaml and F refs from before 0.4,
                                          moved to report-values.yaml and V refs

Every number a report prints comes from `report-values.yaml` as either a leaf — a
value with a source — or a formula over other values. Arithmetic lives here
and nowhere else, least of all in prose. `formats.md` covers how a number is
written into a document and how a ref attaches to it.

A kind says where an error could originate: M measured, R recorded from an
authority, D derived, E estimated. A derived value with an estimated input
prints as estimated — the weakest input decides.

A leaf may also say where its value lives in a run's committed data files
(`from:`, read by `evidence.py` beside this file). `pull` writes that value in, and
`check` fails when the stored one no longer matches it.

The registry is found by walking up from the working directory, so the command
works from anywhere inside a report. `--path` names one explicitly, which is
also how you check a registry that is not the one you are standing in.

This file is the command. The model lives in the modules beside it and prints
nothing, so a caller that wants a value rather than a page imports `Registry`
and calls it directly. Every
failure that depends on what the registry says arrives as `RegistryError`
rather than as whatever exception the parser happened to raise; a `from:`
that names no value is `evidence.EvidenceError`, reported per value.
"""

from __future__ import annotations

import argparse
import sys

from report_kit.constants import OK

from . import points
from .errors import RegistryError
from .registry import MARK, REGISTRY, Registry
from .checks import check_coverage, check_marks, check_orphans, check_retired, validate
from .readings import check_evidence, pull
from .links import check_links
from .migrate import migrate
from .trace import lines, trace
from .surgery import value_text
from .edits import (
    Renumbered, add_point, adopt_point, delete_point, rename_point, renumber,
    retype)


# Not `constants.EXIT_*`, which numbers what a runner did. These three are
# this command's own contract, and the report's CI reads them.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
POINT_COMMANDS = ("add-point", "adopt-point", "rename-point", "delete-point")


def cmd_list(registry: Registry, values: dict, args: argparse.Namespace) -> int:
    groups = registry.groups()
    for group, names in groups.items():
        if args.group and group != args.group:
            continue
        print(f"\n{group}")
        for name in names:
            spec = registry.entries[name]
            kind = registry.effective_kind(name)
            basis = spec.get("formula") or spec.get("source") or spec.get("metric", "")
            print(f"  {registry.display(name, values[name]):>14} "
                  f"{MARK.get(kind, '?'):1} {str(spec.get('ref', '?')):>6}  "
                  f"{name:<28} {basis}")
    print()
    return EXIT_OK


def cmd_check(registry: Registry, values: dict, args: argparse.Namespace) -> int:
    documents = registry.documents()
    failed = False
    print(f"scanned {len(documents)} documents, {len(registry.entries)} values\n")

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
    print(f"\ncoverage: {len(rows) - len(missing)}/{len(rows)} values present "
          f"where declared")
    for row in missing:
        print(f"  {row.status:<8} {row.name:<28} {row.wanted:>12}  expected in "
              f"{row.file}")
    if missing and args.strict:
        failed = True

    failed = report_evidence(registry, args.strict) or failed
    failed = report_links(registry) or failed
    print()
    return EXIT_FAILED if failed else EXIT_OK


def report_links(registry: Registry) -> bool:
    """Prints the metric section of `check`; True when it fails."""
    seen, problems = check_links(registry)
    print(f"\nmetric refs: {seen - len(problems)}/{seen} defined by their "
          f"execution's register")
    for problem in problems:
        print(f"  FAIL {problem.name:<28} {problem.metric}: {problem.why}")
    return bool(problems)


def report_evidence(registry: Registry, strict: bool) -> bool:
    """Prints the evidence section of `check`; True when it fails."""
    rows = check_evidence(registry)
    off = [row for row in rows if row.status != "ok"]
    print(f"\nevidence: {len(rows) - len(off)}/{len(rows)} values agree with "
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


def cmd_validate(registry: Registry, values: dict,
                 args: argparse.Namespace) -> int:
    problems, notes = validate(registry)
    for line in problems:
        print(f"  FAIL {line}")
    for line in notes:
        print(f"  note {line}")
    print(f"\n{len(registry.entries)} values, {len(problems)} problems, "
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
        print(f"unknown value or ref '{wanted}'", file=sys.stderr)
        return EXIT_USAGE
    print(registry.display(name, values[name]))
    return EXIT_OK


def cmd_trace(registry: Registry, values: dict, wanted: str) -> int:
    name = registry.by_ref().get(wanted, wanted)
    if name not in values:
        print(f"unknown value or ref '{wanted}'", file=sys.stderr)
        return EXIT_USAGE
    print("\n".join(lines(trace(registry, values, name))))
    return EXIT_OK


def cmd_add_point(registry: Registry, rest: list[str],
                  opts: argparse.Namespace) -> int:
    if len(rest) != 2:
        return usage("add-point <run.point.json> [--as LABEL] "
                             "[--allow-invalid]")
    added = add_point(registry, rest[1], opts.as_label, opts.allow_invalid)
    for name, why in added.gaps:
        print(f"  FAIL {name:<28} {why}")
    if added.gaps:
        print(f"\npoint {added.label}: {len(added.gaps)} value(s) with no "
              f"reading; nothing was written")
        return EXIT_FAILED
    print(f"added point {added.label}")
    for name, spec in added.entries.items():
        shown = (value_text(spec["value"]) if "value" in spec
                 else spec.get("formula", ""))
        print(f"  {spec['ref']:>6}  {name:<28} {shown}")
    return EXIT_OK


def cmd_adopt_point(registry: Registry, rest: list[str],
                    opts: argparse.Namespace) -> int:
    if len(rest) != 3:
        return usage("adopt-point <label> <run.point.json> "
                             "[--allow-invalid]")
    bound = adopt_point(registry, rest[1], rest[2], opts.allow_invalid)
    print(f"point {rest[1]} adopted; refs unchanged")
    for name in bound:
        print(f"  {registry.entries[name].get('ref', '?'):>6}  {name}")
    if not bound:
        print("  every value already carried it")
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


COMMANDS = {"add-point": cmd_add_point, "adopt-point": cmd_adopt_point,
            "rename-point": cmd_rename_point, "delete-point": cmd_delete_point}


def cmd_migrate(opts: argparse.Namespace) -> int:
    done = migrate(opts.path)
    print(f"[{OK}] {done.path}: {done.refs} refs now V…")
    print(f"marks moved in: {', '.join(done.documents) or 'no document'}")
    print("CI jobs and editor hooks that ran report-kit figures now run "
          "report-kit values")
    return EXIT_OK


def report_renumbered(done: Renumbered) -> int:
    print(f"refs renumbered: {done.counts}")
    for old, new in done.refs.items():
        print(f"  {old} -> {new}")
    print(f"marks moved in: {', '.join(done.documents) or 'no document'}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit values", description=__doc__,
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
                   help="add-point, adopt-point: take a point whose guards "
                        "failed or whose export has gaps")
    p.add_argument("--force", action="store_true",
                   help="delete-point: delete a cited point, removing its marks")
    p.add_argument("args", nargs="*", metavar="<command|value>")
    return p


def usage(message: str) -> int:
    print(f"usage: report-kit values {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_intermixed_args(argv)
    rest = opts.args
    command = rest[0] if rest else "list"

    try:
        if command == "migrate":
            return cmd_migrate(opts)
        registry = Registry.load(opts.path)

        # These rewrite the file and never need a value, so they run before
        # resolution — a registry with a value that does not resolve is
        # exactly one you may still want to renumber, or pull a value into.
        if command == "pull":
            return cmd_pull(registry, rest[1:])
        if command in POINT_COMMANDS:
            return COMMANDS[command](registry, rest, opts)
        if command == "retype":
            if len(rest) != 3:
                return usage("retype <value> <M|R|D|E>")
            done = retype(registry, rest[1], rest[2])
            print(f"{rest[1]} is now {rest[2]}")
            return report_renumbered(done)
        if command == "renumber":
            return report_renumbered(renumber(registry))

        values = registry.resolve()

        if command == "validate":
            return cmd_validate(registry, values, opts)
        if command == "check":
            return cmd_check(registry, values, opts)
        if command == "orphans":
            if len(rest) != 2:
                return usage("orphans <file>")
            return cmd_orphans(registry, values, rest[1])
        if command == "trace":
            if len(rest) != 2:
                return usage("trace <value|ref>")
            return cmd_trace(registry, values, rest[1])
        if command != "list":
            return cmd_one(registry, values, command)
        return cmd_list(registry, values, opts)
    except (RegistryError, points.PointError) as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_USAGE
