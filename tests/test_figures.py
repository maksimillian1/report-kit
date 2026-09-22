"""The registry's arithmetic, its marks, its file surgery, and the command's
exit codes.

    pytest tests/test_figures.py

`report-kit figures check` is what a report runs; this proves the checker
itself still works. Every failure that depends on a registry's contents must
arrive as `FigureError`, so `pytest.raises` asserts the message too.
"""

from __future__ import annotations

import contextlib
import copy
import io
import pickle
from pathlib import Path

import pytest

from report_kit.tools import figures
from report_kit.tools.figures import FigureError, Registry


def fig(ref, **spec):
    """A figure spec: kind comes from the ref, leaves get a source."""
    return {"ref": ref, "kind": ref[1], "source": "s", **spec}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = figures.main(list(argv))
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 2
    return code, out.getvalue(), err.getvalue()


MARKS = {
    "price": fig("FR12", value=552.91),
    "total": fig("FD7", formula="price + 0.92"),
    "rate": fig("FM9", value=0.2195, display=4),
    "later": fig("FE4", pending=True),
}

REGISTRY_TEXT = """\
scan:
  - report.md

figures:
  alpha:
    ref: FM1
    kind: M
    value: 10
    source: a measurement

  beta:
    ref: FM2
    kind: M
    value: 4
    source: another measurement

  total:
    ref: FD1
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
        path = tmp_path / figures.REGISTRY
        path.write_text(text)
        return path
    return write


@pytest.fixture
def marks_in(tmp_path):
    def check(*lines):
        (tmp_path / "doc.md").write_text("\n".join(lines) + "\n")
        registry = Registry(MARKS, root=tmp_path, scan=("doc.md",))
        return figures.check_marks(registry, registry.resolve(),
                                   registry.documents())
    return check


@pytest.fixture
def coded(tmp_path):
    (tmp_path / "doc.md").write_text(
        "prose says $553.83<!--FD7-->\n"
        "```bash\n"
        "curl 'price=$19,460' # 552.92<!--FR12-->\n"
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
        "total": fig("FD1", formula="10 + 4", appears_in=["report.md"]),
        "share": fig("FD2", formula="92", display=0, appears_in=["report.md"]),
        "absent": fig("FD3", formula="77", appears_in=["report.md"]),
        "nofile": fig("FD4", formula="1", appears_in=["nowhere.md"]),
    }
    return lambda **over: Registry(figures_map, root=tmp_path,
                                   scan=("report.md",), **over)


@pytest.fixture
def scanned(tmp_path):
    (tmp_path / "report.md").write_text("552.91<!--FR12-->\n")
    (tmp_path / "execution.md").write_text("0.2195<!--FM9-->\n")
    (tmp_path / "notes.txt").write_text("552.91<!--FR12-->\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text("552.91<!--FR12-->\n")
    return tmp_path


@pytest.fixture
def reported(registry_file, tmp_path):
    path = registry_file()
    (tmp_path / "report.md").write_text("the total is 14.00<!--FD1-->\n")
    return tmp_path, ["--path", str(path)]


@pytest.fixture
def loud(registry_file, tmp_path):
    path = registry_file(
        "scan:\n  - report.md\n\n"
        "figures:\n"
        "  total:\n    ref: FD1\n    kind: D\n    formula: 10 + 4\n"
        "  guess:\n    ref: FE1\n    kind: E\n    value: 2\n"
        "    source: an estimate\n"
        "  over:\n    ref: FD2\n    kind: D\n    formula: guess * 2\n"
        "  solo:\n    ref: FM1\n    kind: M\n    value: 5\n"
        "    source: s\n    group: totals\n"
        "  stray:\n    ref: FM2\n    kind: M\n    value: 1\n\n"
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
        ("1", figures.PENDING, False),
    ])
    def test_a_figure_matches_every_legal_rendering_of_itself(
            self, shown, value, matches):
        assert figures.rounds_to(shown, value) is matches

    @pytest.mark.parametrize("shown, value, matches", [
        ("2", 2.5, True), ("3", 2.5, False),
        ("4", 3.5, True), ("3", 3.5, False)])
    def test_ties_round_half_to_even(self, shown, value, matches):
        assert figures.rounds_to(shown, value) is matches


class TestResolve:
    def test_the_four_operators_and_a_literal(self):
        values = Registry({
            "a": fig("FM1", value=10),
            "b": fig("FM2", value=4),
            "sum": fig("FD1", formula="a + b"),
            "diff": fig("FD2", formula="a - b"),
            "prod": fig("FD3", formula="a * b"),
            "quot": fig("FD4", formula="a / b"),
            "neg": fig("FD5", formula="-a"),
            "nested": fig("FD6", formula="(a - b) / b * 100"),
            "literal": fig("FD7", formula="1000 / 60"),
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
        ("__import__", "unknown figure"),
        ("'x'", "non-numeric constant"),
        ("True", "non-numeric constant"),
        ("1 / 0", "division by zero"),
        ("nope + 1", "unknown figure"),
        ("a +", "is not an expression"),
    ])
    def test_anything_outside_the_four_operators_is_refused(self, formula,
                                                            message):
        with pytest.raises(FigureError, match=message):
            Registry({"x": fig("FD1", formula=formula)}).resolve()

    @pytest.mark.parametrize("figures_map, message", [
        ({"a": fig("FD1", formula="b + 1"), "b": fig("FD2", formula="a + 1")},
         "cycle"),
        ({"a": fig("FD1", formula="a + 1")}, "cycle"),
        ({"a": {"ref": "FM1", "kind": "M"}}, "neither value nor formula"),
        ({"a": fig("FM1", value="⟨number⟩")}, "is not a number"),
    ])
    def test_a_registry_that_cannot_resolve_says_why(self, figures_map,
                                                     message):
        with pytest.raises(FigureError, match=message):
            Registry(figures_map).resolve()


PENDING_REGISTRY = Registry({
    "known": fig("FM1", value=2),
    "unknown": fig("FM2", pending=True),
    "over": fig("FD1", formula="known + unknown"),
    "far": fig("FD2", formula="over * 3"),
    "negated": fig("FD3", formula="-unknown"),
})


class TestPending:
    @pytest.mark.parametrize("name", ["unknown", "over", "far", "negated"])
    def test_it_poisons_everything_downstream_instead_of_zeroing_it(self, name):
        assert PENDING_REGISTRY.resolve()[name] is figures.PENDING

    def test_it_displays_as_a_word(self):
        values = PENDING_REGISTRY.resolve()
        assert PENDING_REGISTRY.display("over", values["over"]) == "pending"

    def test_it_survives_copying_as_the_same_object(self):
        values = PENDING_REGISTRY.resolve()
        assert copy.deepcopy(values)["over"] is figures.PENDING
        assert copy.copy(values["over"]) is figures.PENDING
        assert pickle.loads(pickle.dumps(figures.PENDING)) is figures.PENDING
        assert figures.Pending() is figures.PENDING
        assert repr(figures.PENDING) == "pending"


KINDS_REGISTRY = Registry({
    "measured": fig("FM1", value=1),
    "guess": fig("FE1", value=2),
    "clean": fig("FD1", formula="measured * 2"),
    "tainted": fig("FD2", formula="measured + guess"),
    "downstream": fig("FD3", formula="tainted * 2"),
    "far": fig("FD4", formula="downstream + measured"),
})


class TestEffectiveKind:
    @pytest.mark.parametrize("name, kind", [
        ("measured", "M"), ("clean", "D"), ("tainted", "E"),
        ("downstream", "E"), ("far", "E")])
    def test_the_weakest_input_decides_however_far_upstream(self, name, kind):
        assert KINDS_REGISTRY.effective_kind(name) == kind

    def test_the_marks_are_the_documented_glyphs(self):
        assert [figures.MARK[k] for k in figures.KINDS] == ["", "ᴿ", "ᴰ", "ᴱ"]

    def test_it_terminates_on_a_cycle_and_names_an_unknown_figure(self):
        cyclic = Registry({"a": fig("FD1", formula="b"),
                           "b": fig("FD2", formula="a")})
        assert cyclic.effective_kind("a") == "D"
        with pytest.raises(FigureError, match="unknown figure"):
            KINDS_REGISTRY.effective_kind("nope")


DISPLAY_REGISTRY = Registry({
    "two": fig("FM1", value=1234.5678),
    "none": fig("FM2", value=1234.5678, display=0),
    "four": fig("FM3", value=0.21954, display=4),
    "hours": fig("FM4", value=61.7, unit="hours"),
    "hours_forced": fig("FM5", value=61.7, unit="hours", display=1),
    "bad": fig("FM6", value=1.0, display="two"),
})


class TestDisplay:
    @pytest.mark.parametrize("name, written", [
        ("two", "1,234.57"), ("none", "1,235"), ("four", "0.2195"),
        ("hours", "62"), ("hours_forced", "61.7")])
    def test_a_figure_is_written_at_its_own_precision(self, name, written):
        values = DISPLAY_REGISTRY.resolve()
        assert DISPLAY_REGISTRY.display(name, values[name]) == written

    def test_a_display_that_is_not_a_count_of_decimals_is_refused(self):
        with pytest.raises(FigureError, match="whole number"):
            DISPLAY_REGISTRY.display("bad", 1.0)


class TestMarks:
    @pytest.mark.parametrize("line", [
        "| **552.91<!--FR12-->** |",
        "$553.83<!--FD7--> / month",
        "0.2195<!--FM9--> GB/h",
        "a sentence ending in 552.91<!--FR12-->.",
        "$554<!--FD7-->",
        "$553.8<!--FD7-->",
    ])
    def test_the_hidden_form_parses_in_every_wrapping(self, marks_in, line):
        assert marks_in(line) == (1, [])

    @pytest.mark.parametrize("line", [
        "**$554** ᴿ (FD7)",
        "554 (FD7)",
        "554(FD7)",
        "`553.83`(FD7)",
        "553.83 ᴰ (FD7)",
        "**553.83** (FD7)",
    ])
    def test_the_visible_form_parses_with_bold_and_trust_markers(
            self, marks_in, line):
        assert marks_in(line) == (1, [])

    def test_two_on_one_line_are_both_counted(self, marks_in):
        assert marks_in("**552.91<!--FR12-->** and 0.2195<!--FM9-->") == (2, [])

    @pytest.mark.parametrize("line", [
        "**552.91**<!--FR12-->",
        "552.91 <!--FR12-->",
        "552.91 and (FD7)",
        "$0.3833/h<!--FR3-->",
    ])
    def test_a_shape_formats_md_calls_wrong_claims_nothing(self, marks_in,
                                                           line):
        assert marks_in(line)[0] == 0

    @pytest.mark.parametrize("line, why", [
        ("$553.83<!--FD07-->", "no such ref"),
        ("1.00<!--FD99-->", "no such ref"),
        ("552.92<!--FR12-->", "shows 552.92"),
        ("0.51<!--FE4-->", "pending"),
    ])
    def test_one_that_does_not_hold_is_caught(self, marks_in, line, why):
        seen, problems = marks_in(line)
        assert seen == 1
        assert len(problems) == 1 and why in problems[0].why

    def test_a_failing_one_names_its_file_and_line(self, marks_in):
        _, problems = marks_in("one", "two", "552.92<!--FR12-->")
        assert (problems[0].file, problems[0].line) == ("doc.md", 3)


class TestCodeIsSkipped:
    def test_no_mark_retired_value_or_orphan_is_read_inside_a_fence(self,
                                                                    coded):
        _, registry, values = coded
        documents = registry.documents()
        assert figures.check_marks(registry, values, documents) == (1, [])
        assert figures.check_retired(registry, documents) == []
        assert figures.check_orphans(registry, values, "doc.md") == {}

    def test_the_same_text_outside_a_fence_still_fails(self, coded):
        tmp_path, registry, values = coded
        (tmp_path / "doc.md").write_text("an old number $19,460 in prose\n"
                                         "and 552.92<!--FR12--> beside it\n"
                                         "a stray $7.25 too\n")
        documents = registry.documents()
        assert len(figures.check_retired(registry, documents)) == 1
        assert len(figures.check_marks(registry, values, documents)[1]) == 1
        assert sorted(figures.check_orphans(registry, values, "doc.md")) == [
            "19,460", "7.25"]

    def test_a_mark_wins_over_the_inline_span_rule(self, coded):
        tmp_path, registry, values = coded
        (tmp_path / "doc.md").write_text("| `553.83`(FD7) | `$0.75` |\n")
        assert figures.check_marks(registry, values,
                                   registry.documents()) == (1, [])
        assert figures.check_orphans(registry, values, "doc.md") == {}

    def test_a_fence_closes_only_on_one_at_least_as_long(self):
        lines = figures.split_lines("````\n```\n$1\n```\n````\nprose $2\n")
        assert [line.number for line in lines if line.prose] == [6]


VALIDATE_PROBLEMS = figures.validate(Registry({
    "good": fig("FM1", value=1),
    "no_ref": {"kind": "M", "value": 1, "source": "s"},
    "bad_ref": {"ref": "M1", "kind": "M", "value": 1, "source": "s"},
    "padded": {"ref": "FM01", "kind": "M", "value": 1, "source": "s"},
    "zero": {"ref": "FM0", "kind": "M", "value": 1, "source": "s"},
    "mismatch": {"ref": "FD9", "kind": "M", "value": 1, "source": "s"},
    "bad_kind": {"ref": "FX1", "kind": "X", "value": 1, "source": "s"},
    "sourceless": {"ref": "FM2", "kind": "M", "value": 1},
    "dupe_a": fig("FR1", value=1),
    "dupe_b": fig("FR1", value=2),
}))[0]


class TestValidate:
    @pytest.mark.parametrize("problem", [
        "no_ref: no ref",
        "bad_ref: ref 'M1' is not F<MRDE><n>",
        "padded: ref 'FM01' is not F<MRDE><n>",
        "zero: ref 'FM0' is not F<MRDE><n>",
        "mismatch: ref FD9 disagrees with kind M",
        "bad_kind: kind 'X' is not one of",
        "sourceless: a leaf with no source",
        "ref FR1 used by 2",
    ])
    def test_it_catches(self, problem):
        assert any(problem in reported for reported in VALIDATE_PROBLEMS)

    def test_it_is_quiet_on_a_clean_figure(self):
        assert [p for p in VALIDATE_PROBLEMS if p.startswith("good")] == []

    def test_it_notes_a_derived_figure_that_prints_estimated(self):
        _, notes = figures.validate(Registry({
            "guess": fig("FE1", value=1),
            "over": fig("FD1", formula="guess * 2")}))
        assert any("over" in note and "estimate" in note for note in notes)


SHAPE_REGISTRY = Registry({
    "a": fig("FM1", value=1, group="totals"),
    "b": fig("FM2", value=2),
    "c": fig("FD1", formula="a + b", group="totals"),
    "refless": {"kind": "M", "value": 3, "source": "s"},
})


class TestRegistryShape:
    def test_by_ref_maps_a_ref_to_a_name_and_skips_a_refless_figure(self):
        index = SHAPE_REGISTRY.by_ref()
        assert index["FD1"] == "c"
        assert None not in index

    def test_groups_follow_the_file_and_the_ungrouped_land_in_inputs(self):
        assert list(SHAPE_REGISTRY.groups()) == ["totals", "inputs"]
        assert SHAPE_REGISTRY.groups()["totals"] == ["a", "c"]

    def test_inputs_lists_what_a_formula_names(self):
        assert sorted(SHAPE_REGISTRY.inputs("c")) == ["a", "b"]
        assert SHAPE_REGISTRY.inputs("a") == []
        with pytest.raises(FigureError, match="unknown figure"):
            SHAPE_REGISTRY.inputs("nope")


class TestCoverage:
    @pytest.mark.parametrize("name, status", [
        ("total", "ok"), ("share", "ok"),
        ("absent", "MISSING"), ("nofile", "NO FILE")])
    def test_each_figure_is_checked_where_it_is_claimed(self, report, name,
                                                        status):
        registry = report()
        rows = {row.name: row.status
                for row in figures.check_coverage(registry,
                                                  registry.resolve())}
        assert rows[name] == status

    def test_a_bare_appears_in_path_is_read_as_one_file(self, report):
        single = Registry({"total": fig("FD1", formula="10 + 4",
                                        appears_in="report.md")},
                          root=report().root)
        assert [row.status for row in
                figures.check_coverage(single, single.resolve())] == ["ok"]


class TestRetired:
    def test_a_superseded_number_is_found_with_its_line_and_replacement(
            self, report):
        registry = report(retired=RETIRED)
        hits = figures.check_retired(registry, registry.documents())
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
        assert (figures.check_retired(registry, registry.documents()) == []
                ) is silenced

    @pytest.mark.parametrize("over, message", [
        ({"retired": ({"why": "oops"},)}, "needs a 'pattern'"),
        ({"retired": RETIRED, "allow": ("$19,460",)}, "must be mappings"),
    ])
    def test_a_malformed_entry_is_named(self, report, over, message):
        registry = report(**over)
        with pytest.raises(FigureError, match=message):
            figures.check_retired(registry, registry.documents())


class TestOrphans:
    def test_a_currency_token_no_figure_claims_is_listed_with_its_lines(
            self, report):
        registry = report()
        orphans = figures.check_orphans(registry, registry.resolve(),
                                        "report.md")
        assert orphans["19,460"] == [2]

    def test_a_missing_file_is_told_from_a_clean_one(self, report):
        registry = report()
        assert figures.check_orphans(registry, registry.resolve(),
                                     "nowhere.md") is None


class TestScan:
    def test_a_file_named_twice_is_read_once_so_marks_are_not_doubled(
            self, scanned):
        registry = Registry(MARKS, root=scanned,
                            scan=("report.md", "*.md", "report.md"))
        assert [d.rel for d in registry.documents()] == ["report.md",
                                                         "execution.md"]
        seen, _ = figures.check_marks(registry, registry.resolve(),
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
        with pytest.raises(FigureError, match="not a usable path"):
            Registry(MARKS, root=scanned, scan=("",)).documents()
        with pytest.raises(FigureError, match="cannot read"):
            figures.read_document(scanned, scanned)

    def test_a_document_is_named_relative_to_the_root(self, scanned):
        assert Registry(MARKS, root=scanned).relative(
            scanned / "report.md") == "report.md"
        assert figures.relative(scanned / "report.md", scanned / "sub") == str(
            Path("..") / "report.md")


class TestLoading:
    def test_the_registry_is_found_by_walking_up(self, tmp_path):
        root = tmp_path / "report"
        nest = root / "executions" / "01-load"
        nest.mkdir(parents=True)
        (root / figures.REGISTRY).write_text(REGISTRY_TEXT)

        found_root, path = figures.find_registry(start=nest)
        assert (found_root, path.name) == (root.resolve(), figures.REGISTRY)
        assert figures.find_registry(
            explicit=root / figures.REGISTRY)[0] == root.resolve()

        registry = Registry.load(start=nest)
        assert registry.resolve()["total"] == 14
        assert registry.root == root.resolve()
        assert registry.scan == ("report.md",)

    @pytest.mark.parametrize("explicit, start, message", [
        (None, "not-a-report", "no figures.yaml"),
        ("nope.yaml", None, "no such registry"),
    ])
    def test_one_that_is_not_there_says_so(self, tmp_path, explicit, start,
                                           message):
        with pytest.raises(FigureError, match=message):
            figures.find_registry(
                explicit=tmp_path / explicit if explicit else None,
                start=tmp_path / start if start else None)

    @pytest.mark.parametrize("text, message", [
        ("figures:\n  a: [oops\n", "not valid YAML"),
        ("", "is empty"),
        ("- a\n- b\n", "must be a mapping"),
        ("meta: {}\n", "no 'figures' mapping"),
        ("figures:\n", "empty 'figures'"),
        ("figures:\n  - a\n  - b\n", "must be a mapping"),
        ("figures:\n  12: {ref: FM1, kind: M, value: 1, source: s}\n",
         "must be strings"),
        ("figures:\n  a: {ref: FM1, kind: M, value: 1, source: s}\n"
         "scan: x.md\n", "must be a list"),
    ])
    def test_a_malformed_one_is_a_figure_error(self, registry_file, text,
                                               message):
        with pytest.raises(FigureError, match=message):
            Registry.load(explicit=registry_file(text))


class TestFileSurgery:
    def test_renumber_follows_file_order_and_is_idempotent(self,
                                                           registry_file):
        path = registry_file()
        assert figures.renumber(path) == {"M": 2, "D": 1}
        registry = Registry.load(explicit=path)
        assert [(n, s.get("ref")) for n, s in registry.figures.items()] == [
            ("alpha", "FM1"), ("beta", "FM2"), ("total", "FD1")]
        assert registry.resolve()["total"] == 14

        before = path.read_text()
        figures.renumber(path)
        assert path.read_text() == before

    def test_retype_moves_one_kind_and_closes_the_refs_up(self, registry_file):
        path = registry_file()
        figures.renumber(path)
        assert figures.retype("beta", "R", path) == {"M": 1, "R": 1, "D": 1}
        registry = Registry.load(explicit=path)
        assert registry.figures["beta"]["kind"] == "R"
        assert [s.get("ref") for s in registry.figures.values()] == [
            "FM1", "FR1", "FD1"]
        assert registry.resolve()["total"] == 14
        assert figures.validate(registry)[0] == []

    @pytest.mark.parametrize("name, kind, message", [
        ("beta", "Z", "kind must be one of"),
        ("nope", "M", "unknown figure"),
    ])
    def test_retype_refuses_what_it_cannot_do(self, registry_file, name, kind,
                                              message):
        with pytest.raises(FigureError, match=message):
            figures.retype(name, kind, registry_file())

    @pytest.mark.parametrize("text, message", [
        ("figures:\n"
         "  alpha: {ref: FM9, kind: M, value: 1, source: s}\n"
         "\n"
         "  beta:\n    ref: FM2\n    kind: M\n    value: 2\n    source: s\n",
         "cannot see"),
        ("figures: {a: {ref: FM1, kind: M, value: 1, source: s}}\n",
         "inline mapping"),
        ("figures:\n  a:\n    ref: FX1\n    kind: X\n    value: 1\n"
         "    source: s\n", "is not one of"),
    ])
    def test_the_rewriter_refuses_and_writes_nothing_rather_than_half_applying(
            self, registry_file, text, message):
        path = registry_file(text)
        with pytest.raises(FigureError, match=message):
            figures.renumber(path)
        assert path.read_text() == text

    def test_renumber_refuses_an_override_naming_no_kind(self, registry_file):
        with pytest.raises(FigureError, match="kind must be one of"):
            figures.renumber(registry_file(), {"alpha": "Z"})

    @pytest.mark.parametrize("alpha", [
        "  alpha:\n    ref: FM1\n    value: 1\n    source: s\n",
        "  alpha:\n    ref: FM1\n    kind: M  # why\n    value: 1\n"
        "    source: s\n",
    ])
    def test_retype_changes_the_figure_it_was_given_not_its_neighbour(
            self, registry_file, alpha):
        path = registry_file("figures:\n" + alpha + "\n"
                             "  beta:\n    ref: FM2\n    kind: M\n"
                             "    value: 2\n    source: s\n")
        figures.retype("alpha", "E", path)
        registry = Registry.load(explicit=path)
        assert registry.figures["alpha"]["kind"] == "E"
        assert registry.figures["beta"]["kind"] == "M"
        assert [s.get("ref") for s in registry.figures.values()] == ["FE1",
                                                                     "FM1"]


class TestCommand:
    def test_a_clean_report_exits_clean(self, reported):
        _, at = reported
        assert run(*at)[0] == 0
        code, out, _ = run(*at, "check")
        assert code == 0
        assert "marked numbers: 1" in out and "coverage: 1/1" in out
        assert run(*at, "validate")[0] == 0

    @pytest.mark.parametrize("wanted", ["total", "FD1"])
    def test_one_figure_prints_its_bare_value(self, reported, wanted):
        assert run(*reported[1], wanted) == (0, "14.00\n", "")

    def test_an_unknown_figure_exits_two_and_says_so(self, reported):
        code, _, err = run(*reported[1], "nope")
        assert code == 2 and "unknown figure" in err

    def test_drift_exits_one_and_names_the_ref(self, reported):
        tmp_path, at = reported
        (tmp_path / "report.md").write_text("the total is 99.00<!--FD1-->\n")
        code, out, _ = run(*at, "check")
        assert code == 1 and "FD1" in out

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
        assert Registry.load(explicit=tmp_path / figures.REGISTRY
                             ).figures["beta"]["ref"] == "FE1"

    @pytest.mark.parametrize("text, message", [
        ("figures:\n  a: [oops\n", "not valid YAML"),
        ("figures:\n  a:\n    ref: FM1\n    kind: M\n    value: ⟨number⟩\n"
         "    source: s\n", "not a number"),
    ])
    def test_a_registry_it_cannot_read_exits_two(self, registry_file, text,
                                                 message):
        code, _, err = run("--path", str(registry_file(text)), "check")
        assert code == 2 and message in err

    def test_a_registry_that_is_not_there_exits_two(self, tmp_path):
        assert run("--path", str(tmp_path / "nope.yaml"), "check")[0] == 2

    def test_renumber_works_on_a_registry_that_does_not_resolve(
            self, registry_file):
        path = registry_file("figures:\n  a:\n    ref: FM1\n    kind: M\n"
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


def test_the_shipped_template_is_a_registry_of_placeholders(registry_file):
    from importlib.resources import files
    path = registry_file((Path(str(files("report_kit"))) / "templates"
                          / "figures.yaml").read_text())
    registry = Registry.load(explicit=path)

    assert {s.get("kind") for s in registry.figures.values()} == set(
        figures.KINDS)
    assert all(figures.REF_RE.match(str(s.get("ref")))
               for s in registry.figures.values())
    assert registry.scan and registry.allow is not None
    with pytest.raises(FigureError, match="is not a number"):
        registry.resolve()
