# runners/ — measurement points for two workload profiles

A **point** is one measured run at one setting of whatever you're sweeping.
A **sweep** is a series of points that differ in exactly one variable; every
point of a sweep must agree about everything else, or the curve you fit at
the end is comparing two different systems.

These are templates, not a framework. Copy the one that matches your
workload; what a point is run with you declare in the execution's
`execution.yaml`, and what is left in the copy is the little only your system
knows. Nothing here subclasses anything; the flow of a run is the body of
`main()`, readable top to bottom, and each step in it is one library call.

## Which profile

| | `api_point.py` — sync | `jobs_point.py` — async |
|---|---|---|
| Workload | request/response: an API serving traffic | queue/worker: a batch drained by consumers |
| You control | arrival rate, duration | how much work, how much parallelism |
| Load is applied by | a generator run to completion (k6, vegeta, locust, a script) | a producer running **in the background, concurrently with the watch** |
| The window closes when | every gated deployment is back at its floor, held | queues empty **and** worker pool at zero **and** shared tiers at floor, all held together |
| Usually answers | latency and cost at a given offered rate | throughput and cost for a given amount of work |

`api_point.py` has run end to end against a real cluster — that is what
`examples/simple-api/` is. `jobs_point.py` has only ever run against the
selftest's fakes: its shape came from a real ingestion sweep, but this copy
has never driven a real queue and worker pool. Expect to debug it on first
use.

If your system is both (an API that also enqueues work), measure them as two
sweeps rather than one. A point that closes on two unrelated conditions
tells you when the slower of them finished and nothing about either.

## Shared lifecycle

Both runners do the same things in the same order, and the line between the
two halves is the window closing:

```
preflight   assert a known starting state; collect every failure, then stop
load        apply it, recording exactly when it started
watch       poll until the close condition has HELD, not merely occurred
──────────  the window is known: <run>.point.json is written here
export      snapshot the Prometheus series for the window to .jsonl
guards      evaluate the frozen bounds; an empty result is a gap, not a pass
derive      work out every ref metrics.yaml defines from this run's data
record      write <run>.point.md, then exit by verdict
```

Everything above the line needs the live system and is the copy's. Everything
below it is `report-kit point finish`, which the runner calls in-process: it
reads only the record and the files beside it, so it is the same for every
profile and can be run again — after an export that failed, or under a newer
kit. Re-running it re-exports and re-reads; it never re-measures.

## What the runner needs to run at all

**Python**: standard library, plus `PyYAML` (for `env.yaml`), both pulled in
by `pip install report-kit`. Add `report-kit[s3]` only if you use
`report_kit.cloud.aws_s3`. **On PATH**: `kubectl` with a working context,
`aws` for the jobs profile's queue reads and for `prices_match_aws`, `git` for
the commit the point records. **Prometheus** is assumed as the metrics
backend, and **OpenCost** scraped by it wherever a point is priced — see
[Pricing a point with OpenCost](#pricing-a-point-with-opencost).

The library is a dependency, so a copied runner imports it like any other
package — there is no path to configure and nothing at the top of the file to
edit for it:

```bash
cd executions/01-load/scripts && ./api_point.py --run r-200 --rate 200
```

The version that ran is written into each point record as `kit_version`,
because the library no longer shares a commit history with the report it
measured.

## Copying one

`report-kit new-point <execution> --profile api|jobs` copies the runner and an
`env.yaml` to fill. Then:

- **`execution.yaml` → `point:`** — what a point is run with. A key left out
  takes the `DEFAULTS` at the top of the runner. See 3 below.
- **`env.yaml`** — addresses, port-forwards, the load command, poll interval
  and timeout.
- **The runner itself** — only what is your system's: for the api profile how
  your generator's exit code reads (`doubts`); for the jobs profile what a
  reset clears (`reset`) and how a loss puts a point in doubt.

The split is deliberate — **env.yaml may differ between clusters;
`execution.yaml` and the runner may not differ between points of one sweep.**
If you find yourself wanting to sweep something from env.yaml, make it a
setting first.

## What you have to provide

Five things. A runner reads all of them and will not invent any of them.
Three are YAML files, each with one job: `env.yaml` says how to reach the
cluster and may differ between clusters; `metrics.yaml` says what is read
and from where, and `execution.yaml` what a point is run with, when its
window closes and what makes it valid — neither of those two may change
between points of one sweep.

### 1. `env.yaml` — addresses

Required keys, both profiles:

| key | meaning |
| :--- | :--- |
| `namespace` | default namespace for kubectl reads |
| `namespaces.<workload>` | optional per-workload override |
| `poll_seconds` | how often to poll while watching (float; 15 is sane) |
| `max_wait_seconds` | give up on the window after this; must exceed `point.hold_seconds` |
| `prometheus.url` | where to query |
| `prometheus.service` / `.namespace` / `.mapping` | optional: open a port-forward instead of assuming reachability |
| `eks_cluster` | the EKS cluster whose control-plane fee `prices_match_aws` checks; needed only when the register reads that fee |

`api_point.py` also needs `generator.command` (a list) and optionally
`generator.env`; `jobs_point.py` needs `producer.command` the same way. In
both, `{run}`, `{log}`, `{summary}` and every setting `point:` declares are
filled in — `{rate}` and `{duration}` for the api defaults, `{n}` and
`{count}` for the jobs ones — and a placeholder that is none of those stops
the run before anything starts.

`jobs_point.py` also needs `sqs.<label>` for every queue that has to drain —
all of them are watched — `nodepool_workers`, the label selector of the
worker pool that has to return to zero, and `worker_selector` for the
pod-per-node read. Its reset step additionally uses `s3.bucket` /
`s3.prefix` and `qdrant.url` / `qdrant.collection` if present, and skips
whatever is absent.

See `env.example.yaml` for a filled-in version of all of it.

### 2. `metrics.yaml` — what is read, and from where

The execution's register, beside its `index.md`, one directory above the
runner. Every metric is defined there once. Each `M` ref with a `promql` is
exported over the window into `<run>.jsonl` at every point; every ref with
`record:`, `series:` or `formula:` is worked out of the run's data when the
point finishes and printed in `<run>.point.md` — which is where a derived
number belongs, rather than in the runner. `report-kit metrics write`
renders the register table from the same file.

```yaml
metrics:
  M1:
    what: served rate
    promql: sum(rate(http_requests_total[30s]))
    status: confirmed 2026-09-04
    notes: the numerator of D3
  M2:
    what: client latency p95
    record: client.p95_ms            # where a generator's summary lands
    status: confirmed 2026-09-04
  D3:
    what: offered load served
    formula: M1 / settings.rate      # refs and point-record fields
    status: active
  D4:
    what: drain duration
    formula: events.queues_empty - events.load_started
    status: active
```

### 3. `execution.yaml` — what a point is run with, when the window closes, and what makes it valid

Beside `metrics.yaml`. `point:` is how a point is run; a key it leaves out
takes the runner's `DEFAULTS`:

| key | api default | jobs default | meaning |
| :--- | :--- | :--- | :--- |
| `settings` | `rate`, `duration` (10m) | `n`, `count` | each one a `--flag`, filled into the load command and the guards' `{placeholders}`, and recorded under `settings` in the point record; one without a `default` must be given at every point |
| `load` | `foreground` | `background` | run the load to completion, or run it **while** the window is watched |
| `hold_seconds` | 60 | 90 | how long the close condition must hold — longer than one autoscaler decision interval |
| `freeze` | none | none | the workloads whose image digests are pinned for the sweep, as `kind/name` |
| `step` | 15s | 15s | the export's resolution |
| `guards_at` | `load_end` | `window_end` | the instant the guards are read as of |

`window_closes_when_back_to_idle` names the deployments the load scales: the
api runner needs at least one; the jobs runner lists its always-on tiers
there, beside the queues and worker pool env.yaml names.
`point_validity_guards` are the checks a point must pass to be compared with
the others: `min`, `max` or both, and either `metric:` — a register ref whose
query it reuses — or a `promql` of its own. `{name}` placeholders are filled
from the run's settings. Evaluated once, as of `guards_at`.

```yaml
point:
  settings:
    rate: {}
    duration: {default: 10m}
  hold_seconds: 60
  freeze: [deployment/api]

window_closes_when_back_to_idle:
  api:
    idle_replicas: 1     # the window waits until it is back here, held
    max_replicas: 10     # reaching it means the point measured that limit

point_validity_guards:
  G1: {max: 0.01, promql: 'sum(rate(http_requests_total{code=~"5.."}[1m])) or vector(0)'}
  G2: {min: 1, metric: M4}
  G3: {min: 0.9, max: 1.1, promql: 'sum(rate(http_requests_total[1m])) / {rate}'}
```

A guard whose query returns nothing **fails** — an empty result is a gap,
not a pass. Write `or vector(0)` where zero is genuinely the answer.

`prices_match_aws: {within: 0.01}` holds every price OpenCost published
during a point against AWS's for the same thing, and doubts the point when
one is further off than `within`, a share of AWS's price. It is refused in an
execution whose register reads no OpenCost price. See
[Pricing a point with OpenCost](#pricing-a-point-with-opencost).

### 4. `image-freeze.json` — what the sweep claims to have measured

Generated, not hand-written: name the workloads under `point.freeze`, run
`--set-freeze` once at the start of a sweep and commit the file. Every later point compares against it and fails
preflight if an image moved. Delete and re-generate only when deliberately
starting a new sweep.

### 5. What only your system knows, in your copy of the runner

`DEFAULTS` at the top, then a handful of functions `main()` calls: how the
generator's exit code reads (api), how the queues and the pool are read, what
a reset clears and which losses put a point in doubt (jobs). This is the only
code you edit.

### Optional

`--out-dir` (defaults to `./data`), `--env` / `--metrics` / `--execution` /
`--freeze-file` if you keep them somewhere other than where the layout puts
them.

An execution laid out before 0.4 keeps a hand-written `series.txt` and
`guards.txt` beside the runner copied then, and that runner goes on reading
them. `report-kit metrics import` builds its `metrics.yaml` and an
`execution.yaml` with its guards; a runner from `report-kit new-point` reads
only those two.

## Output per point

```
<out-dir>/<run>.point.json    the machine-readable record, written the moment the
                              window is known and completed after the export:
                              settings · window · load (exit, window) · events
                              (epoch seconds: load_started, load_finished,
                              window_closed, and every event the watch named) ·
                              observations (peaks of every reading, ceilings
                              reached, the profile's own) · doubts · plan ·
                              queries · guards, their failures and what each
                              read · export · price_check and prices, when the
                              execution asks for the check · image digests ·
                              commit · kit_version
<out-dir>/<run>.point.md      the block to paste into the Journal: the run, then
                              every ref metrics.yaml defines worked out of it
<out-dir>/<run>.jsonl         the exported series
<out-dir>/<run>.meta.json     export manifest: per-ref series and sample counts
<out-dir>/<run>.generator.log the generator's / producer's own output
```

Times in `events` are kept unrounded, so a D ref measured between two of
them — `events.queues_empty - events.load_started` — is exact, not a
difference of two timestamps rounded to the second.

## Exit codes

| | |
| :--- | :--- |
| 0 | clean |
| 1 | preflight or usage failed — nothing ran |
| 2 | the run is valid but at least one ref exported nothing. **The window and the queries are in the point record; run `report-kit point finish <run>.point.json --force` before retention drops it.** |
| 3 | ran, but validity is in doubt: a guard breached, or a doubt was recorded — a generator that failed, a node lost while it held work, a price that does not match AWS's. `report-kit values add-point` refuses such a point without `--allow-invalid` |
| 4 | the window never closed inside the timeout — nothing exported, because an unclosed window has no end |

## Pricing a point with OpenCost

What a point cost comes out of the same Prometheus as what it measured, once
OpenCost runs in the cluster and that Prometheus scrapes it. A price is an
ordinary `M` ref with a `promql`, exported over the window like any other, and
a cost is a `D` ref over it — so no runner, tool or person computes one, and
`report-kit values` reads it by ref like any other number. The rates are list
prices, which is what `methodology.md` §8 prices a window at; CUR is still the
source of record.

**In the cluster**: Prometheus; kube-state-metrics, with
`--metric-labels-allowlist=nodes=[karpenter.sh/nodepool]` when a ref sums one
pool; cAdvisor scraped, since OpenCost works usage out of it; and OpenCost,
its `PROMETHEUS_SERVER_ENDPOINT` at that Prometheus, scraped by it once a
minute. `examples/priced-api/` in the report-kit repository is the four wired
together and run.

**One `M` ref per line**, USD per hour at each instant. `max by` drops the
second copy of a series scraped twice.

| Line | `promql` |
| :--- | :--- |
| a pool's nodes | `sum(max by (node) (node_total_hourly_cost) * on (node) group_left () max by (node) (kube_node_labels{label_karpenter_sh_nodepool="⟨pool⟩"}))` |
| a namespace's requests | `sum(kube_pod_container_resource_requests{job="kube-state-metrics", namespace="⟨ns⟩", resource="cpu"} * on (node) group_left () max by (node) (node_cpu_hourly_cost)) + sum(kube_pod_container_resource_requests{job="kube-state-metrics", namespace="⟨ns⟩", resource="memory"} / 1073741824 * on (node) group_left () max by (node) (node_ram_hourly_cost))` |
| a namespace's allocation, as OpenCost has it | `sum(container_cpu_allocation{namespace="⟨ns⟩"} * on (node) group_left () max by (node) (node_cpu_hourly_cost)) + sum(container_memory_allocation_bytes{namespace="⟨ns⟩"} / 1073741824 * on (node) group_left () max by (node) (node_ram_hourly_cost))` |
| a namespace's volumes | `sum(max by (persistentvolume) (pv_hourly_cost) * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_capacity_bytes{job="kube-state-metrics"}) / 1073741824 * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_claim_ref{job="kube-state-metrics", claim_namespace="⟨ns⟩"}))` |
| a namespace's load balancers | `sum(max by (service_name) (kubecost_load_balancer_cost{namespace="⟨ns⟩"}))` |
| the control plane | `max(kubecost_cluster_management_cost)` |

Then a mean per price and a cost per window:

```yaml
  D12:
    what: mean pool price over the window, USD/h
    series: {ref: M6, reduce: mean}
    status: active
  D18:
    what: the service's own cost over the window, USD
    formula: (D13 + D15 + D16) * window.seconds / 3600
    status: active
```

The mean times the window's hours is the price integrated over the window,
because the export samples it at one step from one end to the other. The
service's own cost — its requests, volumes and load balancers — is §8's B;
the pool's price less those requests, plus the control plane, is A, and is
never divided among the tenants.

### Checking them against AWS

`prices_match_aws` in `execution.yaml` turns the check on:

```yaml
prices_match_aws:
  within: 0.01          # how far apart, as a share of AWS's price
```

When the point finishes, every price OpenCost published during the window,
for every line the register reads, is held against what AWS publishes for the
same thing:

| Line | AWS's price |
| :--- | :--- |
| nodes | the on-demand rate for the instance type in its region (Linux, shared tenancy), or the spot price in its zone at the instant OpenCost first published that price |
| volumes | the EBS GB-month rate for the volume's type, over 730 hours — provisioned IOPS and throughput are not in it |
| load balancers | the NLB hourly rate in the region, before LCUs |
| control plane | EKS's per-cluster hour, plus extended support while the cluster's version is in it; `eks_cluster` in `env.yaml` names the cluster |

A price further off than `within`, a price that cannot be checked — not an
EC2 instance, a volume EC2 no longer describes, a region `cloud/aws.py` has
no location for — and a node kube-state-metrics saw that OpenCost never
priced are each a doubt: exit 3, and `values add-point` refuses the point.
Whatever the outcome, the record keeps `prices`, every price and AWS's beside
it: the dated price basis of that window, §5's first unrecoverable item. The
`aws` CLI needs `pricing:GetProducts`, `ec2:DescribeSpotPriceHistory`,
`ec2:DescribeVolumes`, `eks:DescribeCluster` and `eks:DescribeClusterVersions`.

What it is there to catch, each read out of OpenCost's own source (1.115):

- **A spot node without a Spot Data Feed is priced at the on-demand rate**,
  or at the configured default spot rate where the price list has no entry
  for its type. OpenCost after 1.115 asks spot price history first.
- **Every load balancer is $0.025/h.** OpenCost downloads only the EC2 price
  list, which holds no load balancer, so its default stands whatever the
  region's NLB costs.
- **The EKS fee is $0.10/h only while some node is in a managed node group.**
  A cluster on Karpenter alone reads 0; extended support, Auto Mode's
  per-node fee and provisioned control-plane tiers are in no OpenCost price.
- **Savings Plans and Reserved Instances**, once OpenCost is configured with
  them, turn a node's price into the effective rate. §8 prices at published
  rates, so the check flags it.

## Resetting between points

Not a separate script: `./jobs_point.py --reset-only` wipes the S3 prefix,
purges the queues, clears the sink and waits for the system to read idle.
It lives in the runner because it reads exactly what the runner reads — the
queues env.yaml lists and the deployments `execution.yaml` names — and a
second file with its own copy of them is a second file to keep in sync. `--reset-after` does it once a point's files are
written; `--dry-run` prints what it would touch.

Run it between points of a jobs sweep. Waiting for organic drain costs
about an hour per point.

## The tools — run as-is, nothing to edit

Subcommands of the same CLI; `report-kit <tool> --help` for the options.

- **`report-kit point finish <run>.point.json`** — everything after the
  window closed, run again on the record: export, guards as of the recorded
  instant, every register ref worked out, the journal block, the verdict.
  `--force` overwrites an export already there.
- **`report-kit export-metrics`** — re-export a window by hand. The case that
  matters: the run finished, the export didn't, and the window is sitting
  in the point record with retention counting down. `--record
  data/<run>.point.json` takes the run id, the window and the queries from
  the record, which a runner writes before its export for exactly this. A
  window can be re-exported but never re-measured. It is the one command
  built to work when the rest of the package cannot load: the record is
  JSON, and nothing here needs PyYAML.
- **`report-kit inspect-metrics`** — read back what an export actually
  captured. Worth one look per point: an export can succeed and still be
  useless (one series where you expected twelve, a query matching the wrong
  label). `--settle-on M4 --until <the point record's generator end>` splits
  every ref into "while still reacting" and "once settled", because a mean
  across both describes neither. Measured on a three-minute point:
  whole-window mean 18.00 req/s against a steady state of 23.99 — the first
  reads as a system falling a quarter short, the second as a flat plateau at
  exactly the offered rate. When it says there are no settled samples, that
  is the answer: the run was too short, or the export step too coarse, to
  contain a steady state at all.
- **`report-kit node-cost`** — what the nodes cost during a window, the same
  day, without waiting for CUR. Prices nodes that are already terminated,
  since `kube_node_info`'s `provider_id` outlives them in Prometheus.
  Provisional by construction: reconcile against CUR before the value
  reaches a report.
- **`report-kit selftest`** — runs both runner templates end to end against a
  faked cluster, no cluster or AWS needed. Run it after editing a runner. It
  is also the worked example for testing your own: about sixty lines of
  fakes, patching only `report_kit.shell.sh` / `sh_json` / `http_json`.

## Traps these encode

Each of these cost someone a wasted run:

- **OpenCost's allocation runs a minute behind the pods.** It recomputes
  `container_*_allocation` once a minute, so a pod enters it up to a minute
  after it starts and leaves it up to a minute after it is gone, and one that
  lives less than that can be missed altogether. Over a window of a few
  minutes it trails the replicas: 22–42 % below their requests in
  `examples/priced-api/`. Requests from kube-state-metrics follow the
  replicas at scrape resolution — price the service's share with those, and
  keep the allocation as a second opinion.
- **OpenCost republishes kube-state-metrics' series under its own job.**
  `kube_pod_container_resource_requests` and the volume series arrive twice,
  so a `sum` over them without `job="kube-state-metrics"` counts every
  request twice.
- **A pool that can scale to zero returns no series while it is empty.** The
  export calls that a gap, and `or vector(0)` makes it a free pool — which is
  also what an OpenCost that stopped publishing looks like. Add it only with
  `prices_match_aws` on, whose unpriced-node check tells the two apart.

- **A condition that is true right now is not a condition that has held.** A
  queue reads zero while messages are still in flight; a deployment touches
  its floor between two scaling decisions. Closing on the instantaneous
  reading records a point that measures half a run.
- **The producer runs alongside the watch, never before it.** Filling the
  queue first measures a system draining a backlog that already exists —
  a different experiment, and the arrival pattern is gone from the data.
- **An idle system satisfies the close condition.** Empty queues, a pool at
  zero and every tier at its floor is also exactly what a system that has not
  started yet looks like. A producer slower to start than the hold — an
  upload, a seeding pass, an image pull — closes a zero-length window over a
  system that never did any work, and the point reads clean. With a
  background load the watch will not begin the hold until it has seen the
  system busy at least once.
- **A worker pool that scales to zero takes its `/metrics` with it.** Guards
  are checked at the window's close, and by then the workers are gone: every
  worker-side series is absent, `check_guards` reports NO DATA, and the point
  fails on instrumentation rather than on the system. Anything that decides
  validity has to be published by something still running when the window
  closes — the queue, an always-on tier, a durable counter.
- **An empty query result is a gap, not a zero.** Both the guards and the
  export treat "no series" as a failure. Where zero is genuinely the answer,
  write it as `... or vector(0)` in the query and say so.
- **Guards are evaluated as of when the load stopped, not when you got round
  to checking.** Minutes pass between the two — the scale-in wait, the hold,
  the export. A rate-based guard with a `[5m]` lookback checked at "now" is
  averaging that lookback over dead air instead of over the load it exists to
  validate, and passes quietly. `point finish` reads them as of the instant
  `guards_at` names, taken from the record, for this reason.
- **Scale-in belongs to the point that caused it.** The window ends when the
  system settled, not when the load stopped — otherwise the cost of coming
  back down lands on whoever runs next, or on nobody.
- **A generator's non-zero exit is not always a malfunction.** k6 returns 99
  when a threshold is breached — the system failed to meet it, which is the
  finding, not a broken tool. The runner records the code and flags it;
  deciding which kind of failure it was is yours, and the two are not
  distinguishable from the exit code alone.
- **A node vanishing only matters if it held work.** Ordinary consolidation
  of an idle node is not an interruption; the jobs runner tracks per-node
  pod counts to tell the two apart instead of counting every node teardown
  against the run.
