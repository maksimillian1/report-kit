# charts.md — the contract between a chart and the report it illustrates

`formats.md` is how a number is written into prose. This is how a number gets
into a picture: what a chart CSV may contain, where its cells have to come from,
and what the renderer will and will not decide for you.

```bash
report-kit charts --list                 # the column contract, every CSV
report-kit charts --check                # what is drawable, and what is not
report-kit charts all --out assets       # render, light surface
report-kit charts all --theme navy --out assets
```

Rendering needs matplotlib — `pip install "report-kit[charts]"`. `--list` and
`--check` do not: they read CSVs and `figures.yaml` and draw nothing, so the
contract stays readable in an environment that cannot render.

## Where things live

| | |
| :--- | :--- |
| `charts/*.csv` | one CSV per chart, the input. Yours to fill |
| `assets/*.svg` | the output, one file per chart per surface |
| `assets/manifest-⟨theme⟩.json` | what was rendered from which CSV, with the CSV's hash |

`init` copies the five CSVs in header-only, so every column name you need is
already in front of you and `--check` has something to talk about from the first
revision.

## A chart CSV is a view, and it is yours

Three kinds of file hold numbers in a report, and they are not interchangeable.

| | Holds | Rule |
| :--- | :--- | :--- |
| `executions/⟨NN⟩/data/` | readings | a field of what an authority returned (`methodology.md` §2) |
| `figures.yaml` | results | every number a document prints, resolved and marked |
| `charts/*.csv` | a view | a transcription of what the documents already print |

A chart CSV exists so that the renderer needs no knowledge of the report: it
reads columns, not sections. Nothing in it is a new claim. **Copy numbers, never
compute a replacement** — if the document states `$44,200`, write `44200`. The
one exception is a column the schema marks as *derived*: when the source gives
the inputs but not the result, compute it with the stated formula and say so.

Which makes drift the only real risk — and it is the registry's question, not
this tool's. See the next section.

### An unknown value is an empty cell

Never fill a gap with a plausible number, a number from an earlier revision, or
a number from a different point. The renderer skips rows missing what a chart
plots, and a skipped row is a correct outcome. A chart drawn from four of five
points is honest; one drawn from five with an invented fifth is not.

If a figure carries a caveat that changes what it means — provisional, not
resolved, a window average rather than a steady state — keep the figure and put
the caveat in `note`. Do not drop the row.

If two documents give different values for the same figure, stop. Do not pick
one. That is a defect in the documents, and charting either value hides it.

## Drift is caught by the registry, not by this tool

Add one line to `figures.yaml`:

```yaml
scan:
  - report.md
  - charts/*.csv          # ← the chart inputs, scanned like any other document
```

Now `report-kit figures check` reads the CSVs along with the prose, and a value
the report has retired is named where it survives:

```
retired values
  FAIL charts/frontier-api.csv:5  0.00117 -> d16_gross_r500 = 0.00121
```

That is the whole mechanism, and it belongs there for two reasons. The registry
already owns `retired`, and it knows which figure replaced the stale one — which
this tool could not say. And it is **your** registry that decides what it
governs: a report that registers its cost columns and not its throughput ones
says so by what it puts in `retired`, not by a list inside the kit.

`report-kit charts --check` answers a narrower question: given these columns,
what can be drawn.

## The columns

`report-kit charts --list` prints the live contract; it is generated from the
schema, so it cannot fall out of step with the code. What the shapes mean:

| | |
| :--- | :--- |
| **required** | the shortest list this chart can draw anything from. Absent or non-numeric is a *problem* |
| **optional** | absent is fine, and usually means one fewer panel rather than no chart |
| **derived** | recomputed from other columns and compared. A gap is a *problem*: the CSV and its source table disagree, and it is resolved against the document, not by editing the number to pass |
| **open** | this schema takes further columns from the header (below) |

**A problem costs an exit code; a note does not.** A problem means this file
cannot produce its chart, or contradicts itself. Everything else is a note: a
column this tool does not read (ignored, not rejected), a placeholder left from
the template, a file nobody has filled in yet. None of that is a defect in your
report, so none of it fails.

**Which panels a chart has depends on the columns it was given.** The jobs
frontier drops its cost panel when nothing was priced; the api frontier drops
its replica panel when no `replicas_⟨tier⟩` column exists; the split drops its
unused-capacity bar when no fleet figure was pulled. Both worked examples under
`examples/` are reports with no price basis at all, and both chart their
frontier — see `examples/async-jobs/report.md` §3.2 and
`examples/simple-api/report.md` §3.2 for what that looks like and why.

Three conventions the renderer relies on:

- **`dominated` and `excluded` are flags.** `1` marks the row, empty leaves it
  clear. A dominated point is one where another point is both faster and
  cheaper; it is drawn hollow and off the line rather than dropped. An excluded
  point is one the source says not to read as a capacity result; it is dropped
  from the chart, so use it only when the document actually says that.
- **`mark` carries provenance** as the documents use it: `M` measured, `R`
  recorded, `D` derived, `E` estimated. It is not drawn. It exists so a caption
  can be written without re-reading the source. Where a row's plotted columns
  differ in provenance, mark the weakest — the same rule `figures.yaml` applies
  to a derived figure with an estimated input.
- **`note` is free text** and must be quoted if it contains a comma.

### Two open schemas

Names belonging to one report's architecture do not belong in a kit, so two
CSVs take their series from the header instead of from a list in the code.

**`split-jobs.csv`** — every column beyond `n_set`, `unused_fleet` and
`workload_total` is one workload's cost. Name them after your workloads. The
renderer ranks them by what they cost across every row: the two largest keep a
ramp step of their own and the rest fold into one `other` segment, because a
stack of five is five colours nobody can hold apart. The callout names the
*smallest* workload and its share, which is usually the finding.

**`frontier-api.csv`** — every `replicas_⟨name⟩` column is one autoscaled tier,
drawn as a step in the lower panel and labelled `⟨name⟩`. They are ranked by
peak, so the busiest tier takes the solid style. Three is the most a reader
separates on one frame.

### Three values read from the first row

All are properties of the data rather than of one invocation, so they live in
the file and `charts all` needs no flags.

| | |
| :--- | :--- |
| `unit` | the noun in the axis labels — `docs`, `queries`, `units`, `events`. Defaults to `unit`. In `amortization.csv` it is a real per-row key instead: one chart is rendered per distinct value |
| `period` | the time base `throughput` and `duration` are stated in — `min`, `s`. Defaults to `min`, and the axis reads `⟨unit⟩/⟨period⟩`. A drain measured in units per second and a sweep measured in documents per minute are the same chart, so the denominator is a cell rather than a column name |
| `reference_ms` · `reference_note` | a horizontal reference line on the api chart and its label. No line is drawn when the cell is empty |

`amortization.csv` reads `crossover_volume` from the **lowest-volume row of
each unit**, because the crossover belongs to the curve rather than to a point
on it. Leave it blank on the rest.

## What the renderer decides, and what it will not

Three rules are wired in, and none of them is a per-chart option. They are the
reasons a chart can be trusted at a glance.

**No chart carries two y-scales.** A second measure goes in a second panel
sharing the x-axis. Two scales on one frame let the author choose where the
lines cross, which makes the picture an argument rather than a reading.

**Series colours are steps of one hue ordered by magnitude**, not one hue per
name, so adjacent segments stay apart for a colour-blind reader. Text sitting on
a fill picks its own ink by the fill's luminance.

**No label sits at a fixed offset.** An offset is in points, which the data
limits know nothing about, so a label near an edge would leave the canvas and
two labels on neighbouring marks would land on each other. Every label is
measured against the frame and against what is already placed, and takes the
first free position: beside the mark, below it, then stacked a row higher. A
label is never dropped — one in a tight corner still carries its number. Where
the only free position crosses a hairline rule it takes it, because a rule
behind text reads and two labels in one spot do not.

So: **do not edit the renderer to accommodate a value.** Change the CSV, or say
the schema needs a new column and stop. A chart that needed the code bent to fit
it is a chart whose data is telling you something.

## Two surfaces, one asset

Each SVG is authored at 1620 × 1000 user units, so a font size in the code is a
pixel on an 1800px slide canvas, and scales down to roughly 700px for an article
without dropping below a readable label size. Text is emitted as text: the fonts
are named in the file and resolved by whatever opens it, so they need not be
installed on the machine that builds it. Backgrounds are transparent, which is
why nothing is masked behind an opaque box.

`--theme light` is for a document, `--theme navy` for a slide. Render both from
the same CSV; the navy files carry a `-navy` suffix.

## Reading the output

```
assets/frontier-jobs.svg
assets/manifest-light.json
skipped — jobs-split: needs at least one workload column
```

A skipped chart is printed to stderr and the rest still render, so one unfilled
CSV does not block the others. The manifest records each SVG against its CSV and
the first 12 hex of that CSV's SHA-256 — enough to tell later whether a chart in
a document was rendered from the data now in the repository.

## Verifying a revision

```bash
report-kit figures check        # every number, prose and charts/*.csv alike
report-kit charts --check       # whether each CSV can still draw its chart
```

Both, in that order, and they answer different questions. The first is the
report's contract over everything in `scan` — which includes the chart CSVs once
you have added the glob above. The second is whether the columns still support
the pictures.
