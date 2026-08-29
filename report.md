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

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| ⟨⟩ | ⟨measured⟩ | ⟨`01-⟨name⟩` §3⟩ | ⟨what this would have supported⟩ | ⟨v1⟩ |
| ⟨⟩ | ⟨declared, not measured⟩ | — | ⟨⟩ | ⟨v1⟩ |
| ⟨⟩ | ⟨out of scope⟩ | — | ⟨⟩ | ⟨v1⟩ |

---

## 1. BLUF

* **Unit cost at optimum** — ⟨$X / 1M units⟩ (vs ⟨$A on alternative⟩)
* **Idle floor, Block B** — ⟨$Y / month⟩ (vs ⟨$B always-on baseline⟩)
* **Peak stable rate** — ⟨Z units/min at N=n⟩ (knee at ⟨N=m⟩)
* **SLO under load** — ⟨p95 = W ms @ R RPS⟩ (target < ⟨target⟩ ms)
* **Primary constraint** — ⟨component⟩ ᴿ (headroom cost ⟨$C⟩ ᴰ)

**Verdict** — ⟨ship · ship with guardrails · do not ship⟩. ⟨One sentence, one action.⟩

---

## 2. Workload Contract & Envelope

- **Unit of work** — ⟨definition, including the moment a unit counts as done⟩
- **Workload fixture** — ⟨profile · distribution · arrival pattern · frozen at ⟨date⟩ `⟨sha⟩`⟩
- **Denominator** — ⟨N⟩, from ⟨`00-baseline` §2⟩
- **Envelope** — ⟨conditions under which these numbers hold⟩
- **Metric sources** — ⟨instruments the figures are read from⟩

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| ⟨Axis⟩ | Units/min | Wall time | Resource-hours | $/run | $/1M units | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨⟩ | | | | ᴰ | ᴰ | ⟨⟩ |

### 3.2 Chart — throughput plateau vs unit-cost curve

`assets/⟨name⟩.svg` — from `executions/⟨NN⟩/data/⟨file⟩`.

### 3.3 Knee · sweet spot · waste boundary

⟨One sentence: what you pay extra to run at the knee, what throughput you give up at the
sweet spot.⟩

### 3.4 Shape of the cost curve

⟨What the curve does past the knee, and the mechanism that produces it.⟩

### 3.5 Constraint ladder

* **Tier 1** — ⟨component⟩. Proof: ⟨metric and reading⟩. Cost to relieve: ⟨$X⟩.

---

## 4. Cost Structure

### 4.1 Floor

| Block | Line | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| **B · Dedicated** | ⟨⟩ | ⟨⟩ | ⟨⟩ |
| A · Shared | ⟨⟩ | ⟨⟩ | ⟨⟩ |
| **C · Total** | `A + B` | ⟨⟩ ᴰ | — |

⟨One sentence: Block B against its reference value.⟩

### 4.2 Marginal — unit economics at the sweet spot

| Component | $/1M units | Share |
| :--- | :--- | :--- |
| ⟨⟩ | ⟨⟩ ᴰ | ⟨%⟩ |

### 4.3 Amortization — effective $/unit across monthly volumes

⟨The volume at which floor share drops below half, and the effective $/unit at two or three
volumes around it.⟩

### 4.4 Break-even against ⟨alternative⟩

⟨Crossover volume, stated as a number.⟩

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| ⟨key⟩ | ⟨⟩ | ⟨§3.1, run #⟨n⟩⟩ | ⟨`file`⟩ |

---

## 6. Reliability Economics

⟨Failure injection · work lost · duplicates · time to recovery · resilience overhead.⟩

## 7. Levers Evaluated

| Lever | Effort | Δ Throughput | Δ Cost | Quality / risk price | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ |

## 8. Quality / Cost Trade-off

⟨Only where savings are purchased with accuracy. Ground truth is the unoptimised baseline.⟩
