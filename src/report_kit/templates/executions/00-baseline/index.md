# 00 · Baseline

- **Purpose** — system at rest: frozen constants, denominator, price basis, metric register, floor
- **Produces** — frozen config · price basis · metric register · floor baseline
- **Expected** — ⟨recorded ⟨date⟩, before capture: expected floor split and which line dominates⟩
- **Revision** — v⟨n⟩ (supersedes ⟨v(n-1) · none⟩)
- **Capture window** — ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen at** — `⟨sha⟩` · by ⟨name⟩
- **Capture notes** — ⟨success · anomaly and how it was treated⟩

---

## 1 · Plan

### Preflight

- [ ] System frozen at a tagged commit.
- [ ] Every `M` ref confirmed against a live endpoint and dated in the register.
- [ ] Every confirmed ref returns data with non-empty label dimensions under its selector.
- [ ] Cost attribution tags verified active in IaC (`terraform/`).
- [ ] Price basis captured → `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Fixture profile captured → `./data/⟨name⟩-profile.txt`.
- [ ] Idle window scheduled: spans a full daily cycle, zero execution points.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | ⟨⟩ | `⟨metric_name{selector}⟩` | ⟨confirmed YYYY-MM-DD⟩ | ⟨→ K1⟩ |
| D2 | ⟨⟩ | `⟨M1 / …⟩` | active | |
| R3 | ⟨⟩ | hand-recorded at ⟨moment⟩ · ⟨who⟩ | active | |
| E4 | ⟨⟩ | ⟨basis⟩ vs ⟨reference value⟩ | active | |

---

## 2 · Results

### Configuration freeze

| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| ⟨instance_type⟩ | ⟨c6i.xlarge⟩ | `terraform/main.tf` | ⟨baseline compute tier⟩ |

### Input fixture — the denominator → report §2

- **Unit of work** — ⟨one sentence: the exact moment a unit is complete⟩
- **Exact unit count** — `⟨N⟩`
- **Distribution** — median ⟨X⟩ · p95 ⟨Y⟩ · total ⟨Z⟩
- **Profile source** — `./data/⟨name⟩-profile.txt`, frozen ⟨YYYY-MM-DD⟩ (`⟨sha⟩`)

### Price basis → report §4.3–4.4

- **Data file** — `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate type** — ⟨EDP · Savings Plan · On-Demand list⟩
- **Region & currency** — `⟨eu-central-1⟩` · ⟨USD⟩

### Envelope → report §2

- **Platform** — ⟨AWS EKS v1.30, x86_64⟩. Re-measure on ⟨ARM64 migration, minor K8s upgrade⟩
- **Scale range** — ⟨0 to 10,000 req/sec⟩. Re-measure on ⟨traffic above 10k req/sec⟩
- **Commercial** — ⟨Enterprise Discount Plan 2026⟩. Re-measure on ⟨rate card update⟩

### Floor → report §4.1

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| ⟨EKS control plane⟩ | A | ⟨73⟩ ᴰ | fixed |
| ⟨⟩ | B | ⟨⟩ | ⟨⟩ |

- **A · Shared** — ⟨$⟩
- **B · Dedicated** — ⟨$⟩ → report §1 BLUF
- **C · Total** — ⟨$⟩ ᴰ
- **Reference value** — ⟨always-on alternative · a previously published idle claim⟩
- **Raw data** — `./data/idle-⟨YYYY-MM-DD⟩.csv`

### Retro

- **Expectation** — ⟨held · inverted, state the surprise⟩
- **Cost against estimate** — ⟨actual vs budgeted capture cost⟩
- **Not observed** — ⟨line and why⟩ → report Coverage
