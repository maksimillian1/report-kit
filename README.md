# report-kit

An engineering report framework for decisions ranging from simple single-function app
to multi-execution architecture trade-offs.
The reasoning behind it is in `methodology.md`.

---

## Installation

```bash
# full (multi-execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) docs/report

# minimal (single execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) --minimal docs/report
```

---

## Profiles

### A · Minimal — one execution

```text
report/
├── report.md
├── methodology.md
├── assets/                    # created with the first rendered chart
└── execution/
    ├── index.md               # 1 Preflight · 2 Givens · 3 Plan · 4 Journal · 5 Results
    ├── concepts.md            # optional — when the block outgrows index.md
    ├── metrics.md             # optional — when the register outgrows index.md
    ├── data/
    └── scripts/
```

### B · Full — 2+ executions

```text
report/
├── report.md
├── methodology.md
├── assets/
├── executions/
│   ├── 00-baseline/           # 1 Plan · 2 Results
│   │   ├── index.md
│   │   ├── concepts.md
│   │   ├── metrics.md         
│   │   ├── data/
│   │   └── scripts/
│   └── 01-⟨name⟩/             # 1 Plan · 2 Journal · 3 Results
│       ├── index.md
│       ├── metrics.md         
│       ├── data/
│       └── scripts/
└── scripts/
```
---

## Two execution templates

The flows diverge, so the templates are separate files. Do not use one for the other.

* **Minimal (`execution/index.md`)**: Sections are 1 Preflight, 2 Givens, 3 Plan, 4 Journal, 5 Results. Metric registers are local in §2 or `metrics.md`. Routing directly targets the main report.
* **Full (`executions/NN-⟨name⟩/index.md`)**: Sections are 1 Plan, 2 Journal, 3 Results. Givens inherited from `00-baseline`. Routing goes to specific report sections.

**Migration A → B** is the one operation that rewrites existing files: `execution/` becomes
`executions/00-baseline/` plus `01-⟨name⟩/`, and §2 Givens moves into the baseline. Do it
before the second execution runs.

---

## Rules of placement

1. **Is it under test?**
   - No — a given. `00-baseline` §3, or minimal §2 Givens. Never in a Plan: changing a given
     is preparation, not a run.
   - Yes — an axis. `NN-⟨name⟩` §1 Plan, or minimal §3 Plan.
2. **Metric definition or metric usage?**
   - All metrics are flat, selected, planned, and populated within a specific execution.
   - A portion of these execution metrics makes it to the final report; others serve as the base for derived metrics.
   - Why a metric behaves the way it does → `concepts.md`.
3. **Where does a explanation go?** By who it addresses:
   - the **reader** of the report → stays in `report.md`
   - the **author** filling a template → `methodology.md`, or an HTML comment in the template
   - a mechanism of the **system** → `concepts.md` as `M⟨n⟩`
4. **Execution vs publication.** Executions are units of work; `report.md` is the unit of
   decision. Insignificant results are carried into the report's Coverage section.
