# ⟨NN⟩-⟨name⟩

- **Why this execution exists** — ⟨the engineering question it answers⟩
- **Produces** — ⟨the finding it yields, or the hypothesis it settles⟩
- **Expected** — ⟨recorded ⟨date⟩, before the first run: outcome and mechanism⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — frozen in `00-baseline`, cited from there

---

## 1 · Plan

<!-- Frozen before the first run. If the outcome inverts the expectation, record it in
     Retro — do not edit this section. -->

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep strategy** — coarse-to-fine: 3 boundary points, then refinement
- **Held constant** — ⟨what must not move during runs, beyond inherited givens⟩

### Window

- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Metrics

| Ref | What it measures | Formula / name | Provenance | Status | Selector | Inputs / notes |
|:----| :--- | :--- | :--- | :--- | :--- | :--- |
| M1  | | | Measured | active | | |
| D2  | | | Derived | active | n/a — post-run | |
| R3  | | | Recorded | active | n/a — hand-recorded at ⟨moment⟩ | |

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 2 · Journal

<!-- One row per run, not per point. `#` is the execution sequence — monotonic, never
     reused, so a re-run of a point is a new row rather than an edit. `Point` is the axis
     identity and the name used in ./data/ filenames and in the report. Prose only where a
     run has something to say; a clean run needs no paragraph. -->

### Run ledger

| # | Point | Window UTC | Commit | Status | Exported | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ⟨name⟩-⟨value⟩ | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨PASS · SATURATED · ABORTED · INVALID⟩ | ⟨✓⟩ | ⟨✓ · reason⟩ |

Rows are in the order runs happened, which under coarse-to-fine is not the order of the
axis. `Exported` — raw telemetry written to `./data/run-⟨#⟩-⟨point⟩.json` **before** the
retention window expires. `Valid` — carries the reason inline when it is not a tick.

### Notes

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Every run exported while still inside the retention window
- [ ] Every invalid run carries a reason and a rerun decision
- [ ] Saturation identified, or headroom confirmed at the top of the grid
- [ ] Every number in §3 marked (unmarked / ᴰ / ᴿ / ᴱ)
- [ ] Expectation compared against outcome in Retro, inversion included

---

## 3 · Results

**Finding:** ⟨one actionable sentence for the decision maker⟩ → report §⟨n⟩

### Matrix

<!-- `Run` cites the ledger, so every figure resolves to one window and one commit — which
     is what makes a re-run point unambiguous. Runs marked invalid do not appear here. -->

| Run | Axis value | Throughput | Latency p95 | Unit cost ($/1M) |
| :--- | :--- | :--- | :--- | :--- |
| | | | | ᴰ |

- **Reference value** — ⟨target · alternative · previous revision⟩
- **Condition boundary** — ⟨where it stops holding⟩
- **Raw data** — `./data/`

### Saturation

<!-- One block per tier actually observed. A tier counts as proven only when the previous
     ceiling was relieved and a new saturation was then observed — methodology.md §8.
     Do not add a block for a tier you expect but did not see; that is a Coverage row. -->

**Tier 1 — ⟨component⟩ at ⟨axis value⟩, run #⟨n⟩**

- **Evidence** — ⟨metric and the reading that shows the ceiling⟩
- **Relieved by** — ⟨what would remove it, and its cost⟩

### Guardrails

- **⟨config key⟩ = ⟨value⟩** — from ⟨the number in §3 that produced it⟩ · `⟨file⟩` → report §⟨n⟩

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨⟩
