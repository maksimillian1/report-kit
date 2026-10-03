"""The frozen CSV format, and the four shapes drawn from it.

    pytest tests/test_charts.py

The format half needs no matplotlib and is where the value is: what the file
decides on its own is the whole design. The render half is skipped where
matplotlib is not installed.

Shapes and conventions that `examples/tenant-platform/` already demonstrates are
asserted here against those same files, so an example that stops working fails a
test rather than going quietly stale.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from report_kit.tools import charts
from report_kit.tools.charts import table

matplotlib = pytest.importorskip("matplotlib", reason="charts extra not installed")

FIXTURES = Path(__file__).resolve().parent.parent / "examples" / "tenant-platform" / "charts"


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


# ------------------------------------------------------------------- format

def test_the_units_row_is_required(tmp_path):
    path = write(tmp_path / "f.csv", "a,b", "1,2", "3,4")
    with pytest.raises(charts.Skip, match="must be the units row"):
        table.read(path)


def test_a_unit_is_required_for_every_column(tmp_path):
    path = write(tmp_path / "f.csv", "a,b,c", "label,$", "x,1,2")
    with pytest.raises(charts.Skip, match="a unit for every column"):
        table.read(path)


def test_a_file_with_no_data_rows_says_so(tmp_path):
    path = write(tmp_path / "f.csv", "a,b", "label,$")
    with pytest.raises(charts.Skip, match="no rows yet"):
        table.read(path)


def test_a_file_with_nothing_numeric_says_so(tmp_path):
    path = write(tmp_path / "f.csv", "a,b", "label,label", "x,y")
    with pytest.raises(charts.Skip, match="no numeric column"):
        table.read(path)


def test_the_units_row_sorts_labels_from_series(tmp_path):
    path = write(tmp_path / "f.csv", "name,note,x,y",
                 "label,label,s,$", "first,ok,1,10", "second,ok,2,20")
    data = table.read(path)
    assert [c.name for c in data.labels] == ["name", "note"]
    assert [c.name for c in data.series] == ["x", "y"]


def test_a_non_numeric_column_is_a_label_whatever_its_unit(tmp_path):
    path = write(tmp_path / "f.csv", "name,x", "$,s", "first,1")
    assert [c.name for c in table.read(path).labels] == ["name"]


def test_columns_sharing_a_unit_share_a_group(tmp_path):
    path = write(tmp_path / "f.csv", "x,a,b,c", "s,ms,ms,$",
                 "1,10,11,100", "2,20,21,200")
    groups = {g.unit: [c.name for c in g.columns] for g in table.read(path).groups}
    assert groups == {"s": ["x"], "ms": ["a", "b"], "$": ["c"]}


def test_an_aside_unit_is_its_own_group(tmp_path):
    path = write(tmp_path / "f.csv", "step,a,spare", "label,$,$ aside",
                 "first,1,4")
    data = table.read(path)
    assert [g.unit for g in data.panels] == ["$"]
    assert [g.title for g in data.aside] == ["$"]


def test_the_first_series_column_becomes_the_axis(tmp_path):
    path = write(tmp_path / "f.csv", "n,reached,rate", "label,concurrency,docs/min",
                 "N=1,9.0,0.7", "N=2,19.0,1.6")
    data = table.with_axis(table.read(path))
    assert data.x.name == "reached"
    assert [c.name for c in data.series] == ["rate"]


def test_a_file_whose_only_number_would_be_the_axis_is_refused(tmp_path):
    path = write(tmp_path / "f.csv", "name,x", "label,s", "first,1", "second,2")
    with pytest.raises(charts.Skip, match="nothing is left to plot"):
        table.with_axis(table.read(path))


def test_an_empty_cell_is_a_gap_not_a_zero(tmp_path):
    path = write(tmp_path / "f.csv", "x,y", "s,$", "1,10", "2,", "3,30")
    assert table.read(path).series[1].values == (10.0, None, 30.0)


def test_a_thousands_separator_is_read(tmp_path):
    path = write(tmp_path / "f.csv", "x,y", "s,$", "1,\"44,707\"")
    assert table.read(path).series[1].values == (44707.0,)


# ---------------------------------------------- what the file decides itself

@pytest.mark.parametrize("values,wide", [((1, 7), False), ((1000, 1_000_000), True)])
def test_log_follows_how_wide_the_axis_is(tmp_path, values, wide):
    path = write(tmp_path / "f.csv", "x,y", "s,$",
                 f"{values[0]},1", f"{values[1]},100")
    assert table.log_x(table.with_axis(table.read(path))) is wide


def test_y_follows_x_into_log_only_when_it_is_also_wide(tmp_path):
    wide = table.with_axis(table.read(write(
        tmp_path / "w.csv", "x,y", "s,$", "1000,1", "1000000,100")))
    narrow = table.with_axis(table.read(write(
        tmp_path / "n.csv", "x,y", "s,$", "1000,1", "1000000,2")))
    assert table.log_y(wide, wide.panels[0])
    assert not table.log_y(narrow, narrow.panels[0])


def test_each_panel_decides_its_own_log_y(tmp_path):
    data = table.with_axis(table.read(write(
        tmp_path / "f.csv", "x,cost,share", "n,$,%",
        "10000,0.05,99.99", "1000000,0.0005,99.3", "1000000000,0.000004,12.5")))
    cost, share = data.panels
    assert table.log_y(data, cost) and not table.log_y(data, share)


def test_a_subtotal_is_a_row_restating_the_running_total():
    assert table.subtotals((2.4505, 2.8783, 5.3288, -0.9582, 4.3706)) == (
        False, False, True, False, True)


def test_a_row_that_only_looks_like_a_subtotal_is_a_step():
    assert table.subtotals((5.0, 5.0)) == (False, True)
    assert table.subtotals((5.0, 3.0, 2.0)) == (False, False, False)


def test_the_tail_of_a_long_stack_folds_into_one_segment():
    from report_kit.tools.charts.kinds import fold
    columns = [table.Column(n, "$", (v,))
               for n, v in (("a", 5), ("b", 4), ("c", 3), ("d", 2), ("e", 1))]
    folded = fold(columns, 3)
    assert [c.name for c in folded] == ["a", "b", "other"]
    assert folded[-1].values == (6,)


def test_a_stack_within_the_ramp_is_left_alone():
    from report_kit.tools.charts.kinds import fold
    columns = [table.Column(n, "$", (1,)) for n in ("a", "b", "c")]
    assert [c.name for c in fold(columns, 3)] == ["a", "b", "c"]


# -------------------------------------------------------------- the command

def test_format_prints_the_contract_and_needs_no_file():
    code, out, _ = run("--format")
    assert code == charts.EXIT_OK
    for kind in charts.KINDS:
        assert kind in out
    assert "line 2" in out and "aside" in out


def test_a_kind_is_required_to_draw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "floor.csv"))
    assert code == charts.EXIT_USAGE
    assert "--kind is the one thing the file cannot say" in err


def test_new_writes_a_skeleton_the_reader_then_accepts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for kind in charts.KINDS:
        code, _, err = run("new", "--kind", kind)
        assert code == charts.EXIT_OK, err
        table.read(tmp_path / "charts" / f"{kind}.csv")
    entries = charts.spec.read_spec()
    assert [(e.name, e.kind) for e in entries] == [(k, k) for k in charts.KINDS]


def test_new_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("new", "--kind", "parts")
    (tmp_path / "charts" / "parts.csv").write_text("mine\n", encoding="utf-8")
    code, out, _ = run("new", "--kind", "parts")
    assert code == charts.EXIT_OK and "left alone" in out
    assert (tmp_path / "charts" / "parts.csv").read_text(encoding="utf-8") == "mine\n"


def test_check_reports_without_drawing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files = sorted(FIXTURES.glob("*.csv"))
    code, out, _ = run("--check", *[str(p) for p in files])
    assert code == charts.EXIT_OK
    assert out.count("note:") == len(files)
    assert not (tmp_path / "charts").exists()


def test_check_fails_on_a_file_it_cannot_read(tmp_path, monkeypatch):
    broken = write(tmp_path / "b.csv", "a,b", "1,2", "3,4")
    monkeypatch.chdir(tmp_path)
    code, out, _ = run("--check", str(broken))
    assert code == charts.EXIT_FAILED
    assert "must be the units row" in out


def test_an_unknown_theme_names_the_ones_there_are(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "floor.csv"), "--kind", "parts",
                       "--theme", "chartreuse")
    assert code == charts.EXIT_USAGE
    assert "light" in err and "navy" in err


def test_a_theme_file_replaces_or_adds_one(tmp_path, monkeypatch):
    theme = dict(charts.DEFAULT_THEMES["light"], cost="#123456")
    write(tmp_path / "charts" / "themes.json", json.dumps({"print": theme}))
    monkeypatch.chdir(tmp_path)
    code, out, err = run(str(FIXTURES / "floor.csv"), "--kind", "parts",
                         "--theme", "print")
    assert code == charts.EXIT_OK, err
    assert "floor-print.svg" in out


def test_a_theme_missing_a_key_is_refused(tmp_path, monkeypatch):
    write(tmp_path / "charts" / "themes.json", json.dumps({"half": {"ink": "#000"}}))
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "floor.csv"), "--kind", "parts",
                       "--theme", "half")
    assert code == charts.EXIT_USAGE
    assert "is missing" in err


def test_a_rule_wants_a_number_first(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "failover.csv"), "--kind", "line",
                       "--rule", "soon")
    assert code == charts.EXIT_USAGE
    assert "wants a number first" in err


def test_a_mark_x_wants_a_number_first(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "failover.csv"), "--kind", "line",
                       "--mark-x", "later")
    assert code == charts.EXIT_USAGE
    assert "--mark-x wants a number first" in err


@pytest.mark.parametrize("flag", [["--rule", "1"], ["--mark-x", "1"],
                                  ["--points"]])
def test_a_mark_is_refused_by_a_shape_that_cannot_draw_it(tmp_path,
                                                          monkeypatch, flag):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(str(FIXTURES / "floor.csv"), "--kind", "parts", *flag)
    assert code == charts.EXIT_USAGE
    assert "draw on line only" in err


# ------------------------------------------------------- the four shapes

@pytest.mark.parametrize("name,kind", [
    ("amortization.csv", "line"), ("failover.csv", "line"),
    ("isolation.csv", "line"), ("tier-cost.csv", "bars"),
    ("floor-resize.csv", "bars"), ("monthly-bill.csv", "bars"),
    ("floor.csv", "parts"), ("margin.csv", "waterfall")])
def test_every_example_still_renders_on_both_surfaces(tmp_path, monkeypatch,
                                                      name, kind):
    monkeypatch.chdir(tmp_path)
    for theme in ("light", "navy"):
        code, out, err = run(str(FIXTURES / name), "--kind", kind,
                             "--theme", theme)
        assert code == charts.EXIT_OK, err
        suffix = "" if theme == "light" else "-navy"
        assert (tmp_path / "charts" / f"{Path(name).stem}{suffix}.svg").exists()


def test_several_csvs_render_in_one_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = run(str(FIXTURES / "amortization.csv"),
                         str(FIXTURES / "failover.csv"), "--kind", "line")
    assert code == charts.EXIT_OK, err
    assert (tmp_path / "charts" / "amortization.svg").exists()
    assert (tmp_path / "charts" / "failover.svg").exists()
    entries = json.loads((tmp_path / "charts" / "manifest-light.json").read_text())
    assert [e["svg"] for e in entries] == ["amortization.svg", "failover.svg"]
    assert entries[0]["source_sha256_12"] == table.sha256(FIXTURES / "amortization.csv")


def test_separate_calls_keep_each_others_manifest_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(str(FIXTURES / "floor.csv"), "--kind", "parts")
    run(str(FIXTURES / "failover.csv"), "--kind", "line", "--mark-x", "20", "lost")
    entries = json.loads((tmp_path / "charts" / "manifest-light.json").read_text())
    assert [e["svg"] for e in entries] == ["failover.svg", "floor.svg"]
    assert entries[0]["mark_x"] == [20.0, "lost"]
    assert "mark_x" not in entries[1]


FAILOVER = ("failover:", "  kind: line",
            "  mark_x: {at: 20, text: primary lost}")


def specified(tmp_path, *lines):
    for name in ("floor.csv", "failover.csv"):
        (tmp_path / "charts").mkdir(exist_ok=True)
        (tmp_path / "charts" / name).write_bytes((FIXTURES / name).read_bytes())
    return write(tmp_path / "charts" / "charts.yaml", *lines)


def test_all_draws_every_chart_on_every_theme(tmp_path, monkeypatch):
    specified(tmp_path, "# the example", "floor:", "  kind: parts", *FAILOVER)
    monkeypatch.chdir(tmp_path)
    code, _, err = run("--all")
    assert code == charts.EXIT_OK, err
    for name in ("floor", "failover", "floor-navy", "failover-navy"):
        assert (tmp_path / "charts" / f"{name}.svg").exists()
    entries = json.loads((tmp_path / "charts" / "manifest-light.json").read_text())
    assert [e["svg"] for e in entries] == ["failover.svg", "floor.svg"]
    assert entries[0]["mark_x"] == [20.0, "primary lost"]


def test_all_replaces_the_manifest_so_a_dropped_chart_leaves(tmp_path,
                                                             monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts", "failover:", "  kind: line")
    monkeypatch.chdir(tmp_path)
    run("--all", "--theme", "light")
    write(tmp_path / "charts" / "charts.yaml", "floor:", "  kind: parts")
    run("--all", "--theme", "light")
    entries = json.loads((tmp_path / "charts" / "manifest-light.json").read_text())
    assert [e["svg"] for e in entries] == ["floor.svg"]


def test_all_deletes_an_svg_no_entry_draws(tmp_path, monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts", "failover:", "  kind: line")
    monkeypatch.chdir(tmp_path)
    run("--all")
    write(tmp_path / "charts" / "charts.yaml", "floor:", "  kind: parts")
    code, out, err = run("--all")
    assert code == charts.EXIT_OK, err
    assert not list((tmp_path / "charts").glob("failover*.svg"))
    assert (tmp_path / "charts" / "floor-navy.svg").exists()
    assert "removed" in out


def test_every_svg_says_it_is_generated_and_from_what(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(str(FIXTURES / "floor.csv"), "--kind", "parts")
    head = (tmp_path / "charts" / "floor.svg").read_text(encoding="utf-8")[:300]
    assert "generated by report-kit charts from floor.csv" in head


def test_all_without_a_spec_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run("--all")
    assert code == charts.EXIT_USAGE
    assert "charts/charts.yaml" in err


def test_all_takes_nothing_the_spec_already_says(tmp_path, monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts")
    monkeypatch.chdir(tmp_path)
    code, _, err = run("--all", "--kind", "line")
    assert code == charts.EXIT_USAGE
    assert "from charts/charts.yaml" in err


@pytest.mark.parametrize("lines,said", [
    (("failover: line",), "expected `kind:`"),
    (("failover:", "  kind: pie"), "kind must be one of"),
    (("floor:", "  kind: parts", "  points: true"), "draw on line only"),
    (("failover:", "  kind: line", "  colour: red"), "unknown key colour"),
    (("failover:", "  kind: line", "  rule: {at: soon}"), "rule.at must be a number"),
    (("failover:", "  kind: line", "  rule: 300"), "rule wants {at:"),
    (("failover:", "  kind: line", "  points: yes please"), "points is true or false"),
    (("floor:", "  kind: parts", "floor:", "  kind: bars"), "floor given twice")])
def test_a_bad_entry_is_named_by_its_chart(tmp_path, monkeypatch, lines, said):
    specified(tmp_path, *lines)
    monkeypatch.chdir(tmp_path)
    code, _, err = run("--all")
    assert code == charts.EXIT_USAGE
    assert "charts.yaml" in err and said in err


def test_check_names_a_csv_the_spec_leaves_out(tmp_path, monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts")
    monkeypatch.chdir(tmp_path)
    run("--all")
    code, out, _ = run("--check")
    assert code == charts.EXIT_FAILED
    assert "failover.csv: no entry in charts.yaml" in out


def test_check_passes_once_everything_is_drawn(tmp_path, monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts", *FAILOVER)
    monkeypatch.chdir(tmp_path)
    code, out, _ = run("--check")
    assert code == charts.EXIT_FAILED and "nothing drawn yet" in out
    run("--all")
    code, out, _ = run("--check")
    assert code == charts.EXIT_OK, out


def test_check_fails_when_a_csv_changed_after_it_was_drawn(tmp_path,
                                                         monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts")
    monkeypatch.chdir(tmp_path)
    run("--all")
    floor = tmp_path / "charts" / "floor.csv"
    floor.write_text(floor.read_text(encoding="utf-8") + "extra,1\n",
                     encoding="utf-8")
    code, out, _ = run("--check")
    assert code == charts.EXIT_FAILED
    assert "floor.csv changed since floor.svg was drawn" in out


def test_check_fails_when_the_spec_changed_after_drawing(tmp_path,
                                                        monkeypatch):
    specified(tmp_path, *FAILOVER)
    monkeypatch.chdir(tmp_path)
    run("--all")
    write(tmp_path / "charts" / "charts.yaml", "failover:", "  kind: line")
    code, out, _ = run("--check")
    assert code == charts.EXIT_FAILED
    assert "charts.yaml changed since failover.svg was drawn" in out


def test_check_fails_when_an_svg_is_missing(tmp_path, monkeypatch):
    specified(tmp_path, "floor:", "  kind: parts")
    monkeypatch.chdir(tmp_path)
    run("--all")
    (tmp_path / "charts" / "floor-navy.svg").unlink()
    code, out, _ = run("--check")
    assert code == charts.EXIT_FAILED
    assert "floor: not drawn on navy" in out


def test_the_example_spec_covers_the_example_and_is_current(monkeypatch):
    monkeypatch.chdir(FIXTURES.parent)
    code, out, _ = run("--check")
    assert code == charts.EXIT_OK, out


def drawn(monkeypatch, path, **marks):
    """The figure a shape builds, kept open instead of saved."""
    figures = []
    monkeypatch.setattr(charts.kinds, "save",
                        lambda fig, *_: figures.append(fig) or Path("x.svg"))
    charts.canvas.load_backend()
    charts.canvas.configure(charts.DEFAULT_THEMES["light"])
    charts.kinds.line(table.read(path), charts.DEFAULT_THEMES["light"],
                      Path("."), "light", charts.kinds.Marks(**marks))
    return figures[0]


def test_an_empty_cell_breaks_the_line(monkeypatch):
    fig = drawn(monkeypatch, FIXTURES / "failover.csv")
    p95 = fig.axes[0].lines[0].get_ydata()
    assert any(value != value for value in p95)
    charts.canvas.plt.close(fig)


def test_points_draws_the_marks_without_joining_them(monkeypatch):
    fig = drawn(monkeypatch, FIXTURES / "isolation.csv", join=False)
    assert all(line.get_linestyle() == "None" for line in fig.axes[0].lines)
    charts.canvas.plt.close(fig)


def test_a_narrow_panel_stays_linear_beside_a_wide_one(monkeypatch, tmp_path):
    path = write(tmp_path / "f.csv", "x,cost,share", "n,$,%",
                 "10000,0.05,99.99", "1000000,0.0005,99.3",
                 "1000000000,0.000004,12.5")
    fig = drawn(monkeypatch, path)
    assert [ax.get_yscale() for ax in fig.axes] == ["log", "linear"]
    assert all(ax.get_xscale() == "log" for ax in fig.axes)
    charts.canvas.plt.close(fig)


def test_a_mark_x_crosses_every_panel(monkeypatch):
    fig = drawn(monkeypatch, FIXTURES / "amortization.csv", mark_x=(100.0, "x"))
    for ax in fig.axes:
        assert any(list(line.get_xdata()) == [100.0, 100.0] for line in ax.lines)
    charts.canvas.plt.close(fig)


def test_one_unreadable_file_does_not_stop_the_others(tmp_path, monkeypatch):
    broken = write(tmp_path / "b.csv", "a,b", "1,2", "3,4")
    monkeypatch.chdir(tmp_path)
    code, out, err = run(str(broken), str(FIXTURES / "floor.csv"),
                         "--kind", "parts")
    assert code == charts.EXIT_OK
    assert "skipped — b.csv" in err
    assert (tmp_path / "charts" / "floor.svg").exists()


def test_text_is_emitted_as_text_so_the_fonts_resolve_later(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(str(FIXTURES / "floor.csv"), "--kind", "parts")
    svg = (tmp_path / "charts" / "floor.svg").read_text(encoding="utf-8")
    assert "IBM Plex Mono" in svg and "<text" in svg


def test_rendering_twice_writes_the_same_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(str(FIXTURES / "failover.csv"), "--kind", "line")
    first = (tmp_path / "charts" / "failover.svg").read_bytes()
    run(str(FIXTURES / "failover.csv"), "--kind", "line")
    assert (tmp_path / "charts" / "failover.svg").read_bytes() == first


def test_a_draw_called_directly_loads_its_own_backend(tmp_path):
    charts.canvas.plt = None
    fig, _ = charts.canvas.new_figure()
    assert charts.canvas.plt is not None
    charts.canvas.plt.close(fig)


# --- what the label placement guarantees ------------------------------------

def crowded_axis():
    charts.canvas.load_backend()
    charts.canvas.configure(charts.DEFAULT_THEMES["light"])
    fig, ax = charts.canvas.new_figure()
    ax.plot([1.0, 1.02], [1.0, 1.01], marker="o")
    renderer = charts.labels.renderer_for(fig)
    obstacles = []
    for x, y in ((1.0, 1.0), (1.02, 1.01)):
        charts.labels.place_label(ax, "a label of some width", (x, y),
                                  charts.DEFAULT_THEMES["light"], renderer,
                                  obstacles)
    return fig, ax


def placements(fig, ax):
    renderer = charts.labels.renderer_for(fig)
    return [a.get_window_extent(renderer) for a in ax.texts]


def test_two_labels_on_neighbouring_marks_do_not_overlap():
    first, second = placements(*crowded_axis())
    assert not first.overlaps(second)


def test_a_label_stays_inside_the_frame():
    fig, ax = crowded_axis()
    frame = ax.get_window_extent(charts.labels.renderer_for(fig))
    for box in placements(fig, ax):
        assert charts.labels.within(frame, box)


def test_a_label_is_placed_even_where_nothing_is_clear():
    charts.canvas.load_backend()
    charts.canvas.configure(charts.DEFAULT_THEMES["light"])
    fig, ax = charts.canvas.new_figure()
    ax.plot([1.0], [1.0], marker="o")
    renderer = charts.labels.renderer_for(fig)
    charts.labels.place_label(ax, "nowhere to go", (1.0, 1.0),
                              charts.DEFAULT_THEMES["light"], renderer,
                              [ax.get_window_extent(renderer)])
    assert len(ax.texts) == 1
