# ⟨NN⟩ · ⟨name⟩

- **Why this execution exists:** ⟨The engineering question it answers, in one sentence⟩
- **Produces:** ⟨The finding it exists to yield — or the hypothesis it settles⟩
- **Expected:** ⟨Recorded YYYY-MM-DD before the first run: expected outcome and mechanism⟩
- **Status:** planned · running · closed · abandoned
- **Plan Frozen:** ⟨YYYY-MM-DD⟩ · commit `⟨sha⟩`
- **Inherits:** `00-baseline` (Constants · Metrics · Applicability)
- **Depends On:** ⟨Other executions · none⟩
- **Optional Files:** `./concepts.md` ⟨exists · none⟩ · `./metrics.md` ⟨exists · none⟩

> **§1 Plan is frozen before the first run.** If the outcome inverts the expectation, record
> the inversion in Retro — do not edit the Plan. An expectation written after the result is
> worthless.
>
> **A closed execution is immutable.** A re-run under changed conditions is a new numbered
> execution, not an edit to this one. Even `abandoned`, this execution stays listed in the
> report header.

---

## 1 · Plan

### Givens
*Minimal Profile only. In the Full Profile this block does not exist — givens live in
`00-baseline` §2 and this execution inherits them.*

| Block | Content |
| :--- | :--- |
| Configuration Freeze | ⟨parameter · value · set in · why frozen⟩ |
| Input Fixture | ⟨unit of work · exact count N · distribution · profile file⟩ |
| Price Basis | ⟨data file · rate type · region & currency⟩ |
| Applicability | ⟨platform · scale range · commercial · re-measure triggers⟩ |

### Axis
| Field | Value |
| :--- | :--- |
| Varied Parameter | ⟨Parameter name and location in config/code⟩ |
| Candidate Grid | ⟨e.g., 10, 50, 100, 250, 500 RPS⟩ |
| Sweep Strategy | Coarse-to-fine (3 boundary points first, then internal refinement) |
| Held Constant | ⟨Parameters that must not move during runs⟩ |

### Preflight Checklist
1. [ ] Metric names validated on live endpoints for **every component new to this execution**.
2. [ ] Inherited refs resolve under this run's selector (non-empty series at idle).
3. [ ] Cost attribution tags active for the resources this axis creates.
4. [ ] Abort condition wired to an alert, not to human attention.

### Extended Applicability
| Condition | Active During | Mechanism / Notes |
| :--- | :--- | :--- |
| ⟨e.g., Cold cache baseline⟩ | Point 1 only | Flush Redis before execution → M⟨n⟩ |

### Window & Telemetry Capture
| Boundary | Signal | Triggered / Recorded By |
| :--- | :--- | :--- |
| Opens | ⟨Warmup phase complete / Synthetic traffic start⟩ | Automated script |
| Closes | ⟨Traffic drain / Cooldown complete⟩ | Automated script |

### Metric Reference Gate
*Sets the **per-run selector and gate** only. Inherited refs keep their definition from
`00-baseline/metrics.md` and are never redefined here or in `./metrics.md`. New refs local
to this execution are defined in `./metrics.md`, continuing the global numbering.*

| Metric Ref | Origin | Role in this Run | Run Selector / Filter | Required Gate |
| :--- | :--- | :--- | :--- | :--- |
| E1 | inherited | Primary Load Metric | `{namespace="prod", container="app"}` | Yes |
| E2 | inherited | Cost Boundary Check | `{namespace="prod", container="app"}` | Yes |
| C1 | local | Unit cost formula | n/a — evaluated post-run | Yes |

### Execution Safeguards
- **Estimated Cost / Duration:** ⟨e.g., $12.50 · 45 minutes⟩ ᴱ
- **Abort Condition:** ⟨e.g., Error rate > 1% for 3 consecutive minutes OR Pod OOMKilled⟩

### Target Deliverables
| Target Report Section | Deliverable |
| :--- | :--- |
| Report §3.1 | Throughput vs Unit Cost matrix table |
| Report §3.5 | Primary constraint component identification |

---

## 2 · Journal

> Array of execution runs. Each entry is an immutable record of an execution point,
> accompanied by mandatory post-run validation.

---

### Run ⟨ID⟩ — ⟨Axis Value / Target State⟩

- **Meta:** `⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩` ᴿ · Commit: `⟨sha⟩` · Status: `⟨PASS | INVALID | ABORTED | SATURATED⟩`
- **Setup & Scope:** ⟨Specific override or setup applied before starting this run (e.g., Redis flushed, 500 RPS target)⟩

#### Observations & Field Notes
- ⟨Anomaly, latency behavior, GC pause, or resource saturation observation⟩
- ⟨Mid-run decisions, e.g., aborted at minute 4 due to OOM⟩

#### Post-Run Checklist
- [ ] **Artifacts Exported:** Raw telemetry and logs exported to `./data/run-⟨ID⟩-raw.json`
- [ ] **Window Sanity Check:** No background noise, cron jobs, or egress spikes during the execution window
- [ ] **Saturation Verification:** Primary bottleneck identified or headroom confirmed
- [ ] **Data Provenance Assigned:** Every exported number marked (unmarked / ᴰ / ᴿ / ᴱ)
- [ ] **Verdict:** Point marked `Valid` for Result Matrix (if `No`, state reason and schedule rerun)

---

## 3 · Results

> **Provenance** — unmarked = measured · ᴰ derived · ᴿ recorded · ᴱ estimated
> (`methodology.md` §5). Marks are inline, per cell — one row per measured point.

### Matrix

**Finding:** ⟨One actionable sentence for C-Level / Decision Maker. If two sentences are needed, split into two findings.⟩

| Point ID | Axis Value | Throughput | Latency p95 | Unit Cost ($/1M) | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- |
| P01 | 10 RPS | 600 req/min | 12 ms | $0.15 ᴰ | Yes |

- **Reference Value:** ⟨Target / Alternative / Previous Revision baseline⟩
- **Condition Boundary:** ⟨Holds only under current grid constraints⟩
- **Raw Data Location:** `./data/` · charts rendered to `../../assets/`

---

### Metrics (Local)

> Extract to `./metrics.md` if this block exceeds one screen. **Local refs only** — never
> restate an inherited ref here.

| Ref | Name / Concept | Formula / Calculation | Input Sources | Provenance |
| :--- | :--- | :--- | :--- | :--- |
| C1 | Unit Cost per 1M | `(Total Cost / Executed Units) * 1,000,000` | E1, E4, price basis | Derived |

---

### Saturation Analysis

| Axis Value | Saturating Component | Evidence Metric | Relieved By |
| :--- | :--- | :--- | :--- |
| 500 RPS | Database Connection Pool | `pg_stat_activity` count = max_connections ᴿ | Provisioning PgBouncer |

> *A tier counts as proven only when the previous ceiling was actually relieved and a new
> saturation was observed.*

---

### Guardrails

| Target Configuration | Enforced Value | Derived From | File / Location |
| :--- | :--- | :--- | :--- |
| HPA Max Replicas | 24 | Saturation at 500 RPS | `helm/values.yaml` |

---

### Routing

| Result Item | Target Destination | Status |
| :--- | :--- | :--- |
| Efficiency Knee | Report §3.3 | Routed |
| HPA Guardrail | Report §5 | Routed |
| ⟨Insignificant result⟩ | Report Coverage table | Routed |

---

### Retro

- **Expectation vs Reality:** ⟨Held · Inverted — state primary surprise⟩
- **Cost vs Estimate:** ⟨Actual run cost vs estimated budget⟩
- **Process Improvement:** ⟨What should have been caught in Preflight/Validity checks⟩
