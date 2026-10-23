"""`report-kit values trace`: a value followed from the documents that print it
to the run data that produce it.

    pytest tests/test_trace.py

Every name and number here is invented.
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from report_kit.tools import values as values_tool
from test_derive import EXPORT, RECORD, REGISTER, VALUES


@pytest.fixture
def report(tmp_path):
    data = tmp_path / "executions" / "01-drain" / "data"
    data.mkdir(parents=True)
    (tmp_path / "executions" / "01-drain" / "metrics.yaml").write_text(REGISTER)
    (data / "n04.point.json").write_text(json.dumps(RECORD))
    (data / "n04.jsonl").write_text("\n".join(json.dumps(line) for line in EXPORT) + "\n")
    (tmp_path / "report-values.yaml").write_text(
        VALUES + "  per_worker:\n    ref: VD4\n    kind: D\n    formula: rate_n04 / 4\n"
        "  workers:\n    ref: VR1\n    kind: R\n    value: 4\n"
        "    source: the pool ceiling, read off the manifest\n")
    (tmp_path / "report.md").write_text("Drained in 150.5(VD1) s.\n\n| rate | 3.99`(VD2)` |\n")
    return tmp_path


def trace(report, wanted: str) -> list[str]:
    path = str(report / "report-values.yaml")
    with contextlib.redirect_stdout(io.StringIO()):
        assert values_tool.main(["--path", path, "pull"]) == 0
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = values_tool.main(["--path", path, "trace", wanted])
    assert code == 0, out.getvalue()
    return out.getvalue().splitlines()


def test_a_derived_value_is_followed_down_to_the_record_fields(report):
    lines = trace(report, "VD2")
    assert any("printed in report.md:3 (3.99)" in line for line in lines)
    assert any("D5 (drain rate) of executions/01-drain/data/n04.point.json, as "
               "executions/01-drain/metrics.yaml defines it" in line for line in lines)
    assert any("D5 = 3.98671  ← settings.count / D4" in line for line in lines)
    assert any("D4 = 150.5  ← events.drained_at - events.load_started" in line
               for line in lines)
    assert any("events.load_started = 1000  ← record" in line for line in lines)


def test_a_formula_over_values_traces_each_input(report):
    lines = trace(report, "per_worker")
    assert lines[0].startswith("VD4 per_worker = 1.00ᴰ")
    assert any("formula rate_n04 / 4" in line for line in lines)
    assert any("VD2 rate_n04 = 3.99ᴰ" in line for line in lines)


def test_a_hand_recorded_value_ends_at_its_source(report):
    lines = trace(report, "workers")
    assert "printed in no scanned document" in lines[-2]
    assert lines[-1].endswith("source: the pool ceiling, read off the manifest")


def test_an_unknown_value_is_a_usage_error(report):
    with contextlib.redirect_stderr(io.StringIO()):
        assert values_tool.main(["--path", str(report / "report-values.yaml"),
                                 "trace", "nope"]) == 2
