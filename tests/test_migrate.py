"""`report-kit values migrate`: a report from before 0.4 moved to
report-values.yaml and V refs, its marks with it, all at once or not at all.

    pytest tests/test_migrate.py

Every name and number here is invented.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from report_kit.tools import values as values_tool

OLD = """\
scan:
  - report.md

points:
  axis: n
  figures:
    drain_{point}: {kind: M, unit: s, from: {path: drain.seconds}}

figures:
  base:
    ref: FR1
    kind: R
    value: 100
    source: an invented setting

  share:
    ref: FD1
    kind: D
    formula: base / 2
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = values_tool.main(list(argv))
    return code, out.getvalue() + err.getvalue()


@pytest.fixture
def old_report(tmp_path):
    (tmp_path / "figures.yaml").write_text(OLD)
    (tmp_path / "report.md").write_text(
        "base 100<!--FR1--> and half **50** (FD1)\n```\nan example 100<!--FR1-->\n```\n")
    return tmp_path


def test_it_moves_the_file_the_refs_and_every_mark(old_report):
    code, out = run("--path", str(old_report / "figures.yaml"), "migrate")
    assert code == 0 and "2 refs now V" in out
    assert not (old_report / "figures.yaml").exists()
    text = (old_report / "report-values.yaml").read_text()
    assert "\nvalues:\n" in text and "\n  values:\n" in text
    assert "    ref: VR1\n" in text and "    ref: VD1\n" in text
    assert (old_report / "report.md").read_text() == (
        "base 100<!--VR1--> and half **50** (VD1)\n```\nan example 100<!--FR1-->\n```\n")
    assert run("--path", str(old_report / "report-values.yaml"), "check")[0] == 0


def test_a_report_still_on_the_old_name_is_told_to_migrate(old_report, monkeypatch):
    monkeypatch.chdir(old_report)
    code, out = run("check")
    assert code == 2 and "run report-kit values migrate" in out


def test_it_refuses_when_the_new_file_already_exists(old_report):
    (old_report / "report-values.yaml").write_text("values: {}\n")
    code, out = run("--path", str(old_report / "figures.yaml"), "migrate")
    assert code == 2 and "already exists" in out
    assert (old_report / "figures.yaml").read_text() == OLD


def test_naming_the_old_file_directly_is_told_to_migrate(old_report):
    code, out = run("--path", str(old_report / "figures.yaml"), "check")
    assert code == 2 and "run report-kit values migrate" in out
