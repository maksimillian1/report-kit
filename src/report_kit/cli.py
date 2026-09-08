"""cli.py — the single entry point: scaffolding and the run-as-is tools.

    report-kit init docs/report --full
    report-kit new-point docs/report/executions/01-load --profile api
    report-kit export-metrics --start … --end …
    report-kit inspect-metrics data/r-200.jsonl --settle-on M4
    report-kit node-cost --last 40m --nodepool apps-compute
    report-kit selftest

**Subcommands are imported only once one is chosen.** `export-metrics` exists
for the case where a run finished, its export did not, and retention is
counting down — a window can be re-exported but never re-measured. That only
works if it loads when the rest of the package cannot: importing every tool up
front would drag `env` and PyYAML into a command that needs neither, and the
rescue path would break on the one day it is needed. Hence the table below
holds module *names*, resolved after the arguments are parsed.
"""

from __future__ import annotations

import argparse
import importlib
import sys

TOOLS = {
    "export-metrics": ("report_kit.tools.export_metrics",
                       "re-export a window whose metrics are aging out"),
    "inspect-metrics": ("report_kit.tools.inspect_metrics",
                        "read back what an export actually captured"),
    "node-cost": ("report_kit.tools.node_cost",
                  "what the nodes cost during a window, the same day"),
    "selftest": ("report_kit.tools.selftest",
                 "drive both runner templates against a faked cluster"),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report-kit",
        description="Measurement tooling and templates for engineering reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="A tool's own options: report-kit <tool> --help")
    p.add_argument("--version", action="store_true",
                   help="print the installed version and exit")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    init = sub.add_parser("init", help="write a report skeleton")
    init.add_argument("directory")
    layout = init.add_mutually_exclusive_group()
    layout.add_argument("--full", dest="layout", action="store_const",
                        const="full", help="2+ executions (default)")
    layout.add_argument("--minimal", dest="layout", action="store_const",
                        const="minimal", help="a single execution")
    init.set_defaults(layout="full")
    init.add_argument("--force", action="store_true",
                      help="write into a non-empty directory")

    point = sub.add_parser("new-point",
                           help="copy a runner into an execution's scripts/")
    point.add_argument("directory", help="the execution directory")
    point.add_argument("--profile", choices=["api", "jobs"], required=True,
                       help="api = request/response, jobs = queue/worker")
    point.add_argument("--force", action="store_true",
                       help="overwrite an existing runner or its inputs")

    for name, (_, help_text) in TOOLS.items():
        sub.add_parser(name, help=help_text, add_help=False)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # A tool parses its own arguments, so hand the rest over untouched rather
    # than teaching this parser every flag the tools have.
    if argv and argv[0] in TOOLS:
        module_name, _ = TOOLS[argv[0]]
        return importlib.import_module(module_name).main(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from . import version
        print(version() or "not installed (running from a source tree)")
        return 0
    if not args.command:
        parser.print_help()
        return 1

    from pathlib import Path

    from . import scaffold
    target = Path(args.directory)
    if args.command == "init":
        return scaffold.init(target, args.layout, args.force)
    return scaffold.new_point(target, args.profile, args.force)


if __name__ == "__main__":
    sys.exit(main())
