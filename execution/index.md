# Execution process

- **Why this execution exists** — ⟨the engineering question it answers⟩
- **Produces** — ⟨the finding it yields, or the hypothesis it settles⟩
- **Expected** — ⟨recorded ⟨date⟩, before the first run: outcome and mechanism⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Givens frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Optional files** — `./concepts.md` ⟨exists · none⟩ · `./metrics.md` ⟨exists · none⟩

---

## 1 · Preflight

- [ ] Every metric name validated on the live endpoint, not from chart docs — gates every figure
- [ ] Every ref returns data with non-empty label dimensions under the intended selector — gates every figure
- [ ] Cost attribution active in IaC; controller-created resources carry the tag — gates every $ figure
- [ ] Retention recorded and shorter than the campaign, so export after every point — gates every point
- [ ] §2 Givens frozen by name and date · run script dry run clean — gates comparability

---

## 2 · Givens

<!-- Frozen before the Plan. Changing one is preparation, not a run: it needs a new freeze
     commit and a note in §4 Journal. Nothing here is under test. -->

### Configuration freeze

| Parameter | Value | Where it is set | Why frozen |
| :--- | :--- | :--- | :--- |
| | | | |

### Input fixture — the denominator

- **Source · snapshot** — ⟨⟩
- **Exact unit count** — ⟨N⟩
- **Distribution** — median ⟨⟩ · p95 ⟨⟩ · total ⟨⟩
- **Unit of work** — ⟨exact moment a unit counts as done⟩
- **Frozen** — ⟨date⟩ · `./data/⟨name⟩-profile.txt`

### Price basis

- **File** — `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩`
- **Rate type** — ⟨list · Savings Plan · EDP⟩
- **Region · currency** — ⟨⟩
- **Covers** — ⟨every resource class any figure will price⟩

### Applicability

<!-- One line per dimension: what it holds for, and what invalidates it. A single shared
     re-measure trigger hides that each dimension has its own. -->

- **Platform** — ⟨⟩. Re-measure on: ⟨⟩
- **Scale range** — ⟨⟩. Re-measure on: ⟨⟩
- **Input** — ⟨the frozen fixture profile⟩. Re-measure on: ⟨⟩
- **Commercial** — ⟨rate type and date⟩. Re-measure on: ⟨⟩

---

## 3 · Plan

<!-- Frozen before the first run. If the outcome inverts the expectation, record it in
     Retro — do not edit this section. -->

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep strategy** — coarse-to-fine: 3 boundary points, then refinement
- **Held constant** — ⟨what must not move during runs⟩

### Window

- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Metrics

<!-- Every metric this execution collects, derives or records. Provenance marks:
     unmarked (measured) · ᴰ derived · ᴿ recorded · ᴱ estimated. -->

| Ref | What it measures | Formula / name | Provenance | Status | Selector | Inputs / notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | | | Measured | active | | |
| 2 | | | Derived | active | n/a — post-run | |
| 3 | | | Recorded | active | n/a — hand-recorded at ⟨moment⟩ | |

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 4 · Journal

<!-- One row per run, not per point. `#` is the execution sequence — monotonic, never
     reused, so a re-run of a point is a new row rather than an edit. Prose only where a
     run has something to say; a clean run needs no paragraph. -->

### Run ledger

| # | Point | Window UTC | Commit | Status | Exported | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ⟨name⟩-⟨value⟩ | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨PASS · SATURATED · ABORTED · INVALID⟩ | ⟨✓⟩ | ⟨✓ · reason⟩ |

Rows are in the order runs happened, which under coarse-to-fine is not the order of the
axis. `Exported` — raw telemetry written to `./data/run-⟨#⟩-⟨point⟩.json` **before** the
retention window expires. `Valid` — carries the reason inline when it is not a tick.

### Notes

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted, a given
re-frozen mid-campaign and at which commit⟩

### Close

- [ ] Every run exported while still inside the retention window
- [ ] Every invalid run carries a reason and a rerun decision
- [ ] Saturation identified, or headroom confirmed at the top of the grid
- [ ] Every number in §5 marked (unmarked / ᴰ / ᴿ / ᴱ)
- [ ] Expectation compared against outcome in Retro, inversion included

---

## 5 · Results

**Finding:** ⟨one actionable sentence for the decision maker⟩ → report §⟨n⟩

### Matrix
| Run | Axis value | Throughput | Latency p95 | Unit cost ($/1M) |
| :--- | :--- | :--- | :--- | :--- |
| | | | | ᴰ |

- **Reference value** — ⟨target · alternative · previous revision⟩
- **Condition boundary** — ⟨where it stops holding⟩
- **Raw data** — `./data/`

### Saturation

<!-- One block per tier actually observed. A tier counts as proven only when the previous
     ceiling was relieved and a new saturation was then observed. Do not add a block for a
     tier you expect but did not see; that is a Coverage row in the report. -->

**Tier 1 — ⟨component⟩ at ⟨axis value⟩, run #⟨n⟩**

- **Evidence** — ⟨metric and the reading that shows the ceiling⟩
- **Relieved by** — ⟨what would remove it, and its cost⟩

### Guardrails

- **⟨config key⟩ = ⟨value⟩** — from ⟨the number in §5 that produced it⟩ · `⟨file⟩` → report §⟨n⟩

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught in Preflight** — ⟨⟩
