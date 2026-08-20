# Execution · ⟨NN-name⟩

| | |
| :--- | :--- |
| Produces | ⟨decided at Close — see §3⟩ |
| Preconditions | ⟨`00-baseline` §7.6 gate green · other executions⟩ |
| Data | `./data/` |
| Scripts | `./scripts/` — anything pinned to this execution's data |
| Optional | `./metrics.md` — move §1 Instrumentation there when this file gets long |
| Status | ⟨planned · running · closed · abandoned⟩ |

> **Three phases. The Plan is frozen before the first run and is not edited afterwards.**
> A plan written after the result cannot support a recorded hypothesis, and the recorded
> hypothesis is what makes an inverted finding credible instead of embarrassing. If the
> plan turns out wrong, say so in Close — do not rewrite §1.
>
> **Where the result lands is decided at Close, not now.** The same execution can become
> the whole report, one section of it, a benchmark, baseline material, or nothing at all.
> That call is made against the finished report, from significance and volume — never from
> structure decided in advance.

---

# 1 · Plan  *(frozen ⟨date⟩)*

### What this execution measures

⟨One paragraph. If it may produce no benchmark, say what question it settles instead.⟩

### Axis and points

| | |
| :--- | :--- |
| Varied | ⟨parameter⟩ |
| Values | ⟨list — and whether coarse-to-fine⟩ |
| Held constant | ⟨what must not move between points⟩ |

### Conditions

Baseline envelope applies in full (`00-baseline/index.md` §6). This execution adds:

> ⟨What is true only during this run.⟩

⟨List any condition that is really a conclusion in disguise — a setting that shapes the
result and would move it if changed.⟩

### Window rule

| | |
| :--- | :--- |
| Opens | ⟨signal, and who records the timestamp⟩ |
| Closes | ⟨signal — and why the obvious one is wrong, if it is⟩ |

### Validity criteria

- [ ] ⟨what must be identical across points⟩
- [ ] ⟨what must be reset between points⟩
- [ ] ⟨what invalidates a point, and what happens to it — re-run, or marked ᴱ and excluded⟩

### Instrumentation

Which observable series this run reads and what each gates. Names live in
`00-baseline/index.md` §1 — referenced here, never redefined. Move to `./metrics.md` if
this grows.

| Ref | Read as | Filter | Gates |
| :--- | :--- | :--- | :--- |
| E⟨n⟩ | ⟨role in this run⟩ | ⟨selector⟩ | ⟨which claim fails without it⟩ |

Derived figures (ᴬ): ⟨C⟨n⟩ = formula⟩
Recorded by hand: ⟨run log · saturation signal — what no query returns⟩

Query file: `./scripts/⟨queries⟩` · dry run clean: ⟨date⟩

### Hypothesis

⟨What you expect to happen and why. Dated. The single most valuable line in this file, and
the one most often written too late.⟩

### Cost and stop condition

| | |
| :--- | :--- |
| Estimated cost | ⟨time · money⟩ |
| Stop if | ⟨the condition under which this is abandoned rather than pushed through⟩ |

---

# 2 · Journal

## How a point is run

```
⟨command⟩
```

⟨What the tooling does automatically, and what must be done by hand immediately after each
point while the window is fresh.⟩

## Points

| Point | Date UTC | Config commit | Outcome | Data |
| :--- | :--- | :--- | :--- | :--- |
| | | | | |

### ⟨point id⟩

⟨Paste the point block, or write it out.⟩

## Anomalies and validity decisions

| Point | Anomaly | Decision |
| :--- | :--- | :--- |
| | | |

⟨State the rule being applied, not just the outcome. "Re-run" and "excluded and marked ᴱ"
are both defensible; averaging an anomalous point in silently is not.⟩

---

# 3 · Close

## Export manifest

| Artifact | Written | Gaps | Notes |
| :--- | :--- | :--- | :--- |
| | | | |

## Routing — where the result went

Decided here, against the finished report.

| Destination | When it applies | Used |
| :--- | :--- | :--- |
| **The whole report** | this is the only execution | |
| **A report section**, table inline | the material is significant and fits | |
| **A benchmark**, cited from a section | too detailed for the report, or needed as the regression unit across revisions | |
| **`00-baseline` sections** | it is a given, not a finding, and has two or more consumers | |
| **Nothing** | measured, and insignificant against the rest — or the hypothesis did not hold | |

> **"Nothing" is a result, not a failure.** A module contributing a few percent of cost has
> earned its way *out* of an executive report, and the run proved it. Record the finding in
> the report's out-of-scope table so the question is not asked again next revision, keep
> this folder intact, and move on.

Detail is what sends material to a benchmark — not the existence of the benchmarks folder.
A run matrix that fits in the report stays in the report.

| Result | Destination | Applied |
| :--- | :--- | :--- |
| | | |

## Hypothesis outcome

- [ ] Confirmed
- [ ] Inverted — ⟨what actually happened; this goes into the report verbatim⟩
- [ ] Untestable — ⟨why⟩

## Retro

- What did this execution cost against its estimate?
- Which precondition should have been checked earlier?
- What belongs back in the kit?
