#!/usr/bin/env python3
"""test_scaffold.py — every template ships, and nothing else does.

    python3 tests/test_scaffold.py

This replaces the removal list the old `bootstrap.sh` carried. That script
installed by *subtraction*: it copied the whole repository into a project and
deleted what did not belong, so a file added to the repo and forgotten
silently shipped to everyone. `scaffold.py` installs by addition instead, and
the failure mode inverts — a template nobody names simply never arrives, and
nobody notices either. So both directions are asserted here:

  · every file under templates/ is placed by some command  (nothing orphaned)
  · nothing lands in a project that is not a template      (nothing leaks)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

from report_kit import scaffold

OK, BAD = "\033[32m  ok  \033[0m", "\033[31m FAIL \033[0m"


def templates() -> set[str]:
    """Every shipped template, as a path relative to the package."""
    base = Path(str(files("report_kit")))
    found = {p.relative_to(base).as_posix()
             for p in (base / "templates").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    return found | {"API.md"}


def placed_by_commands(root: Path) -> set[str]:
    """Run every scaffolding command and collect what reached the project."""
    scaffold.init(root / "full", "full")
    scaffold.init(root / "min", "minimal")
    scaffold.new_point(root / "full" / "executions" / "00-baseline", "api")
    scaffold.new_point(root / "full" / "executions" / "NN-name", "jobs")
    return {p.relative_to(base).as_posix()
            for base in [root]
            for p in root.rglob("*") if p.is_file()}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="scaffold-"))
    failures = 0
    try:
        shipped = templates()
        landed = placed_by_commands(root)

        # Match on basename: a template is renamed on the way out (env.example
        # .yaml becomes env.yaml) and the layouts sit at different depths.
        shipped_names = {Path(p).name for p in shipped}
        landed_names = {Path(p).name for p in landed}

        renamed = {"env.example.yaml": "env.yaml",
                   "series.example.txt": "series.txt",
                   "guards.example.txt": "guards.txt"}
        expected = {renamed.get(n, n) for n in shipped_names}

        orphans = expected - landed_names
        if orphans:
            failures += 1
            print(f"[{BAD}] templates no command places: {sorted(orphans)}")
            print("        Either wire them into scaffold.py or delete them — "
                  "an unreachable template is dead weight nobody will notice.")
        else:
            print(f"[{OK}] all {len(expected)} templates are placed by a command")

        leaks = landed_names - expected
        if leaks:
            failures += 1
            print(f"[{BAD}] reached a project but is not a template: "
                  f"{sorted(leaks)}")
        else:
            print(f"[{OK}] nothing reaches a project that is not a template")

        # The repo's own files must never travel. This is the specific bug the
        # old removal list existed to prevent.
        never = {"pyproject.toml", "bootstrap.sh", "cli.py", "scaffold.py",
                 "selftest.py", "shell.py", "prometheus.py"}
        escaped = never & landed_names
        if escaped:
            failures += 1
            print(f"[{BAD}] repo-only files escaped into a project: "
                  f"{sorted(escaped)}")
        else:
            print(f"[{OK}] no repo-only file escaped into a project")

        # The library is a dependency now, not a copy. A vendored second copy
        # is the ambiguity `src/` layout exists to prevent.
        if (root / "full" / "scripts").exists():
            failures += 1
            print(f"[{BAD}] init created a scripts/ at the report root — the "
                  f"library is a dependency, not a vendored copy")
        else:
            print(f"[{OK}] no library copy at the report root")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    print("scaffold test: " + ("everything passed" if not failures
                               else f"{failures} check(s) FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
