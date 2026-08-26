# report-kit

A skeleton for producing an engineering report that a decision maker can act on and an
engineer can reproduce.

Copy what you need, fill it in, delete the guidance blockquotes as you go.

---

## Installation

Stateless bootstrap into your repository, leaving no `.git` history behind. Replace
`maksimillian1` with your GitHub username.

```bash
# full (multi-execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) docs/report

# minimal (single execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) --minimal docs/report
```

---

## Structure

```text
report/
├── report.md                  # ONE report. Decisions. Written last
├── methodology.md             # the kit's rules — cited, never restated
├── benchmarks/⟨name⟩.md       # overflow from a report section; the regression unit
├── executions/
│   ├── 00-baseline/           # the system at rest. Cited by everything
│   │   ├── index.md           # Plan · Journal · Results
│   │   ├── concepts.md        # optional — mechanisms, in plain words
│   │   ├── metrics.md         # optional — the Metrics block, extracted
│   │   ├── data/
│   │   └── scripts/
│   └── 01-⟨name⟩/             # execution under test — same three sections
└── scripts/                   # tooling used by more than one execution
```

**Every execution has the same three sections**, baseline included:

| Section | Answers | Written |
| :--- | :--- | :--- |
| 1 · Plan | what will be done, read and held constant | before the first action, then frozen |
| 2 · Journal | what actually happened, point by point | during |
| 3 · Results | what leaves this execution | at close |

Baseline is not an exception to the shape — it is the case with no axis. Its Plan is what
must exist before anything runs, its Journal is the idle window, its Results are the
constants, the metric register and the floor.

---

## The one rule that decides where things go

> **Is it under test?**

Not "is it shared", not "is it technical".

| Kind | Example | Home |
| :--- | :--- | :--- |
| Given | the model, an instance type, a frozen parameter, the rate card, the fixture | `00-baseline` §3 Constants |
| Measured | throughput against an axis, cost per unit, where saturation moved | an execution §3 → a report section |

The moment a given becomes an axis — an execution named *"model A versus model B"* — it
leaves the baseline and becomes that execution's input. The winner returns next revision.

---

## The second rule: where a *why* goes

The file that gets bloated is always the one doing another file's job.

| Kind of explanation | Home | Test |
| :--- | :--- | :--- |
| True on any project, input and platform | `methodology.md` | it is a kit rule — cite it, never restate it |
| True only for this system: a term, a mechanism, a number nobody chose directly | that execution's `concepts.md` | strip every value out of it and it still reads |
| Written for the report's reader | `report.md` | duplication with an execution is intended — different audience |
| Already true of the codebase: component versions, placement, topology | the repository's own docs | if `git log` can answer it, the report does not repeat it |

**`index.md` states values. `concepts.md` explains mechanisms.** They do not overlap by
construction, which is what stops them drifting apart across revisions. A row carries
`→ M⟨n⟩` where its explanation lives. **Anything that fits in one table cell stays there.**

---

## Refs

| Ref | Means | Scope |
| :--- | :--- | :--- |
| `E⟨n⟩` | an exposed metric — a property of the system | global |
| `M⟨n⟩` | a concept needing a paragraph | execution-local, cited as `00-baseline M3` |

| Source column | Means |
| :--- | :--- |
| measured | read from an instrument during a window |
| derived | arithmetic on other rows — the formula is in Metrics |
| recorded | written down by hand at the time; nothing else produces it |
| estimated | neither measured nor derived — carries its own reference value |

Refs are permanent. A retired metric keeps its number and gains a status, so links from
older revisions resolve. **Runs are named, metrics are numbered** — never let one identifier
mean both.

---

## §3 is a catalogue, not a fixed list

Blocks are chosen per execution. Absent blocks are deleted, not left empty.

| Block | Include when |
| :--- | :--- |
| Constants | this execution froze values other executions inherit |
| Matrix | there is an axis with points |
| Metrics | any figure is arithmetic on another, or the floor was measured |
| Saturation | a component was observed at its ceiling |
| Applicability | this execution sets or narrows the conditions figures hold under |
| Guardrails | a number came out that can be committed to a config file |
| Routing · Open · Retro | always |

---

## Start with one file, add on the second consumer

`index.md` is the default and is often the whole thing. Everything else appears when
something forces it, never in advance. An empty optional file is worse than a missing one:
it invites filling.

| File | Created when |
| :--- | :--- |
| `concepts.md` | an explanation needs a paragraph, and a second section cites it |
| `metrics.md` | the Metrics block stops fitting on one screen |
| `benchmarks/⟨name⟩.md` | a report section outgrows the report, or regression tracking begins |
| `executions/NN-⟨name⟩/` | a second execution exists — then numbering |

---

## One report, many executions

**The report's section list is fixed by the template.** What varies is which sections have
material. A report with three of eight sections filled is complete with declared coverage,
not a draft.

**An execution is the unit of work, not the unit of publication.** Where its result lands is
decided in Routing, against the finished report:

| Destination | When |
| :--- | :--- |
| the whole report | it is the only execution |
| a report section, table inline | significant, and it fits |
| a benchmark, cited from a section | too detailed for the report, or needed as the regression unit |
| `00-baseline` | it is a given with two or more consumers |
| **nothing** | measured, and insignificant against the rest — or the expectation did not hold |

**Benchmarks are overflow, not a layer.** A benchmark makes no recommendations — it is the
regression unit. The section citing it keeps the finding, handing over only the tables.

---

## Where data lives

**Inside the execution that produced it** — it is that package's output. Nothing sits in a
shared pool where provenance has to be reconstructed.

**Constants live in the execution that captured them**, dated in the filename:
`00-baseline/data/price-2026-08-19.csv`. Downstream cites that path explicitly.

**Scripts split by reuse, not by topic.** Root `scripts/` for cross-execution tools;
execution-local `scripts/` for query files and plotters pinned to the data beside them.

---

## Working order

1. **Freeze the execution's Plan before the first run.** A plan written after the result cannot support a recorded hypothesis.
2. **Fill the coverage register with statuses before measuring.** A row reading *Declared, not measured* is what lets the report ship at partial coverage.
3. **Capture the unrecoverable first** — attribution setup, dated prices, input profile.
4. **Run one execution at a time.** Route its result at Close.
5. **Write `report.md` last**, from finished numbers, and the BLUF last of all.

---

## Minimal structure

Collapse to a single directory, if a baseline split is overhead.

```text
report/
├── report.md
├── methodology.md
└── execution/
    ├── index.md               # Plan · Journal · Results
    ├── data/
    └── scripts/
```
