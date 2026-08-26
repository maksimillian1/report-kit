# ⟨NN⟩ · ⟨name⟩

| Field | Value |
| :--- | :--- |
| Why this execution exists | ⟨the engineering question it answers, in one sentence⟩ |
| Produces | ⟨the finding it exists to yield — or, if it may yield none, the question it settles⟩ |
| Expected *(recorded ⟨date⟩, before the first point)* | ⟨what you expect and why. If it inverts, the inversion goes into the report verbatim⟩ |
| Status | ⟨planned · running · closed · abandoned⟩ |
| Plan frozen | ⟨date⟩ · commit ⟨sha⟩ |
| Inherits | `00-baseline` — Constants · Metrics · Applicability |
| Depends on | ⟨other executions · none⟩ |
| Optional files | `./concepts.md` ⟨exists · none⟩ · `./metrics.md` ⟨exists · none⟩ |

> **§1 is frozen before the first point and is not edited afterwards.** If it turns out
> wrong, say so in Retro — do not rewrite the Plan. An expectation written after the result
> is worthless, and every reader can tell.

---

# 1 · Plan  *(frozen ⟨date⟩)*

## Axis

| Field | Value |
| :--- | :--- |
| Varied | ⟨parameter, and where it is set⟩ |
| Candidate grid | ⟨list⟩ |
| Order | ⟨coarse to fine: three points across the range, then place the rest by the shape they produce⟩ |
| Held constant | ⟨what must not move between points, beyond the baseline freeze⟩ |

## Conditions added on top of baseline Applicability

| Condition | True only during | Mechanism |
| :--- | :--- | :--- |
| | | ⟨one line — or → M⟨n⟩⟩ |

## Window rule

| Boundary | Signal | Recorded by |
| :--- | :--- | :--- |
| Opens | | |
| Closes | ⟨the obvious closing signal usually deletes the tail the report exists to explain → M⟨n⟩⟩ | |

## What this run reads

Names live in `00-baseline` Metrics — referenced, never redefined.

| Ref | Read as | Selector | Gates which claim | Required |
| :--- | :--- | :--- | :--- | :--- |
| E⟨n⟩ | ⟨role in this run⟩ | ⟨when the raw series mixes producers⟩ | ⟨what fails without it⟩ | ⟨yes · no⟩ |

| Field | Value |
| :--- | :--- |
| Query file | `./scripts/⟨queries⟩` · dry run clean ⟨date⟩ |
| Export | after **every** point — a missing point costs a re-run, an extra one costs nothing |
| Recorded by hand | ⟨point id · axis value · config commit · UTC window · which component was at its ceiling and from which metric⟩ |

## Validity criteria

| Criterion | What happens when it fails |
| :--- | :--- |
| ⟨identical across points⟩ | ⟨re-run · excluded⟩ |
| ⟨reset between points⟩ | |
| ⟨cross-check: the same figure from two independent sources⟩ | ⟨what disagreement means⟩ |

## Cost and stop condition

| Field | Value |
| :--- | :--- |
| Estimated | ⟨time · money⟩ |
| Stop if | ⟨the condition under which this is abandoned rather than pushed through⟩ |

## What this execution owes the report

Written now, from the report's section list. If no section is named, the execution does not
need to run.

| Report section | Expected to produce |
| :--- | :--- |
| §⟨n⟩ ⟨name⟩ | ⟨table · figure · one number · a sentence⟩ |

---

# 2 · Journal

One command per point — see `./scripts/`. What the tooling does not capture must be written
down immediately, while the window is fresh.

| Point | Date UTC | Window | Config commit | Valid | Data |
| :--- | :--- | :--- | :--- | :--- | :--- |
| | | ⟨open → close⟩ | | ⟨yes · no⟩ | `./data/⟨file⟩` |

| Point | Anomaly | Rule applied | Decision |
| :--- | :--- | :--- | :--- |
| | | | |

---

# 3 · Results

| Block | Present | Feeds |
| :--- | :--- | :--- |
| Matrix | ⟨yes · no⟩ | ⟨report §⟨n⟩⟩ |
| Metrics | ⟨yes · no⟩ | |
| Saturation | ⟨yes · no⟩ | |
| Constants | ⟨yes · no — only if this run froze something others inherit⟩ | |
| Applicability | ⟨yes · no — only if it narrows the baseline envelope⟩ | |
| Guardrails | ⟨yes · no⟩ | |
| Routing · Open · Retro | yes | |

> Blocks are chosen from the catalogue in `methodology.md` §4. **Absent blocks are deleted,
> not left empty** — an empty heading invites filling.

---

## Matrix

**Finding:** ⟨one sentence a decision maker can act on. If it needs two, it is two findings.⟩

| ⟨axis⟩ | ⟨metric⟩ | ⟨metric⟩ | ⟨$ / unit⟩ | Source | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | ⟨measured · derived · recorded · estimated⟩ | |

| Field | Value |
| :--- | :--- |
| Reference value | ⟨target · alternative · previous revision — an absolute number decides nothing⟩ |
| Holds only under | ⟨conditions beyond baseline applicability · nothing extra⟩ |
| Raw data | `./data/⟨file⟩` |

⟨Mechanism, when the table reads as noise without it. More than a paragraph → M⟨n⟩.⟩

---

## Metrics

> Extract to `./metrics.md` when this stops fitting on one screen.

| Figure | Formula | Inputs | Value |
| :--- | :--- | :--- | :--- |
| | `⟨formula⟩` | ⟨E refs · Matrix rows · `00-baseline` §⟩ | |

---

## Saturation

| Axis value | Component at its ceiling | Evidence | Relieved by |
| :--- | :--- | :--- | :--- |
| | | ⟨which metric, which value⟩ | |

> A tier counts as proven only when the previous ceiling was **actually relieved** and a new
> saturation was then observed — never because its numbers looked close. An unproven tier
> weakens the tiers that were proven.

---

## Guardrails

A guardrail is a config value traceable to a row above and committable to a file. If it
cannot be committed it is a recommendation, and recommendations get forgotten. Rows whose
source number did not survive the runs are deleted, not left blank.

| Value | Where it is set | From |
| :--- | :--- | :--- |
| | ⟨file · CRD field · env var⟩ | ⟨block · row⟩ |

---

## Routing

Decided here, against the finished report — `methodology.md` §3.

| Result | Destination | Applied |
| :--- | :--- | :--- |
| | ⟨report §⟨n⟩ · `benchmarks/⟨name⟩.md` · `00-baseline` · nothing⟩ | |

> **"Nothing" is a result.** The run proved the question is not worth a section; the finding
> goes to the report's out-of-scope table so it is not re-asked next revision.

---

## Open

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| | | |

---

## Retro

Never published.

| Field | Value |
| :--- | :--- |
| Expectation | ⟨held · inverted — what actually happened, in the words that go into the report⟩ |
| Cost against estimate | |
| What should have been checked earlier | ⟨and which validity criterion should have caught it⟩ |
| What belongs back in the kit | |
