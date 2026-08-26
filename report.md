# Executive Engineering Report — ⟨System Name⟩

⟨Description of the decision this report supports.⟩

| | |
| :--- | :--- |
| Report | `⟨system⟩` · v⟨n⟩ · ⟨date⟩ |
| System under test | commit `⟨sha⟩` · ⟨date⟩ |
| Envelope | ⟨workload profile⟩ · ⟨scale range⟩ · ⟨topology⟩ |
| Executions | ⟨`00-system` · `01-⟨name⟩` · …⟩ |
| Raw data | `executions/⟨…⟩/data/` |
| Supersedes | ⟨v(n-1) · date, or —⟩ |
| Changes | ⟨one line — what moved, what did not. From v2 onward⟩ |

> All figures are measured unless marked: ᴬ arithmetic · ᴹᵒ modeled · ᴱ estimated.

---

## Coverage

What this revision measured, what it declares without measuring, and what is out of scope.
A reader who cannot see the boundary of a report cannot trust any number inside it.

| Area | Status | Evidence | Since |
| :--- | :--- | :--- | :--- |
| | | | |

**Measured** — evidence exists and this report cites it · **Derived** — arithmetic on a
measured figure · **Declared, not measured** — named so its absence is visible, scheduled
for a stated revision · **Out of scope** — deliberately not this report's question.

> Fill in the statuses **before** measuring. A row reading *Declared, not measured* is what
> lets the report ship at partial coverage without pretending to be complete — and what
> stops the subject from being split into two documents that each answer half a question.

---

## 1. BLUF

*Conclusion first, evidence after. Written **last**, from finished numbers.*

An absolute number decides nothing. Every row carries a reference value and a plain
sentence saying what it means.

| Metric | Result | Reference | What it means |
| :--- | :--- | :--- | :--- |
| Unit cost at optimum | ⟨$X / 1M units⟩ | vs ⟨$A on alternative⟩ | |
| Idle floor | ⟨$Y / month⟩ ᴬ | vs ⟨$B always-on baseline⟩ | |
| Peak stable rate | ⟨Z units/min at N=n⟩ | knee at ⟨N=m⟩ | |
| SLO under load | ⟨p95 = W ms @ R RPS⟩ | target < ⟨target⟩ ms | |
| Primary constraint | ⟨component⟩ | headroom cost ⟨$C⟩ ᴬ | |

**Verdict:** ship / ship with guardrails / do not ship — one sentence, one action.

---

## 2. Workload Contract & Envelope

- **Unit of work:** exact definition, including the moment a unit counts as done.
  Everything below is priced per this unit. One denominator only.
- **Workload fixture:** what was fed in — profile, distribution, arrival pattern. Frozen
  and identical across all runs.
- **Envelope:** conditions under which these numbers hold. Outside them, re-measure.
  Forward-looking, never an apology.
- **Measurement architecture:** metric sources; blind spots and how they were closed. A
  component that is not observed cannot be named as a constraint.

> When more than one execution shares this material, it moves to
> `executions/00-baseline/` and this section becomes a citation. With a single execution it
> stays here.

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| N | Units/min | Wall time | Resource-hours | $/run | $/1M units | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | | | |

### 3.2 Chart — throughput (plateau) vs unit cost (U-curve)

### 3.3 Knee · Sweet spot · Waste boundary

The gap between the knee and the sweet spot is the finding. State it as a sentence: what
you pay extra to run at the knee, and what throughput you give up at the sweet spot.

### 3.4 Why the cost curve turns back up — warm-up share of resource-hours

Without the mechanism the chart reads as noise.

### 3.5 Constraint ladder

Tier 1 → Tier 2, each with proof metric and cost to remove. A tier counts as proven only
when the previous one was relieved and a new saturation was then observed. Promote to its
own section only when a second tier is proven.

> **If this section outgrows the report** — validity columns, excluded points, per-point
> journals — the tables move to `benchmarks/⟨name⟩.md` and §3 keeps the finding and the
> citation. Detail is the trigger, not structure.

---

## 4. Cost Structure

### 4.1 Floor — line by line, each classified fixed vs variable

Split into shared / dedicated / standalone where the subject runs on infrastructure that
exists anyway. For anything claiming elastic economics the floor is the whole argument.

### 4.2 Marginal — decomposed unit economics at the sweet spot; components sum to total

Floor lines excluded by definition — mixing them corrupts §4.4.

### 4.3 Amortization — effective $/unit across monthly volumes

### 4.4 Break-even — total cost vs volume against credible alternatives; crossovers stated

The alternative is the one a reader would actually consider, not the dramatic one.

---

## 5. Guardrails

A recommendation is prose and gets forgotten. A guardrail is a config value, sourced from a
number in this report, that can be committed to a file.

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| | | | |

Rows whose source number does not survive the runs are deleted, not left blank.

---
--- Tier 1: include only when the material exists ---

## 6. Reliability Economics

Failure injection result · work lost · duplicates · time to recovery · resilience overhead.
State recovery time; do not price SLA breach.

## 7. Levers Evaluated

| Lever | Effort | Δ Throughput | Δ Cost | Quality / risk price | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | | |

Rejected levers included, with the reason. A list of only the accepted ones reads as a
summary of what was done, not as an evaluation.

## 8. Quality / Cost Trade-off

Only where savings are purchased with accuracy. Ground truth = the unoptimised baseline.

---

## Out of scope for this revision

Stated rather than omitted silently, and phrased as scope, not apology.

| Not included | What it would have supported | Why |
| :--- | :--- | :--- |
| | | |

> An execution that ran and turned out insignificant belongs here too — with its finding.
> "Measured, contributed under ⟨n⟩ % of cost, omitted" is a result, and it stops the
> question being asked again next revision.
