"""One run's figures as a set: add a point, rename it, delete it.

    pytest tests/test_points.py

The grid, its runs, names and numbers are invented for these tests.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from report_kit import points
from report_kit.points import PointError
from report_kit.tools import figure_points, figures
from report_kit.tools.figures import FigureError, Registry

GRID = """\
scan:
  - report.md

points:
  axis: n
  label: "n{n:02d}"
  held: {count: 100}
  figures:
    drain_{point}: {kind: M, unit: seconds, display: 1, from: {path: drain.seconds}}
    peak_{point}: {kind: M, unit: units, display: 0, from: {ref: M1, reduce: max}}
    speedup_{point}: {kind: D, unit: ratio, formula: "base_rate / drain_{point}"}

figures:
  # the baseline every point is divided into
  base_rate:
    ref: FR1
    kind: R
    value: 100
    source: an invented setting

retired: []
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = figures.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def grid(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "report.md").write_text("no marks yet\n")
    path = tmp_path / figures.REGISTRY
    path.write_text(GRID)
    return path


def record(root, run_id, n=8, count=100, drain=50.0, peak=("3", "7"), **extra):
    point = root / "data" / f"{run_id}.point.json"
    point.write_text(json.dumps({"run": run_id, "n": str(n), "count": count,
                                 "drain": {"seconds": drain},
                                 "guard_failures": [], "empty_refs": [],
                                 **extra}))
    if peak is not None:
        values = [[t, v] for t, v in enumerate(peak, 1)]
        (root / "data" / f"{run_id}.jsonl").write_text(json.dumps(
            {"metric": "M1", "result": [{"metric": {}, "values": values}]}) + "\n")
    return point


def add(grid, run_id, *flags, **fields):
    point = record(grid.parent, run_id, **fields)
    return run("--path", str(grid), "add-point", str(point), *flags)


def labels(grid):
    return points.labels_in_use(Registry.load(explicit=grid).figures)


class TestLabels:
    def test_a_repeat_takes_the_next_letter_and_never_a(self):
        taken = {"n08", "n08b"}
        assert points.free_label("n08", taken.__contains__) == "n08c"
        assert points.free_label("n09", taken.__contains__) == "n09"

    def test_past_z_is_an_error(self):
        with pytest.raises(PointError, match="n08z are all taken"):
            points.free_label("n08", lambda label: True)

    def test_three_runs_at_one_n_become_n08_n08b_n08c(self, grid):
        for run_id in ("a", "b", "c"):
            assert add(grid, run_id)[0] == 0
        assert labels(grid) == {"n08", "n08b", "n08c"}

    def test_a_number_stored_as_a_string_formats_as_a_number(self):
        template = points.read_template({"axis": "n", "label": "n{n:02d}",
                                         "figures": {"x_{point}": {"kind": "M"}}})
        assert points.base_label(template, {"n": "8"}) == "n08"

    def test_as_names_the_point(self, grid):
        assert add(grid, "a", "--as", "n08_cold")[0] == 0
        assert labels(grid) == {"n08_cold"}

    @pytest.mark.parametrize("label, message", [
        ("n08", "label n08 is taken"), ("n 08", "only letters, digits")])
    def test_as_refuses_a_taken_or_unusable_label(self, grid, label, message):
        add(grid, "a")
        before = grid.read_text()
        code, _, err = add(grid, "b", "--as", label)
        assert code == 2 and message in err
        assert grid.read_text() == before

    def test_a_name_already_in_the_registry_takes_the_label_too(self, grid):
        grid.write_text(GRID.replace("retired: []", "  drain_n08:\n"
                                     "    ref: FM1\n    kind: M\n    value: 1\n"
                                     "    source: typed before the template existed\n\n"
                                     "retired: []"))
        assert add(grid, "a")[0] == 0
        assert labels(grid) == {"n08b"}


class TestAdd:
    def test_it_appends_with_values_pulled_and_refs_after_the_last(self, grid):
        before = grid.read_text()
        code, out, _ = add(grid, "a", drain=40.0)
        assert code == 0 and "added point n08" in out
        text = grid.read_text()
        assert text.startswith(before[:before.index("retired:")].rstrip("\n"))
        registry = Registry.load(explicit=grid)
        assert [(n, s["ref"]) for n, s in registry.figures.items()] == [
            ("base_rate", "FR1"), ("drain_n08", "FM1"), ("peak_n08", "FM2"),
            ("speedup_n08", "FD1")]
        assert registry.figures["peak_n08"]["from"] == {
            "file": "data/a.jsonl", "ref": "M1", "reduce": "max"}
        assert registry.resolve()["speedup_n08"] == 2.5
        assert run("--path", str(grid), "check", "--strict")[0] == 0

    @pytest.mark.parametrize("fields, message", [
        ({"guard_failures": ["G1"]}, "guard_failures: G1"),
        ({"empty_refs": ["M3"]}, "empty_refs: M3"),
        ({"export": {"empty_refs": ["M4"]}}, "empty_refs: M4"),
    ])
    def test_an_invalid_point_needs_allow_invalid(self, grid, fields, message):
        code, _, err = add(grid, "a", **fields)
        assert code == 2 and message in err and "--allow-invalid" in err
        assert grid.read_text() == GRID
        assert add(grid, "a", "--allow-invalid", **fields)[0] == 0

    def test_a_point_of_another_grid_is_refused_even_when_invalid_is_allowed(
            self, grid):
        code, _, err = add(grid, "first-pass", "--allow-invalid", count=40)
        assert code == 2 and "count is 40, the grid holds 100" in err
        assert grid.read_text() == GRID

    @pytest.mark.parametrize("flags", [(), ("--as", "n09", "--allow-invalid")])
    def test_the_same_run_file_twice_is_refused_whatever_the_flags(self, grid,
                                                                    flags):
        add(grid, "a")
        once = grid.read_text()
        code, _, err = add(grid, "a", *flags)
        assert code == 2 and "data/a.point.json is already registered" in err
        assert "drain_n08, peak_n08 read it" in err
        assert grid.read_text() == once

    def test_a_figure_that_reads_only_the_export_registers_the_run(self, grid):
        grid.write_text(GRID.replace("retired: []", "  peak_by_hand:\n"
                                     "    ref: FM1\n    kind: M\n    value: 7\n"
                                     "    from: {file: data/a.jsonl, ref: M1, "
                                     "reduce: max}\n\nretired: []"))
        code, _, err = add(grid, "a")
        assert code == 2 and "peak_by_hand read it" in err

    def test_a_gap_writes_nothing_and_exits_one(self, grid):
        code, out, _ = add(grid, "a", peak=None)
        assert code == 1 and "FAIL peak_n08" in out and "nothing was written" in out
        assert grid.read_text() == GRID

    def test_a_registry_without_points_cannot_add(self, grid):
        grid.write_text(GRID[:GRID.index("points:")]
                        + GRID[GRID.index("\nfigures:") + 1:])
        code, _, err = add(grid, "a")
        assert code == 2 and "no points: block" in err

    @pytest.mark.parametrize("change, message", [
        (("axis: n", "axis: rate"), "has no rate"),
        (("drain_{point}:", "drain:"), "has no {point}"),
        (("{path: drain.seconds}}", "{path: drain.seconds}, ref: FM9}"),
         "sets ref"),
    ])
    def test_a_template_it_cannot_use_is_named(self, grid, change, message):
        grid.write_text(GRID.replace(*change))
        code, out, err = add(grid, "a")
        assert code != 0 and message in out + err


def typed_by_hand(text):
    """What add-point writes, as a person would have typed it before 0.4.0."""
    return "".join(line for line in text.splitlines(keepends=True)
                   if not line.startswith("    point:"))


def adopt(grid, label, run_id, *flags):
    return run("--path", str(grid), "adopt-point", label,
               str(grid.parent / "data" / f"{run_id}.point.json"), *flags)


class TestAdopt:
    @pytest.fixture
    def typed(self, grid):
        add(grid, "a")
        bound = grid.read_text()
        grid.write_text(typed_by_hand(bound))
        return grid, bound

    def test_it_binds_hand_typed_figures_into_what_add_point_writes(self, typed):
        grid, bound = typed
        code, out, _ = adopt(grid, "n08", "a")
        assert code == 0 and "FM1  drain_n08" in out and "refs unchanged" in out
        assert grid.read_text() == bound
        assert adopt(grid, "n08", "a")[0] == 0
        assert grid.read_text() == bound

    def test_the_prose_keys_are_the_authors(self, typed):
        grid, _ = typed
        grid.write_text(grid.read_text().replace("unit: seconds", "unit: s")
                        .replace("display: 1", "display: 2"))
        assert adopt(grid, "n08", "a")[0] == 0

    @pytest.mark.parametrize("old, new, problem", [
        ("formula: base_rate / drain_n08", "formula: base_rate / drain_n08 * 2",
         "speedup_n08 computes base_rate / drain_n08 * 2, the template computes"),
        ("a.point.json, path: drain.seconds", "a.point.json, path: drain.minutes",
         "drain_n08 reads {file: data/a.point.json, path: drain.minutes}"),
        ("kind: M\n    value: 7", "kind: E\n    value: 7",
         "peak_n08 is kind E, the template makes it M"),
    ])
    def test_one_disagreement_refuses_and_writes_nothing(self, typed, old, new,
                                                         problem):
        grid, _ = typed
        text = grid.read_text().replace(old, new)
        assert text != grid.read_text()
        grid.write_text(text)
        code, _, err = adopt(grid, "n08", "a")
        assert code == 2 and problem in err and "nothing was written" in err
        assert grid.read_text() == text

    def test_a_missing_figure_refuses(self, typed):
        grid, _ = typed
        text = grid.read_text()
        start = text.index("  peak_n08:")
        text = text[:start] + text[text.index("  speedup_n08:"):]
        grid.write_text(text)
        code, _, err = adopt(grid, "n08", "a")
        assert code == 2 and "peak_n08 is missing" in err
        assert grid.read_text() == text

    def test_a_run_already_bound_to_another_label_refuses(self, grid):
        add(grid, "a")
        before = grid.read_text()
        code, _, err = adopt(grid, "n09", "a")
        assert code == 2 and "already bound to point n08" in err
        assert grid.read_text() == before

    def test_held_and_validity_apply_and_allow_invalid_passes_through(
            self, typed):
        grid, bound = typed
        record(grid.parent, "a", count=40)
        assert "the grid holds 100" in adopt(grid, "n08", "a")[2]
        record(grid.parent, "a", guard_failures=["G1"])
        assert "--allow-invalid" in adopt(grid, "n08", "a")[2]
        assert adopt(grid, "n08", "a", "--allow-invalid")[0] == 0
        assert grid.read_text() == bound


RENAMING = """\
figures:
  base_rate:
    ref: FR1
    kind: R
    value: 100
    source: s

  drain_n08:
    ref: FM1
    kind: M
    point: n08
    value: 50
    source: s

  drain_n08b:
    ref: FM2
    kind: M
    point: n08b   # the repeat
    value: 52
    source: s

  speedup_n08b:
    ref: FD1
    kind: D
    point: n08b
    formula: base_rate / drain_n08b

  # a figure outside the point that reads it
  repeat_gap:
    ref: FD2
    kind: D
    formula: drain_n08b - drain_n08

retired:
  - pattern: "51.0"
    replaced_by: drain_n08b
"""


class TestRename:
    @pytest.fixture
    def renaming(self, tmp_path):
        path = tmp_path / figures.REGISTRY
        path.write_text(RENAMING)
        return path

    def test_every_reference_moves_and_nothing_else(self, renaming):
        code, out, _ = run("--path", str(renaming), "rename-point", "n08b", "n09")
        assert code == 0 and "drain_n08b -> drain_n09" in out
        assert renaming.read_text() == (
            RENAMING.replace("drain_n08b", "drain_n09")
            .replace("speedup_n08b", "speedup_n09")
            .replace("point: n08b", "point: n09"))

    def test_the_label_is_matched_whole_so_n08_leaves_n08b_alone(self, renaming):
        assert run("--path", str(renaming), "rename-point", "n08", "n10")[0] == 0
        registry = Registry.load(explicit=renaming)
        assert "drain_n10" in registry.figures and "drain_n08b" in registry.figures
        assert registry.figures["repeat_gap"]["formula"] == "drain_n08b - drain_n10"
        assert [s["ref"] for s in registry.figures.values()] == [
            "FR1", "FM1", "FM2", "FD1", "FD2"]

    @pytest.mark.parametrize("new", ["n08", "n08b"])
    def test_a_taken_label_is_refused(self, renaming, new):
        old = "n08b" if new == "n08" else "n08"
        code, _, err = run("--path", str(renaming), "rename-point", old, new)
        assert code == 2 and f"label {new} is taken" in err
        assert renaming.read_text() == RENAMING

    def test_a_formula_the_rewriter_cannot_see_refuses_the_rename(self, renaming):
        text = RENAMING.replace("    formula: drain_n08b - drain_n08\n",
                                "    formula: >-\n      drain_n08b - drain_n08\n")
        renaming.write_text(text)
        code, _, err = run("--path", str(renaming), "rename-point", "n08b", "n09")
        assert code == 2 and "could not rename every reference" in err
        assert renaming.read_text() == text


def shifting(tmp_path, report):
    """FM1 belongs to point n01; FM2..FM12 follow it and shift down by one."""
    lines = ["figures:\n", "  gone_n01:\n", "    ref: FM1\n", "    kind: M\n",
             "    point: n01\n", "    value: 1\n", "    source: s\n"]
    for k in range(2, 13):
        lines += ["\n", f"  m{k}:\n", f"    ref: FM{k}\n", "    kind: M\n",
                  f"    value: {k}\n", "    source: s\n"]
    path = tmp_path / figures.REGISTRY
    path.write_text("scan:\n  - report.md\n  - notes.md\n\n" + "".join(lines))
    (tmp_path / "report.md").write_text(report)
    (tmp_path / "notes.md").write_text("twelve is 12<!--FM12-->\n")
    return path


SHIFTED = ("two is 2<!--FM2-->, eleven is 11 (FM11), twelve is 12<!--FM12-->\n"
           "a cell `12`(FM12)\n"
           "```\n"
           "an example 12<!--FM12--> is not a mark\n"
           "```\n")


class TestDelete:
    def test_shifted_marks_move_by_an_exact_map_and_fm1_never_hits_fm12(
            self, tmp_path):
        path = shifting(tmp_path, SHIFTED)
        code, out, _ = run("--path", str(path), "delete-point", "n01")
        assert code == 0 and "FM12 -> FM11" in out and "FM1 -> (deleted)" in out
        assert (tmp_path / "report.md").read_text() == (
            "two is 2<!--FM1-->, eleven is 11 (FM10), twelve is 12<!--FM11-->\n"
            "a cell `12`(FM11)\n"
            "```\n"
            "an example 12<!--FM12--> is not a mark\n"
            "```\n")
        assert (tmp_path / "notes.md").read_text() == "twelve is 12<!--FM11-->\n"
        registry = Registry.load(explicit=path)
        assert "gone_n01" not in registry.figures
        assert registry.figures["m12"]["ref"] == "FM11"
        assert run("--path", str(path), "check")[0] == 0

    def test_a_cited_point_is_refused_until_forced(self, tmp_path):
        path = shifting(tmp_path, "one is 1<!--FM1--> and two 2<!--FM2-->\n")
        before = path.read_text()
        code, _, err = run("--path", str(path), "delete-point", "n01")
        assert code == 2 and "FM1 at report.md:1" in err
        assert path.read_text() == before
        assert run("--path", str(path), "delete-point", "n01", "--force")[0] == 0
        assert (tmp_path / "report.md").read_text() == "one is 1 and two 2<!--FM1-->\n"
        assert run("--path", str(path), "check")[0] == 0

    def test_a_formula_outside_the_point_refuses_even_forced(self, tmp_path):
        path = shifting(tmp_path, "nothing\n")
        text = path.read_text() + ("\n  uses_it:\n    ref: FD1\n    kind: D\n"
                                   "    formula: gone_n01 * 2\n")
        path.write_text(text)
        code, _, err = run("--path", str(path), "delete-point", "n01", "--force")
        assert code == 2 and "still used by uses_it" in err
        assert path.read_text() == text

    def test_add_then_delete_leaves_the_registry_as_it_was(self, grid):
        add(grid, "a")
        assert run("--path", str(grid), "delete-point", "n08")[0] == 0
        assert grid.read_text() == GRID

    def test_nothing_is_written_when_one_document_fails(self, tmp_path,
                                                        monkeypatch):
        path = shifting(tmp_path, SHIFTED)
        before = {p: p.read_text() for p in tmp_path.iterdir() if p.is_file()}
        real = figure_points.rewrite_marks
        calls = []

        def second_fails(text, refs):
            calls.append(text)
            if len(calls) == 2:
                raise FigureError("the second document cannot be rewritten")
            return real(text, refs)

        monkeypatch.setattr(figure_points, "rewrite_marks", second_fails)
        code, _, err = run("--path", str(path), "delete-point", "n01")
        assert code == 2 and "second document" in err
        assert {p: p.read_text() for p in tmp_path.iterdir() if p.is_file()} == before

    def test_a_write_that_fails_leaves_every_file_and_no_residue(self, tmp_path,
                                                                 monkeypatch):
        path = shifting(tmp_path, SHIFTED)
        before = {p: p.read_text() for p in tmp_path.iterdir() if p.is_file()}
        real = pathlib.Path.write_text

        def refuse_the_registry(self, text, *args, **kwargs):
            if self.name == f".{figures.REGISTRY}.report-kit":
                raise OSError(28, "No space left on device", str(self))
            return real(self, text, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "write_text", refuse_the_registry)
        code, _, err = run("--path", str(path), "delete-point", "n01")
        assert code == 2 and "nothing was changed" in err
        assert {p: p.read_text() for p in tmp_path.iterdir() if p.is_file()} == before

    def test_an_unknown_label_is_named(self, grid):
        code, _, err = run("--path", str(grid), "delete-point", "n99")
        assert code == 2 and "no figure carries point: n99" in err


def test_validate_names_a_points_block_it_cannot_use(grid):
    grid.write_text(GRID.replace("  axis: n\n", ""))
    code, out, _ = run("--path", str(grid), "validate")
    assert code == 1 and "points: needs axis:" in out


def test_both_examples_carry_a_points_template_that_validates():
    examples = pathlib.Path(__file__).resolve().parent.parent / "examples"
    for name in ("simple-api", "async-jobs"):
        registry = Registry.load(explicit=examples / name / figures.REGISTRY)
        assert points.read_template(registry.points).figures, name


def test_help_names_every_subcommand_main_dispatches():
    for command in ("check", "pull", "validate", "orphans", "retype", "renumber",
                    *figures.POINT_COMMANDS):
        assert f"report-kit figures {command}" in figures.__doc__, command
