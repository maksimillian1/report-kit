# tenant-platform — one worked CSV per chart shape and flag

**Every number here is invented.** `tenant-platform` is a made-up multi-tenant
SaaS: a primary and a standby region, three plans, three ways to isolate a
tenant. Nothing was deployed or measured, and there is no registry behind these
files. The numbers are round on purpose and agree with each other, so a reader
can check the shape against the arithmetic: the floor in `floor.csv` is the
$4,000 that `amortization.csv` spreads over the tenants and `monthly-bill.csv`
stacks under usage, and the $13 of infrastructure in `margin.csv` is what one
tenant costs at 1,000 tenants.

`simple-api/` and `async-jobs/` are real runs on a local cluster, which nobody
bills, so neither can show a cost chart. This directory covers the shapes and
flags those two never reach.

## What each file proves

`charts/charts.yaml` gives every file its kind and marks, so the whole
directory renders with one command:

```bash
report-kit charts --all       # every entry of charts/charts.yaml, both surfaces
report-kit charts --check     # drawable, none left out, no SVG older than its CSV
```

| File | Kind and marks (as the `--kind` flags) | The rule it shows |
| :--- | :--- | :--- |
| `amortization.csv` | `line --mark-x 100 break-even at the pro plan` | x spans 1000×, so both axes go log without a flag; `--mark-x` draws one vertical line through every panel |
| `failover.csv` | `line --rule 300 p99 target --mark-x 20 primary lost` | time on the x axis; `p95` and `p99` share a unit, so they share a panel and differ by line style; the empty cells at 20 s break the line rather than bridge the outage |
| `isolation.csv` | `line --points` | silo, bridge and pool are three options, not a sequence, so no line joins them; the `label` column names each point |
| `tier-cost.csv` | `bars` | four components against a three-step palette, so `cache` and `egress` fold into `other`; `standby` carries an ` aside` unit and stands beside the stack |
| `floor-resize.csv` | `bars` | the plain stack, no aside: the floor as built against right-sized, $4,000 against $3,200 |
| `monthly-bill.csv` | `bars` | no `label` column, so the first numeric column is the axis and its values are the ticks: the bill at 250 to 2,000 tenants, the $4,000 floor plus $9 a tenant |
| `floor.csv` | `parts` | no axis: the rows are the parts of one bar, and parts beyond the palette fold the same way |
| `margin.csv` | `waterfall` | `gross margin` and `net margin` equal the running total, so they are drawn from zero as subtotals without a column to say so |

Each SVG sits beside its CSV, committed so the shapes can be read without
installing anything; `manifest-<theme>.json` records which CSV and which flags
made each SVG.

## What is not here

The edge cases are in `tests/test_charts.py`: a missing units row, a file whose
only numeric column would be the axis, a theme replaced through
`charts/themes.json`, a flag given to a shape that cannot draw it, a bad line
in `charts.yaml`, a stale SVG, and several CSVs rendered in one call.
