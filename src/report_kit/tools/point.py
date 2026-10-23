#!/usr/bin/env python3
"""point — what a point does once its window has closed, run again by hand.

    report-kit point finish data/r-200.point.json
    report-kit point finish data/r-200.point.json --force    # re-export too

A runner does this itself the moment its window closes. Run it again when the
export failed and retention is counting down, or to rebuild a point's journal
block and verdict under a newer kit: the window, the queries, the filled
guards and the instant they are read as of are all in the record, so nothing
here re-measures anything. The register is the first `metrics.yaml` above
the record; Prometheus is reached the way `env.yaml` says, by default the one
beside the directory the record sits in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_kit.env import Env
from report_kit.finish import finish_point
from report_kit.portforward import PortForwards, forward_spec
from report_kit.register import REGISTER, RegisterError, find_register, read_register

EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="report-kit point", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["finish"])
    p.add_argument("record", type=Path, help="the point's <run>.point.json")
    p.add_argument("--env", type=Path,
                   help="env.yaml (default: beside the record's directory)")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="overwrite the export already beside the record")
    return p


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    record = opts.record.resolve()
    if not record.is_file():
        print(f"no such point record: {record}", file=sys.stderr)
        return EXIT_USAGE
    found = find_register(record.parent)
    if found is None:
        print(f"no {REGISTER} above {record}", file=sys.stderr)
        return EXIT_USAGE
    try:
        register = read_register(found)
    except RegisterError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    env = Env(opts.env or record.parent.parent / "env.yaml")
    with PortForwards([forward_spec(env, "prometheus")], enabled=not opts.no_port_forward):
        return finish_point(record, env.prom_url, register, force=opts.force)


if __name__ == "__main__":
    sys.exit(main())
