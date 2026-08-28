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

- **Hold conditions:** ⟨Dimensions where these figures hold true⟩
- **Re-measure trigger:** ⟨When to discard these results and run again⟩

---

## 3 · Plan

<!-- Frozen before the first run. Metrics are strictly local to this execution. -->

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep strategy** — coarse-to-fine: 3 boundary points, then refinement
- **Held constant** — ⟨what must not move during runs⟩

### Window

- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Execution Metrics

<!-- All metrics collected, derived, or recorded for this specific execution. -->

* **⟨Metric 1⟩:** ⟨What it measures⟩. Source/Formula: ⟨query/math⟩. Gate/Selector: ⟨selector⟩.
* **⟨Metric 2⟩ ᴰ:** ⟨What it measures⟩. Source/Formula: ⟨query/math⟩. Gate/Selector: ⟨selector⟩.
* **⟨Metric 3⟩ ᴿ:** ⟨What it measures⟩. Source/Formula: ⟨query/math⟩. Gate/Selector: ⟨selector⟩.

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 4 · Journal

### Run ⟨ID⟩ — ⟨axis value⟩

- **Meta** — `⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩` ᴿ · commit `⟨sha⟩` · `⟨PASS · INVALID · ABORTED · SATURATED⟩`
- **Setup** — ⟨override applied before this run⟩
- **Observations** — ⟨anomaly · latency behaviour · saturation · mid-run decisions⟩

- [ ] Artifacts exported to `./data/run-⟨ID⟩-raw.json`
- [ ] Window clean — no cron, backup or co-tenant activity
- [ ] Saturation identified or headroom confirmed
- [ ] Every number marked (unmarked / ᴰ / ᴿ / ᴱ)
- [ ] Point valid for the matrix ⟨yes · no + reason⟩

---

## 5 · Results

**Finding:** ⟨one actionable sentence for the decision maker⟩

### Matrix

| Point | Axis value | Throughput | Latency p95 | Unit cost ($/1M) | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | | |

- **Reference value** — ⟨target · alternative · previous revision⟩
- **Condition boundary** — ⟨where it stops holding⟩
- **Raw data** — `./data/`

### Saturation

| Axis value | Saturating component | Evidence metric | Relieved by |
| :--- | :--- | :--- | :--- |
| | | | |

### Guardrails

| Configuration | Enforced value | Derived from | File |
| :--- | :--- | :--- | :--- |
| | | | |

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught in Preflight** — ⟨⟩
