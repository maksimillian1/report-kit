"""What each guard read, kept next to the verdict.

    pytest tests/test_guards.py

The guards and their readings are invented for these tests.
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from report_kit import prometheus

GUARDS = [
    {"ref": "G1", "query": "sum(errors_total)", "max": 5},
    {"ref": "G2", "query": "sum(absent_total)", "min": 1},
    {"ref": "G3", "query": "sum(retries_total)", "max": 2},
]
READINGS = {"sum(errors_total)": "3", "sum(retries_total)": "4"}


def answer(method, url, body=None, timeout=30):
    query = parse_qs(urlparse(url).query)["query"][0]
    found = [{"metric": {}, "value": [0, READINGS[query]]}] if query in READINGS else []
    return {"status": "success", "data": {"result": found}}


def test_every_guard_keeps_what_it_read_and_a_gap_reads_none():
    with patch("report_kit.shell.http_json", answer):
        result = prometheus.evaluate_guards("http://prom", GUARDS)
    assert result.values == {"G1": 3.0, "G2": None, "G3": 4.0}
    assert result.failures == ["G2", "G3"]


def test_check_guards_still_returns_only_the_failures():
    with patch("report_kit.shell.http_json", answer):
        assert prometheus.check_guards("http://prom", GUARDS) == ["G2", "G3"]
