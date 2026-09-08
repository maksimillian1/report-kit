# ⟨name⟩

- **Why this execution exists** — ⟨the engineering question it answers⟩
- **Produces** — ⟨the finding it yields, or the hypothesis it settles⟩
- **Expected** — ⟨recorded ⟨date⟩, before the first run: outcome and mechanism⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Givens frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`

---

## 1 · Givens

### System under test

- **Build** — `⟨repo⟩` @ `⟨sha⟩` · ⟨date⟩
- **Topology** — ⟨what is deployed, and what it depends on⟩
- **Deployed by** — ⟨`⟨file⟩` · how it is brought up⟩

| Parameter | Value | Where it is set | Why frozen |
| :--- | :--- | :--- | :--- |
| ⟨⟩ | ⟨⟩ | `⟨file⟩` | ⟨⟩ |

### Workload — the denominator → report §2

- **Unit of work** — ⟨exact moment a unit counts as done⟩
- **Fixture** — ⟨request mix · payload profile · source⟩
- **Exact unit count** — ⟨N⟩
- **Distribution** — median ⟨⟩ · p95 ⟨⟩ · total ⟨⟩
- **Arrival pattern** — ⟨open · closed loop · ramp shape⟩
- **Frozen** — ⟨date⟩ · `./data/⟨name⟩-profile.txt`

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | ⟨⟩ | `⟨metric_name{selector}⟩` | ⟨confirmed YYYY-MM-DD⟩ | ⟨→ K1⟩ |
| M2 | ⟨⟩ | `⟨metric_name{selector}⟩` | unconfirmed | ⟨what blocks it⟩ |
| D3 | ⟨⟩ | `⟨M1 / M2⟩` | active | |
| R4 | ⟨⟩ | hand-recorded at ⟨moment⟩ · ⟨who⟩ | active | |
| E5 | ⟨⟩ | ⟨basis⟩ vs ⟨reference value⟩ | active | |

- **Retention** — ⟨⟩ · campaign length ⟨⟩

### Price basis → report §4

- **File** — `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩`
- **Rate type** — ⟨list · Savings Plan · EDP⟩
- **Region · currency** — ⟨⟩
- **Covers** — ⟨every resource class any figure will price⟩

### Envelope → report §2

- **Platform** — ⟨⟩. Re-measure on: ⟨⟩
- **Scale range** — ⟨⟩. Re-measure on: ⟨⟩
- **Input** — ⟨the frozen fixture profile⟩. Re-measure on: ⟨⟩
- **Commercial** — ⟨rate type and date⟩. Re-measure on: ⟨⟩

### Preflight

- [ ] Every `M` ref confirmed on the live endpoint, not from chart docs — gates every figure
- [ ] Every confirmed ref returns data with non-empty label dimensions under its selector — gates every figure
- [ ] Cost attribution active in IaC; controller-created resources carry the tag — gates every $ figure
- [ ] Retention compared against campaign length; export after every point if shorter — gates every point
- [ ] Load generator and system on separate hosts; generator not the bottleneck — gates every throughput figure
- [ ] Run script dry run clean — gates comparability

---

## 2 · Plan

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep order** — ⟨low end · high end · midpoint⟩, then refinement by the shape
- **Held constant** — ⟨what must not move during runs⟩

### Window

- **Warm-up** — ⟨duration, discarded from every figure⟩
- **Steady state** — ⟨duration each point is held⟩
- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 3 · Journal

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ⟨name⟩-⟨value⟩ | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ |

### Notes

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted, a given
re-frozen mid-campaign and at which commit⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid
- [ ] Every figure in §4 marked (unmarked · ᴰ · ᴿ · ᴱ)
- [ ] Outcome compared against Expected in Retro, inversion included

---

## 4 · Results

**Finding** — ⟨one actionable sentence for the decision maker⟩ → report §⟨n⟩

### Matrix

| Run | ⟨Axis⟩ | ⟨Unit⟩/sec | p95 ms | Errors % | $/1M ⟨unit⟩ | Signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨#01⟩ | ⟨⟩ | | | | ⟨⟩ ᴰ | ⟨⟩ |

- **Cost formula** — ⟨resource-hours × price basis ÷ units⟩
- **Reference value** — ⟨SLO target · alternative · previous revision⟩
- **Condition boundary** — ⟨where it stops holding⟩
- **Raw data** — `./data/`

### Saturation

**Tier 1 — ⟨component⟩ at ⟨axis value⟩, run #⟨n⟩**

- **Evidence** — ⟨metric and the reading that shows the ceiling⟩
- **Relieved by** — ⟨what would remove it, and its cost⟩

### Guardrails

- **⟨config key⟩ = ⟨value⟩** — from ⟨the figure in §4 that produced it⟩ · `⟨file⟩` → report §⟨n⟩

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught in Preflight** — ⟨⟩
