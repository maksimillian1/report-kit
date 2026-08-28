# Executive Engineering Report — ⟨System Name⟩

⟨One paragraph: the decision this report supports.⟩

- **Report** — `⟨system⟩` · v⟨n⟩ · ⟨date⟩
- **System under test** — commit `⟨sha⟩` · ⟨date⟩
- **Envelope** — ⟨workload profile⟩ · ⟨scale range⟩ · ⟨topology⟩
- **Executions** — ⟨`00-baseline` · `01-⟨name⟩` · …⟩
- **Raw data** — `executions/⟨…⟩/data/` · charts in `assets/`
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated
- **Supersedes** — ⟨v(n-1) · date · —⟩
- **Changes** — ⟨one line⟩

---

## Coverage

<!-- Rules: methodology.md §11. List items written before measuring; statuses resolve at Close.
     Statuses: measured · derived · declared, not measured · out of scope. -->

* **⟨Area 1⟩:** ⟨Status⟩ — ⟨Evidence link⟩. Cost of absence: ⟨Impact⟩. (Since ⟨Revision⟩)
* **⟨Area 2⟩:** ⟨Status⟩ — ⟨Evidence link⟩. Cost of absence: ⟨Impact⟩. (Since ⟨Revision⟩)

---

## 1. BLUF

<!-- Written last, from finished numbers. Every line carries a reference value. -->

* **Unit cost at optimum:** ⟨$X / 1M units⟩ (vs ⟨$A on alternative⟩)
* **Idle floor (Block B):** ⟨$Y / month⟩ (vs ⟨$B always-on baseline⟩)
* **Peak stable rate:** ⟨Z units/min at N=n⟩ (knee at ⟨N=m⟩)
* **SLO under load:** ⟨p95 = W ms @ R RPS⟩ (target < ⟨target⟩ ms)
* **Primary constraint:** ⟨component⟩ ᴿ (headroom cost ⟨$C⟩ ᴰ)

**Verdict:** ⟨ship · ship with guardrails · do not ship⟩ — one sentence, one action.

---

## 2. Workload Contract & Envelope

<!-- One denominator per cost curve. -->

- **Unit of work** — ⟨definition, including the moment a unit counts as done⟩
- **Workload fixture** — ⟨profile · distribution · arrival pattern · frozen at⟩
- **Envelope** — ⟨conditions under which these numbers hold⟩
- **Measurement architecture** — ⟨metric sources · blind spots and how they were closed⟩

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| N | Units/min | Wall time | Resource-hours | $/run | $/1M units | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | | | |

### 3.2 Chart — throughput plateau vs unit-cost curve

`assets/⟨name⟩.svg` — from `executions/⟨NN⟩/data/⟨file⟩`.

### 3.3 Knee · sweet spot · waste boundary

⟨One sentence: what you pay extra to run at the knee, what throughput you give up at the
sweet spot.⟩

### 3.4 Why the cost curve turns back up

⟨Warm-up share of resource-hours.⟩

### 3.5 Constraint ladder

<!-- A tier counts as proven only when the previous one was relieved and a new saturation
     observed (methodology.md §8). -->

* **Tier 1:** ⟨Component⟩ — Proof metric: ⟨Metric⟩. Cost to remove: ⟨$X⟩.
* **Tier 2:** ⟨Component⟩ — Proof metric: ⟨Metric⟩. Cost to remove: ⟨$Y⟩.

---

## 4. Cost Structure

### 4.1 Floor

<!-- Blocks A shared / B dedicated / C total — methodology.md §9. B is the headline. -->

* **Block A (Shared):** ⟨Line⟩ — ⟨$/month⟩ (Fixed/Variable)
* **Block B (Dedicated):** ⟨Line⟩ — ⟨$/month⟩ (Fixed/Variable)
* **Block C (Total):** ⟨Line⟩ — ⟨$/month⟩ (Fixed/Variable)

### 4.2 Marginal — unit economics at the sweet spot

* **⟨Component 1⟩:** ⟨$/1M units⟩ (⟨Share %⟩)
* **⟨Component 2⟩:** ⟨$/1M units⟩ (⟨Share %⟩)

### 4.3 Amortization — effective $/unit across monthly volumes

⟨Data or short statement⟩

### 4.4 Break-even against ⟨alternative⟩

⟨Crossover volume, stated as a number.⟩

---

## 5. Guardrails

* **⟨Guardrail Name⟩:** ⟨Value⟩ — Derived from ⟨Source⟩. Enforced in ⟨Config/System⟩.

---
<!-- Sections 6-8: include only when the material exists. -->

## 6. Reliability Economics

⟨Failure injection · work lost · duplicates · time to recovery · resilience overhead.⟩

## 7. Levers Evaluated

* **⟨Lever 1⟩:** Effort ⟨Level⟩. Δ Throughput ⟨X⟩. Δ Cost ⟨Y⟩. Quality/risk price ⟨Z⟩. **Decision:** ⟨Action⟩.
* **⟨Lever 2⟩:** Effort ⟨Level⟩. Δ Throughput ⟨X⟩. Δ Cost ⟨Y⟩. Quality/risk price ⟨Z⟩. **Decision:** ⟨Action⟩.

## 8. Quality / Cost Trade-off

⟨Only where savings are purchased with accuracy. Ground truth = the unoptimised baseline.⟩
