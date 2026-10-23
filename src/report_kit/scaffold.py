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
    "templates/report-values.yaml": "report-values.yaml",
    # Read-only reference that travels with a report: the rules its author
    # fills templates against, how to make a point, and what is importable —
    # so an agent working in the project can see all three without leaving it.
    "templates/methodology.md": "methodology.md",
    "templates/formats.md": "formats.md",
    "templates/runners.md": "runners.md",
    "API.md": "API.md",
}

RUNNERS = {"api": "api_point.py", "jobs": "jobs_point.py"}

# Copied under a working name, because it is an input the author edits.
POINT_INPUTS = {"env.example.yaml": "env.yaml"}

FALLBACK_REGISTER = "templates/execution/metrics.yaml"
FALLBACK_EXECUTION = "templates/execution/execution.yaml"


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

    # No charts/ here: `report-kit charts new --kind <shape>` writes a file
    # when one is wanted, the way new-point copies one runner.

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
    kept = [name for name in ("series.txt", "guards.txt") if (scripts / name).exists()]
    if kept and not (target / "metrics.yaml").exists():
        print(f"{WARN} {scripts} keeps {' and '.join(kept)} from before 0.4, and a "
              f"runner from new-point reads metrics.yaml and execution.yaml "
              f"instead. Run report-kit metrics import in {target} first, so they "
              f"define what the new runner measures; nothing was copied.")
        return 1

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
    if not render_register(target):
        return 1
    print(f"[{OK}] copied. Fill env.yaml, define the metrics in "
          f"{target / 'metrics.yaml'}, and what a point is run with, the window "
          f"and the guards in {target / 'execution.yaml'}. What is left in the "
          f"runner is what only your system knows.")
    print(f"\nWhy a copy and not an import: a runner edited in place would "
          f"change what the earlier points of the same sweep measured.")
    return 0


def render_register(target: Path) -> bool:
    """The execution's metrics.yaml and execution.yaml, which the runner reads,
    and the register table where a document holds the markers. An execution
    laid out before these files existed gets the template's."""
    from .execution_config import EXECUTION, ExecutionError, read_execution
    from .register import RegisterError, read_register
    from .tools.metrics.views import write_table

    for name, template in (("metrics.yaml", FALLBACK_REGISTER),
                           (EXECUTION, FALLBACK_EXECUTION)):
        if not (target / name).exists():
            _copy(_package() / template, target / name)
            print(f"    {name} (the template's — the execution had none)")
    try:
        register = read_register(target / "metrics.yaml")
        read_execution(target / EXECUTION, register)
    except (RegisterError, ExecutionError) as exc:
        print(f"{WARN} {exc}")
        return False
    try:
        write_table(register)
    except RegisterError as missing_table:
        print(f"{WARN} the register table is not rendered: {missing_table}")
    return True
