# report-kit

A flexible engineering report framework for decisions ranging from single-function micro-benchmarks to complex multi-execution architecture trade-offs.

---

## Installation

Stateless bootstrap into your repository:

```bash
# full (multi-execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) docs/report

# minimal (single execution)
bash <(curl -sL https://raw.githubusercontent.com/maksimillian1/report-kit/master/bootstrap.sh) --minimal docs/report
```

---

## Scalability Profiles

Choose structure based on complexity.

### Profile A: Minimal (Single-Function / 1 Execution)
Used for single-purpose benchmarks or localized decisions. Baseline state and experimental
run live within a single execution block. No `00-baseline/` directory created — givens go
into the **§1 Plan › Givens** block of `execution/index.md`.

```text
report/
├── report.md                  # Executive summary & decision
├── methodology.md             # Kit rules
├── assets/                    # Rendered charts (created with the first one)
└── execution/                 # Single combined execution
    ├── index.md               # Plan (incl. Givens) · Journal · Results
    ├── concepts.md            # optional — only if the block outgrows index.md
    ├── metrics.md             # optional — only if the block outgrows index.md
    ├── data/                  # Captured artifacts
    └── scripts/               # Local scripts
```

### Profile B: Full (Multi-Execution System)
Used when multiple executions share common constants, price bases, or infrastructure baseline.

```text
report/
├── report.md                  # Executive report
├── methodology.md             # Kit rules
├── assets/                    # Rendered charts
├── executions/
│   ├── 00-baseline/           # System at rest (NO Journal needed)
│   │   ├── index.md           # 1 · Plan, 2 · Results
│   │   ├── concepts.md        # System mechanisms
│   │   ├── metrics.md         # Global metric register (permanent refs)
│   │   ├── data/
│   │   └── scripts/
│   └── 01-⟨name⟩/             # Active execution under test
│       ├── index.md           # 1 · Plan, 2 · Journal, 3 · Results
│       ├── metrics.md         # optional — LOCAL refs only
│       ├── data/
│       └── scripts/
└── scripts/                   # Shared multi-execution tooling
```

### Orthogonal to both profiles

`benchmarks/⟨name⟩.md` is **not** a property of the profile. It appears in either one, the
moment a report section grows validity columns and per-point detail, or the moment
regression tracking begins. A minimal report can have a benchmark.

### Migrating A → B

Renaming `execution/` into `executions/00-baseline/` + `01-⟨name⟩/` and moving the Givens
block out of the Plan is the **one** operation in this kit that rewrites existing files. Do
it before the second execution runs. Everything after that is additive.

---

## Execution Structure Breakdown

Executions follow a fixed layout depending on whether they are baseline or active tests:

| Target | Structure | Purpose |
| :--- | :--- | :--- |
| `00-baseline` | **2 Sections:**<br>1. Plan<br>2. Results | Capture point-in-time system state at rest. |
| `NN-⟨name⟩` | **3 Sections:**<br>1. Plan<br>2. Journal<br>3. Results | Active experiment. Plan is frozen before execution, Journal captures runtime events, Results exports routed findings. |

Closed executions are **immutable**. A re-run under changed conditions gets a new number;
only `00-baseline` is re-captured in place, as a new revision.

---

## Rules of Placement

1. **Is it under test?**
   - **No (Given/Constant):** `00-baseline` §2 — or, in the Minimal Profile,
     `execution/index.md` §1 › **Givens**.
   - **Yes (Axis/Variable):** active execution `NN-⟨name⟩` §1 Plan.
2. **Metric definition vs. metric usage?**
   - **Definition + exposed name:** `00-baseline/metrics.md`. Refs are permanent, never
     renumbered, never re-listed downstream, never overridden.
   - **Per-run selector, gate, formula:** the execution's §1 Metric Reference Gate; new
     local refs in the execution's own `metrics.md`, continuing the global numbering.
3. **Where does explanation go?**
   - **General framework logic:** `methodology.md`
   - **System mechanisms:** `concepts.md`
   - **Executive findings:** `report.md`
4. **Execution vs Publication:**
   - Executions are units of work. `report.md` is the unit of decision. Insignificant
     results are documented in execution logs and carried into the report's **Coverage**
     table — the single scope register. There is no separate "out of scope" section.
5. **Provenance:** one convention, `methodology.md` §5. Unmarked = measured ·
   ᴰ derived · ᴿ recorded · ᴱ estimated.
