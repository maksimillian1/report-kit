# 00 · Baseline

- **Purpose:** System at rest — frozen constants, denominator, price basis, metric register, floor.
- **Produces:** Frozen config · Price basis · Metric register · Floor baseline
- **Expected:** ⟨Recorded YYYY-MM-DD before capture: expected floor split and which line dominates⟩
- **Revision:** v⟨n⟩ (supersedes: ⟨v(n-1) · none⟩)
- **Capture Window:** ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen At:** `⟨sha⟩` · by ⟨name⟩
- **Capture Notes:** ⟨Success / Egress spike at 04:00 UTC filtered out as scheduled backup⟩

---

## 1 · Plan

### Preflight Checklist
- [ ] Metric names validated on live endpoints.
- [ ] Every metric returns data with non-empty label dimensions under its selector.
- [ ] Cost attribution tags verified active in IaC (`terraform/`).
- [ ] Price basis captured and saved to `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Fixture profile captured and saved to `./data/⟨name⟩-profile.txt`.
- [ ] Proof of idleness window scheduled (spans daily cycle, zero execution points).

### Baseline Metrics

<!-- Metrics collected, derived, or recorded for this capture. Provenance marks:
     unmarked (measured) · ᴰ derived · ᴿ recorded · ᴱ estimated — `methodology.md` §5. -->

| Ref | What it measures | Formula / name | Provenance | Status | Selector | Inputs / notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | | | Measured | active | | |
| 2 | | | Derived | active | n/a — post-capture | |
| 3 | | | Recorded | active | n/a — hand-recorded at ⟨moment⟩ | |

---

## 2 · Results

### Constants

#### Configuration Freeze
| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| ⟨instance_type⟩ | ⟨c6i.xlarge⟩ | `terraform/main.tf` | Baseline compute tier |

#### Input Fixture (Denominator)
- **Unit of work:** ⟨One sentence: exact moment a unit is complete⟩
- **Exact unit count:** `⟨N⟩` (the denominator for every $/unit figure on this path)
- **Distribution:** median ⟨X⟩ · p95 ⟨Y⟩ · total ⟨Z⟩
- **Profile Source:** `./data/⟨name⟩-profile.txt` frozen at ⟨YYYY-MM-DD⟩ (`⟨sha⟩`)

<!-- A second unit is defined here only for a physically different path (ingestion vs.
     query). Repeat the block; never convert between them — `methodology.md` §5. -->

#### Price Basis
- **Data File:** `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate Type:** EDP / Savings Plan / On-Demand List
- **Region & Currency:** `eu-central-1` · USD

---

### Applicability

* **Platform:** ⟨AWS EKS v1.30, x86_64⟩. Re-measure on: ⟨ARM64 migration, minor K8s upgrade⟩
* **Scale Range:** ⟨0 to 10,000 req/sec⟩. Re-measure on: ⟨Traffic > 10k req/sec⟩
* **Commercial:** ⟨Enterprise Discount Plan 2026⟩. Re-measure on: ⟨Rate card update⟩

---

### Floor

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| ⟨EKS control plane⟩ | A | ⟨73⟩ ᴰ | fixed |
| ⟨⟩ | B | ⟨⟩ | |

- **A · Shared:** ⟨$⟩ — platform lines the subject consumes but does not cause
- **B · Dedicated:** ⟨$⟩ — exists only because the subject does. **The headline**
- **C · Total:** ⟨$⟩ ᴰ — `A + B`, the whole idle bill
- **Reference value:** ⟨always-on alternative · a previously published idle claim⟩
- **Never divided by:** an assumed tenant count — the divisor is invented
- **Raw data:** `./data/idle-⟨YYYY-MM-DD⟩.csv`

---

### Routing

* **Floor block B** → Report §4.1 · BLUF (Status: ⟨Routed⟩)
* **Floor lines** → Report §4.1 (Status: ⟨Routed⟩)
* **Denominator N, unit of work, fixture profile** → Report §2 (Status: ⟨Routed⟩)
* **Applicability** → Report §2 Envelope (Status: ⟨Routed⟩)
* **Price basis** → Report §4.3–4.4, computed there (Status: ⟨Routed⟩)

---

### Retro

- **Expectation vs Reality:** ⟨Held · Inverted — state primary surprise⟩
- **Cost vs Estimate:** ⟨Actual run cost vs budgeted run cost⟩
- **Intentionally Not Observed:** ⟨e.g., Pod-to-Pod Egress excluded — managed via VPC Flow logs to avoid telemetry overhead⟩ → carry to Report Coverage
