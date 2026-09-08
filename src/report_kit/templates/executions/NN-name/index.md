# ⟨NN⟩-⟨name⟩

- **Why this execution exists** — ⟨the engineering question it answers⟩
- **Produces** — ⟨the finding it yields, or the hypothesis it settles⟩
- **Expected** — ⟨recorded ⟨date⟩, before the first run: outcome and mechanism⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there

---

## 1 · Plan

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep order** — ⟨low end · high end · midpoint⟩, then refinement by the shape
- **Held constant** — ⟨what must not move during runs, beyond inherited givens⟩

### Window

- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | ⟨⟩ | `⟨metric_name{selector}⟩` | ⟨confirmed YYYY-MM-DD⟩ | ⟨→ K1⟩ |
| D2 | ⟨⟩ | `⟨M1 / 00-baseline/M4⟩` | active | |
| R3 | ⟨⟩ | hand-recorded at ⟨moment⟩ · ⟨who⟩ | active | |

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 2 · Journal

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ⟨name⟩-⟨value⟩ | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ |

### Notes

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] Every figure in §3 marked (unmarked · ᴰ · ᴿ · ᴱ).
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one actionable sentence for the decision maker⟩ → report §⟨n⟩

### Matrix

| Run | ⟨Axis⟩ | Units/min | Wall time | Resource-hours | $/run | $/1M units | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨#01⟩ | ⟨⟩ | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ |

- **Reference value** — ⟨target · alternative · previous revision⟩
- **Condition boundary** — ⟨where it stops holding⟩
- **Raw data** — `./data/`

### Saturation

**Tier 1 — ⟨component⟩ at ⟨axis value⟩, run #⟨n⟩**

- **Evidence** — ⟨metric and the reading that shows the ceiling⟩
- **Relieved by** — ⟨what would remove it, and its cost⟩

### Guardrails

- **⟨config key⟩ = ⟨value⟩** — from ⟨the figure in §3 that produced it⟩ · `⟨file⟩` → report §⟨n⟩

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨⟩
