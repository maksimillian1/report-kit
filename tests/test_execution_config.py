"""execution.yaml: when a point's window closes, and what makes the point
valid — its own rules, and the guards a runner evaluates.

    pytest tests/test_execution_config.py

Every name and number here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from report_kit.execution_config import (ExecutionError, IdleTarget, parse_execution,
                                         run_guards)
from report_kit.register import parse_register

REGISTER = parse_register("""\
metrics:
  M1:
    what: serving instances
    promql: count(up{job="api"} == 1)
    status: unconfirmed
  D2:
    what: served share
    source: M1 ÷ offered
    status: active
""", Path("x/metrics.yaml"))

EXECUTION_TEXT = """\
window_closes_when_back_to_idle:
  api:
    idle_replicas: 1
    max_replicas: 10
  cache:
    idle_replicas: 0

point_validity_guards:
  G1:
    min: 1
    metric: M1
  G2:
    min: 0.9
    max: 1.1
    promql: sum(rate(requests_total[1m])) / {rate}
  G3:
    min: '{count}'
    promql: max(enqueued_total)
"""


def execution(text: str = EXECUTION_TEXT):
    return parse_execution(text, Path("x/execution.yaml"), REGISTER)


def test_the_window_names_each_deployment_and_its_bounds():
    assert execution().window_closes_when_back_to_idle == (
        IdleTarget("api", 1, 10), IdleTarget("cache", 0))


def test_a_guard_naming_a_metric_reuses_its_query():
    first = execution().point_validity_guards[0]
    assert (first.metric, first.promql) == ("M1", 'count(up{job="api"} == 1)')


def test_guards_with_the_runs_own_arguments_filled_in():
    assert run_guards(execution(), {"rate": 24, "count": 400}) == [
        {"ref": "G1", "query": 'count(up{job="api"} == 1)', "min": 1.0},
        {"ref": "G2", "query": "sum(rate(requests_total[1m])) / 24",
         "min": 0.9, "max": 1.1},
        {"ref": "G3", "query": "max(enqueued_total)", "min": 400.0}]


def test_a_placeholder_the_run_does_not_fill_is_named():
    with pytest.raises(ExecutionError, match=r"G2 names \{rate\}, which this run does not fill"):
        run_guards(execution(), {"count": 400})


def test_both_sections_are_optional():
    empty = execution("")
    assert empty.window_closes_when_back_to_idle == () and empty.point_validity_guards == ()


@pytest.mark.parametrize("change, message", [
    (("  cache:\n    idle_replicas: 0\n", "  cache: {}\n"), "idle_replicas must be a whole number"),
    (("    idle_replicas: 0\n", "    idle_replicas: -1\n"), "idle_replicas must be a whole number"),
    (("    idle_replicas: 0\n", "    idle_replicas: true\n"), "idle_replicas must be a whole number"),
    (("    max_replicas: 10\n", "    max_replicas: 1\n"), "max_replicas 1 is not above"),
    (("    idle_replicas: 0\n", "    floor: 0\n"), "unknown key 'floor'"),
    (("    metric: M1\n", "    metric: D2\n"), "D2 is not an M ref with a promql"),
    (("    metric: M1\n", "    metric: M9\n"), "M9 is not an M ref with a promql"),
    (("    metric: M1\n", "    metric: M1\n    promql: up\n"), "exactly one of metric"),
    (("    min: 1\n    metric: M1\n", "    metric: M1\n"), "needs min, max or both"),
    (("    min: '{count}'\n", "    min: many\n"), "neither a number nor"),
    (("  G3:\n", "  G1:\n"), "appears twice"),
    (("  G3:\n", "  G0:\n"), "is not G followed by a number"),
    (("point_validity_guards:\n", "guards: {}\npoint_validity_guards:\n"),
     "unknown section 'guards'"),
])
def test_a_broken_execution_yaml_is_refused_with_the_reason(change, message):
    with pytest.raises(ExecutionError, match=message):
        execution(EXECUTION_TEXT.replace(*change, 1))
