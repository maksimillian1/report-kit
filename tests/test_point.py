"""A point's live phase built from the library, and everything after its
window closes: `execution.yaml`'s `point:`, the command line it makes, the
watch, and `report-kit point finish` on a record.

    pytest tests/test_point.py

Every name and number here is invented. The cluster and Prometheus are the
three `shell` seams, patched; `report-kit selftest` drives the same code
through both runner templates.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from report_kit import finish, launch, point as points, watch
from report_kit.constants import EXIT_CLEAN, EXIT_EXPORT_GAP, EXIT_SUSPECT
from report_kit.execution_config import (ExecutionError, PointPlan, Setting,
                                         parse_execution)
from report_kit.register import parse_register
from report_kit.tools import point as point_tool
from report_kit.tools.values.points import record_fields, validity_problems

REGISTER_TEXT = """\
metrics:
  M1:
    what: requests
    promql: sum(rate(requests_total[1m]))
    status: unconfirmed
  D2:
    what: peak request rate
    series: {ref: M1, reduce: max}
    status: active
  R3:
    what: offered rate
    record: settings.rate
    status: active
  D4:
    what: seconds to empty the queues per unit offered
    formula: (events.queues_empty - events.load_started) / R3
    status: active
"""
REGISTER = parse_register(REGISTER_TEXT, Path("x/metrics.yaml"))

API = PointPlan(settings=(Setting("rate"), Setting("duration", "10m")))


def execution(text: str):
    return parse_execution(text, Path("x/execution.yaml"), REGISTER)


class TestPlan:
    def test_execution_yaml_replaces_the_profiles_defaults_key_by_key(self):
        plan = execution("point:\n  hold_seconds: 5\n  freeze: [deployment/api]\n"
                         "  settings: {rate: {}, warmup: {default: 30s}}\n").plan(API)
        assert plan.hold_seconds == 5.0
        assert plan.freeze == ("deployment/api",)
        assert plan.settings == (Setting("rate"), Setting("warmup", "30s"))
        assert (plan.load, plan.guards_at, plan.step) == ("foreground", "load_end", "15s")

    def test_without_a_point_section_the_profile_decides(self):
        assert execution("").plan(API) == API

    @pytest.mark.parametrize("text, message", [
        ("point: {load: sideways}", "not one of foreground, background"),
        ("point: {guards_at: now}", "not one of load_end, window_end"),
        ("point: {hold_seconds: 0}", "positive number"),
        ("point: {freeze: [api]}", "kind/name"),
        ("point: {step: fast}", "Prometheus resolution"),
        ("point: {settings: {Rate: {}}}", "lowercase"),
        ("point: {settings: {rate: {max: 3}}}", "unknown key 'max'"),
        ("point: {retries: 3}", "unknown key 'retries'"),
    ])
    def test_a_plan_nothing_could_run_is_refused(self, text, message):
        with pytest.raises(ExecutionError, match=message):
            execution(text)


@pytest.fixture
def execution_dir(tmp_path):
    (tmp_path / "metrics.yaml").write_text(REGISTER_TEXT)
    (tmp_path / "execution.yaml").write_text(
        "point:\n  settings: {rate: {}, duration: {default: 10m}}\n"
        "point_validity_guards:\n  G1: {min: '{rate}', promql: sum(served)}\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "env.yaml").write_text(
        "namespace: app\npoll_seconds: 0.01\nmax_wait_seconds: 5\n"
        "prometheus: {url: 'http://prom'}\n"
        "generator: {command: [k6, run, '--rate={rate}', '--for={duration}', "
        "'--out={summary}']}\n")
    return scripts


class TestCommandLine:
    def test_each_setting_is_a_flag_and_fills_the_load_and_the_guards(self, execution_dir):
        point = points.open_point(execution_dir, "api", API, "", ["--run", "r24", "--rate", "24"])
        assert point.settings == {"rate": "24", "duration": "10m"}
        command, _, log = launch.load_command(point, "generator")
        assert command[2:4] == ["--rate=24", "--for=10m"]
        assert command[4].endswith("data/r24.summary.json")
        assert log.name == "r24.generator.log"
        assert points.require_settings(point) == [
            {"ref": "G1", "query": "sum(served)", "min": 24.0}]

    def test_a_measured_point_without_its_settings_stops_before_any_load(self, execution_dir):
        point = points.open_point(execution_dir, "api", API, "", ["--run", "r24"])
        with pytest.raises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            points.require_settings(point)
        assert "--run and --rate are required" in err.getvalue()

    def test_a_setting_cannot_take_a_runner_flags_name(self, execution_dir):
        (execution_dir.parent / "execution.yaml").write_text("point:\n  settings: {force: {}}\n")
        with pytest.raises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            points.open_point(execution_dir, "api", API, "", ["--run", "x"])


def watched_with(states: list[dict], load: str, require_busy=None, events=None):
    plan = PointPlan(load=load, hold_seconds=0.03)
    stub = SimpleNamespace(plan=plan, env=SimpleNamespace(poll_seconds=0.01, max_wait_seconds=2))
    readings = iter(states)
    last = states[-1]
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with contextlib.redirect_stdout(io.StringIO()):
        return watch.watch(stub, lambda: next(readings, last),
                           lambda state: state["queue"] == 0, start,
                           require_busy=require_busy, events=events)


class TestWatch:
    def test_a_background_load_never_closes_on_a_system_not_yet_busy(self):
        idle_then_busy = [{"queue": 0}] * 5 + [{"queue": 7}, {"queue": 9}] + [{"queue": 0}]
        watched = watched_with(idle_then_busy, "background",
                               events={"drained": lambda state: state["queue"] == 0})
        assert watched.window is not None
        assert watched.peaks == {"queue": 9.0}
        assert set(watched.events) == {"drained"}

    def test_a_foreground_load_closes_on_the_first_held_rest(self):
        watched = watched_with([{"queue": 0}], "foreground")
        assert watched.window is not None and watched.peaks == {"queue": 0.0}

    def test_a_system_that_never_rests_times_out(self):
        stub_states = [{"queue": 1}]
        plan = PointPlan(hold_seconds=0.02)
        stub = SimpleNamespace(plan=plan, env=SimpleNamespace(poll_seconds=0.01,
                                                              max_wait_seconds=0.1))
        with contextlib.redirect_stdout(io.StringIO()):
            watched = watch.watch(stub, lambda: stub_states[0], lambda s: False,
                                  datetime.now(timezone.utc))
        assert watched.window is None


RECORD = {
    "run": "r24",
    "profile": "api",
    "settings": {"rate": "24", "duration": "10m"},
    "window": {"start": "2026-01-02T00:00:00Z", "end": "2026-01-02T00:02:00Z", "seconds": 120.4},
    "load": {"exit": 0, "window": None},
    "events": {"load_started": 1767312000.0, "load_finished": 1767312060.5,
               "window_closed": 1767312120.4, "queues_empty": 1767312030.0},
    "observations": {"peaks": {"tiers.api": 4.0}, "ceilings_reached": []},
    "doubts": [],
    "plan": {"step": "5s", "guards_at": "load_end"},
    "queries": {"M1": "sum(rate(requests_total[1m]))"},
    "guards": [{"ref": "G1", "query": "sum(errors)", "max": 5.0}],
    "commit": "a" * 40,
}


class Prometheus:
    """Answers the export and the guards the way a server would, and keeps
    the instant each guard was read as of."""

    def __init__(self, series: list | None = None, guard: str = "1"):
        self.series = [{"metric": {}, "values": [[1767312000, "3"], [1767312060, "8"]]}] \
            if series is None else series
        self.guard = guard
        self.asked_at: list[float] = []

    def http_json(self, method, url, body=None, timeout=30):
        if "/api/v1/query_range" in url:
            return {"status": "success", "data": {"result": self.series}}
        self.asked_at.append(float(url.split("time=")[1].split("&")[0]))
        return {"status": "success", "data": {"result": [
            {"metric": {}, "value": [0, self.guard]}]}}


def finished(tmp_path: Path, prometheus: Prometheus, record: dict = RECORD,
             force: bool = False) -> tuple[int, Path]:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    path = data / "r24.point.json"
    if not path.exists():
        path.write_text(json.dumps(record))
    with patch("report_kit.shell.http_json", prometheus.http_json), \
            contextlib.redirect_stdout(io.StringIO()):
        code = finish.finish_point(path, "http://prom", REGISTER, force=force)
    return code, path


class TestFinish:
    def test_a_clean_point_exports_reads_its_guards_and_works_out_the_register(self, tmp_path):
        prometheus = Prometheus()
        code, path = finished(tmp_path, prometheus)
        assert code == EXIT_CLEAN
        record = json.loads(path.read_text())
        assert record["guard_values"] == {"G1": 1.0}
        assert record["export"]["series"] == 1
        assert prometheus.asked_at == [1767312060.5]
        block = path.with_name("r24.point.md").read_text()
        assert "| D2 | peak request rate | 8 |" in block
        assert "| R3 | offered rate | 24 |" in block
        assert "| D4 | seconds to empty the queues per unit offered | 1.25 |" in block
        assert "| peaks | tiers.api=4 |" in block

    def test_guards_at_window_end_read_as_of_the_close(self, tmp_path):
        prometheus = Prometheus()
        finished(tmp_path, prometheus, {**RECORD, "plan": {"guards_at": "window_end"}})
        assert prometheus.asked_at == [1767312120.4]

    def test_an_empty_ref_is_an_export_gap(self, tmp_path):
        code, _ = finished(tmp_path, Prometheus(series=[]))
        assert code == EXIT_EXPORT_GAP

    @pytest.mark.parametrize("change", [{"doubts": ["generator exited 1"]}, {}])
    def test_a_doubt_or_a_breached_guard_is_suspect(self, tmp_path, change):
        guard = "1" if change else "9"
        code, _ = finished(tmp_path, Prometheus(guard=guard), {**RECORD, **change})
        assert code == EXIT_SUSPECT

    def test_a_gap_in_the_data_is_named_in_the_block_not_raised(self, tmp_path):
        record = {**RECORD, "settings": {"duration": "10m"}}
        code, path = finished(tmp_path, Prometheus(), record)
        assert "| R3 | offered rate | gap — " in path.with_name("r24.point.md").read_text()

    def test_it_runs_again_on_the_record_and_will_not_overwrite_an_export(self, tmp_path):
        finished(tmp_path, Prometheus())
        with pytest.raises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            finished(tmp_path, Prometheus())
        assert finished(tmp_path, Prometheus(), force=True)[0] == EXIT_CLEAN

    def test_the_command_finds_the_register_and_env_from_the_record(self, tmp_path):
        (tmp_path / "metrics.yaml").write_text(REGISTER_TEXT)
        (tmp_path / "env.yaml").write_text("namespace: app\nprometheus: {url: 'http://prom'}\n")
        data = tmp_path / "data"
        data.mkdir()
        (data / "r24.point.json").write_text(json.dumps(RECORD))
        with patch("report_kit.shell.http_json", Prometheus().http_json), \
                contextlib.redirect_stdout(io.StringIO()):
            code = point_tool.main(["finish", str(data / "r24.point.json"), "--no-port-forward"])
        assert code == EXIT_CLEAN
        assert (data / "r24.point.md").is_file()


def test_a_record_from_before_events_is_exported_over_its_window():
    legacy = {key: value for key, value in RECORD.items() if key != "events"}
    window = finish.window_of(legacy)
    assert window.seconds == 120


class TestTheRegistryReadsTheRecord:
    def test_settings_are_fields_a_points_template_can_name(self):
        fields = record_fields({"run": "r24", "settings": {"rate": "24"}})
        assert fields["rate"] == 24

    def test_a_point_in_doubt_is_not_a_valid_point(self):
        assert validity_problems({"doubts": ["node lost"]}) == ["doubts: node lost"]
