"""scaffold.py — lay out a report, and drop a runner into an execution.

Both operations copy named files out of `templates/`. Nothing is generated and
nothing is deleted: what lands in a project is what someone chose to put in
`templates/` and named here. The predecessor of this module was a bootstrap
script that downloaded the whole repository and removed what did not belong,
which meant every file added to the repo silently shipped to every project.
Adding is the quieter half of that trade in the right direction — a file
nobody names simply never arrives.
"""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path

from .constants import ARROW, OK, WARN

# What each layout puts at the report root. The pair of profiles is the whole
# of the minimal/full distinction — there is no third thing that differs.
LAYOUTS = {
    "minimal": ["execution"],
    "full": ["executions"],
}

# What lands at the report root, as source → name-in-the-project. Paths are
# relative to the package, because `API.md` belongs next to the library it
# documents rather than in `templates/`; copying it from there would leave two
# copies to keep in step.
ROOT_FILES = {
    "templates/report.md": "report.md",
    # A working file like report.md, not a reference: every number the
    # documents print resolves from here, so it belongs at the report root
    # rather than inside any one execution.
    "templates/figures.yaml": "figures.yaml",
    # Read-only reference that travels with a report: the rules its author
    # fills templates against, how to make a point, and what is importable —
    # so an agent working in the project can see all three without leaving it.
    "templates/methodology.md": "methodology.md",
    "templates/formats.md": "formats.md",
    "templates/runners.md": "runners.md",
    "API.md": "API.md",
}

RUNNERS = {"api": "api_point.py", "jobs": "jobs_point.py"}

# Copied under a working name, because these are inputs the author edits.
POINT_INPUTS = {
    "env.example.yaml": "env.yaml",
    "series.example.txt": "series.txt",
    "guards.example.txt": "guards.txt",
}


def _package():
    return files("report_kit")


def _copy(source, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with as_file(source) as path:
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)


def init(target: Path, profile: str, force: bool = False) -> int:
    """Write the report skeleton for one layout into `target`."""
    if profile not in LAYOUTS:
        raise ValueError(f"unknown layout {profile!r} — expected minimal or full")

    existing = [p.name for p in target.iterdir()] if target.is_dir() else []
    if existing and not force:
        print(f"{WARN} {target} is not empty ({', '.join(sorted(existing)[:4])}"
              f"{', …' if len(existing) > 4 else ''}) — pass --force to write "
              f"into it anyway")
        return 1

    package = _package()
    target.mkdir(parents=True, exist_ok=True)

    written = []
    for source, name in ROOT_FILES.items():
        _copy(package / source, target / name)
        written.append(name)
    for name in LAYOUTS[profile]:
        _copy(package / "templates" / name, target / name)
        written.append(f"{name}/")

    # Charts land here once something renders one. Created empty so the path
    # in report.md resolves from the first revision rather than the second.
    (target / "assets").mkdir(exist_ok=True)
    written.append("assets/")

    print(f"{ARROW} {profile} layout → {target}")
    for name in written:
        print(f"    {name}")
    print(f"[{OK}] report skeleton ready")
    print(f"\nNext: report-kit new-point {target / LAYOUTS[profile][0]}"
          f"{'/00-baseline' if profile == 'full' else ''} --profile api")
    return 0


def new_point(target: Path, profile: str, force: bool = False) -> int:
    """Copy a runner and its inputs into one execution's `scripts/`."""
    if profile not in RUNNERS:
        raise ValueError(f"unknown profile {profile!r} — expected api or jobs")

    templates = _package() / "templates" / "runners"
    scripts = target / "scripts"

    planned = {RUNNERS[profile]: RUNNERS[profile], **POINT_INPUTS}
    clashes = [dst for dst in planned.values() if (scripts / dst).exists()]
    if clashes and not force:
        print(f"{WARN} {scripts} already has {', '.join(clashes)} — pass "
              f"--force to overwrite. A runner is edited per execution, so "
              f"overwriting one discards what defined the points already run.")
        return 1

    scripts.mkdir(parents=True, exist_ok=True)
    for source, dst in planned.items():
        _copy(templates / source, scripts / dst)
        (scripts / dst).chmod(0o755 if dst.endswith(".py") else 0o644)

    print(f"{ARROW} {profile} point → {scripts}")
    for dst in planned.values():
        print(f"    {dst}")
    print(f"[{OK}] copied. The runner is yours now: edit its CONSTANTS block, "
          f"then fill env.yaml, series.txt and guards.txt.")
    print(f"\nWhy a copy and not an import: a runner edited in place would "
          f"change what the earlier points of the same sweep measured.")
    return 0
