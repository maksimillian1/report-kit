# Executive Engineering Report — <System Name>
[//]: # (metadata block)

| | |
| :--- | :--- |
| Report | `<system>` · v1.0 |
| System under test | commit `<sha>` · <date> |
| Envelope | <workload profile> · <scale range> · <topology> |
| Runs | E1 sweep · E2 idle · E3 chaos |
| Raw data | `docs/benchmarks/` |
| Supersedes | — |

Provenance: ᴹ Measured · ᴬ Arithmetic · ᴹᵒ Modeled · ᴱ Estimated

---

## 1. BLUF
| Metric | Result | Reference |
| :--- | :--- | :--- |
| Unit cost at optimum | $X / 1M units ᴹ | vs $A on <alternative> |
| Idle floor | $Y / month ᴬ | vs $B always-on baseline |
| Peak stable rate | Z units/min at N=<n> ᴹ | knee at N=<m> |
| SLO under load | p95 = W ms @ R RPS ᴹ | target < <target> ms |
| Primary constraint | <component> ᴹ | headroom cost: $C |

**Verdict:** ship / ship with guardrails / do not ship — one sentence, one action.

---

## 2. Workload Contract & Envelope
- **Unit of work:** exact definition. Everything below is priced per this unit.
- **Workload profile:** size distribution, format mix, arrival pattern.
- **Envelope:** conditions under which these numbers hold. Outside it, re-measure.
- **Measurement architecture:** metric sources; blind spots and how they were closed.

---

## 3. Efficiency Frontier
### 3.1 Run matrix
| N | Units/min | Wall time | Node-hours | $/run | $/1M units | Saturation signal |
### 3.2 Chart — throughput (plateau) vs unit cost (U-curve)
### 3.3 Knee · Sweet spot · Waste boundary
### 3.4 Why the cost curve turns back up — the analytical core
### 3.5 Constraint ladder — Tier 1 → Tier 2, each with proof metric and $ to remove
     (promote to its own section only when a third proven tier exists)

---

## 4. Cost Structure
### 4.1 Floor — line by line, marked scales-to-zero yes/no
### 4.2 Marginal — decomposed unit economics at the sweet spot
### 4.3 Amortization — effective $/unit vs monthly volume
### 4.4 Break-even — total cost vs volume against credible alternatives

---

## 5. Guardrails
Enforceable caps in code. Each traceable to a number in §3–4.
| Guardrail | Value | Derived from | Enforced in |

---
--- Tier 1: include only when the material exists ---

## 6. Reliability Economics
Failure injection result · resilience overhead · time-to-recovery.
State recovery time; do not price SLA breach.

## 7. Levers Evaluated
| Lever | Effort | Δ Throughput | Δ Cost | Quality / Risk price | Decision |
Rejected levers included, with the reason.

## 8. Quality / Cost Trade-off
Only for systems where savings are purchased with accuracy.
