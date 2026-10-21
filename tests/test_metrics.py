"""The metric register: its own rules, what a runner exports from it, the
table it renders, the import from hand-kept files, and the command's exit
codes. execution.yaml's own rules are tests/test_execution_config.py.

    pytest tests/test_metrics.py

What a runner reads from the register is checked against what it used to read
from `series.txt` and `guards.txt` through `refs.py`, so an execution moved onto
a register exports and guards exactly what it did before.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
from pathlib import Path

import pytest

from report_kit import refs, scaffold
from report_kit.tools import metrics
from report_kit.execution_config import read_execution, run_guards
from report_kit.register import RegisterError, parse_register, read_register, series_rows
from report_kit.tools.metrics.views import BEGIN, END, table_lines

ROOT = Path(__file__).resolve().parent.parent

REGISTER_TEXT = """\
metrics:
  M1:
    what: served rate
    promql: sum(rate(requests_total{code=~"2..|3.."}[30s]))
    status: confirmed 2026-01-02
    notes: the denominator of D3
  M2:
    what: client p95
    source: '`p(95)`, generator summary'
    status: unconfirmed
  D3:
    what: served share
    source: '`M1 ÷ offered`'
    status: active
"""

TABLE = """\
| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | served rate | `sum(rate(requests_total{code=~"2..\\|3.."}[30s]))` | confirmed 2026-01-02 | the denominator of D3 |
| M2 | client p95 | `p(95)`, generator summary | unconfirmed | |
| D3 | served share | `M1 ÷ offered` | active | |
"""


def run(*argv, cwd: Path | None = None):
    out, err = io.StringIO(), io.StringIO()
    before = Path.cwd()
    try:
        if cwd:
            os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = metrics.main(list(argv))
    finally:
        os.chdir(before)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def execution(tmp_path):
    (tmp_path / "metrics.yaml").write_text(REGISTER_TEXT)
    (tmp_path / "index.md").write_text(f"# Run\n\n### Metrics\n\n{BEGIN}\n{END}\n\nafter\n")
    return tmp_path


def register(text: str = REGISTER_TEXT, path: Path = Path("x/metrics.yaml")):
    return parse_register(text, path)


class TestRules:
    def test_a_valid_register_exports_only_its_queries(self):
        assert [m.ref for m in register().exported] == ["M1"]

    @pytest.mark.parametrize("change, message", [
        (("  M2:\n", "  M1:\n"), "appears twice"),
        (("  D3:\n", "  D1:\n"), "one sequence across M, D, R and E"),
        (("  D3:\n", "  M0:\n"), "is not M, D, R or E"),
        (("    source: '`M1 ÷ offered`'\n", "    promql: up\n"), "only an M ref is a query"),
        (("    source: '`p(95)`, generator summary'\n",
          "    source: x\n    promql: up\n"), "exactly one of promql"),
        (("    status: unconfirmed\n", "    status: confirmed\n"), "'confirmed YYYY-MM-DD'"),
        (("    notes: the denominator of D3\n", "    notes: |\n      a\n      b\n"),
         "spans lines"),
        (("    notes: the denominator of D3\n", "    why: x\n"), "unknown key 'why'"),
        (("metrics:\n", "checks: {}\nmetrics:\n"), "unknown section 'checks'"),
        (("    status: active\n", "    status: 2026-01-02\n"), "must be text"),
    ])
    def test_a_broken_register_is_refused_with_the_reason(self, change, message):
        with pytest.raises(RegisterError, match=message):
            register(REGISTER_TEXT.replace(*change, 1))

    def test_a_register_with_nothing_to_export_is_refused(self):
        text = REGISTER_TEXT.replace(
            '    promql: sum(rate(requests_total{code=~"2..|3.."}[30s]))\n',
            "    source: a counter\n")
        with pytest.raises(RegisterError, match="no metric has a promql"):
            register(text)

    def test_a_missing_file_is_a_register_error(self, tmp_path):
        with pytest.raises(RegisterError, match="cannot read"):
            read_register(tmp_path / "metrics.yaml")

    def test_guards_and_the_window_belong_to_execution_yaml(self):
        with pytest.raises(RegisterError, match="execution.yaml's"):
            register(REGISTER_TEXT + "guards: {}\n")


class TestWhatARunnerReads:
    def test_the_exported_refs_and_their_queries(self):
        assert series_rows(register()) == [
            ["M1", 'sum(rate(requests_total{code=~"2..|3.."}[30s]))']]

    def test_the_table_escapes_pipes_and_leaves_empty_cells_empty(self):
        assert "\n".join(table_lines(register())) + "\n" == TABLE


class TestCommand:
    def test_write_renders_the_table_alone_and_check_then_passes(self, execution):
        assert run("write", cwd=execution)[0] == 0
        document = (execution / "index.md").read_text()
        assert document == f"# Run\n\n### Metrics\n\n{BEGIN}\n\n{TABLE}\n{END}\n\nafter\n"
        assert not (execution / "scripts").exists()
        assert run("check", cwd=execution)[0] == 0

    def test_check_names_the_table_the_register_moved_away_from(self, execution):
        run("write", cwd=execution)
        register_file = execution / "metrics.yaml"
        register_file.write_text(register_file.read_text().replace("client p95", "client p99"))
        code, out, _ = run("check", cwd=execution)
        assert code == 1 and "the table in index.md no longer matches" in out

    def test_a_hand_edit_to_the_table_fails_the_check(self, execution):
        run("write", cwd=execution)
        index = execution / "index.md"
        index.write_text(index.read_text().replace("served share", "share served"))
        assert run("check", cwd=execution)[0] == 1

    def test_check_fails_on_a_guard_naming_a_metric_the_register_lacks(self, execution):
        run("write", cwd=execution)
        (execution / "execution.yaml").write_text(
            "point_validity_guards:\n  G1: {metric: M9, min: 1}\n")
        code, out, _ = run("check", cwd=execution)
        assert code == 1 and "M9 is not an M ref with a promql" in out

    def test_the_register_is_found_from_below_it(self, execution):
        (execution / "scripts").mkdir()
        assert run("write", cwd=execution / "scripts")[0] == 0

    def test_no_register_is_a_usage_error(self, tmp_path):
        code, _, err = run("check", cwd=tmp_path)
        assert code == 2 and "no metrics.yaml" in err

    def test_a_document_without_the_markers_says_where_they_go(self, execution):
        (execution / "index.md").write_text("# Run\n")
        code, _, err = run("write", cwd=execution)
        assert code == 2 and BEGIN in err

    def test_two_marked_documents_are_refused(self, execution):
        (execution / "metrics.md").write_text(f"{BEGIN}\n{END}\n")
        code, _, err = run("write", cwd=execution)
        assert code == 2 and "renders into one" in err

    def test_all_reaches_every_register_below_and_skips_hidden_ones(self, tmp_path):
        for name in ("00-baseline", "01-load", ".worktree"):
            directory = tmp_path / "executions" / name
            directory.mkdir(parents=True)
            (directory / "metrics.yaml").write_text(REGISTER_TEXT)
            (directory / "index.md").write_text(f"{BEGIN}\n{END}\n")
        code, out, _ = run("write", "--all", cwd=tmp_path)
        assert code == 0 and out.count("metrics.yaml") == 2 and ".worktree" not in out
        assert run("check", "--all", cwd=tmp_path)[0] == 0


def test_all_leaves_out_what_git_ignores(tmp_path):
    for name in ("execution", "build/execution"):
        directory = tmp_path / name
        directory.mkdir(parents=True)
        (directory / "metrics.yaml").write_text(REGISTER_TEXT)
        (directory / "index.md").write_text(f"{BEGIN}\n{END}\n")
    (tmp_path / ".gitignore").write_text("build/\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    code, out, _ = run("write", "--all", cwd=tmp_path)
    assert code == 0 and "execution/metrics.yaml" in out and "build" not in out


class TestMentions:
    def test_a_ref_named_in_notes_that_nothing_defines_fails_the_check(self, execution):
        register_file = execution / "metrics.yaml"
        register_file.write_text(REGISTER_TEXT.replace("the denominator of D3",
                                                       "the denominator of D7"))
        run("write", cwd=execution)
        code, out, _ = run("check", cwd=execution)
        assert code == 1 and "M1 names D7, which this register does not define" in out

    @pytest.mark.parametrize("cited, ok", [("00-baseline/M1", True),
                                           ("00-baseline/M9", False)])
    def test_a_ref_cited_by_path_is_looked_up_in_that_execution(self, tmp_path, cited, ok):
        for name in ("00-baseline", "01-load"):
            directory = tmp_path / name
            directory.mkdir()
            text = REGISTER_TEXT if name == "00-baseline" else REGISTER_TEXT.replace(
                "the denominator of D3", f"read beside {cited}")
            (directory / "metrics.yaml").write_text(text)
            (directory / "index.md").write_text(f"{BEGIN}\n{END}\n")
            run("write", cwd=directory)
        code, out, _ = run("check", cwd=tmp_path / "01-load")
        assert (code == 0) is ok
        assert ok or "00-baseline's register does not define" in out


SERIES_FILE = """\
# what gets exported
#
# the served rate, from the server
M1|sum(rate(requests_total{code=~"2..|3.."}[30s]))
"""

GUARDS_FILE = """\
# the replica guard
G1|min 1|count(up{job="api"} == 1)
G2|min 0.9 max 1.1|sum(rate(requests_total[1m])) / {rate}
G3|min {count}|max(enqueued_total)
"""


@pytest.fixture
def legacy(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "series.txt").write_text(SERIES_FILE)
    (tmp_path / "scripts" / "guards.txt").write_text(GUARDS_FILE)
    (tmp_path / "index.md").write_text(f"# Run\n\n{TABLE}\nafter\n")
    return tmp_path


class TestImport:
    def test_the_table_survives_byte_for_byte_inside_the_markers(self, legacy):
        code, out, _ = run("import", cwd=legacy)
        assert code == 0 and "warn" not in out
        assert (legacy / "index.md").read_text() == f"# Run\n\n{BEGIN}\n\n{TABLE}\n{END}\n\nafter\n"
        assert run("check", cwd=legacy)[0] == 0

    def test_the_register_exports_and_guards_what_the_pipe_files_did(self, legacy):
        before = (refs.read_ref_file(legacy / "scripts" / "series.txt", 2),
                  refs.load_guards(legacy / "scripts" / "guards.txt", {"rate": 1, "count": 2}))
        run("import", cwd=legacy)
        imported = read_register(legacy / "metrics.yaml")
        execution = read_execution(legacy / "execution.yaml", imported)
        assert before == (series_rows(imported), run_guards(execution, {"rate": 1, "count": 2}))

    def test_a_guard_repeating_an_exported_query_names_that_metric(self, legacy):
        series = legacy / "scripts" / "series.txt"
        series.write_text(series.read_text() + 'M4|count(up{job="api"} == 1)\n')
        index = legacy / "index.md"
        index.write_text(index.read_text().replace(
            "| D3 | served share", '| M4 | serving | `count(up{job="api"} == 1)` | unconfirmed | |\n| D5 | served share').replace("| D3 |", "| D5 |"))
        assert run("import", cwd=legacy)[0] == 0
        text = (legacy / "execution.yaml").read_text()
        assert "  G1:\n    min: 1\n    metric: M4\n" in text

    def test_comments_move_into_the_register_and_the_pipe_files_stay(self, legacy):
        run("import", cwd=legacy)
        text = (legacy / "metrics.yaml").read_text()
        assert "  # the served rate, from the server\n  M1:" in text
        assert "  # the replica guard\n  G1:" in (legacy / "execution.yaml").read_text()
        assert (legacy / "scripts" / "series.txt").read_text() == SERIES_FILE
        assert (legacy / "scripts" / "guards.txt").read_text() == GUARDS_FILE

    def test_a_query_the_table_and_series_disagree_on_is_refused(self, legacy):
        index = legacy / "index.md"
        index.write_text(index.read_text().replace("[30s]))`", "[1m]))`"))
        code, _, err = run("import", cwd=legacy)
        assert code == 2 and "M1: the table shows" in err
        assert not (legacy / "metrics.yaml").exists()

    def test_a_series_ref_the_table_never_defines_is_refused(self, legacy):
        series = legacy / "scripts" / "series.txt"
        series.write_text(series.read_text() + "M7|up\n")
        code, _, err = run("import", cwd=legacy)
        assert code == 2 and "series.txt exports M7" in err

    def test_an_existing_register_is_kept_unless_forced(self, legacy):
        (legacy / "metrics.yaml").write_text("mine\n")
        assert run("import", cwd=legacy)[0] == 2
        assert (legacy / "metrics.yaml").read_text() == "mine\n"

    def test_a_document_imported_once_is_not_marked_twice(self, legacy):
        run("import", cwd=legacy)
        code, _, err = run("import", "--force", cwd=legacy)
        assert code == 2 and "imported before" in err


@pytest.mark.parametrize("example", ["simple-api", "async-jobs"])
def test_each_example_renders_what_it_prints(example):
    assert run("check", "--path", str(ROOT / "examples" / example))[0] == 0


@pytest.mark.parametrize("layout, execution", [
    ("minimal", "execution"),
    ("full", "executions/00-baseline"),
    ("full", "executions/NN-name"),
])
def test_a_fresh_point_starts_with_a_register_its_runner_can_read(tmp_path, layout,
                                                                  execution):
    with contextlib.redirect_stdout(io.StringIO()):
        scaffold.init(tmp_path, layout)
        assert scaffold.new_point(tmp_path / execution, "api") == 0
    target = tmp_path / execution
    fresh = read_register(target / "metrics.yaml")
    execution = read_execution(target / "execution.yaml", fresh)
    assert series_rows(fresh) and run_guards(execution, {"rate": 1})
    assert execution.window_closes_when_back_to_idle
    assert not (target / "scripts" / "series.txt").exists()
    assert run("check", "--path", str(target))[0] == 0


def test_new_point_never_touches_a_hand_written_pipe_file(tmp_path):
    target = tmp_path / "execution"
    with contextlib.redirect_stdout(io.StringIO()):
        scaffold.init(tmp_path, "minimal")
        guards = target / "scripts" / "guards.txt"
        guards.parent.mkdir(exist_ok=True)
        guards.write_text("G1|min 1|up\n")
        assert scaffold.new_point(target, "api") == 0
    assert guards.read_text() == "G1|min 1|up\n"


def test_an_execution_older_than_registers_gets_the_template_one(tmp_path):
    (tmp_path / "index.md").write_text("# Run\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert scaffold.new_point(tmp_path, "jobs") == 0
    assert series_rows(read_register(tmp_path / "metrics.yaml"))
    assert (tmp_path / "execution.yaml").is_file()
    assert not (tmp_path / "scripts" / "series.txt").exists()
    assert "the register table is not rendered" in out.getvalue()
    assert (tmp_path / "index.md").read_text() == "# Run\n"


def test_new_point_on_a_pre_0_4_execution_asks_for_an_import_first(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "series.txt").write_text("M1|up\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert scaffold.new_point(tmp_path, "api") == 1
    assert "report-kit metrics import" in out.getvalue()
    assert not (tmp_path / "metrics.yaml").exists()
    assert not (tmp_path / "scripts" / "api_point.py").exists()
