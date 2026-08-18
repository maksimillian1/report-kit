# Executive Engineering Report — Methodology

Portable reasoning framework for cost + performance reports. Applies to any system.
`template.md` is the shape; this document is why it has that shape.

---

## Core identity

```
Unit Cost = Infrastructure Spend / Units of Business Work
```

Performance is not a parallel topic to cost — it is the **denominator** of cost.
Throughput has no standalone value in an executive report; it exists only to move this
ratio. This collapses "performance report" and "FinOps report" into one document with
one currency.

**Inclusion filter:** a metric belongs in the report only if it moves $/unit or defends
an SLO. Everything else is lab noise and belongs in the design doc.

---

## Three cost curves — universal across projects

| Curve | Definition | Audience |
| :--- | :--- | :--- |
| **Floor** | Cost at zero load | CFO — what burns on weekends |
| **Marginal** | Cost per unit at the optimum | Product — scales with the business |
| **Ceiling** | Where +100% spend buys <10% work | Architect — where the guardrail goes |

Any system — ingestion, API, ETL, training, multi-tenant — reduces to these three.

---

## BLUF

Bottom Line Up Front (US Army staff writing; equivalent to Minto's Pyramid Principle).
Conclusion and recommendation in the first 3–5 lines, evidence after.

Engineers write chronologically ("we set up X, then ran Y, therefore Z"). Executives
read the first 30 seconds. Inverting that order is the single most visible
Senior → Architect signal in any document.

Rules:
- Numbers, never promises of numbers. A list of what will be measured is a table of
  contents, not a BLUF.
- Every row carries a **reference value**. An absolute number produces no decision:
  "$X per 1M units" is unreadable without "vs $A on the alternative".
- Verdict is one sentence naming one action.
- Written last, from finished numbers.

---

## Two axes, two sections — the most common structural error

Efficiency Frontier and Cost Structure look like one topic cut in half. They are not.

| | Efficiency Frontier | Cost Structure |
| :--- | :--- | :--- |
| X axis | concurrency / parallelism | monthly business volume |
| Who turns the knob | engineer | the business |
| Question | how do we configure it? | should we build it this way at all? |
| Output | marginal cost per unit | break-even vs alternatives |
| Horizon | one run, minutes | a year of ownership |

Linked by one equation — the spine of the report:

```
Monthly Cost = Floor + (Marginal_per_unit × Volume)
                 ↑                ↑
            Cost Structure    Frontier supplies this coefficient
```

Frontier without Cost Structure is tuning with no business meaning.
Cost Structure without Frontier has no coefficient.

---

## The two charts that carry the report

**1. Frontier** — dual axis vs the swept parameter: throughput rising to a plateau,
unit cost as a U-curve. The **knee** (throughput plateaus) and the **sweet spot** (cost
bottoms) are different points. That gap is the finding: most engineers tune to the knee
and never learn that cost minimises earlier.

*Why the cost curve turns back up:* fixed per-unit-of-capacity overhead does not amortize
at high concurrency. Provisioning, image pull and initialisation are billed per node and
produce zero work; consolidation delay adds a paid idle tail. At high N the batch drains
faster, but a larger share of every resource-hour is warm-up. For ephemeral
scale-to-zero workers this is the dominant effect and is rarely quantified.

**2. Break-even** — total monthly cost vs volume, one line per architecture. Each
architecture has a different `Floor + Marginal × V` shape:

| | Floor | Marginal |
| :--- | :--- | :--- |
| FaaS | ~0 | high (billed per invocation, cold init每 call) |
| Always-on | high (capacity burns 24/7) | ~0 (capacity already paid for) |
| Elastic + spot | medium | low |

Crossovers divide the volume axis into **regimes**. The output is a sentence like:
"below ~50k units/month this architecture loses to FaaS; above that it wins with a
widening gap." This is the Principal-level judgement — it honestly bounds the
applicability of your own design — and it is nearly free arithmetic on data already
collected.

If both charts exist, the report is written. No other section compensates for their absence.

---

## Provenance

Reports mix numbers of different strength and readers cannot tell them apart, so they
trust none. Minimal discipline:

> **Unmarked = measured. Anything not produced by a run carries a mark.**
> ᴬ arithmetic (price list × count; dimension × bytes) · ᴹᵒ modeled (extrapolated from
> measured points) · ᴱ estimated (judgement, no data)

State the convention once in the header. Five or six marks in a document read as
precision; marking everything reads as bureaucracy.

Unmarked estimates are the one failure mode that converts a strong report into negative
reputation. Self-marking makes the report unattackable.

---

## Guardrails — the difference from a recommendation

A recommendation is prose. A guardrail is a config value, sourced from a number in the
report, that can be committed to a file.

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Max concurrency | `maxReplicaCount: 6` | §3 sweet spot | `keda/scaledjob.yaml` |
| Memory ceiling | `limits.memory: 2Gi` | §3 peak RSS +30% | `apps/x/deployment.yaml` |
| Backlog alert | `> 5000 for 15m` | §3 drain rate | `prometheus/rules.yaml` |
| Budget alarm | `$<floor × 1.4>` | §4.1 floor | `terraform/budgets.tf` |

Test: if it cannot be committed to a file, it is not a guardrail.

---

## The cutting rule

The report is a tree: BLUF is the root, sections are evidence. **Every section must yield
at least one number that reaches BLUF or Guardrails.** If it yields none, it demonstrates
that you can measure — not that anything was decided. Cut it, or drive it to a guardrail.

This rule is also the defence against grandiosity: the more sections, the more often it fires.

---

## Tier 0 — the non-negotiable minimum

```
Metadata · BLUF · Envelope · Efficiency Frontier · Cost Structure · Guardrails
```

Test: remove any one and the verdict loses its support. Envelope = validity conditions.
Frontier = the coefficient. Cost Structure = the decision. Guardrails = the decision
made executable. None is decorative.

~6–8 pages. Two days on a system that already exists. Repeatable per project.

---

## Growth tiers

**Tier 1 — when the material exists**
- **Reliability Economics** — only where resilience was an architectural decision. One
  injection of the most likely failure, not a chaos programme. The question is not
  "does it survive" but "what does the mechanism cost and what does recovery cost".
- **Levers evaluated, including rejected** — highest-signal content in the report,
  because nobody publishes what they turned down.
- **Quality / cost trade-off** — only where savings are bought with accuracy (ML systems).
  Ground truth is usually your own unoptimised baseline, not a labeled dataset.
- **Second constraint tier** — the ladder is the order in which ceilings are hit. Tier 1
  saturates now; Tier 2 saturates immediately after Tier 1 is relieved. It counts as
  proven only if Tier 1 was actually relieved and a new saturation was observed. Its
  value to an executive: it prices the *next* scaling step, which can be an order of
  magnitude more expensive than the current one.

**Tier 2 — from the second report on the same system**
- **Regression vs previous report.** Requires `Supersedes` in metadata. After two or
  three cycles this becomes the strongest asset available: not "I measured a system"
  but "I managed a system's economics over time".
- Sensitivity analysis; forecast at 10× volume.

---

## Reuse economics

Two experiments and one waiting window produce the entire document:

| Source | Feeds |
| :--- | :--- |
| **E1** sweep over the tuning parameter | Frontier, constraint ladder, marginal cost, BLUF |
| **E2** 24h idle window (passive) | Floor, amortization, break-even |
| **E3** one failure injection | Reliability Economics |

Everything else is derivation. Rule: **any section requiring its own experiment must
justify itself.** This is where reports stay repeatable instead of becoming projects.

---

## Refusals — hold these against pressure

| Never | Why |
| :--- | :--- |
| Speculative third constraint tier | Unproven tiers weaken the proven ones |
| Priced SLA breach | Depends on contracts you don't have. State recovery time; let the reader price it |
| Unmarked non-measured numbers | The one failure mode with negative reputational ROI |
| A closing "future work" / "untested" list | Reads as apology. Same content as a forward-looking Envelope reads as scope discipline |
| Empty table cells | Delete the column, not the content. Four honest columns beat eight with N/A |
| Sections producing no number | Decoration |
| Duplicated architecture description | Link the design doc |
| Carbon footprint, exhaustive instance matrices | Nobody reads them |

**Envelope phrasing** — forward-looking, never apologetic:
> These numbers hold for <profile> at <scale> in <topology>. Outside that, re-measure.

---

## Per-system substitutions

The skeleton does not change. Three things do:

| System type | Unit of work | Frontier X axis | Dominant curve |
| :--- | :--- | :--- | :--- |
| Async ingestion | document / GB | worker concurrency | Floor, Marginal |
| Sync API | request | RPS | Ceiling (overprovisioning), SLO |
| Batch ETL | partition / TB | cluster size | Wall-clock vs cost |
| ML training | experiment | GPU-hours | Ceiling, utilisation |
| Multi-tenant SaaS | tenant | tenants/node | Floor, cost per tenant |

For sync systems the Floor section shrinks and Reliability Economics grows.
For async the Floor dominates — the entire value of the architecture lives there.

---

## Lineage

BLUF (US Army) · Pyramid Principle (Minto/McKinsey) · Theory of Constraints (Goldratt) ·
USE method (Gregg) · Universal Scalability Law (Gunther) · FinOps Foundation unit
economics · SPEC/TPC disclosure rules (the Envelope) · SRE production readiness review
(Guardrails).

The framework is not novel; the **stitching** is. Performance reports stop at the
constraint ladder; FinOps reports start at cost structure and carry no engineering
evidence. Joining them is rare. Cite the lineage in published versions — a report that
names its sources reads as an architect's work.
