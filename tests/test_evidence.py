"""Reading a figure's value back out of a run's data files.

    pytest tests/test_evidence.py

The run, its refs and its numbers are invented for these tests.
"""

from __future__ import annotations

import json

import pytest

from report_kit import evidence, jsonl
from report_kit.evidence import EvidenceError, MissingEvidence

POINT = {
    "rate": "24",
    "client": {"failed_share": 0.0022, "p95_ms": 97.6},
    "gone": None,
    "clean": True,
}

EXPORT = [
    {"metric": "M1", "result": [{"metric": {}, "values": [
        [1, "3"], [2, "9"], [3, "NaN"], [4, "5"]]}]},
    {"metric": "M5", "result": [{"metric": {}, "values": [
        [1, "0.5"], [2, "2"], [3, "4"], [4, "0"]]}]},
    {"metric": "M7", "result": [
        {"metric": {"pod": "a"}, "values": [[1, "1"], [2, "2"], [3, "6"], [4, "1"]]},
        {"metric": {"pod": "b"}, "values": [[1, "0"], [2, "2"], [3, "6"], [4, "1"]]}]},
    {"metric": "M9", "result": []},
]


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "r1.point.json").write_text(json.dumps(POINT))
    (tmp_path / "data" / "r1.jsonl").write_text(
        "\n".join(json.dumps(line) for line in EXPORT) + "\n")
    return tmp_path


def value(root, **raw):
    return evidence.reproduce(evidence.read_source(raw), root)


def from_export(root, **raw):
    return value(root, file="data/r1.jsonl", **raw)


class TestPointRecord:
    def test_a_dotted_path_reads_a_nested_key(self, root):
        assert value(root, file="data/r1.point.json",
                     path="client.p95_ms") == 97.6

    def test_a_number_stored_as_a_string_is_a_number(self, root):
        assert value(root, file="data/r1.point.json", path="rate") == 24.0

    def test_scale_turns_a_share_into_a_percent(self, root):
        assert value(root, file="data/r1.point.json",
                     path="client.failed_share", scale=100) == pytest.approx(0.22)

    @pytest.mark.parametrize("path, message", [
        ("gone", "null — a gap, not a zero"),
        ("clean", "not a number"),
        ("client", "a dict, not a number"),
        ("client.nope", "no client.nope"),
        ("rate.deeper", "no rate.deeper"),
    ])
    def test_what_is_not_a_number_is_refused(self, root, path, message):
        with pytest.raises(EvidenceError, match=message):
            value(root, file="data/r1.point.json", path=path)

    def test_a_data_file_that_is_not_there_is_its_own_error(self, root):
        with pytest.raises(MissingEvidence, match="no such data file"):
            value(root, file="data/r9.point.json", path="rate")


class TestExport:
    @pytest.mark.parametrize("reduce, expected", [
        ("max", 9), ("min", 3), ("last", 5), ("mean", 17 / 3)])
    def test_reductions_skip_a_sample_that_is_not_a_number(self, root, reduce,
                                                           expected):
        assert from_export(root, ref="M1", reduce=reduce) == pytest.approx(expected)

    def test_several_series_and_no_across_is_refused_not_summed(self, root):
        with pytest.raises(EvidenceError,
                           match=r"M7 holds 2 series \(pod=a; pod=b\) .* across:"):
            from_export(root, ref="M7", reduce="max")

    @pytest.mark.parametrize("across, expected", [
        ("sum", 19 / 4), ("max", 10 / 4), ("min", 9 / 4), ("mean", 9.5 / 4)])
    def test_across_combines_the_series_at_each_timestamp(self, root, across,
                                                          expected):
        assert from_export(root, ref="M7", across=across,
                           reduce="mean") == pytest.approx(expected)

    def test_per_divides_sample_by_sample_where_masks_and_scale_multiplies(
            self, root):
        assert from_export(root, ref="M7", across="sum", per="M5",
                           where="M5 > 1", reduce="mean",
                           scale=1000) == pytest.approx(2500)

    @pytest.mark.parametrize("where, reduce, expected", [
        ("M5 >= 2", "min", 9), ("M5 < 2", "max", 5), ("M5<=2", "mean", 17 / 3)])
    def test_every_comparison_masks(self, root, where, reduce, expected):
        assert from_export(root, ref="M1", where=where,
                           reduce=reduce) == pytest.approx(expected)

    def test_dividing_by_a_zero_sample_asks_for_a_mask(self, root):
        with pytest.raises(EvidenceError, match="M5 is 0 .* where:"):
            from_export(root, ref="M7", across="sum", per="M5", reduce="mean")

    @pytest.mark.parametrize("raw", [
        {"ref": "M9", "reduce": "max"},
        {"ref": "M1", "where": "M5 > 100", "reduce": "max"},
    ])
    def test_no_samples_is_a_gap_not_a_zero(self, root, raw):
        with pytest.raises(EvidenceError, match="a gap, not a zero"):
            from_export(root, **raw)

    def test_a_ref_the_export_never_held_is_named(self, root):
        with pytest.raises(EvidenceError, match="holds no ref M4"):
            from_export(root, ref="M4", reduce="max")

    def test_a_line_that_is_not_json_is_named_rather_than_exiting(self, root):
        (root / "data" / "r1.jsonl").write_text('{"metric": "M1"}\nnot json\n')
        with pytest.raises(EvidenceError, match="r1.jsonl:2 not valid JSON"):
            from_export(root, ref="M1", reduce="max")


class TestReadSource:
    @pytest.mark.parametrize("raw, message", [
        ("data/r1.jsonl", "must be a mapping"),
        ({"file": "f", "path": "p", "ref": "M1"}, "not both"),
        ({"file": "f"}, "needs path: .* or ref:"),
        ({"path": "p"}, "needs file:"),
        ({"file": "f", "path": "p", "reduce": "max"}, "does not take reduce"),
        ({"file": "f", "ref": "M1"}, "needs reduce:"),
        ({"file": "f", "ref": "M1", "reduce": "median"}, "not one of"),
        ({"file": "f", "ref": "M1", "reduce": "max", "across": "last"},
         "across 'last' is not one of"),
        ({"file": "f", "path": "p", "across": "sum"}, "does not take across"),
        ({"file": "f", "ref": "M1", "reduce": "max", "where": "M5 ~ 1"},
         "is not '<ref> <op> <number>'"),
        ({"file": "f", "ref": "M1", "reduce": "max", "where": "M5 > high"},
         "not a number"),
        ({"file": "f", "path": "p", "scale": "100"}, "scale must be a number"),
        ({"file": "f", "path": "p", "scale": True}, "scale must be a number"),
    ])
    def test_it_refuses_anything_outside_the_two_shapes(self, raw, message):
        with pytest.raises(EvidenceError, match=message):
            evidence.read_source(raw)

    def test_it_reads_both_shapes(self):
        assert evidence.read_source({"file": "f", "path": "a.b"}) == \
            evidence.PointSource("f", "a.b")
        assert evidence.read_source(
            {"file": "f", "ref": "M7", "per": "M5", "where": "M5 > 1",
             "reduce": "mean", "scale": 1000, "across": "sum"}) == \
            evidence.ExportSource("f", "M7", "mean", "M5",
                                  evidence.Mask("M5", ">", 1.0), 1000.0, "sum")


@pytest.mark.parametrize("stored, found, same", [
    (0.22, 0.0022 * 100, True),
    (0, 0.0, True),
    (72.0, 71.9664268448005, False),
    (1070, 1070.0, True),
])
def test_agrees_forgives_float_noise_and_nothing_else(stored, found, same):
    assert evidence.agrees(stored, found) is same


def test_read_lines_raises_where_load_lines_would_exit(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\n{oops\n")
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        jsonl.read_lines(path)
    with pytest.raises(SystemExit):
        jsonl.load_lines(path)
