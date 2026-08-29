# report-kit

An engineering report framework for decisions ranging from a single-function app to
multi-execution architecture trade-offs. The reasoning behind it is in `methodology.md`.

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
└── executions/
    ├── 00-baseline/           # 1 Plan · 2 Results
    │   ├── index.md
    │   ├── concepts.md
    │   ├── metrics.md
    │   ├── data/
    │   └── scripts/
    └── 01-⟨name⟩/             # 1 Plan · 2 Journal · 3 Results
        ├── index.md
        ├── concepts.md
        ├── metrics.md
        ├── data/
        └── scripts/
```

---

## Two execution templates

The flows diverge, so the templates are separate files. Do not use one for the other.

* **Minimal (`execution/index.md`)** — 1 Preflight, 2 Givens, 3 Plan, 4 Journal, 5 Results.
  Givens live in §2. Routing targets the report directly.
* **Full (`executions/NN-⟨name⟩/index.md`)** — 1 Plan, 2 Journal, 3 Results. Givens are
  inherited from `00-baseline` §2 and cited from there.

**Migration A → B** is the one operation that rewrites existing files: `execution/` becomes
`executions/00-baseline/` plus `01-⟨name⟩/`, and §2 Givens moves into the baseline. Do it
before the second execution runs.

---

## Order of operations — first revision

Every step below is forward-only: skip it and the figure cannot be reconstructed later
(`methodology.md` §6). Steps 1–6 are preparation, not runs — they produce a freeze commit
and a journal note.

1. **Freeze the system.** Tag the commit under test. Nothing below survives a rebuild.
2. **Confirm metric names against live endpoints.** Date each confirmation in the register.
   An unconfirmed ref cannot appear in a Plan, which makes this the first real gate.
3. **Verify cost attribution tags are active in IaC.** Tagging is forward-only; a tag added
   late yields a partial month and no way to tell which part.
4. **Capture the price basis** → `data/price-⟨date⟩.json`. An undated basis invalidates every
   derived figure downstream.
5. **Freeze the input fixture** → `data/⟨name⟩-profile.txt`, and record the exact unit count.
6. **Write the Expected line**, dated, before the first run — the baseline included.
7. **Capture the floor** over a window with zero execution points. Split A / B / C.
8. **Write the Coverage rows** in `report.md`, statuses left unresolved.
9. **Freeze the first execution's Plan**, then run.

---

## Rules of placement

1. **Is it under test?** No — a given: `00-baseline` §2, or minimal §2. Yes — an axis:
   `NN-⟨name⟩` §1 Plan. Changing a given is preparation, not a run. → §2
2. **Every metric is defined once**, in the execution that uses it, and carries a ref.
   `M` measured · `D` derived · `R` recorded · `E` estimated. No global register, no
   inheritance; cite across executions by path — `00-baseline/M2`. → §2
3. **Why a metric behaves as it does** is not register material — `concepts.md` as `K⟨n⟩`,
   cited from the register's Notes. → §2
4. **Who is the sentence addressed to?** The report's reader → `report.md`. The author filling
   a template → `methodology.md`. An engineer new to the system → `concepts.md`. Templates
   themselves carry placeholders and nothing else. → §13
5. **Executions are units of work; the report is the unit of decision.** Insignificant results
   are carried into Coverage, not deleted. → §3, §11
