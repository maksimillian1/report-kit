# Execution · ⟨NN-name⟩ — Instrumentation

> **Optional file.** Everything here belongs to `index.md` §1 Plan. Extract it only when
> that section makes the file hard to scan. Frozen with the Plan, before the first run.

Scope: **what this run measures and how**. The metric names themselves are a property of
the system and live in `executions/00-baseline/` — referenced here, never redefined.

---

## Series read

| Ref | Read as | Filter | Gates |
| :--- | :--- | :--- | :--- |
| E⟨n⟩ | ⟨role in this run⟩ | ⟨selector, if the raw series mixes producers⟩ | ⟨which claim fails without it⟩ |

**Required vs optional.** Say which refs gate the run itself and which gate a single claim.
An optional series blocks one conclusion, not the campaign — and a campaign that waits on a
nice-to-have is a campaign that does not happen.

Query file: `./scripts/⟨queries⟩` · dry run clean: ⟨date⟩

---

## Derived figures

Computed, not measured. Everything here carries ᴬ in the report.

| Ref | Definition | From |
| :--- | :--- | :--- |
| C⟨n⟩ | `⟨formula⟩` | ⟨refs⟩ |

---

## Recorded by hand

What no query returns, and what is lost if not written down at the time.

| Ref | What | Why nothing else produces it |
| :--- | :--- | :--- |
| R⟨n⟩ | ⟨run log — point id, axis value, config commit, UTC window, validity decision⟩ | the backend does not know when a run began; a window guessed later is a different run |
| R⟨n⟩ | ⟨saturation signal — which component was at its ceiling, and the metric it was read from⟩ | no query returns "component X was the bottleneck"; it is a reading across several series |

---

## Window boundaries

The most commonly mis-set values, and the usual reason a campaign is thrown away.

- **Start** — ⟨signal, and who records the timestamp⟩
- **End** — ⟨signal⟩

⟨State why the obvious closing signal is wrong, if it is. Closing on the visible completion
signal often deletes exactly the tail the report exists to explain.⟩

Extra points in an export are harmless. Missing ones require re-running at full cost.
