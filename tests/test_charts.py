"""The chart contract: what `--check` says, and what the renderer decides.

    pytest tests/test_charts.py

Three halves. The first is the grading — a problem costs an exit code, a note
does not — because that line is the whole difference between a utility and a
gatekeeper, and the CSVs belong to the consumer. The second is what a chart
will draw from partial data: a sweep that never priced itself, one that
recorded only the ceiling it was given, a split with no fleet figure. The third
renders, and is skipped where matplotlib is not installed.

Nothing here checks a value against `figures.yaml`. That is the registry's
question, answered by putting `charts/*.csv` in its `scan`.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pytest

from report_kit.tools import charts

matplotlib = pytest.importorskip("matplotlib", reason="charts extra not installed")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = charts.main(list(argv))
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def write(path: Path, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


JOBS_HEADER = ("n_set,n_reached,throughput,usd_per_1m_units,unit,"
               "usd_per_run,unit_count,dominated")
JOBS_ROWS = ("10,9.0,0.76,44700,docs,4.47,100,1",
             "25,19.5,1.62,24900,docs,2.49,100,",
             "50,32.6,2.27,44300,docs,4.43,100,")

REGISTRY = """\
scan:
  - report.md

figures:
  cost_n10:
    ref: FD1
    kind: D
    formula: 4.47
    unit: usd
    display: 2
  cost_per_1m_n10:
    ref: FD2
    kind: D
    formula: 44700
    unit: usd
    display: 0
"""


# ------------------------------------------------------------------ contract

def test_list_prints_every_schema_and_needs_no_data():
    code, out, _ = run("--list")
    assert code == 0
    for name in charts.SCHEMA:
        assert name in out
    assert "ignored, not rejected" in out
    assert "figures.yaml's question" in out


def test_no_schema_asks_a_report_to_register_a_particular_column():
    """The kit does not decide what a consuming report registers. Row 7 of
    TECH-DEBT.md was this key; it is gone, and nothing replaced it."""
    for spec in charts.SCHEMA.values():
        assert "figures" not in spec


def test_every_chart_has_a_csv_and_a_drawing_function():
    """One table pairs them, so the only drift left is a CSV with no schema."""
    for csv_name, draw in charts.CHART.values():
        assert csv_name in charts.SCHEMA
        assert callable(draw)


def test_a_draw_function_called_directly_loads_its_own_backend():
    """API.md promises the model is importable. A caller that never ran the
    command must not meet `NoneType has no attribute subplots`."""
    charts.canvas.plt = None
    fig, _ = charts.new_figure()
    assert charts.canvas.plt is not None
    charts.canvas.plt.close(fig)


def test_a_column_the_tool_does_not_read_is_a_note_not_a_failure(tmp_path):
    """The CSV is the consumer's. An extra column is named once, then ignored."""
    path = write(tmp_path / "frontier-jobs.csv",
                 JOBS_HEADER + ",surprise", JOBS_ROWS[0] + ",1")
    problems, notes = charts.validate(path)
    assert problems == []
    assert notes == ["frontier-jobs.csv: surprise is not a column this tool "
                     "reads"]


def test_a_missing_required_column_fails(tmp_path):
    path = write(tmp_path / "floor-blocks.csv", "block", "B")
    problems, _ = charts.validate(path)
    assert any("required column absent — usd_per_month" in p for p in problems)


def test_a_non_numeric_required_cell_fails(tmp_path):
    path = write(tmp_path / "floor-blocks.csv", "block,usd_per_month", "B,soon")
    problems, _ = charts.validate(path)
    assert any("usd_per_month is not a number" in p for p in problems)


def test_a_naming_column_is_not_asked_to_be_a_number(tmp_path):
    path = write(tmp_path / "floor-blocks.csv", "block,usd_per_month", "B,10")
    problems, _ = charts.validate(path)
    assert problems == []


def test_the_templates_placeholder_is_named_as_such(tmp_path):
    path = write(tmp_path / "split-jobs.csv",
                 "n_set,⟨workload⟩,unused_fleet", "10,1.0,2.0")
    problems, notes = charts.validate(path)
    assert problems == []
    assert any("still the template's placeholder" in n for n in notes)


def test_a_header_only_file_is_reported_without_failing(tmp_path):
    """The ordinary state of a first revision, and it costs no exit code."""
    path = write(tmp_path / "split-jobs.csv", "n_set,⟨workload⟩,unused_fleet")
    problems, notes = charts.validate(path)
    assert problems == []
    assert any("header only, no rows yet" in n for n in notes)
    assert any("placeholder" in n for n in notes)


def test_an_unschemad_filename_says_so_without_failing(tmp_path):
    path = write(tmp_path / "invented.csv", "a,b", "1,2")
    problems, notes = charts.validate(path)
    assert problems == []
    assert notes == ["invented.csv: no schema — this tool draws nothing from it"]


# ------------------------------------------------------------------- derived

def test_a_derived_column_that_disagrees_with_its_inputs_is_reported(tmp_path):
    path = write(tmp_path / "frontier-jobs.csv", JOBS_HEADER,
                 "10,9.0,0.76,90000,docs,4.47,100,")
    problems, _ = charts.validate(path)
    assert any("usd_per_1m_units states 90,000" in p for p in problems)
    assert any("usd_per_run / unit_count * 1e6 gives 44,700" in p
               for p in problems)


def test_a_derived_column_inside_tolerance_passes(tmp_path):
    path = write(tmp_path / "frontier-jobs.csv", JOBS_HEADER, *JOBS_ROWS)
    problems, _ = charts.validate(path)
    assert problems == []


def test_a_derived_column_with_an_input_missing_is_not_guessed_at(tmp_path):
    path = write(tmp_path / "frontier-jobs.csv", JOBS_HEADER,
                 "10,9.0,0.76,90000,docs,,,")
    problems, _ = charts.validate(path)
    assert problems == []


def test_the_open_split_schema_sums_whatever_the_header_names(tmp_path):
    path = write(tmp_path / "split-jobs.csv",
                 "n_set,alpha,beta,gamma,workload_total,unused_fleet",
                 "10,0.5,0.3,0.2,1.0,4.0",
                 "25,0.5,0.3,0.2,9.9,4.0")
    problems, _ = charts.validate(path)
    assert problems == [
        "split-jobs.csv:3: workload_total states 9.9, workload_total = every "
        "workload column added up gives 1 (890.0% apart)"]


def test_an_open_split_schema_with_no_workload_column_says_so(tmp_path):
    path = write(tmp_path / "split-jobs.csv", "n_set,unused_fleet", "10,4.0")
    problems, notes = charts.validate(path)
    assert problems == []
    assert any("no workload column yet" in n for n in notes)


# ------------------------------------------------- what partial data still draws

def test_a_sweep_that_was_never_priced_still_gets_one_panel(tmp_path,
                                                            monkeypatch):
    """`usd_per_1m_units` is optional, so a report with no price basis — both
    worked examples — charts its throughput rather than nothing."""
    write(tmp_path / "charts" / "frontier-jobs.csv",
          "n_set,n_reached,throughput\n1,1.0,4.23\n2,1.9,8.18\n")
    monkeypatch.chdir(tmp_path)
    assert charts.validate(tmp_path / "charts" / "frontier-jobs.csv") == ([], [])
    code, out, err = run("jobs-frontier")
    assert code == charts.EXIT_OK, err
    assert (tmp_path / "assets" / "frontier-jobs.svg").exists()


def test_the_axis_falls_back_to_the_ceiling_that_was_set(tmp_path):
    """A run that recorded only what it was given, not what it held."""
    rows = [{"n_set": "1", "n_reached": ""}, {"n_set": "2", "n_reached": ""}]
    assert charts.jobs_axis(rows) == ("n_set", "concurrency set")
    rows[1]["n_reached"] = "1.9"
    assert charts.jobs_axis(rows)[0] == "n_reached"


def test_a_split_with_no_fleet_figure_still_draws_its_workloads(tmp_path,
                                                                monkeypatch):
    write(tmp_path / "charts" / "split-jobs.csv",
          "n_set,alpha,beta\n10,0.5,0.3\n25,0.4,0.2\n")
    monkeypatch.chdir(tmp_path)
    code, _, err = run("jobs-split")
    assert code == charts.EXIT_OK, err
    assert (tmp_path / "assets" / "split-jobs.svg").exists()


def test_the_tradeoff_skips_rather_than_invents_a_price(tmp_path, monkeypatch):
    write(tmp_path / "charts" / "frontier-jobs.csv",
          "n_set,throughput\n1,4.23\n2,8.18\n")
    monkeypatch.chdir(tmp_path)
    code, _, err = run("jobs-tradeoff")
    assert code == charts.EXIT_OK
    assert "needs throughput and usd_per_1m_units" in err
    assert not (tmp_path / "assets" / "tradeoff-jobs.svg").exists()


# --------------------------------------------------------------- open series

def test_replica_series_come_from_the_header():
    spec = charts.SCHEMA["frontier-api.csv"]
    header = ["offered_rps", "p95_ms", "replicas_api", "replicas_tei", "note"]
    assert charts.series_columns(spec, header) == [
        ("replicas_api", "api"), ("replicas_tei", "tei")]


def test_a_placeholder_series_is_not_taken_for_a_real_one():
    spec = charts.SCHEMA["frontier-api.csv"]
    assert charts.series_columns(spec, ["replicas_⟨tier⟩"]) == []


def test_split_segments_rank_by_total_and_fold_the_remainder():
    rows = [{"a": "1", "b": "5", "c": "3", "d": "0.5"},
            {"a": "1", "b": "5", "c": "3", "d": "0.5"}]
    segments = charts.split_segments(rows, ["a", "b", "c", "d"])
    assert [key for key, _ in segments] == ["b", "c", "other"]
    assert segments[-1][1] == [1.5, 1.5]      # a + d, per row


def test_a_unit_is_read_from_the_first_row_and_defaults():
    assert charts.unit_of([{"unit": "events"}]) == "events"
    assert charts.unit_of([{"unit": ""}]) == "unit"
    assert charts.unit_of([]) == "unit"


@pytest.mark.parametrize("plural,one", [("docs", "doc"), ("queries", "query"),
                                        ("events", "event"), ("unit", "unit")])
def test_a_unit_is_singularised_for_a_per_unit_axis(plural, one):
    assert charts.singular(plural) == one


# ------------------------------------------------------------------ renderer

@pytest.fixture
def rendered(tmp_path):
    """One of each chart, from data thin enough to reason about."""
    write(tmp_path / "charts" / "frontier-jobs.csv", JOBS_HEADER, *JOBS_ROWS)
    write(tmp_path / "charts" / "split-jobs.csv",
          "n_set,alpha,beta,gamma,workload_total,unused_fleet",
          "10,0.5,0.3,0.2,1.0,4.0", "25,0.4,0.3,0.2,0.9,3.0")
    write(tmp_path / "charts" / "frontier-api.csv",
          "offered_rps,p95_ms,unit,replicas_api,replicas_tei,reference_ms,"
          "reference_note,p95_converged_ms",
          "50,2418,queries,2,3,2000,stub,", "500,7934,queries,3,16,,,2425")
    write(tmp_path / "charts" / "floor-blocks.csv",
          "block,usd_per_month", "B,534.12", "A,343.42")
    write(tmp_path / "charts" / "amortization.csv",
          "unit,volume,effective_usd_per_unit,floor_share_pct,crossover_volume",
          "docs,1000,0.559,95.6,21472", "docs,1000000,0.0254,2.1,")
    return tmp_path


def test_all_renders_every_chart_on_both_surfaces(rendered, monkeypatch):
    monkeypatch.chdir(rendered)
    for theme in ("light", "navy"):
        code, _, err = run("all", "--theme", theme)
        assert code == charts.EXIT_OK, err
    names = {p.name for p in (rendered / "assets").iterdir()}
    assert names == {
        "frontier-jobs.svg", "tradeoff-jobs.svg", "split-jobs.svg",
        "frontier-api.svg", "floor-blocks.svg", "amortization-docs.svg",
        "manifest-light.json",
        "frontier-jobs-navy.svg", "tradeoff-jobs-navy.svg",
        "split-jobs-navy.svg", "frontier-api-navy.svg",
        "floor-blocks-navy.svg", "amortization-docs-navy.svg",
        "manifest-navy.json"}


def test_the_manifest_records_the_csv_it_drew_from(rendered, monkeypatch):
    monkeypatch.chdir(rendered)
    run("floor", "--theme", "light")
    import json
    entry = json.loads((rendered / "assets" / "manifest-light.json").read_text())
    assert entry[0]["chart"] == "floor"
    assert entry[0]["source_sha256_12"] == charts.sha256(
        rendered / "charts" / "floor-blocks.csv")


def test_text_is_emitted_as_text_so_the_fonts_resolve_later(rendered,
                                                            monkeypatch):
    monkeypatch.chdir(rendered)
    run("floor")
    svg = (rendered / "assets" / "floor-blocks.svg").read_text()
    assert "IBM Plex Mono" in svg and "<text" in svg


def test_a_csv_with_no_usable_row_is_skipped_and_the_rest_still_render(
        rendered, monkeypatch):
    write(rendered / "charts" / "floor-blocks.csv", "block,usd_per_month",
          "B,534.12")
    monkeypatch.chdir(rendered)
    code, out, err = run("all")
    assert code == charts.EXIT_OK
    assert "needs blocks A and B" in err
    assert "frontier-jobs.svg" in out


def test_check_fails_on_a_problem_and_not_on_a_note(rendered, monkeypatch):
    monkeypatch.chdir(rendered)
    clean, out, _ = run("floor", "--check")
    assert (clean, out.strip().endswith("across 1 file(s)")) == (charts.EXIT_OK,
                                                                 True)
    write(rendered / "charts" / "floor-blocks.csv",
          "block,usd_per_month,surprise", "B,534.12,1")
    noted, out, _ = run("floor", "--check")
    assert noted == charts.EXIT_OK
    assert "note: floor-blocks.csv: surprise is not a column" in out
    write(rendered / "charts" / "floor-blocks.csv", "block", "B")
    broken, out, _ = run("floor", "--check")
    assert broken == charts.EXIT_FAILED
    assert "required column absent — usd_per_month" in out


def test_all_refuses_a_single_data_path(rendered, monkeypatch):
    monkeypatch.chdir(rendered)
    code, _, err = run("all", "--data", "charts/floor-blocks.csv")
    assert code == charts.EXIT_USAGE
    assert "cannot be combined with 'all'" in err


# --- what the label placement guarantees ------------------------------------

def placements(fig, ax):
    """Every annotation on one axis as a display box, layout settled."""
    renderer = charts.renderer_for(fig)
    return [a.get_window_extent(renderer) for a in ax.texts]


def crowded_axis():
    """Two marks a hair apart, each wanting a label wider than the gap."""
    charts.load_backend()
    charts.configure(charts.THEMES["light"])
    fig, ax = charts.new_figure()
    ax.plot([1.0, 1.02], [1.0, 1.01], marker="o")
    renderer = charts.renderer_for(fig)
    obstacles = []
    for x, y in ((1.0, 1.0), (1.02, 1.01)):
        charts.place_label(ax, "a label of some width", (x, y),
                           charts.THEMES["light"], renderer, obstacles)
    return fig, ax


def test_two_labels_on_neighbouring_marks_do_not_overlap():
    fig, ax = crowded_axis()
    first, second = placements(fig, ax)
    assert not first.overlaps(second), (
        "labels on adjacent marks landed on each other — the candidate rows "
        "are what stop that, so one of them stopped working")


def test_a_label_stays_inside_the_frame():
    fig, ax = crowded_axis()
    frame = ax.get_window_extent(charts.renderer_for(fig))
    for box in placements(fig, ax):
        assert charts.within(frame, box)


def test_a_label_is_placed_even_where_nothing_is_clear():
    charts.load_backend()
    charts.configure(charts.THEMES["light"])
    fig, ax = charts.new_figure()
    ax.plot([1.0], [1.0], marker="o")
    renderer = charts.renderer_for(fig)
    obstacles = [ax.get_window_extent(renderer)]      # the whole frame is taken
    charts.place_label(ax, "nowhere to go", (1.0, 1.0),
                       charts.THEMES["light"], renderer, obstacles)
    assert len(ax.texts) == 1, "a label with no free position was dropped"


def test_a_soft_obstacle_yields_before_a_hard_one_does():
    """A rule may end up behind a label; another label may not."""
    charts.load_backend()
    charts.configure(charts.THEMES["light"])
    fig, ax = charts.new_figure()
    ax.plot([1.0, 2.0], [1.0, 2.0], marker="o")
    renderer = charts.renderer_for(fig)
    rule = charts.rule_obstacle(ax, 1.5, renderer)
    obstacles = []
    charts.place_label(ax, "first", (1.5, 1.5), charts.THEMES["light"],
                       renderer, obstacles, soft=[rule])
    charts.place_label(ax, "second", (1.5, 1.5), charts.THEMES["light"],
                       renderer, obstacles, soft=[rule])
    first, second = placements(fig, ax)
    assert not first.overlaps(second)
