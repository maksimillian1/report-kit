# Methodology

Why the structure is shaped this way. Read once; the templates encode the rest.
Basic filling logic is in `README.md`.

---

## 1. One report, one question

A report is defined by the decision it supports, not by the ground it covers. One subject,
one document, however many executions it took to measure.

The failure mode is splitting it by measurement campaign — "Part 1: ingestion", "Part 2:
queries". Each half then answers half a question, neither is publishable alone, and the
second half never ships. Areas not yet measured belong in the coverage register (§11), not
in a separate document.

**The section list is fixed by the template; what varies is which sections have material.**
A report with three of eight sections filled is a complete report with declared coverage —
not a draft.

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
type, a rate card, an input fixture — all givens. The moment one becomes an axis it leaves
the givens and becomes an execution's input; the winner returns as a given next revision.

**A given never lives in a Plan.** Changing one is preparation — a new freeze commit and a
journal note — not a run. In the full profile givens sit in `00-baseline` §2; in the minimal
profile they get their own section, frozen before the Plan is written.

### The metric register

Every metric is defined **exactly once**, in the execution that uses it, and carries a ref.
There is no shared register and no inheritance: a ref is cited from anywhere by path.

| Ref | Class | Mark on the figure | What `Source` holds |
| :--- | :--- | :--- | :--- |
| `M⟨n⟩` | Measured | *(unmarked)* | the exposed metric name and its selector |
| `D⟨n⟩` | Derived | ᴰ | the formula, written over other refs |
| `R⟨n⟩` | Recorded | ᴿ | the moment it was written down, and by whom |
| `E⟨n⟩` | Estimated | ᴱ | the basis, and the reference value it is judged against |

The letter is the class, so the register needs no provenance column and a row copied into
the report needs no lookup. Numbering is a single sequence per execution — `M1, M2, D3, R4` —
never one counter per letter, so a mistyped letter fails to resolve instead of quietly
naming a second live metric. **A number is never reused**, including by a dropped ref: raw
data files and published revisions already point at it.

Inside its own execution the bare ref is enough. From outside, cite the path:
`00-baseline/M2`, `01-frontier/D6`.

Three rules follow, and they are the whole of the register's discipline:

1. **Name confirmation is the gate.** A target can be up while the string in the table was
   copied from chart documentation — the query then returns nothing on a healthy endpoint,
   and the failure reads as a missing scrape. An `M` ref carries the date its name was
   checked against the live endpoint; until it does, its status is `unconfirmed` and it
   cannot appear in a Plan. Scrape health is transient and belongs to preflight, not here.
2. **Refs are lettered, runs are numbered.** `M4` is a metric; `#04` is a run. One
   identifier never means both.
3. **The register holds no explanations.** Why a series lies, which exporter flag its label
   dimensions depend on, what changed between minor versions — those are mechanisms of the
   system and live in `concepts.md` as `K⟨n⟩`, cited from the register's Notes cell. A
   register that explains itself stops being scannable, which is the only thing it is for.

Two executions may read the same exposed name under different selectors. That is two refs,
not a conflict — each is defined where it is used. The later row names the earlier one in
Notes, so a reader comparing the two figures sees at once that they are not the same number.

---

## 3. An execution is the unit of work, not of publication

Where a result lands is decided at Close, against the finished report:

| Destination | When |
| :--- | :--- |
| the whole report | it is the only execution |
| a report section, table inline | significant, and it fits |
| a benchmark, cited from a section | too detailed for the report, or needed as the regression unit |
| the givens | it is a constant with two or more consumers |
| **nothing** | measured, and insignificant against the rest — or the hypothesis did not hold |

**"Insignificant" is a finding.** A module worth a few percent of cost has earned its way
*out* of an executive report, and the run is what proved it. The record stays in the
execution; the coverage register carries the result so the question is not re-asked next
revision.

**Every execution that ran is named in the report header**, `abandoned` ones included. An
execution that disappears takes with it the evidence that the question was ever asked.

---

## 4. Start minimal, promote on the second consumer

One function, one run, one report is the default shape. Everything else appears when a
second consumer forces it:

| File | Created when |
| :--- | :--- |
| `executions/00-baseline/` | a second execution would copy the system description |
| `executions/NN-⟨name⟩/` | a second execution exists — then numbering |
| `concepts.md` · `metrics.md` | the block outgrows one screen inside `index.md` |
| `assets/` | the first rendered chart exists |

Why shared material cannot simply live in the first benchmark: the second one starts
depending on it, and you cannot add the second without editing something already frozen.
That property — **adding an execution rewrites nothing** — is what the layout protects.

**The single exception is the minimal→full migration.** It happens once, before the second
execution runs, and it is the price of starting minimal. Paying it is still cheaper than
building the full tree for a report that turns out to need one run.

---

## 5. What makes a figure credible

Five properties. A figure missing any of them will be questioned, and the question will be
correct.

**A denominator.** Total spend supports no decision; cost per unit supports several. Choose
the unit once, state the exact moment it counts as done, and never change it.

> **One denominator per cost curve, not per report.** A second unit appears only for a
> physically different path — ingestion priced per document, queries per query. Then each
> unit gets its own contract block and its own tables, and no table, chart or headline row
> mixes them. A conversion between the two is never published: it depends on an arrival
> ratio nobody measured. Two denominators over the *same* path is the actual failure.

**A reference value.** An absolute number decides nothing. Every headline figure carries
something it is compared against — a target, an alternative, a previous revision.

**A boundary.** The conditions under which it holds, stated forward-looking, before anyone
asks. A reader who cannot falsify a number does not trust any number.

**A provenance mark.** Measured is unmarked so the exceptions are visible at a glance: ᴰ
derived, ᴿ recorded, ᴱ estimated. The mark sits on the figure rather than in a column, so a
row copied into the report carries it. In the register the class is already the ref's first
letter (§2); the mark carries it to a reader who will never open a register — which is why
the report states the legend once, in its header, and nowhere else.

**A path to the raw data.** Report → section or benchmark → file under an execution's
`data/`. Always resolvable. A rendered chart names the data file it came from; both are
committed.

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
first run — which is why a Plan is frozen and not edited. This applies to the baseline too:
a floor capture has an expectation, and it is the one most often wrong. If the result inverts
it, the inversion stays in the report. An unrecorded hypothesis lets you rationalise any
outcome, and readers assume you did.

### The run ledger

One row per run, not per point. `#` is the execution sequence — monotonic, never reused, so
a re-run of a point is a new row rather than an edit to the old one. `Point` is the axis
identity, and the same string names the file under `data/` and the row in the results matrix.
Rows sit in the order the runs happened, which under coarse-to-fine is not the order of the
axis.

`Exported` means raw telemetry was written out **before** the retention window expired, and
it is the only column that stops being true on its own. Prose is written only where a run has
something to say; a clean run needs no paragraph.

---

## 7. Sweep coarse to fine

When the finding is a curve, do not sweep linearly. Take the two ends of the range and one
point between them first, then place the rest by the shape those three produce.

| What three points show | What it means |
| :--- | :--- |
| minimum in the middle | refine on both sides |
| minimum on a range boundary | **not proven** — no descending branch on one side |
| still falling at the top | **the range was wrong** — extend it |

A linear sweep spends its whole budget before revealing the last row. Coarse-to-fine reveals
it on the third run, and reads as a refinement pass rather than a mistake.

---

## 8. Constraint ladders

A ladder is the order in which ceilings are hit. A tier counts as proven only when the
previous one was **actually relieved** and a new saturation was then observed — never
because its numbers looked close.

Sweeping the main axis relieves tiers on its own: if component A is the ceiling at low
concurrency, at high concurrency there is more of A and that ceiling is gone. Whatever
saturates instead is a genuinely proven second tier.

**Never claim a tier beyond what was observed.** An unproven tier weakens the tiers that
were proven, and a reader who catches one speculative claim discounts the rest. An unproven
tier is a coverage row, not a paragraph — which is why the templates carry one tier block
and you add the second only after it exists.

---

## 9. Cost has exactly two terms

```
Cost = Floor + ( Marginal_per_unit × Volume )
```

**The floor is measured with the system idle**, and split three ways rather than totalled:

| Block | What it is | Disappears if the subject is deleted |
| :--- | :--- | :--- |
| **A · Shared** | platform lines the subject consumes but does not cause | no |
| **B · Dedicated** | lines that exist only because this subject does — **the headline** | yes |
| **C · Total** | `A + B`, the whole idle bill | — |

B is the number quoted first. A alone inflates it into a platform bill. Dividing A by an
assumed number of co-tenant features is refused: the divisor is invented, and a headline
built on an invented divisor is not defensible against anyone who picks a different one. A
"cost standing alone" figure has the same defect and is not what C means. C is arithmetic
over A and B and therefore carries no line of its own and no fixed/variable attribute.

**The marginal cost excludes every floor line by definition.** Mixing them inflates the
coefficient and silently corrupts any build comparison downstream.

**Amortization is arithmetic, not a run.** The volume at which floor share drops below half
is the lower bound of where the design makes economic sense.

**A build comparison needs the realistic alternative**, not the dramatic one. If the platform
exists regardless, the alternative is a different mode on the same platform.

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

**Scope has exactly one register: the Coverage table.** Measured, derived, declared-not-
measured and out-of-scope are statuses in that one table, not separate sections. A closing
"future work" list is the failure mode: it duplicates the register, drifts out of sync, and
reads as apology rather than as scope. A measurement blind spot is a row here too — an area
the instrumentation could not reach is an area not covered, whatever the reason.

Write the rows **before** measuring and let the statuses resolve at Close. A row reading
*declared, not measured* is what lets a report ship at partial coverage without pretending
to be complete — and what stops the subject from being split into two documents that each
answer half a question. An execution that ran and proved insignificant is a row here too,
with its finding: "measured, contributed under n % of cost, omitted" is a result, and it
stops the question being asked again next revision.

Each row names what the omission would have supported. A reader who sees a deliberate
boundary trusts the inside of it; a reader who discovers an accidental one trusts nothing.

---

## 12. Revisions, not parts

A report is reissued, not extended. Each revision carries `Supersedes` and a one-line
`Changes` summary — the two lines a returning reader actually reads.

**Executions are immutable once closed.** A re-run under changed conditions is a new numbered
execution, never an edit to the old one — the old numbers are what the regression is computed
against, and editing them deletes the comparison. Only the baseline is re-captured in place,
and then as a new revision with its own `Supersedes`.

From the second revision onward, regression against the previous one is usually the strongest
section available. It cannot exist at all in a structure split into parts, because parts are
never compared to each other.

---

## 13. Where a sentence lives

The kit's own failure mode is instruction leaking into the deliverable. One test:

> **Who is this sentence addressed to?**

| Addressed to | Example | Lives in |
| :--- | :--- | :--- |
| the **reader** of the report | how to read a mark, what a status means | `report.md` |
| the **author** filling a template | "write the rows before measuring", "one row per run, not per point" | `methodology.md` |
| an engineer new to the **system** | why a series lies, what an exporter flag changes | `concepts.md` as `K⟨n⟩` |

The report must read as a standalone document. Guidance to the person filling it in is not
part of the argument, and a decision maker who encounters it stops reading the argument and
starts reading the process.

**The templates therefore carry no guidance at all** — not as prose, not as commented-out
prose. A working file holds headings, tables and `⟨angle-bracket⟩` placeholders. Instructions
kept inside the artifact get copied forward, edited into half-truths, and eventually
contradict this file; instructions kept here are read once and stay correct. The rendered
page and the source say the same thing, which is the point.

The legend is the one thing that looks like a note and is not. It tells a reader how to
interpret a number in front of them — the same role as a key on a map. It appears once, in
the report header, in one line.
