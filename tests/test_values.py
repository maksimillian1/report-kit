"""The registry's arithmetic, its marks, its file surgery, and the command's
exit codes.

    pytest tests/test_values.py

`report-kit values check` is what a report runs; this proves the checker
itself still works. Every failure that depends on a registry's contents must
arrive as `RegistryError`, so `pytest.raises` asserts the message too.
"""

from __future__ import annotations

import contextlib
import copy
import io
import pickle
from pathlib import Path

import pytest

from report_kit.tools import values as values_tool
from report_kit.tools.values import RegistryError, Registry


def fig(ref, **spec):
    """A value spec: kind comes from the ref, leaves get a source."""
    return {"ref": ref, "kind": ref[1], "source": "s", **spec}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = values_tool.main(list(argv))
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 2
    return code, out.getvalue(), err.getvalue()


MARKS = {
    "price": fig("VR12", value=552.91),
    "total": fig("VD7", formula="price + 0.92"),
    "rate": fig("VM9", value=0.2195, display=4),
    "later": fig("VE4", pending=True),
}

REGISTRY_TEXT = """\
scan:
  - report.md

values:
  alpha:
    ref: VM1
    kind: M
    value: 10
    source: a measurement

  beta:
    ref: VM2
    kind: M
    value: 4
    source: another measurement

  total:
    ref: VD1
    kind: D
    formula: alpha + beta
    appears_in:
      - report.md

retired: []
"""

RETIRED = ({"pattern": "$19,460", "replaced_by": "total",
            "why": "superseded"},)


@pytest.fixture
def registry_file(tmp_path):
    def write(text=REGISTRY_TEXT):
        path = tmp_path / values_tool.registry.REGISTRY
        path.write_text(text)
        return path
    return write


@pytest.fixture
def marks_in(tmp_path):
    def check(*lines):
        (tmp_path / "doc.md").write_text("\n".join(lines) + "\n")
        registry = Registry(MARKS, root=tmp_path, scan=("doc.md",))
        return values_tool.checks.check_marks(registry, registry.resolve(),
                                   registry.documents())
    return check


@pytest.fixture
def coded(tmp_path):
    (tmp_path / "doc.md").write_text(
        "prose says $553.83<!--VD7-->\n"
        "```bash\n"
        "curl 'price=$19,460' # 552.92<!--VR12-->\n"
        "```\n"
        "a threshold of `$0.75` per call\n"
        "~~~\n"
        "$4,242\n"
        "~~~\n")
    registry = Registry(MARKS, root=tmp_path, scan=("doc.md",),
                        retired=({"pattern": "$19,460",
                                  "replaced_by": "total"},))
    return tmp_path, registry, registry.resolve()


@pytest.fixture
def report(tmp_path):
    (tmp_path / "report.md").write_text(
        "the total is 14.00 and the share is 92 %\n"
        "an old number $19,460 still here\n")
    figures_map = {
        "total": fig("VD1", formula="10 + 4", appears_in=["report.md"]),
        "share": fig("VD2", formula="92", display=0, appears_in=["report.md"]),
        "absent": fig("VD3", formula="77", appears_in=["report.md"]),
        "nofile": fig("VD4", formula="1", appears_in=["nowhere.md"]),
    }
    return lambda **over: Registry(figures_map, root=tmp_path,
                                   scan=("report.md",), **over)


@pytest.fixture
def scanned(tmp_path):
    (tmp_path / "report.md").write_text("552.91<!--VR12-->\n")
    (tmp_path / "execution.md").write_text("0.2195<!--VM9-->\n")
    (tmp_path / "notes.txt").write_text("552.91<!--VR12-->\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text("552.91<!--VR12-->\n")
    return tmp_path


@pytest.fixture
def reported(registry_file, tmp_path):
    path = registry_file()
    (tmp_path / "report.md").write_text("the total is 14.00<!--VD1-->\n")
    return tmp_path, ["--path", str(path)]


@pytest.fixture
def loud(registry_file, tmp_path):
    path = registry_file(
        "scan:\n  - report.md\n\n"
        "values:\n"
        "  total:\n    ref: VD1\n    kind: D\n    formula: 10 + 4\n"
        "  guess:\n    ref: VE1\n    kind: E\n    value: 2\n"
        "    source: an estimate\n"
        "  over:\n    ref: VD2\n    kind: D\n    formula: guess * 2\n"
        "  solo:\n    ref: VM1\n    kind: M\n    value: 5\n"
        "    source: s\n    group: totals\n"
        "  stray:\n    ref: VM2\n    kind: M\n    value: 1\n\n"
        'retired:\n  - pattern: "$19,460"\n    replaced_by: total\n'
        "    why: superseded\n")
    (tmp_path / "report.md").write_text("an old number $19,460 and $7.25 too\n")
    return ["--path", str(path)]


class TestRoundsTo:
    @pytest.mark.parametrize("shown, value, matches", [
        ("554", 553.83, True),
        ("553.8", 553.83, True),
        ("553.83", 553.83, True),
        ("553.830", 553.83, True),
        ("552.91", 553.83, False),
        ("553.9", 553.83, False),
        ("1,200", 1200.0, True),
        ("-3.5", -3.5, True),
        ("0", 0.0, True),
        ("abc", 1.0, False),
        ("", 1.0, False),
        ("1", values_tool.registry.PENDING, False),
    ])
    def test_a_figure_matches_every_legal_rendering_of_itself(
            self, shown, value, matches):
        assert values_tool.checks.rounds_to(shown, value) is matches

    @pytest.mark.parametrize("shown, value, matches", [
        ("2", 2.5, True), ("3", 2.5, False),
        ("4", 3.5, True), ("3", 3.5, False)])
    def test_ties_round_half_to_even(self, shown, value, matches):
        assert values_tool.checks.rounds_to(shown, value) is matches


class TestResolve:
    def test_the_four_operators_and_a_literal(self):
        values = Registry({
            "a": fig("VM1", value=10),
            "b": fig("VM2", value=4),
            "sum": fig("VD1", formula="a + b"),
            "diff": fig("VD2", formula="a - b"),
            "prod": fig("VD3", formula="a * b"),
            "quot": fig("VD4", formula="a / b"),
            "neg": fig("VD5", formula="-a"),
            "nested": fig("VD6", formula="(a - b) / b * 100"),
            "literal": fig("VD7", formula="1000 / 60"),
        }).resolve()
        assert values["sum"] == 14
        assert values["diff"] == 6
        assert values["prod"] == 40
        assert values["quot"] == 2.5
        assert values["neg"] == -10
        assert values["nested"] == 150.0
        assert values["literal"] == 1000 / 60

    @pytest.mark.parametrize("formula, message", [
        ("2 ** 3", "unsupported expression"),
        ("max(1, 2)", "unsupported expression"),
        ("a.b", "unsupported expression"),
        ("1 < 2", "unsupported expression"),
        ("a[0]", "unsupported expression"),
        ("__import__", "unknown value"),
        ("'x'", "non-numeric constant"),
        ("True", "non-numeric constant"),
        ("1 / 0", "division by zero"),
        ("nope + 1", "unknown value"),
        ("a +", "is not an expression"),
    ])
    def test_anything_outside_the_four_operators_is_refused(self, formula,
                                                            message):
        with pytest.raises(RegistryError, match=message):
            Registry({"x": fig("VD1", formula=formula)}).resolve()

    @pytest.mark.parametrize("figures_map, message", [
        ({"a": fig("VD1", formula="b + 1"), "b": fig("VD2", formula="a + 1")},
         "cycle"),
        ({"a": fig("VD1", formula="a + 1")}, "cycle"),
        ({"a": {"ref": "VM1", "kind": "M"}}, "neither value nor formula"),
        ({"a": fig("VM1", value="⟨number⟩")}, "is not a number"),
    ])
    def test_a_registry_that_cannot_resolve_says_why(self, figures_map,
                                                     message):
        with pytest.raises(RegistryError, match=message):
            Registry(figures_map).resolve()


PENDING_REGISTRY = Registry({
    "known": fig("VM1", value=2),
    "unknown": fig("VM2", pending=True),
    "over": fig("VD1", formula="known + unknown"),
    "far": fig("VD2", formula="over * 3"),
    "negated": fig("VD3", formula="-unknown"),
})


class TestPending:
    @pytest.mark.parametrize("name", ["unknown", "over", "far", "negated"])
    def test_it_poisons_everything_downstream_instead_of_zeroing_it(self, name):
        assert PENDING_REGISTRY.resolve()[name] is values_tool.registry.PENDING

    def test_it_displays_as_a_word(self):
        values = PENDING_REGISTRY.resolve()
        assert PENDING_REGISTRY.display("over", values["over"]) == "pending"

    def test_it_survives_copying_as_the_same_object(self):
        values = PENDING_REGISTRY.resolve()
        assert copy.deepcopy(values)["over"] is values_tool.registry.PENDING
        assert copy.copy(values["over"]) is values_tool.registry.PENDING
        assert pickle.loads(pickle.dumps(values_tool.registry.PENDING)) is values_tool.registry.PENDING
        assert values_tool.registry.Pending() is values_tool.registry.PENDING
        assert repr(values_tool.registry.PENDING) == "pending"


KINDS_REGISTRY = Registry({
    "measured": fig("VM1", value=1),
    "guess": fig("VE1", value=2),
    "clean": fig("VD1", formula="measured * 2"),
    "tainted": fig("VD2", formula="measured + guess"),
    "downstream": fig("VD3", formula="tainted * 2"),
    "far": fig("VD4", formula="downstream + measured"),
})


class TestEffectiveKind:
    @pytest.mark.parametrize("name, kind", [
        ("measured", "M"), ("clean", "D"), ("tainted", "E"),
        ("downstream", "E"), ("far", "E")])
    def test_the_weakest_input_decides_however_far_upstream(self, name, kind):
        assert KINDS_REGISTRY.effective_kind(name) == kind

    def test_the_marks_are_the_documented_glyphs(self):
        assert [values_tool.registry.MARK[k] for k in values_tool.registry.KINDS] == ["", "ᴿ", "ᴰ", "ᴱ"]

    def test_it_terminates_on_a_cycle_and_names_an_unknown_figure(self):
        cyclic = Registry({"a": fig("VD1", formula="b"),
                           "b": fig("VD2", formula="a")})
        assert cyclic.effective_kind("a") == "D"
        with pytest.raises(RegistryError, match="unknown value"):
            KINDS_REGISTRY.effective_kind("nope")


DISPLAY_REGISTRY = Registry({
    "two": fig("VM1", value=1234.5678),
    "none": fig("VM2", value=1234.5678, display=0),
    "four": fig("VM3", value=0.21954, display=4),
    "hours": fig("VM4", value=61.7, unit="hours"),
    "hours_forced": fig("VM5", value=61.7, unit="hours", display=1),
    "bad": fig("VM6", value=1.0, display="two"),
})


class TestDisplay:
    @pytest.mark.parametrize("name, written", [
        ("two", "1,234.57"), ("none", "1,235"), ("four", "0.2195"),
        ("hours", "62"), ("hours_forced", "61.7")])
    def test_a_figure_is_written_at_its_own_precision(self, name, written):
        values = DISPLAY_REGISTRY.resolve()
        assert DISPLAY_REGISTRY.display(name, values[name]) == written

    def test_a_display_that_is_not_a_count_of_decimals_is_refused(self):
        with pytest.raises(RegistryError, match="whole number"):
            DISPLAY_REGISTRY.display("bad", 1.0)


class TestMarks:
    @pytest.mark.parametrize("line", [
        "| **552.91<!--VR12-->** |",
        "$553.83<!--VD7--> / month",
        "0.2195<!--VM9--> GB/h",
        "a sentence ending in 552.91<!--VR12-->.",
        "$554<!--VD7-->",
        "$553.8<!--VD7-->",
    ])
    def test_the_hidden_form_parses_in_every_wrapping(self, marks_in, line):
        assert marks_in(line) == (1, [])

    @pytest.mark.parametrize("line", [
        "**$554** ᴿ (VD7)",
        "554 (VD7)",
        "554(VD7)",
        "`553.83`(VD7)",
        "553.83 ᴰ (VD7)",
        "**553.83** (VD7)",
    ])
    def test_the_visible_form_parses_with_bold_and_trust_markers(
            self, marks_in, line):
        assert marks_in(line) == (1, [])

    def test_two_on_one_line_are_both_counted(self, marks_in):
        assert marks_in("**552.91<!--VR12-->** and 0.2195<!--VM9-->") == (2, [])

    @pytest.mark.parametrize("line", [
        "**552.91**<!--VR12-->",
        "552.91 <!--VR12-->",
        "552.91 and (VD7)",
        "$0.3833/h<!--VR3-->",
    ])
    def test_a_shape_formats_md_calls_wrong_claims_nothing(self, marks_in,
                                                           line):
        assert marks_in(line)[0] == 0

    @pytest.mark.parametrize("line, why", [
        ("$553.83<!--VD07-->", "no such ref"),
        ("1.00<!--VD99-->", "no such ref"),
        ("552.92<!--VR12-->", "shows 552.92"),
        ("0.51<!--VE4-->", "pending"),
    ])
    def test_one_that_does_not_hold_is_caught(self, marks_in, line, why):
        seen, problems = marks_in(line)
        assert seen == 1
        assert len(problems) == 1 and why in problems[0].why

    def test_a_failing_one_names_its_file_and_line(self, marks_in):
        _, problems = marks_in("one", "two", "552.92<!--VR12-->")
        assert (problems[0].file, problems[0].line) == ("doc.md", 3)


class TestCodeIsSkipped:
    def test_no_mark_retired_value_or_orphan_is_read_inside_a_fence(self,
                                                                    coded):
        _, registry, values = coded
        documents = registry.documents()
        assert values_tool.checks.check_marks(registry, values, documents) == (1, [])
        assert values_tool.checks.check_retired(registry, documents) == []
        assert values_tool.checks.check_orphans(registry, values, "doc.md") == {}

    def test_the_same_text_outside_a_fence_still_fails(self, coded):
        tmp_path, registry, values = coded
        (tmp_path / "doc.md").write_text("an old number $19,460 in prose\n"
                                         "and 552.92<!--VR12--> beside it\n"
                                         "a stray $7.25 too\n")
        documents = registry.documents()
        assert len(values_tool.checks.check_retired(registry, documents)) == 1
        assert len(values_tool.checks.check_marks(registry, values, documents)[1]) == 1
        assert sorted(values_tool.checks.check_orphans(registry, values, "doc.md")) == [
            "19,460", "7.25"]

    def test_a_mark_wins_over_the_inline_span_rule(self, coded):
        tmp_path, registry, values = coded
        (tmp_path / "doc.md").write_text("| `553.83`(VD7) | `$0.75` |\n")
        assert values_tool.checks.check_marks(registry, values,
                                   registry.documents()) == (1, [])
        assert values_tool.checks.check_orphans(registry, values, "doc.md") == {}

    def test_a_fence_closes_only_on_one_at_least_as_long(self):
        lines = values_tool.corpus.split_lines("````\n```\n$1\n```\n````\nprose $2\n")
        assert [line.number for line in lines if line.prose] == [6]


VALIDATE_PROBLEMS = values_tool.checks.validate(Registry({
    "good": fig("VM1", value=1),
    "no_ref": {"kind": "M", "value": 1, "source": "s"},
    "bad_ref": {"ref": "M1", "kind": "M", "value": 1, "source": "s"},
    "padded": {"ref": "VM01", "kind": "M", "value": 1, "source": "s"},
    "zero": {"ref": "VM0", "kind": "M", "value": 1, "source": "s"},
    "mismatch": {"ref": "VD9", "kind": "M", "value": 1, "source": "s"},
    "bad_kind": {"ref": "FX1", "kind": "X", "value": 1, "source": "s"},
    "sourceless": {"ref": "VM2", "kind": "M", "value": 1},
    "dupe_a": fig("VR1", value=1),
    "dupe_b": fig("VR1", value=2),
}))[0]


class TestValidate:
    @pytest.mark.parametrize("problem", [
        "no_ref: no ref",
        "bad_ref: ref 'M1' is not V<MRDE><n>",
        "padded: ref 'VM01' is not V<MRDE><n>",
        "zero: ref 'VM0' is not V<MRDE><n>",
        "mismatch: ref VD9 disagrees with kind M",
        "bad_kind: kind 'X' is not one of",
        "sourceless: a leaf with no source",
        "ref VR1 used by 2",
    ])
    def test_it_catches(self, problem):
        assert any(problem in reported for reported in VALIDATE_PROBLEMS)

    def test_it_is_quiet_on_a_clean_figure(self):
        assert [p for p in VALIDATE_PROBLEMS if p.startswith("good")] == []

    def test_it_notes_a_derived_figure_that_prints_estimated(self):
        _, notes = values_tool.checks.validate(Registry({
            "guess": fig("VE1", value=1),
            "over": fig("VD1", formula="guess * 2")}))
        assert any("over" in note and "estimate" in note for note in notes)


SHAPE_REGISTRY = Registry({
    "a": fig("VM1", value=1, group="totals"),
    "b": fig("VM2", value=2),
    "c": fig("VD1", formula="a + b", group="totals"),
    "refless": {"kind": "M", "value": 3, "source": "s"},
})


class TestRegistryShape:
    def test_by_ref_maps_a_ref_to_a_name_and_skips_a_refless_figure(self):
        index = SHAPE_REGISTRY.by_ref()
        assert index["VD1"] == "c"
        assert None not in index

    def test_groups_follow_the_file_and_the_ungrouped_land_in_inputs(self):
        assert list(SHAPE_REGISTRY.groups()) == ["totals", "inputs"]
        assert SHAPE_REGISTRY.groups()["totals"] == ["a", "c"]

    def test_inputs_lists_what_a_formula_names(self):
        assert sorted(SHAPE_REGISTRY.inputs("c")) == ["a", "b"]
        assert SHAPE_REGISTRY.inputs("a") == []
        with pytest.raises(RegistryError, match="unknown value"):
            SHAPE_REGISTRY.inputs("nope")


class TestCoverage:
    @pytest.mark.parametrize("name, status", [
        ("total", "ok"), ("share", "ok"),
        ("absent", "MISSING"), ("nofile", "NO FILE")])
    def test_each_figure_is_checked_where_it_is_claimed(self, report, name,
                                                        status):
        registry = report()
        rows = {row.name: row.status
                for row in values_tool.checks.check_coverage(registry,
                                                  registry.resolve())}
        assert rows[name] == status

    def test_a_bare_appears_in_path_is_read_as_one_file(self, report):
        single = Registry({"total": fig("VD1", formula="10 + 4",
                                        appears_in="report.md")},
                          root=report().root)
        assert [row.status for row in
                values_tool.checks.check_coverage(single, single.resolve())] == ["ok"]


class TestRetired:
    def test_a_superseded_number_is_found_with_its_line_and_replacement(
            self, report):
        registry = report(retired=RETIRED)
        hits = values_tool.checks.check_retired(registry, registry.documents())
        assert len(hits) == 1
        assert (hits[0].line, hits[0].replaced_by) == (2, "total")

    @pytest.mark.parametrize("allow, silenced", [
        (({"pattern": "$19,460", "file": "report.md",
           "must_contain": "still here"},), True),
        (({"pattern": "$19,460", "file": "other.md"},), False),
        (({"pattern": "$19,460", "must_contain": "not on this line"},), False),
        (({"pattern": "$1.00"},), False),
    ])
    def test_an_allow_entry_silences_only_what_it_names(self, report, allow,
                                                        silenced):
        registry = report(retired=RETIRED, allow=allow)
        assert (values_tool.checks.check_retired(registry, registry.documents()) == []
                ) is silenced

    @pytest.mark.parametrize("over, message", [
        ({"retired": ({"why": "oops"},)}, "needs a 'pattern'"),
        ({"retired": RETIRED, "allow": ("$19,460",)}, "must be mappings"),
    ])
    def test_a_malformed_entry_is_named(self, report, over, message):
        registry = report(**over)
        with pytest.raises(RegistryError, match=message):
            values_tool.checks.check_retired(registry, registry.documents())


class TestOrphans:
    def test_a_currency_token_no_figure_claims_is_listed_with_its_lines(
            self, report):
        registry = report()
        orphans = values_tool.checks.check_orphans(registry, registry.resolve(),
                                        "report.md")
        assert orphans["19,460"] == [2]

    def test_a_missing_file_is_told_from_a_clean_one(self, report):
        registry = report()
        assert values_tool.checks.check_orphans(registry, registry.resolve(),
                                     "nowhere.md") is None


class TestScan:
    def test_a_file_named_twice_is_read_once_so_marks_are_not_doubled(
            self, scanned):
        registry = Registry(MARKS, root=scanned,
                            scan=("report.md", "*.md", "report.md"))
        assert [d.rel for d in registry.documents()] == ["report.md",
                                                         "execution.md"]
        seen, _ = values_tool.checks.check_marks(registry, registry.resolve(),
                                      registry.documents())
        assert seen == 2

    @pytest.mark.parametrize("scan, found", [
        (("*.md",), ["execution.md", "report.md"]),
        (("sub/*.md",), ["sub/deep.md"]),
        (("nowhere/*.md",), []),
        ((), []),
    ])
    def test_it_finds_what_it_names_and_is_silent_on_a_miss(self, scanned,
                                                            scan, found):
        registry = Registry(MARKS, root=scanned, scan=scan)
        assert [d.rel for d in registry.documents()] == [str(Path(f))
                                                         for f in found]

    def test_an_entry_or_a_file_that_cannot_be_used_is_named(self, scanned):
        with pytest.raises(RegistryError, match="not a usable path"):
            Registry(MARKS, root=scanned, scan=("",)).documents()
        with pytest.raises(RegistryError, match="cannot read"):
            values_tool.corpus.read_document(scanned, scanned)

    def test_a_document_is_named_relative_to_the_root(self, scanned):
        assert Registry(MARKS, root=scanned).relative(
            scanned / "report.md") == "report.md"
        assert values_tool.corpus.relative(scanned / "report.md", scanned / "sub") == str(
            Path("..") / "report.md")


class TestLoading:
    def test_the_registry_is_found_by_walking_up(self, tmp_path):
        root = tmp_path / "report"
        nest = root / "executions" / "01-load"
        nest.mkdir(parents=True)
        (root / values_tool.registry.REGISTRY).write_text(REGISTRY_TEXT)

        found_root, path = values_tool.registry.find_registry(start=nest)
        assert (found_root, path.name) == (root.resolve(), values_tool.registry.REGISTRY)
        assert values_tool.registry.find_registry(
            explicit=root / values_tool.registry.REGISTRY)[0] == root.resolve()

        registry = Registry.load(start=nest)
        assert registry.resolve()["total"] == 14
        assert registry.root == root.resolve()
        assert registry.scan == ("report.md",)

    @pytest.mark.parametrize("explicit, start, message", [
        (None, "not-a-report", "no report-values.yaml"),
        ("nope.yaml", None, "no such registry"),
    ])
    def test_one_that_is_not_there_says_so(self, tmp_path, explicit, start,
                                           message):
        with pytest.raises(RegistryError, match=message):
            values_tool.registry.find_registry(
                explicit=tmp_path / explicit if explicit else None,
                start=tmp_path / start if start else None)

    @pytest.mark.parametrize("text, message", [
        ("values:\n  a: [oops\n", "not valid YAML"),
        ("", "is empty"),
        ("- a\n- b\n", "must be a mapping"),
        ("meta: {}\n", "no 'values' mapping"),
        ("values:\n", "empty 'values'"),
        ("values:\n  - a\n  - b\n", "must be a mapping"),
        ("values:\n  12: {ref: VM1, kind: M, value: 1, source: s}\n",
         "must be strings"),
        ("values:\n  a: {ref: VM1, kind: M, value: 1, source: s}\n"
         "scan: x.md\n", "must be a list"),
        ("values:\n  a: {ref: VM1, kind: M, value: 1, source: s}\n"
         "  a: {ref: VM2, kind: M, value: 2, source: s}\n",
         "'a' appears twice, at lines 2 and 3"),
        ("values:\n  a:\n    ref: VM1\n    kind: M\n    value: 1\n"
         "    value: 2\n    source: s\n", "'value' appears twice"),
    ])
    def test_a_malformed_one_is_a_figure_error(self, registry_file, text,
                                               message):
        with pytest.raises(RegistryError, match=message):
            Registry.load(explicit=registry_file(text))


def renumber(path, kinds=None):
    return values_tool.edits.renumber(Registry.load(explicit=path), kinds)


def retype(path, name, kind):
    return values_tool.edits.retype(Registry.load(explicit=path), name, kind)


class TestFileSurgery:
    def test_renumber_follows_file_order_and_is_idempotent(self,
                                                           registry_file):
        path = registry_file()
        assert renumber(path).counts == {"M": 2, "D": 1}
        registry = Registry.load(explicit=path)
        assert [(n, s.get("ref")) for n, s in registry.entries.items()] == [
            ("alpha", "VM1"), ("beta", "VM2"), ("total", "VD1")]
        assert registry.resolve()["total"] == 14

        before = path.read_text()
        renumber(path)
        assert path.read_text() == before

    def test_retype_moves_one_kind_and_closes_the_refs_up(self, registry_file):
        path = registry_file()
        renumber(path)
        assert retype(path, "beta", "R").counts == {"M": 1, "R": 1, "D": 1}
        registry = Registry.load(explicit=path)
        assert registry.entries["beta"]["kind"] == "R"
        assert [s.get("ref") for s in registry.entries.values()] == [
            "VM1", "VR1", "VD1"]
        assert registry.resolve()["total"] == 14
        assert values_tool.checks.validate(registry)[0] == []

    @pytest.mark.parametrize("name, kind, message", [
        ("beta", "Z", "kind must be one of"),
        ("nope", "M", "unknown value"),
    ])
    def test_retype_refuses_what_it_cannot_do(self, registry_file, name, kind,
                                              message):
        with pytest.raises(RegistryError, match=message):
            retype(registry_file(), name, kind)

    @pytest.mark.parametrize("text, message", [
        ("values:\n"
         "  alpha: {ref: VM9, kind: M, value: 1, source: s}\n"
         "\n"
         "  beta:\n    ref: VM2\n    kind: M\n    value: 2\n    source: s\n",
         "cannot see"),
        ("values: {a: {ref: VM1, kind: M, value: 1, source: s}}\n",
         "inline mapping"),
        ("values:\n  a:\n    ref: FX1\n    kind: X\n    value: 1\n"
         "    source: s\n", "is not one of"),
    ])
    def test_the_rewriter_refuses_and_writes_nothing_rather_than_half_applying(
            self, registry_file, text, message):
        path = registry_file(text)
        with pytest.raises(RegistryError, match=message):
            renumber(path)
        assert path.read_text() == text

    def test_renumber_refuses_an_override_naming_no_kind(self, registry_file):
        with pytest.raises(RegistryError, match="kind must be one of"):
            renumber(registry_file(), {"alpha": "Z"})

    @pytest.mark.parametrize("alpha", [
        "  alpha:\n    ref: VM1\n    value: 1\n    source: s\n",
        "  alpha:\n    ref: VM1\n    kind: M  # why\n    value: 1\n"
        "    source: s\n",
    ])
    def test_retype_changes_the_figure_it_was_given_not_its_neighbour(
            self, registry_file, alpha):
        path = registry_file("values:\n" + alpha + "\n"
                             "  beta:\n    ref: VM2\n    kind: M\n"
                             "    value: 2\n    source: s\n")
        retype(path, "alpha", "E")
        registry = Registry.load(explicit=path)
        assert registry.entries["alpha"]["kind"] == "E"
        assert registry.entries["beta"]["kind"] == "M"
        assert [s.get("ref") for s in registry.entries.values()] == ["VE1",
                                                                     "VM1"]


class TestRenumberMovesMarks:
    """A ref is renumbered in the registry and in every document citing it,
    or nowhere."""

    REGISTRY = ("scan:\n  - report.md\n\nvalues:\n"
                "  alpha:\n    ref: VM9\n    kind: M\n    value: 1\n    source: s\n\n"
                "  beta:\n    ref: VM12\n    kind: M\n    value: 2\n    source: s\n")

    def report(self, tmp_path, text):
        (tmp_path / "report-values.yaml").write_text(self.REGISTRY)
        (tmp_path / "report.md").write_text(text)
        return tmp_path / "report-values.yaml"

    def test_every_mark_follows_its_figure(self, tmp_path):
        path = self.report(tmp_path, "one 1<!--VM9--> and **2** (VM12)\n")
        done = renumber(path)
        assert done.refs == {"VM9": "VM1", "VM12": "VM2"}
        assert (tmp_path / "report.md").read_text() == "one 1<!--VM1--> and **2** (VM2)\n"
        assert values_tool.main(["--path", str(path), "check"]) == 0

    def test_retype_moves_the_letter_of_the_mark_too(self, tmp_path):
        path = self.report(tmp_path, "1<!--VM9--> 2<!--VM12-->\n")
        retype(path, "alpha", "E")
        assert (tmp_path / "report.md").read_text() == "1<!--VE1--> 2<!--VM1-->\n"

    def test_a_mark_no_figure_holds_is_refused_and_nothing_is_written(self, tmp_path):
        path = self.report(tmp_path, "1<!--VM9--> 3<!--VM1-->\n")
        with pytest.raises(RegistryError, match="VM1 at report.md:1"):
            renumber(path)
        assert path.read_text() == self.REGISTRY
        assert (tmp_path / "report.md").read_text() == "1<!--VM9--> 3<!--VM1-->\n"


class TestCommand:
    def test_a_clean_report_exits_clean(self, reported):
        _, at = reported
        assert run(*at)[0] == 0
        code, out, _ = run(*at, "check")
        assert code == 0
        assert "marked numbers: 1" in out and "coverage: 1/1" in out
        assert run(*at, "validate")[0] == 0

    @pytest.mark.parametrize("wanted", ["total", "VD1"])
    def test_one_figure_prints_its_bare_value(self, reported, wanted):
        assert run(*reported[1], wanted) == (0, "14.00\n", "")

    def test_an_unknown_figure_exits_two_and_says_so(self, reported):
        code, _, err = run(*reported[1], "nope")
        assert code == 2 and "unknown value" in err

    def test_drift_exits_one_and_names_the_ref(self, reported):
        tmp_path, at = reported
        (tmp_path / "report.md").write_text("the total is 99.00<!--VD1-->\n")
        code, out, _ = run(*at, "check")
        assert code == 1 and "VD1" in out

    def test_missing_coverage_is_a_note_until_strict(self, reported):
        tmp_path, at = reported
        (tmp_path / "report.md").write_text("no numbers here\n")
        code, out, _ = run(*at, "check")
        assert code == 0 and "MISSING" in out
        assert run(*at, "check", "--strict")[0] == 1

    @pytest.mark.parametrize("argv, code", [
        (("orphans", "report.md"), 0),
        (("orphans",), 2),
        (("retype", "alpha"), 2),
        (("retype", "beta", "Z"), 2),
    ])
    def test_one_that_cannot_run_exits_two(self, reported, argv, code):
        assert run(*reported[1], *argv)[0] == code

    def test_orphans_says_a_missing_file_rather_than_raising(self, reported):
        code, out, _ = run(*reported[1], "orphans", "nowhere.md")
        assert code == 0 and "no such file" in out

    def test_retype_rewrites_the_file(self, reported):
        tmp_path, at = reported
        assert run(*at, "retype", "beta", "E")[0] == 0
        assert Registry.load(explicit=tmp_path / values_tool.registry.REGISTRY
                             ).entries["beta"]["ref"] == "VE1"

    @pytest.mark.parametrize("text, message", [
        ("values:\n  a: [oops\n", "not valid YAML"),
        ("values:\n  a:\n    ref: VM1\n    kind: M\n    value: ⟨number⟩\n"
         "    source: s\n", "not a number"),
    ])
    def test_a_registry_it_cannot_read_exits_two(self, registry_file, text,
                                                 message):
        code, _, err = run("--path", str(registry_file(text)), "check")
        assert code == 2 and message in err

    def test_validate_refuses_a_figure_defined_twice(self, registry_file):
        text = REGISTRY_TEXT.replace(
            "  total:", "  alpha:\n    ref: VM3\n    kind: M\n    value: 99\n"
            "    source: a second alpha\n\n  total:")
        code, _, err = run("--path", str(registry_file(text)), "validate")
        assert code == 2 and "'alpha' appears twice" in err

    def test_a_merge_key_may_still_be_overridden(self, registry_file):
        text = ("base: &base {kind: M, source: s}\n"
                "values:\n  a: {<<: *base, ref: VM1, value: 1, source: own}\n")
        assert Registry.load(explicit=registry_file(text)
                             ).entries["a"]["source"] == "own"

    def test_a_registry_that_is_not_there_exits_two(self, tmp_path):
        assert run("--path", str(tmp_path / "nope.yaml"), "check")[0] == 2

    def test_renumber_works_on_a_registry_that_does_not_resolve(
            self, registry_file):
        path = registry_file("values:\n  a:\n    ref: VM1\n    kind: M\n"
                             "    value: ⟨number⟩\n    source: s\n")
        assert run("--path", str(path), "renumber")[0] == 0

    def test_check_names_a_retired_value_and_its_replacement(self, loud):
        code, out, _ = run(*loud, "check")
        assert code == 1
        assert "-> total = 14.00" in out and "an old number" in out

    def test_validate_prints_problems_and_notes(self, loud):
        code, out, _ = run(*loud, "validate")
        assert code == 1
        assert "FAIL stray" in out and "note over" in out

    def test_orphans_lists_a_token_with_its_lines(self, loud):
        assert "$19,460" in run(*loud, "orphans", "report.md")[1]

    def test_group_leaves_the_other_groups_out(self, loud):
        _, out, _ = run(*loud, "--group", "totals")
        assert "solo" in out and "guess" not in out


EVIDENCED = """\
# A comment above everything survives a pull.
meta:
  note: >-
    a folded scalar outside the values block, with
    value: 1 on a line that looks like a key

values:
  served:
    ref: VM1
    kind: M
    value: 4.01   # as first typed
    from: {file: data/r1.point.json, path: client.served}
    source: the point record

  peak:
    ref: VM2
    kind: M
    # no value yet: pull writes it below the kind
    from: {file: data/r1.jsonl, ref: M1, reduce: max}
    source: the export
    note: |
      value: 3
      a literal block inside the value

  total:
    ref: VD1
    kind: D
    formula: served + peak
"""

PULLED = EVIDENCED.replace(
    "    value: 4.01   # as first typed\n", "    value: 4.5   # as first typed\n"
).replace(
    "  peak:\n    ref: VM2\n    kind: M\n",
    "  peak:\n    ref: VM2\n    kind: M\n    value: 7\n")


@pytest.fixture
def evidenced(tmp_path, registry_file):
    def write(text=EVIDENCED, served=4.5, peak=("3", "7")):
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "r1.point.json").write_text(
            f'{{"client": {{"served": {served}}}}}\n')
        values = ", ".join(f'[{t}, "{v}"]' for t, v in enumerate(peak, 1))
        (tmp_path / "data" / "r1.jsonl").write_text(
            f'{{"metric": "M1", "result": [{{"metric": {{}}, '
            f'"values": [{values}]}}]}}\n' if peak else
            '{"metric": "M1", "result": []}\n')
        return registry_file(text)
    return write


class TestPull:
    def test_it_rewrites_value_lines_and_nothing_else(self, evidenced):
        path = evidenced()
        code, out, _ = run("--path", str(path), "pull")
        assert code == 0
        assert path.read_text() == PULLED
        assert "4.01 -> 4.5" in out and "(none) -> 7" in out

    def test_a_second_pull_changes_nothing(self, evidenced):
        path = evidenced()
        run("--path", str(path), "pull")
        code, out, _ = run("--path", str(path), "pull")
        assert code == 0 and path.read_text() == PULLED
        assert "0 value(s) rewritten" in out

    def test_a_gap_is_reported_and_never_written_as_zero(self, evidenced):
        path = evidenced(peak=())
        code, out, _ = run("--path", str(path), "pull")
        assert code == 1
        assert "FAIL peak" in out and "a gap, not a zero" in out
        assert path.read_text() == EVIDENCED.replace("value: 4.01", "value: 4.5")

    def test_named_figures_only_by_name_or_ref(self, evidenced):
        path = evidenced()
        assert run("--path", str(path), "pull", "VM2")[0] == 0
        assert "value: 4.01" in path.read_text()
        assert Registry.load(explicit=path).entries["peak"]["value"] == 7

    @pytest.mark.parametrize("wanted, message", [
        ("total", "has no from: to pull"), ("nope", "unknown value")])
    def test_a_figure_it_cannot_pull_exits_two(self, evidenced, wanted, message):
        path = evidenced()
        code, _, err = run("--path", str(path), "pull", wanted)
        assert code == 2 and message in err
        assert path.read_text() == EVIDENCED

    def test_the_rewriter_refuses_a_figure_it_cannot_see(self, evidenced):
        text = ("values:\n  served: {ref: VM1, kind: M, value: 1, "
                "from: {file: data/r1.point.json, path: client.served}}\n")
        path = evidenced(text)
        code, _, err = run("--path", str(path), "pull")
        assert code == 2 and "cannot see 'served'" in err
        assert path.read_text() == text

    @pytest.mark.parametrize("value, text", [
        (0.0022 * 100, "0.22"), (24.0, "24"), (71.96642684480047,
                                               "71.9664268448005")])
    def test_a_value_is_written_at_full_precision_without_float_noise(
            self, value, text):
        assert values_tool.surgery.value_text(value) == text


class TestEvidenceCheck:
    def test_a_stored_value_that_disagrees_with_its_data_fails(self, evidenced):
        path = evidenced(PULLED, served=4.6)
        code, out, _ = run("--path", str(path), "check")
        assert code == 1
        assert "DIFFERS  served" in out and "stores 4.5, its data gives 4.6" in out
        assert "evidence: 1/2" in out

    def test_values_that_agree_with_their_data_pass(self, evidenced):
        code, out, _ = run("--path", str(evidenced(PULLED)), "check")
        assert code == 0 and "evidence: 2/2" in out

    def test_a_missing_data_file_is_a_note_until_strict(self, evidenced, tmp_path):
        path = evidenced(PULLED)
        (tmp_path / "data" / "r1.jsonl").unlink()
        code, out, _ = run("--path", str(path), "check")
        assert code == 0 and "NO FILE  peak" in out
        assert run("--path", str(path), "check", "--strict")[0] == 1

    def test_a_gap_fails_the_check(self, evidenced):
        code, out, _ = run("--path", str(evidenced(PULLED, peak=())), "check")
        assert code == 1 and "FAIL     peak" in out

    def test_a_figure_with_a_from_and_no_value_says_to_pull(self, evidenced):
        code, _, err = run("--path", str(evidenced()), "check")
        assert code == 2 and "report-kit values pull peak" in err

    def test_both_examples_reproduce_from_their_data(self):
        examples = Path(__file__).resolve().parent.parent / "examples"
        for name in ("simple-api", "async-jobs"):
            registry = Registry.load(explicit=examples / name / values_tool.registry.REGISTRY)
            rows = values_tool.readings.check_evidence(registry)
            assert rows and [r for r in rows if r.status != "ok"] == [], name


class TestEvidenceValidate:
    SOURCE = {"file": "data/r1.point.json", "path": "client.served"}

    def test_from_counts_as_a_source(self):
        problems, _ = values_tool.checks.validate(Registry({
            "read": {"ref": "VM1", "kind": "M", "value": 1,
                     "from": self.SOURCE}}))
        assert problems == []

    def test_from_and_formula_together_are_refused(self):
        problems, _ = values_tool.checks.validate(Registry({
            "both": fig("VD1", formula="1 + 1", **{"from": self.SOURCE})}))
        assert any("both: from: and formula: together" in p for p in problems)

    def test_a_from_outside_the_two_shapes_is_refused(self):
        problems, _ = values_tool.checks.validate(Registry({
            "odd": fig("VM1", value=1, **{"from": {
                "file": "data/r1.jsonl", "ref": "M1", "reduce": "median"}})}))
        assert any("odd: from: reduce 'median'" in p for p in problems)


def test_the_shipped_template_is_a_registry_of_placeholders(registry_file):
    from importlib.resources import files
    path = registry_file((Path(str(files("report_kit"))) / "templates"
                          / "report-values.yaml").read_text())
    registry = Registry.load(explicit=path)

    assert {s.get("kind") for s in registry.entries.values()} == set(
        values_tool.registry.KINDS)
    assert all(values_tool.registry.REF_RE.match(str(s.get("ref")))
               for s in registry.entries.values())
    assert registry.scan and registry.allow is not None
    assert any("from" in s for s in registry.entries.values())
    assert not [p for name, spec in registry.entries.items()
                for p in values_tool.checks.evidence_problems(name, spec)]
    with pytest.raises(RegistryError, match="is not a number"):
        registry.resolve()
