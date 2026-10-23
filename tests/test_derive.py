"""A register ref worked out of one run's committed data, and a value in
`report-values.yaml` that reads it by ref instead of repeating its definition.

    pytest tests/test_derive.py

The execution, its refs and every number here are invented for these tests.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from report_kit import arith, derive
from report_kit.register import RegisterError, parse_register, register_above
from report_kit.tools import metrics as metrics_tool
from report_kit.tools import values as values_tool
from report_kit.tools.metrics.views import table_lines
from report_kit.tools.values import evidence
from report_kit.tools.values.checks import validate
from report_kit.tools.values.registry import Registry
from report_kit.window import Window

REGISTER = """\
metrics:
  M1:
    what: queue depth
    promql: max(queue_depth)
    status: unconfirmed
  M2:
    what: completion rate
    promql: sum(rate(completed_total[30s]))
    status: unconfirmed
  M3:
    what: handler seconds per second
    promql: sum(rate(handler_seconds_total[30s]))
    status: unconfirmed
  D4:
    what: drain duration
    formula: events.drained_at - events.load_started
    status: active
  D5:
    what: drain rate
    formula: settings.count / D4
    status: active
  D6:
    what: mean handler time
    series: {ref: M3, per: M2, where: "M2 > 1", reduce: mean}
    status: active
  R7:
    what: pool ceiling
    record: settings.n
    status: active
  R8:
    what: which tier saturated
    source: written at the end of each run · operator
    status: active
"""

RECORD = {
    "settings": {"n": "4", "count": 600},
    "events": {"load_started": 1000.0, "drained_at": 1150.5},
    "gone": None,
}

EXPORT = [
    {"metric": "M1", "result": [{"metric": {}, "values": [[1, "5"], [2, "9"], [3, "0"]]}]},
    {"metric": "M2", "result": [{"metric": {}, "values": [[1, "0.5"], [2, "2"], [3, "4"]]}]},
    {"metric": "M3", "result": [{"metric": {}, "values": [[1, "1"], [2, "0.5"], [3, "2"]]}]},
]


@pytest.fixture
def execution(tmp_path):
    root = tmp_path / "report"
    data = root / "executions" / "01-drain" / "data"
    data.mkdir(parents=True)
    (root / "executions" / "01-drain" / "metrics.yaml").write_text(REGISTER)
    (data / "n04.point.json").write_text(json.dumps(RECORD))
    (data / "n04.jsonl").write_text("\n".join(json.dumps(line) for line in EXPORT) + "\n")
    return root


def register(text: str = REGISTER):
    return parse_register(text, Path("x/metrics.yaml"))


def record_path(root: Path) -> Path:
    return root / "executions" / "01-drain" / "data" / "n04.point.json"


class TestDefinitions:
    def test_each_letter_takes_its_own_definitions(self):
        metrics = register().by_ref
        assert metrics["D4"].formula == "events.drained_at - events.load_started"
        assert metrics["D6"].series.ref == "M3"
        assert metrics["R7"].record == "settings.n"
        assert metrics["D5"].inputs == ["D4"]
        assert metrics["D6"].inputs == ["M3", "M2", "M2"]

    @pytest.mark.parametrize("change, message", [
        (("    formula: settings.count / D4\n", "    promql: up\n"),
         "only an M ref is a query"),
        (("    record: settings.n\n", "    formula: settings.n\n"),
         "formula is not for it; a R ref takes record or source"),
        (("    promql: max(queue_depth)\n", "    formula: '1'\n"),
         "formula is not for it"),
        (("    formula: settings.count / D4\n",
          "    formula: settings.count / D4\n    record: x\n"),
         "exactly one of formula, series, record, source"),
        (("    formula: settings.count / D4\n", "    formula: settings.count ** D4\n"),
         "unsupported expression node BinOp"),
        (("    formula: settings.count / D4\n", "    formula: settings.count /\n"),
         "is not an expression"),
        (("    formula: settings.count / D4\n", "    formula: settings.count / D9\n"),
         "D5 reads D9, which this register does not define"),
        (("    formula: settings.count / D4\n", "    formula: settings.count / M2\n"),
         "D5 reads M2, a series"),
        (("    formula: settings.count / D4\n", "    formula: settings.count / R8\n"),
         "D5 reads R8, which is written by hand"),
        (('    series: {ref: M3, per: M2, where: "M2 > 1", reduce: mean}\n',
          "    series: {ref: M3, reduce: median}\n"),
         "series reduce 'median' is not one of"),
        (('    series: {ref: M3, per: M2, where: "M2 > 1", reduce: mean}\n',
          "    series: {ref: D4, reduce: max}\n"),
         "D6 reads D4, which is not an M ref with a promql"),
        (('    series: {ref: M3, per: M2, where: "M2 > 1", reduce: mean}\n',
          "    series: {ref: M3, reduce: max, scale: 2}\n"),
         "series does not take scale"),
    ])
    def test_a_definition_nothing_could_work_out_is_refused(self, change, message):
        with pytest.raises(RegisterError, match=message):
            register(REGISTER.replace(*change, 1))

    def test_formulas_that_read_each_other_in_a_circle_are_refused(self):
        circular = REGISTER.replace("    formula: events.drained_at - events.load_started\n",
                                    "    formula: D5 * 2\n", 1)
        with pytest.raises(RegisterError, match="cycle: D4 -> D5 -> D4"):
            register(circular)

    def test_the_table_shows_each_definition_as_written(self):
        rows = {line.split("|")[1].strip(): line.split("|")[3].strip()
                for line in table_lines(register())[2:]}
        assert rows["D4"] == "`events.drained_at - events.load_started`"
        assert rows["D6"] == "`mean of M3 per M2 where M2 > 1`"
        assert rows["R7"] == "`settings.n`, point record"
        assert rows["R8"] == "written at the end of each run · operator"


class TestDerive:
    def test_a_formula_reads_record_fields_and_other_refs(self, execution):
        steps = derive.explain(register(), "D5", record_path(execution), "n04.point.json")
        assert steps.value == pytest.approx(600 / 150.5)
        assert [(step.name, step.value) for step in steps.inputs] == [
            ("settings.count", 600.0), ("D4", 150.5)]
        assert [step.name for step in steps.inputs[1].inputs] == [
            "events.drained_at", "events.load_started"]

    def test_a_series_reduces_the_export_beside_the_record(self, execution):
        assert derive.derive(register(), "D6", record_path(execution)) == \
            pytest.approx((0.5 / 2 + 2 / 4) / 2)

    def test_a_recorded_setting_stored_as_text_is_a_number(self, execution):
        assert derive.derive(register(), "R7", record_path(execution)) == 4.0

    @pytest.mark.parametrize("ref, message", [
        ("M1", "series exported at every point"),
        ("R8", "written by hand"),
        ("D9", "defines no D9"),
    ])
    def test_a_ref_no_run_data_holds_says_why(self, execution, ref, message):
        with pytest.raises(derive.DeriveError, match=message):
            derive.derive(register(), ref, record_path(execution))

    def test_a_null_field_is_a_gap_not_a_zero(self, execution):
        text = REGISTER.replace("    record: settings.n\n", "    record: gone\n")
        with pytest.raises(derive.DeriveError, match="gap, not a zero"):
            derive.derive(register(text), "R7", record_path(execution))

    def test_a_missing_export_is_named(self, execution):
        record_path(execution).with_name("n04.jsonl").unlink()
        with pytest.raises(derive.DeriveError, match="no export beside"):
            derive.derive(register(), "D6", record_path(execution))


def test_the_register_above_a_run_is_its_executions(execution):
    found = register_above(record_path(execution).parent, execution)
    assert found == execution / "executions" / "01-drain" / "metrics.yaml"
    assert register_above(execution.parent, execution) is None


VALUES = """\
scan:
  - report.md

values:
  drain_n04:
    ref: VD1
    kind: D
    value: 150.5
    from: {file: executions/01-drain/data/n04.point.json, metric: D4}
  rate_n04:
    ref: VD2
    kind: D
    value: 3.987
    from: {file: executions/01-drain/data/n04.point.json, metric: D5}
  service_ms_n04:
    ref: VD3
    kind: D
    value: 375
    from: {file: executions/01-drain/data/n04.point.json, metric: D6, scale: 1000}
"""


def run_values(root: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = values_tool.main(["--path", str(root / "report-values.yaml"), *argv])
    return code, out.getvalue()


class TestValuesReadARef:
    @pytest.fixture
    def report(self, execution):
        (execution / "report-values.yaml").write_text(VALUES)
        (execution / "report.md").write_text("Drained in 150.5(VD1) s.\n")
        return execution

    def test_from_metric_reproduces_the_registers_definition(self, report):
        source = evidence.read_source(
            {"file": "executions/01-drain/data/n04.point.json", "metric": "D6",
             "scale": 1000})
        assert evidence.reproduce(source, report) == pytest.approx(375)

    def test_check_fails_the_moment_a_definition_changes(self, report):
        assert run_values(report, "pull")[0] == 0
        assert run_values(report, "check")[0] == 0
        path = report / "executions" / "01-drain" / "metrics.yaml"
        path.write_text(path.read_text().replace("reduce: mean", "reduce: max"))
        code, out = run_values(report, "check")
        assert code == 1
        assert "service_ms_n04" in out and "DIFFERS" in out

    def test_a_from_metric_counts_as_the_values_metric(self, report):
        code, out = run_values(report, "check")
        assert "metric refs: 3/3 defined" in out

    @pytest.mark.parametrize("raw, message", [
        ({"file": "d/n04.jsonl", "metric": "D4"}, "reads a run's .point.json"),
        ({"file": "d/n04.point.json", "metric": "drain"}, "not a ref"),
        ({"file": "d/n04.point.json", "metric": "D4", "reduce": "max"},
         "does not take reduce"),
        ({"file": "d/n04.point.json", "metric": "D4", "path": "x"}, "not both"),
    ])
    def test_a_from_metric_takes_a_record_and_a_bare_ref(self, raw, message):
        with pytest.raises(evidence.EvidenceError, match=message):
            evidence.read_source(raw)

    def test_a_run_outside_any_execution_names_the_gap(self, tmp_path):
        (tmp_path / "n04.point.json").write_text("{}")
        source = evidence.read_source({"file": "n04.point.json", "metric": "D4"})
        with pytest.raises(evidence.EvidenceError, match="nothing defines D4"):
            evidence.reproduce(source, tmp_path)


class TestKindFollowsTheRef:
    def registry(self, kind: str, metric: str | None = None, read: str = "D4"):
        spec = {"ref": f"V{kind}1", "kind": kind, "value": 1,
                "from": {"file": "d/n04.point.json", "metric": read}}
        if metric:
            spec["metric"] = metric
        return Registry(entries={"x": spec})

    def test_a_value_read_from_a_d_ref_is_derived(self):
        assert validate(self.registry("D"))[0] == []
        problems = validate(self.registry("M"))[0]
        assert any("kind M, but it measures D4" in line for line in problems)

    def test_a_recorded_ref_makes_a_recorded_value(self):
        assert validate(self.registry("R", read="R7"))[0] == []

    def test_metric_and_from_naming_two_refs_is_a_broken_link(self, execution):
        (execution / "report-values.yaml").write_text(
            VALUES.replace("    from: {file: executions/01-drain/data/n04.point.json, metric: D4}\n",
                           "    metric: D5\n    from: {file: executions/01-drain/data/n04.point.json, metric: D4}\n"))
        (execution / "report.md").write_text("\n")
        code, out = run_values(execution, "check")
        assert "its from: works it out as D4" in out


def test_strict_metrics_check_fails_a_derivation_left_in_prose(execution):
    directory = execution / "executions" / "01-drain"
    (directory / "metrics.yaml").write_text(
        REGISTER + "  D9:\n    what: share served\n    source: M1 ÷ offered\n"
        "    status: active\n")
    (directory / "index.md").write_text(
        "<!-- report-kit metrics: generated from metrics.yaml, edit that file -->\n"
        "<!-- /report-kit metrics -->\n")
    assert metrics_tool.main(["write", "--path", str(directory)]) == 0
    with contextlib.redirect_stdout(io.StringIO()) as out:
        assert metrics_tool.main(["check", "--path", str(directory)]) == 0
        assert metrics_tool.main(["check", "--strict", "--path", str(directory)]) == 1
    assert "D9 is derived in prose only" in out.getvalue()


class TestArith:
    def test_dotted_names_are_record_fields_only_where_allowed(self):
        tree = arith.parse("a.b / c")
        assert arith.names(tree, dotted=True) == ["a.b", "c"]
        with pytest.raises(arith.ArithError, match="unsupported expression node Attribute"):
            arith.check(tree)
        assert arith.evaluate(tree, {"a.b": 6.0, "c": 3.0}.__getitem__, dotted=True) == 2.0

    def test_a_marker_that_is_not_a_number_carries_through(self):
        pending = object()
        assert arith.evaluate(arith.parse("-a + 2"), lambda name: pending) is pending


def test_a_window_keeps_its_length_at_full_precision():
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    window = Window(start, start + timedelta(seconds=59.64))
    assert window.to_dict()["seconds"] == pytest.approx(59.64)
