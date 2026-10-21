"""`report-kit export-metrics --record` re-exports a window from the point
record alone: its run id, its window and the queries the runner exported.

    pytest tests/test_export_metrics.py

The run, its queries and its window are invented.
"""

from __future__ import annotations

import json
import sys

import pytest

from report_kit import prometheus
from report_kit.tools import export_metrics

RECORD = {"run": "r24", "window": {"start": "2026-01-02T10:00:00Z",
                                   "end": "2026-01-02T10:01:30Z", "seconds": 90.0},
          "queries": {"M4": "count(up == 1)", "M5": "sum(rate(requests_total[30s]))"}}


@pytest.fixture
def exported(monkeypatch):
    calls = []

    def export_range(prom_url, series, window, *, out_dir, run_id, step, force):
        calls.append({"series": series, "window": window, "out_dir": out_dir,
                      "run_id": run_id})
        return prometheus.Export(path=out_dir / f"{run_id}.jsonl",
                                 meta_path=out_dir / f"{run_id}.meta.json")
    monkeypatch.setattr(prometheus, "export_range", export_range)
    return calls


def test_the_record_names_the_run_the_window_and_the_queries(tmp_path, exported):
    record = tmp_path / "data" / "r24.point.json"
    record.parent.mkdir()
    record.write_text(json.dumps(RECORD))
    assert export_metrics.main(["--record", str(record), "--prom-url", "http://p"]) == 0
    (call,) = exported
    assert call["run_id"] == "r24" and call["out_dir"] == record.parent
    assert call["series"] == [["M4", "count(up == 1)"],
                              ["M5", "sum(rate(requests_total[30s]))"]]
    assert call["window"].seconds == 90.0


def test_a_record_written_before_0_4_points_at_queries(tmp_path, exported, capsys):
    record = tmp_path / "r24.point.json"
    record.write_text(json.dumps({k: v for k, v in RECORD.items() if k != "queries"}))
    with pytest.raises(SystemExit):
        export_metrics.main(["--record", str(record), "--prom-url", "http://p"])
    assert "pass --queries series.txt" in capsys.readouterr().err
    assert not exported


def test_the_pipe_file_path_still_works_for_an_older_execution(tmp_path, exported):
    series = tmp_path / "series.txt"
    series.write_text("M4|count(up == 1)\n")
    code = export_metrics.main(["--run", "old", "--queries", str(series), "--last", "5m",
                                "--prom-url", "http://p", "--out-dir", str(tmp_path)])
    assert code == 0 and exported[0]["series"] == [["M4", "count(up == 1)"]]


def test_it_still_loads_without_pyyaml(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)
    from report_kit.cli import main
    with pytest.raises(SystemExit) as stopped:
        main(["export-metrics", "--help"])
    assert stopped.value.code == 0
