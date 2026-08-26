# Execution · 00 · Baseline — Metrics

> **Optional file.** Everything here belongs to `index.md` §1. Extract it only when that
> section gets hard to scan. Not existing is the normal case.

Scope: **what is observable** — a property of the system, like a component's version. What a
run *reads*, with which filters and gating which claim, is method and lives in that
execution's Instrumentation. Explanations needing a paragraph are `M⟨n⟩` in `./concepts.md`.

---

## Register

Numbers are permanent: a retired metric keeps its ref and gains a status, so references in
older revisions stay resolvable. Never renumber, never reuse.
Status: *available* · *pending* · *retired in v⟨n⟩* · *superseded by E⟨n⟩*

| Range | Component / domain | Added |
| :--- | :--- | :--- |
| E1–E9 | ⟨cost and capacity — nodes, queues, egress⟩ | v1.0 |
| E10–E19 | ⟨component⟩ | v1.0 |
| E20– | *reserved* | |

> **Runs are named, metrics are numbered** — never let one identifier mean both. **Only E
> refs are global**; C, R and M are execution-local and cited as `01-⟨name⟩ C4`.

---

## ⟨Component⟩ · E⟨n⟩–E⟨m⟩

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E⟨n⟩ | | `⟨name⟩` | | ⟨histogram suffix, port, version-specific name⟩ |

---

## Mandatory filtering — in the query file, never in the analysis

| Ref | Mixes | Required selector |
| :--- | :--- | :--- |
| | | |

## Deliberately not observable

Instrumentation without a consumer generates work rather than evidence.

| What | Why nothing needs it |
| :--- | :--- |
| | |
