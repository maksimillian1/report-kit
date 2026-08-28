# ⟨NN⟩-⟨name⟩

- **Why this execution exists** — ⟨the engineering question it answers⟩
- **Produces** — ⟨the finding it yields, or the hypothesis it settles⟩
- **Expected** — ⟨recorded ⟨date⟩, before the first run: outcome and mechanism⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — Inherited from `00-baseline`

---

## 1 · Plan

### Axis

- **Varied parameter** — ⟨name and location in config/code⟩
- **Candidate grid** — ⟨values⟩
- **Sweep strategy** — coarse-to-fine: 3 boundary points, then refinement
- **Held constant** — ⟨what must not move during runs, beyond inherited givens⟩

### Window

- **Opens** — ⟨signal⟩ · recorded by ⟨⟩
- **Closes** — ⟨signal⟩ · recorded by ⟨⟩

### Metrics

| Ref | Domain | What it measures | Formula / name | Provenance | Status | Inputs / notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| C1 | | | | Derived | active | |
| R1 | | | | Recorded | active | |

### Safeguards

- **Estimated cost / duration** — ⟨⟩ ᴱ
- **Abort condition** — ⟨⟩

---

## 2 · Journal

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

## 3 · Results

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
