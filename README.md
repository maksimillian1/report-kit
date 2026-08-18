# report-kit

Portable framework for Executive Engineering Reports: one document covering
performance and cost, repeatable per project.

````
report-kit/
├── README.md
├── methodology.md          # why the report has this shape — read once
├── template.md             # the report skeleton
├── checklist.md            # pre-flight and execution gates
├── notes.md                # footnotes referenced from the checklist
├── scripts/
│   ├── export-metrics.sh   # Prometheus range export → docs/report/data/
│   └── queries.txt         # per-project query list (adapt, keep the four groups)
├── cost-model.xlsx         # floor line items, resource prices, break-even chart
└── tagging.tf              # default_tags block for cost attribution
````

Per-project layout this kit produces:

````
docs/report/
├── report.md               # the deliverable
├── data/                   # raw exports, one file per run
└── charts/                 # plot scripts + generated images
````

## Assumptions

Swap these out per project; nothing else in the kit depends on them.

| | Default | Where to change |
| :--- | :--- | :--- |
| Metrics backend | Prometheus (`query_range` API) | `scripts/export-metrics.sh` |
| Metric names | kube-state-metrics + cAdvisor conventions | `scripts/queries.txt` |
| Cost data | AWS Cost Explorer, tag-based attribution | `tagging.tf`, `cost-model.xlsx` |
| Short-lived workloads | log-derived metrics via Promtail/Loki | `notes.md` §3 |
| Elastic compute | Kubernetes nodes as the billable unit | `notes.md` §2 |

## Constraints

- **Cost attribution is not retroactive.** Tags must be applied *and* activated in the
  billing console before the first run. Activation is a separate step with up to 24h
  of delay and applies going forward only.
- **Metric retention is shorter than the writing period.** Export raw series after every
  run. Re-running a benchmark costs money; losing its data does not have to.
- **Billing granularity is too coarse for short runs.** Run cost is computed from
  resource-hours; billing exports are only usable for the 24h idle-floor window.
- **One variable per sweep point.** Same commit, same image, same fixture.
- **Empty query results are instrumentation gaps, not zeros.**

## Order of operations

1. `tagging.tf` → apply → activate tags in billing console. Wait.
2. Freeze and profile the workload fixture.
3. Adapt `queries.txt`; run `export-metrics.sh --dry-run` until nothing reports NO DATA.
4. Start the 24h idle window (passive — everything else continues meanwhile).
5. Sweep run, then optional runs.
6. Write the report; BLUF last.
7. Port fixes back into this kit before moving on.
