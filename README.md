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
Used for single-purpose benchmarks or localized decisions. Baseline state and experimental run live within a single execution block. No `00-baseline/` directory created.

```text
report/
├── report.md                  # Executive summary & decision
├── methodology.md             # Kit rules
└── execution/                 # Single combined execution
    ├── index.md               # Plan · Journal · Results
    ├── data/                  # Captured artifacts
    └── scripts/               # Local scripts
```

### Profile B: Full (Multi-Execution System)
Used when multiple executions share common constants, price bases, or infrastructure baseline.

```text
report/
├── report.md                  # Executive report
├── methodology.md             # Kit rules
├── benchmarks/⟨name⟩.md       # Overflow regression tables
├── executions/
│   ├── 00-baseline/           # System at rest (NO Journal needed)
│   │   ├── index.md           # 1 · Plan, 2 · Results
│   │   ├── concepts.md        # System mechanisms
│   │   ├── metrics.md         # Exposed metric definitions
│   │   ├── data/
│   │   └── scripts/
│   └── 01-⟨name⟩/             # Active execution under test
│       ├── index.md           # 1 · Plan, 2 · Journal, 3 · Results
│       ├── data/
│       └── scripts/
└── scripts/                   # Shared multi-execution tooling
```

---

## Execution Structure Breakdown

Executions follow a fixed layout depending on whether they are baseline or active tests:

| Target | Structure | Purpose                                                                                                               |
| :--- | :--- |:----------------------------------------------------------------------------------------------------------------------|
| `00-baseline` | **2 Sections:**<br>1. Plan<br>2. Results | Capture point-in-time system state at rest.                                                                           |
| `NN-⟨name⟩` | **3 Sections:**<br>1. Plan<br>2. Journal<br>3. Results | Active experiment. Plan is frozen before execution, Journal captures runtime events, Results exports routed findings. |

---

## Rules of Placement

1. **Is it under test?**
    - **No (Given/Constant):** Belongs to `00-baseline` §2 (or `execution/index.md` §1 in Minimal Profile).
    - **Yes (Axis/Variable):** Belongs to active execution `NN-⟨name⟩` §1 Plan.
2. **Where does explanation go?**
    - **General framework logic:** `methodology.md`
    - **System mechanisms:** `concepts.md`
    - **Executive findings:** `report.md`
3. **Execution vs Publication:**
    - Executions are units of work. `report.md` is the unit of decision. Insignificant execution results are documented in execution logs but omitted or routed to "Out of scope" in `report.md`.
