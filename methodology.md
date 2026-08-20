# Methodology

Why the structure is shaped this way. Read once; the templates encode the rest.

---

## 1. One report, one question

A report is defined by the decision it supports, not by the ground it covers. One subject,
one document, however many executions it took to measure.

The failure mode is splitting it by measurement campaign — "Part 1: ingestion", "Part 2:
queries". Each half then answers half a question, neither is publishable alone, and the
second half never ships. Areas not yet measured belong in the **coverage register**, not in
a separate document.

**The section list is fixed by the template; what varies is which sections have material.**
That is what the `Tier 1: include only when the material exists` marker means. A report
with three of eight sections filled is a complete report with declared coverage — not a
draft.

| | Report | Article or talk |
| :--- | :--- | :--- |
| Boundary | the whole subject, coverage stated | one finding, told well |
| Audience | decision makers, and the author in a year | the public |
| Lifetime | revisions | once |

The article does not have to cover the whole report, and nobody notices that it did not.
Confusing the two is what turns a finished measurement into an unpublished one.

---

## 2. Given versus measured

The single test that decides where anything lives:

> **Is it under test?**

Not "is it shared", not "is it technical". A model version, a frozen parameter, an instance
type, a rate card, an input fixture — all givens, all in `00-baseline`. The moment one of them
becomes an axis, it leaves that file and becomes an execution's input; the winner returns in
the next revision.

The same seam runs through instrumentation:

| | Belongs to | Because |
| :--- | :--- | :--- |
| What is observable — the exposed metric name, whether it is collected | `00-baseline`, in the component's block | a property of the system, like its version |
| What a run reads — filters, gating, formulas, hand-recorded judgement | that execution | method, and it differs per run |

Configuration and exposed metrics sit in the same block per component, so adding a
component touches one place instead of three.

---

## 3. An execution is the unit of work, not of publication

Where a result lands is decided at Close, against the finished report:

| Destination | When |
| :--- | :--- |
| the whole report | it is the only execution |
| a report section, table inline | significant, and it fits |
| a benchmark, cited from a section | too detailed for the report, or needed as the regression unit |
| `00-baseline` sections | it is a given with two or more consumers |
| **nothing** | measured, and insignificant against the rest — or the hypothesis did not hold |

**"Insignificant" is a finding.** A module worth a few percent of cost has earned its way
*out* of an executive report, and the run is what proved it. The record stays in
`executions/`; the out-of-scope table carries the result so the question is not re-asked
next revision.

**Benchmarks are overflow, not a layer.** A run matrix that fits in §3 stays in §3. It
moves out when it grows validity columns and per-point detail, or when it must be frozen
and compared revision to revision. Two rules once one exists: a benchmark makes no
recommendations — it is the regression unit, and a verdict ages differently from a
measurement; and the section citing it keeps the finding, handing over only the tables.

---

## 4. Start minimal, promote on the second consumer

One function, one run, one report is the default shape:

```
report/
├── report.md
└── execution/{index.md, data/, scripts/}
```

Everything else appears when a second consumer forces it:

| File | Created when |
| :--- | :--- |
| `executions/00-baseline/` | a second execution would copy the system description |

| `benchmarks/⟨name⟩.md` | a section outgrows the report, or regression tracking begins |
| `executions/NN-⟨name⟩/` | a second execution exists — then numbering |

Why shared material cannot simply live in the first benchmark: the second one starts
depending on it, and you cannot add the second without editing something already frozen.
That property — **adding an execution rewrites nothing** — is what the layout exists to
protect.

---

## 5. What makes a figure credible

Five properties. A figure missing any of them will be questioned, and the question will be
correct.

**A denominator.** Total spend supports no decision; cost per unit supports several. Choose
the unit once, state the exact moment it counts as done, and never change it. Two
denominators double every table for a conversion the reader can do themselves.

**A reference value.** An absolute number decides nothing. Every headline figure carries
something it is compared against — a target, an alternative, a previous revision.

**A boundary.** The conditions under which it holds, stated forward-looking, before anyone
asks. A reader who cannot falsify a number does not trust any number.

**A provenance mark.** Measured, arithmetic, modeled or estimated — marked inline, with the
convention stated once. An unmarked derived figure is indistinguishable from a measured
one, and one bad case poisons both.

**A path to the raw data.** Report → section or benchmark → file under an execution's
`data/`. Always resolvable.

---

## 6. Recorded before, not after

Some things cannot be reconstructed once the moment passes. They are the only genuinely
urgent items in any project.

| Class | Why it is unrecoverable |
| :--- | :--- |
| Dated price snapshot | rates change; an undated basis makes every derived figure unverifiable |
| Input profile and exact count | the input can be overwritten and cannot be re-derived from the report |
| Run windows | the backend does not know when a run began; a window guessed later is a different run |
| Saturation judgement | no query returns "component X was the bottleneck" |
| Hypothesis | written afterwards it is worthless, and everyone can tell |
| Attribution setup | usually forward-only, and often delayed by hours |

**The hypothesis rule is the one people skip.** Record what you expect, dated, before the
first run — which is why an execution's Plan is frozen and not edited. If the result
inverts it, the inversion stays in the report: *"we expected to saturate X and saturated Y
instead"* is what makes a measurement credible. An unrecorded hypothesis lets you
rationalise any outcome, and readers assume you did.

---

## 7. Sweep coarse to fine

When the finding is a curve, do not sweep linearly. Three points across the whole range
first, then place the rest by the shape they produce.

| What three points show | What it means |
| :--- | :--- |
| minimum in the middle | refine on both sides |
| minimum on a range boundary | **not proven** — no descending branch on one side |
| still falling at the top | **the range was wrong** — extend it |

A linear sweep spends its whole budget before revealing the last row. Coarse-to-fine
reveals it on the third run, and reads as a refinement pass rather than a mistake.

---

## 8. Constraint ladders

A ladder is the order in which ceilings are hit. A tier counts as proven only when the
previous one was **actually relieved** and a new saturation was then observed — never
because its numbers looked close.

Sweeping the main axis relieves tiers on its own: if component A is the ceiling at low
concurrency, at high concurrency there is more of A and that ceiling is gone. Whatever
saturates instead is a genuinely proven second tier.

**Never claim a tier beyond what was observed.** An unproven tier weakens the tiers that
were proven, and a reader who catches one speculative claim discounts the rest.

---

## 9. Cost has exactly two terms

```
Cost = Floor + ( Marginal_per_unit × Volume )
```

**The floor is measured with the system idle**, split into what is shared with other
workloads and what disappears with this subject. Split rather than totalled: for anything
claiming elastic or scale-to-zero economics, the floor is the entire argument, and it is
where published architectures are least honest.

**The marginal cost excludes every floor line by definition.** Mixing them inflates the
coefficient and silently corrupts any build comparison downstream.

**Amortization is arithmetic, not a run.** The volume at which floor share drops below half
is the lower bound of where the design makes economic sense.

**A build comparison needs the realistic alternative**, not the dramatic one. If the
platform exists regardless, the alternative is a different mode on the same platform.

---

## 10. Guardrails, not recommendations

A recommendation is prose and gets forgotten. A guardrail is a config value, sourced from a
number in the report, that can be committed to a file.

The test: **if it cannot be committed, it does not belong in the table.** Rows whose source
number does not survive the runs are deleted, not left blank.

---

## 11. Declared scope beats silent omission

Every report has boundaries. Stating them is what separates an engineering document from a
student one.

Phrase them as scope, never as apology, and never as a closing "future work" list. Each row
names what the omission would have supported and why it was left out. A reader who sees a
deliberate boundary trusts the inside of it; a reader who discovers an accidental one
trusts nothing.

---

## 12. Revisions, not parts

A report is reissued, not extended. Each revision carries `Supersedes` and a one-line
`Changes` summary — the two lines a returning reader actually reads.

From the second revision onward, regression against the previous one is usually the
strongest section available. It is computed section to section, or benchmark to benchmark
where one exists — and it cannot exist at all in a structure split into parts, because
parts are never compared to each other.
