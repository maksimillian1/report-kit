# 00 · Baseline

- **Purpose:** System at rest — inherited constants, denominator, price basis, metric register, floor.
- **Produces:** Frozen config · Price basis · Metric register · Floor baseline
- **Revision:** v⟨n⟩ (supersedes: ⟨v(n-1) · none⟩)
- **Capture Window:** ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen At:** `⟨sha⟩` · by ⟨name⟩
- **Capture Notes:** ⟨Success / Egress spike at 04:00 UTC filtered out as scheduled backup⟩

---

## 1 · Plan

### Preflight Checklist
1. [ ] Metric names validated on live endpoints against `./metrics.md`.
2. [ ] Cost attribution tags verified active in IaC (`terraform/`).
3. [ ] Price basis captured and saved to `./data/price-⟨YYYY-MM-DD⟩.json`.
4. [ ] Fixture profile captured and saved to `./data/⟨name⟩-profile.txt`.
5. [ ] Proof of idleness window scheduled (spans daily cycle, zero execution points).

### Deliverables
- **§2 Workload Contract:** Unit of work definition, fixture profile, applicability boundary.
- **§4.1 Floor:** Split A (Shared) / B (Dedicated) / C (Standalone).
- **§4.3–4.4 Cost Analysis:** Price basis for amortization and break-even.

---

## 2 · Results

> **Provenance Legend:**
> **Measured** (read from instrument) · **Derived** (arithmetic on other rows) · **Recorded** (hand-written at the time) · **Estimated** (modeled, carries reference value).

### Constants

#### Configuration Freeze
| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| ⟨instance_type⟩ | ⟨c6i.xlarge⟩ | `terraform/main.tf` | Baseline compute tier |

#### Input Fixture (Denominator)
- **Unit of work:** ⟨One sentence: exact moment a unit is complete⟩
- **Exact unit count:** `⟨N⟩` (The single denominator for all $/unit calculations)
- **Distribution:** median ⟨X⟩ · p95 ⟨Y⟩ · total ⟨Z⟩
- **Profile Source:** `./data/⟨name⟩-profile.txt` frozen at ⟨YYYY-MM-DD⟩ (`⟨sha⟩`)

#### Price Basis
- **Data File:** `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate Type:** EDP / Savings Plan / On-Demand List
- **Region & Currency:** `eu-central-1` · USD

---

### Metrics

See metrics definition in [`./metrics.md`](./metrics.md).

---

### Applicability

| Dimension | Scope Boundaries | Re-measure Trigger |
| :--- | :--- | :--- |
| Platform | AWS EKS v1.30, x86_64 | ARM64 migration, minor K8s upgrade |
| Scale Range | 0 to 10,000 req/sec | Traffic > 10k req/sec |
| Commercial | Enterprise Discount Plan 2026 | Rate card update |

---

### Routing

| Result | Target Section | Status |
| :--- | :--- | :--- |
| Floor Cost B | Report §4.1 | Routed |
| Denominator N | Report §2 | Routed |

---

### Retro

- **Expectation vs Reality:** ⟨Held · Inverted — state primary surprise⟩
- **Cost vs Estimate:** ⟨Actual run cost vs budgeted run cost⟩
- **Intentionally Not Observed:** ⟨e.g., Pod-to-Pod Egress excluded — managed via VPC Flow logs to avoid telemetry overhead⟩
