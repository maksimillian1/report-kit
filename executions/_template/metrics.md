# Execution · ⟨NN-name⟩ — Instrumentation

> **Optional file.** Belongs to `index.md` §1 Plan; extract it when that section is hard to
> scan. **Frozen with the Plan, before the first run.**

Scope: **what this run reads and how**. Metric names live in `00-baseline` — referenced,
never redefined. Why a series is read this way, where it needs a paragraph, is `M⟨n⟩`.

---

## Series read

| Ref | Read as | Filter | Gates |
| :--- | :--- | :--- | :--- |
| E⟨n⟩ | ⟨role in this run⟩ | ⟨selector, if the raw series mixes producers⟩ | ⟨which claim fails without it⟩ |

**Required** (gate the run — a point missing one is not worth its cluster time): ⟨refs⟩ ·
**Optional** (gate one claim, not the campaign): ⟨refs⟩ · read once per point, not scraped: ⟨⟩

Query file `./scripts/⟨queries⟩` · dry run clean ⟨date⟩ · retention ⟨⟩ → export after
**every** point; missing points cost a re-run, extra ones are harmless.

---

## Derived figures — all ᴬ in the report

| Ref | Definition | From |
| :--- | :--- | :--- |
| C⟨n⟩ | `⟨formula⟩` | ⟨refs⟩ |

---

## Recorded by hand — unrecoverable if not written down at the time

| Ref | What | Why nothing else produces it |
| :--- | :--- | :--- |
| R⟨n⟩ | ⟨run log — point id, axis value, config commit, UTC window, validity decision⟩ | the backend does not know when a run began |
| R⟨n⟩ | ⟨saturation signal — which component was at its ceiling, and from which metric⟩ | no query returns "component X was the bottleneck" |

---

## Window boundaries — the usual reason a campaign is thrown away

- **Start** — ⟨signal, and who records the timestamp⟩
- **End** — ⟨signal⟩

⟨Why the obvious closing signal is wrong, if it is. Closing on the visible completion signal
often deletes exactly the tail the report exists to explain → M⟨n⟩⟩
