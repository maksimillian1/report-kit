# Report Kit — Checklist

`cp checklist.md ../<project>/docs/report/checklist.md`

## Bindings — fill first

| | |
| :--- | :--- |
| System | |
| Commit under test | |
| **Unit of work** | one unambiguous sentence — everything is priced per this |
| **Workload fixture** | corpus / load script / dataset partition — the frozen input |
| **Frontier X axis** | the knob that is swept (workers, RPS, cluster size, GPUs) |
| Cost data source | |
| Report version | v1.0 |

If the unit of work or the fixture cannot be pinned down, stop. Neither the frontier
nor the cost model means anything without them.

**Skip log** — copy into the report's Envelope when done.

| Skipped block | Section affected |
| :--- | :--- |
| | |

---

## A. CORE — never skip

Each item is unrecoverable: miss it and the run must be repeated.

**A1 · Before spending anything**
- [ ] **Cost attribution live** — tags/labels on resources **and** activated in the
  billing system. Activation is a separate step from tagging and applies going
  forward only. Verify on a real resource, not in the plan output.
- [ ] **Commit pinned** — a rebuild mid-benchmark makes a different report
- [ ] **Fixture frozen** — versioned, snapshotted, identical across every run
- [ ] **Fixture profiled** — size/shape distribution recorded → this is the Envelope
- [ ] **Metric export path proven** — pull one dummy window end-to-end and confirm
  non-empty output. Retention is shorter than the writing period

**A2 · Instrumentation, verified against live data**
- [ ] Every constraint-candidate component is scraped and `UP` [→ notes 1].
  An unmeasured component cannot be named as the constraint, and an absent
  series reads as "no load"
- [ ] **Resource-hours reconstructable** [→ notes 2] — billable units by type over
  time, queryable. Run cost is computed from this; billing granularity is too
  coarse for short runs
- [ ] **Short-lived workloads emit a per-execution summary** [→ notes 3] — on every
  exit path including interruption. Verified against one real execution, and
  once against a killed pod

**A3 · Sweep run**
- [ ] **Only the swept parameter changes between points** — same commit, same image,
  same fixture, same cluster shape. A code change mid-sweep invalidates the matrix
- [ ] Clean state between points: queue drained, elastic capacity at zero, no warm
  resources inherited from the previous point
- [ ] Raw series exported per point before retention expires
- [ ] Per point recorded: units/time · wall clock · resource-hours · $/run ·
  $/1M units · saturation signal

**A4 · Idle-floor window** *(passive — start on day one)*
- [ ] ≥24h with zero workload and zero human activity: no deploys, no config changes,
  no manual commands. Continuous reconciliation stays on — it is part of the floor
- [ ] Window spans a full daily cycle (backups, rotations, scheduled jobs)
- [ ] Spend pulled by tag, daily granularity, grouped by component
- [ ] Every line classified **fixed vs variable** — does it exist at zero load?
- [ ] Always-billed lines audited explicitly: control plane, managed service base fees,
  gateways and NAT, private endpoints (per zone), attached storage, load balancers,
  observability stack, snapshots, cross-zone transfer

**A5 · Report integrity**
- [ ] Every number traceable to a file in `docs/report/data/`
- [ ] **Any number not produced by a run is marked** (ᴬ arithmetic · ᴹᵒ modeled ·
  ᴱ estimated). Unmarked = measured, stated once in the header
- [ ] BLUF written **last**; every row carries a reference value; verdict names one action
- [ ] Every guardrail is a config value with a source: `| Guardrail | Value |
  Derived from | Enforced in |`. If it cannot be committed to a file, it is prose
- [ ] Every section yields at least one number reaching BLUF or Guardrails — otherwise cut

---

## B. OPTIONAL — declare the skip

**B1 · Break-even vs alternative** — total cost vs volume, crossover stated.
> Skip → tunes the system, does not justify the architecture. Worst trade in this list: ~2h of arithmetic on data already collected.

**B2 · Amortization curve** — effective $/unit across volumes; where the floor stops dominating.
> Skip → the lower bound of economic validity goes unstated. Pure arithmetic.

**B3 · Failure injection** — inject under real load; compute expected end state first; measure work lost, duplicates, recovery time; price the resilience overhead, never the SLA breach.
> Skip → no Reliability Economics. Acceptable unless resilience was an architectural selling point.

**B4 · Second constraint tier** — with its own proof metric and cost-to-remove.
> Skip → one named constraint. Fine. Never write a speculative third tier.

**B5 · Levers evaluated, including rejected** — effort · Δ throughput · Δ cost · quality price · decision.
> Skip → loses the highest-signal content. Rejected levers are what nobody else publishes.

**B6 · Quality / cost trade-off** — only where savings are bought with accuracy. Ground truth = the uncompressed/unoptimised baseline.
> Skip → N/A for most systems. Mark it N/A rather than omitting silently.

**B7 · Regression vs previous report** — requires `Supersedes` in metadata.
> Skip → unavoidable at v1.0. From v2.0 this becomes the strongest section available.

---

## C. Archive & retro — 20 min

- [ ] Committed: raw exports · plot scripts · cost model with inputs visible ·
  infrastructure values under test
- [ ] Kit improvements ported back to `report-kit` while fresh
- [ ] Which missing item cost the most time?
- [ ] Which run was wasted, and which gate should have caught it?
