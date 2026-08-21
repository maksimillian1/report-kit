# Benchmark · ⟨Name⟩

⟨One sentence: what behaviour of the system this measures.⟩

| | |
| :--- | :--- |
| Benchmark | `⟨name⟩` · v⟨n⟩ |
| Baseline | `executions/00-baseline/` rev ⟨sha⟩ |
| Execution | `executions/⟨NN-name⟩/` |
| Raw data | `executions/⟨NN-name⟩/data/` |
| Consumed by | `report.md` §⟨⟩ |

> **This document states what the system does. It does not recommend anything** — the
> decisions drawn from it live in `report.md`. A benchmark that recommends stops being
> comparable to its own next version.

> ᴬ arithmetic · ᴹᵒ modeled · ᴱ estimated. Everything unmarked is measured.

---

## 1. Method

### 1.1 Unit of work

⟨One sentence, including the exact moment a unit counts as done. One denominator only.⟩

### 1.2 Axis

⟨What was varied, over what values, and why that range. If swept coarse-to-fine, say so —
it reads as method, not as a mistake.⟩

### 1.3 Window rule

- **Opens** at ⟨signal⟩
- **Closes** at ⟨signal⟩

⟨Say why the obvious closing signal is wrong, if it is. This is where most sweeps are
silently ruined.⟩

### 1.4 Validity rules, fixed before the run

- ⟨what must be identical across points⟩
- ⟨what must be reset between points⟩
- ⟨what invalidates a point, and what happens to it — re-run, or marked ᴱ and excluded⟩

---

## 2. Conditions

Baseline conditions apply in full (`00-baseline/index.md` §6). This benchmark adds:

> ⟨Envelope sentence — the boundary of every figure below, forward-looking.⟩

⟨List any condition that is really a conclusion in disguise — a setting that shapes the
result and would move it if changed.⟩

---

## 3. Results

| ⟨axis⟩ | ⟨measure 1⟩ | ⟨measure 2⟩ | ⟨cost⟩ | ⟨unit cost⟩ | ⟨constraint signal⟩ | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| | | | | | | |

⟨One short paragraph per column that needs explaining: how it was derived, and what makes
it trustworthy. Measure the headline figure twice from independent sources where possible;
disagreement beyond a few percent invalidates the point.⟩

---

## 4. Curves and read-off points

⟨Chart description. Plot script and image under the execution's `scripts/` and the
project's chart folder.⟩

| Point | How it is identified | Value | Evidence |
| :--- | :--- | :--- | :--- |
| | | | |

**Boundary rule.** A minimum or maximum landing on the edge of the swept range is not
proven — there is no branch on one side of it. Either extend the range or state that it is
unproven.

---

## 5. Mechanism

⟨Why the curve has the shape it has. Without this the chart reads as noise. This is
usually the most transferable part of the whole report.⟩

---

## 6. Constraint ladder

| Tier | Component | Proof metric and where it saturated | Relieved by | Cost to remove ᴬ |
| :--- | :--- | :--- | :--- | :--- |
| 1 | | | | |
| 2 | | | | |

A tier counts as proven only when the previous one was actually relieved and a new
saturation was then observed. **No tier is claimed beyond what was observed.**

**Hypothesis recorded before the run** — see `executions/⟨NN-name⟩/index.md` §1.

- [ ] Confirmed
- [ ] Inverted → the inversion stays here. It is what makes the measurement credible

---

## 7. Validity and exclusions

| Point | Anomaly | Included in fit | Reason if excluded |
| :--- | :--- | :--- | :--- |
| | | | |

Excluded points stay in §3 with their figures marked ᴱ. Removing them entirely would hide
that the run happened.

---

## 8. Reproduce

```
⟨command⟩
```

| | |
| :--- | :--- |
| Prerequisites | ⟨baseline freeze · execution gate⟩ |
| Tooling | ⟨scripts and where they live⟩ |
| Metric definitions | `00-baseline/index.md` §1 ⟨refs⟩ |
| Manual steps | ⟨what no script can produce⟩ |

---

## Regression

| Against | ⟨headline 1⟩ | ⟨headline 2⟩ | ⟨constraint⟩ |
| :--- | :--- | :--- | :--- |
| v⟨n-1⟩ | | | |

Comparison is benchmark to benchmark: same axis, same conditions, same window rule. If any
of those changed, the row states what changed instead of a delta.
