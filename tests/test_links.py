"""A value's `metric:` names the register ref that defines what it measures,
and `report-kit values check` fails when that execution's register has no
such ref.

    pytest tests/test_links.py

Every name and number here is invented.
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from report_kit.tools import values as values_tool

REGISTER = """\
metrics:
  M1:
    what: served rate
    promql: sum(rate(requests_total[30s]))
    status: unconfirmed
  D2:
    what: served share
    source: M1 ÷ offered
    status: active
"""


def registry(served: str = "M1", offered: str = "00-baseline/D2") -> str:
    return f"""\
scan:
  - report.md

values:
  served:
    ref: VM1
    kind: M
    value: 5
    from: {{file: executions/00-baseline/data/r1.point.json, path: served}}
    metric: {served}

  offered:
    ref: VR1
    kind: R
    value: 1
    source: an invented setting
    metric: {offered}
"""


@pytest.fixture
def report(tmp_path):
    baseline = tmp_path / "executions" / "00-baseline"
    (baseline / "data").mkdir(parents=True)
    (baseline / "metrics.yaml").write_text(REGISTER)
    (baseline / "data" / "r1.point.json").write_text(json.dumps({"served": 5}))
    (tmp_path / "report.md").write_text("nothing marked\n")

    def write(**metrics):
        path = tmp_path / "report-values.yaml"
        path.write_text(registry(**metrics))
        return path
    return write


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = values_tool.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def test_a_bare_ref_and_a_cited_one_both_resolve(report):
    code, out = run("--path", str(report()), "check")
    assert code == 0 and "metric refs: 2/2" in out


@pytest.mark.parametrize("metrics, problem", [
    ({"served": "M9"}, "defines no M9"),
    ({"offered": "01-load/D2"}, "no metrics.yaml in 01-load"),
    ({"offered": "D2"}, "a bare ref needs a from:"),
])
def test_a_ref_its_execution_does_not_define_fails_the_check(report, metrics, problem):
    code, out = run("--path", str(report(**metrics)), "check")
    assert code == 1 and problem in out


def test_a_malformed_metric_fails_validate(report):
    code, out = run("--path", str(report(served="M")), "validate")
    assert code == 1 and "metric 'M' is not a ref" in out
