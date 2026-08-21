# report-kit

A skeleton for producing an engineering report that a decision maker can act on and an
engineer can reproduce.

The default layout provides a multi-execution structure, designed for systems where the baseline configuration and measured runs are physically separated.

Copy what you need, fill it in, delete the guidance blockquotes as you go.

---

## Installation

Bootstrap the kit directly into your project repository. This approach is stateless and leaves no `.git` history behind. Replace `maksimillian1` with your actual GitHub username.

**Full (Multi-Execution):**
```bash
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/main/bootstrap.sh) docs/report
```

**Minimal (Single Feature):**
```bash
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/main/bootstrap.sh) --minimal docs/report
```

---

## Default Structure: Multi-Execution

This layout protects the baseline. Adding a new execution (e.g., a new architectural module or a different scale) must not rewrite previously frozen givens.

```text
report/
├── report.md                  # ONE report. Decisions. Written last
├── benchmarks/⟨name⟩.md       # overflow from a report section; the regression unit
├── executions/
│   ├── 00-baseline/           # the givens + the floor. Cited by everything
│   │   ├── index.md
│   │   ├── metrics.md         # optional
│   │   ├── data/
│   │   └── scripts/
│   └── 01-⟨name⟩/             # execution under test (index.md, metrics.md, data/, scripts/)
└── scripts/                   # tooling used by more than one execution
```

`00-baseline` is treated as a separate execution. If shared material lived in the first benchmark, adding a second would require editing frozen files.

---

## The one rule that decides where things go

> **Is it under test?**

Not "is it shared", not "is it technical".

| | Example | Home |
| :--- | :--- | :--- |
| **Given** | the embedding model, an instance type, a frozen parameter, the rate card, the input fixture | `00-baseline/index.md` §1–§6 |
| **Measured** | throughput against concurrency, cost per unit, where saturation moved | an execution → a report section |

The moment a given becomes an axis — an execution named *"model A versus model B"* — it leaves the baseline and becomes that execution's input. The winner comes back in the next revision.

---

## One report, many executions

**The report's section list is fixed by the template.** What varies is which sections have material. A report with three of eight sections filled is complete with declared coverage, not a draft.

**An execution is the unit of work, not the unit of publication.** Where its result lands is decided at Close, against the finished report:

| Destination | When |
| :--- | :--- |
| the whole report | it is the only execution |
| a report section, table inline | significant, and it fits |
| a benchmark, cited from a section | too detailed for the report, or needed as the regression unit |
| `00-baseline` sections | it is a given with two or more consumers |
| **nothing** | measured, and insignificant against the rest — or the hypothesis did not hold |

**Benchmarks are overflow, not a layer.** A benchmark makes no recommendations — it is the regression unit. The section citing it keeps the finding, handing over only the tables.

---

## Where data lives

**Inside the execution that produced it.** It is the output of that package. Nothing sits in a shared pool where provenance has to be reconstructed.

**Constants live in the execution that captured them**, dated in the filename: `00-baseline/data/price-2026-08-19.csv`. Downstream cites that path explicitly.

**Scripts split by reuse, not by topic.** Root `scripts/` for cross-execution tools. Execution-local `scripts/` for query files and plotters whose version must stay pinned to the data beside it.

---

## Working order

1. **Freeze the execution's Plan before the first run.** A plan written after the result cannot support a recorded hypothesis.
2. **Fill the coverage register with statuses before measuring.** A row reading *Declared, not measured* is what lets the report ship at partial coverage.
3. **Capture the unrecoverable first** — attribution setup, dated prices, input profile.
4. **Run one execution at a time.** Route its result at Close.
5. **Write `report.md` last**, from finished numbers, and the BLUF last of all.

---

## Scale Down: Start Minimal

If you are evaluating a single feature and a baseline split is overhead paid for nothing, collapse the structure to a single directory.

```text
report/
├── report.md                  # the whole thing, including §2 Envelope
└── execution/
    ├── index.md               # plan · journal · close — instrumentation included
    ├── data/
    └── scripts/
```
