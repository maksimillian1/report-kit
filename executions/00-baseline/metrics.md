# Execution · 00 · Baseline — Metrics

> **Optional file.** Everything here belongs to `index.md` §1. Extract it only when that
> section makes the file hard to scan. If it does not exist, that is the normal case.

Scope: **what is observable** — a property of the system, like a component's version. What
a given run *reads*, with which filters and gating which claim, is method and lives in that
execution's Instrumentation section.

---

## Register

Numbers are permanent. A retired metric keeps its ref and gains a status, so references in
older revisions stay resolvable. Never renumber, never reuse.

| Range | Component / domain | Added |
| :--- | :--- | :--- |
| E1–E9 | ⟨cost and capacity — nodes, queues, egress⟩ | v1.0 |
| E10–E19 | ⟨component⟩ | v1.0 |
| E20–E29 | ⟨component⟩ | v1.0 |
| E30– | *reserved* | |

Status values: *available* · *pending* · *retired in v⟨n⟩* · *superseded by E⟨n⟩*.

> **Runs are named, metrics are numbered.** Executions are `00-baseline`, `01-⟨name⟩`;
> their points are `⟨name⟩-⟨value⟩`. Never let one identifier mean both.

---

## ⟨Component⟩ · E⟨n⟩–E⟨m⟩

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E⟨n⟩ | | `⟨name⟩` | | |

⟨Anything specific to reading this component: histogram suffixes, ports, mandatory label
filters, name changes between versions.⟩

---

## Mandatory filtering

Metrics that mix several producers and cannot be split after the fact. Filter in the query
file, never in the analysis.

| Ref | Mixes | Required selector |
| :--- | :--- | :--- |
| | | |

---

## Deliberately not observable

| What | Why it is not needed |
| :--- | :--- |
| | |

> Instrumentation without a consumer generates work rather than evidence. Add it together
> with the run that needs it.
