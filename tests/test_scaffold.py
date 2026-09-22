"""Every template ships, and nothing else does.

    pytest tests/test_scaffold.py

`scaffold.py` installs by addition, so a template nobody names never arrives
and nobody notices. Both directions are asserted: nothing orphaned, and
nothing leaked.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest

from report_kit import scaffold

RENAMED = {"env.example.yaml": "env.yaml",
           "series.example.txt": "series.txt",
           "guards.example.txt": "guards.txt"}

REPO_ONLY = {"pyproject.toml", "bootstrap.sh", "cli.py", "scaffold.py",
             "selftest.py", "shell.py", "prometheus.py"}


@pytest.fixture(scope="module")
def placed(tmp_path_factory):
    root = tmp_path_factory.mktemp("scaffold")
    scaffold.init(root / "full", "full")
    scaffold.init(root / "min", "minimal")
    scaffold.new_point(root / "full" / "executions" / "00-baseline", "api")
    scaffold.new_point(root / "full" / "executions" / "NN-name", "jobs")

    base = Path(str(files("report_kit")))
    shipped = {p.name for p in (base / "templates").rglob("*")
               if p.is_file() and "__pycache__" not in p.parts} | {"API.md"}
    return (root,
            {RENAMED.get(name, name) for name in shipped},
            {p.name for p in root.rglob("*") if p.is_file()})


def test_every_template_is_placed_by_some_command(placed):
    _, expected, landed = placed
    orphans = expected - landed
    assert not orphans, (
        f"templates no command places: {sorted(orphans)}. Wire them into "
        f"scaffold.py or delete them — an unreachable template is dead "
        f"weight nobody will notice.")


def test_nothing_reaches_a_project_that_is_not_a_template(placed):
    _, expected, landed = placed
    assert not landed - expected


def test_no_repo_only_file_escapes_into_a_project(placed):
    assert not REPO_ONLY & placed[2]


def test_init_leaves_no_library_copy_at_the_report_root(placed):
    assert not (placed[0] / "full" / "scripts").exists()
