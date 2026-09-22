# runners/ — measurement points for two workload profiles

A **point** is one measured run at one setting of whatever you're sweeping.
A **sweep** is a series of points that differ in exactly one variable; every
point of a sweep must agree about everything else, or the curve you fit at
the end is comparing two different systems.

These are templates, not a framework. Copy the one that matches your
workload, edit its CONSTANTS block, and the rest should need no changes.
Nothing here subclasses anything; the flow of a run is the body of `main()`,
readable top to bottom.

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

Both runners do the same six things in the same order:

```
preflight   assert a known starting state; collect every failure, then stop
load        apply it, recording exactly when it started
watch       poll until the close condition has HELD, not merely occurred
export      snapshot the Prometheus series for the window to .jsonl
guards      evaluate the frozen bounds; an empty result is a gap, not a pass
record      write <run>.point.md and <run>.point.json, then exit by verdict
```

## What the runner needs to run at all

**Python**: standard library, plus `PyYAML` (for `env.yaml`), both pulled in
by `pip install report-kit`. Add `report-kit[s3]` only if you use
`report_kit.cloud.aws_s3`. **On PATH**: `kubectl` with a working context,
`aws` for the jobs profile's queue reads, `git` for the commit the point
records. **Prometheus** is assumed as the metrics backend.

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

Edit only the CONSTANTS block at the top:

- **`GATES`** (api) — the deployments whose scaling this point measures.
  `floor` is where the window must return to; `ceiling` is the configured
  max, and reaching it means the point measured your limit rather than the
  system, which the runner flags.
- **`QUEUES` / `WORKER_POOL_KEY` / `SHARED_TIERS`** (jobs) — what has to
  reach empty, zero and floor respectively.
- **`HOLD_SECONDS`** — how long the close condition must hold. Set it longer
  than one autoscaler decision interval. Must be smaller than
  `max_wait_seconds` in env.yaml; `poll.wait_until_stable` refuses the
  reverse rather than timing out forever and blaming the cluster.
- **`FREEZE`** — the workloads whose container image digests are pinned for
  the sweep, as `kind/name`.

Everything else lives in `env.yaml` (see `env.example.yaml`): addresses,
port-forwards, queue URLs, the generator/producer command, poll interval and
timeout. The split is deliberate — **env.yaml may differ between clusters,
the constants block may not differ between points of one sweep.** If you
find yourself wanting to sweep something from env.yaml, move it into the
runner first.

## What you have to provide

Five things. A runner reads all of them and will not invent any of them.

### 1. `env.yaml` — addresses

Required keys, both profiles:

| key | meaning |
| :--- | :--- |
| `namespace` | default namespace for kubectl reads |
| `namespaces.<workload>` | optional per-workload override |
| `poll_seconds` | how often to poll while watching (float; 15 is sane) |
| `max_wait_seconds` | give up on the window after this; must exceed `HOLD_SECONDS` |
| `prometheus.url` | where to query |
| `prometheus.service` / `.namespace` / `.mapping` | optional: open a port-forward instead of assuming reachability |

`api_point.py` also needs `generator.command` (a list; `{run} {rate}
{duration} {log}` are substituted) and optionally `generator.env`.

`jobs_point.py` also needs `producer.command` (same substitution, plus
`{n} {count}`), `sqs.<label>` per queue in `QUEUES`, the selector named by
`WORKER_POOL_KEY`, and `worker_selector` for the pod-per-node read. Its
reset step additionally uses `s3.bucket` / `s3.prefix` and `qdrant.url` /
`qdrant.collection` if present, and skips whatever is absent.

See `env.example.yaml` for a filled-in version of all of it.

### 2. `series.txt` — what gets exported

`ref|promql`, one per line. `#` comments and blank lines ignored. Refs must
be unique. Exported over the window into `<run>.jsonl` at every point.

```
M1|sum(rate(http_requests_total[30s]))
M2|max by (pod) (container_memory_working_set_bytes{pod=~"api-.*"})
```

### 3. `guards.txt` — what makes a point invalid

`ref|bound|promql`. Bound is `min <v>`, `max <v>`, or both separated by
whitespace. `{name}` placeholders are filled from the run's arguments
(`{rate}` for api; `{n}` and `{count}` for jobs). Evaluated once, as of when
the load stopped.

```
G1|max 0.01|sum(rate(http_requests_total{code=~"5.."}[1m])) or vector(0)
G2|min 1|count(up{job="api"} == 1)
G3|min 0.9 max 1.1|sum(rate(http_requests_total[1m])) / {rate}
```

A guard whose query returns nothing **fails** — an empty result is a gap,
not a pass. Write `or vector(0)` where zero is genuinely the answer.

### 4. `image-freeze.json` — what the sweep claims to have measured

Generated, not hand-written: run `--set-freeze` once at the start of a
sweep and commit the file. Every later point compares against it and fails
preflight if an image moved. Delete and re-generate only when deliberately
starting a new sweep.

### 5. The CONSTANTS block in your copy of the runner

Described above. This is the only code you edit.

### Optional

`--out-dir` (defaults to `./data`), `--step` (export resolution, default
15s), `--env` / `--series` / `--guards` / `--freeze-file` if you keep them
somewhere other than next to the runner.

## Output per point

```
<out-dir>/<run>.point.md      the block to paste into the write-up
<out-dir>/<run>.point.json    the machine-readable record: window, guards,
                              observations, image digests, commit
<out-dir>/<run>.jsonl         the exported series
<out-dir>/<run>.meta.json     export manifest: per-ref series and sample counts
<out-dir>/<run>.generator.log the generator's / producer's own output
```

## Exit codes

| | |
| :--- | :--- |
| 0 | clean |
| 1 | preflight or usage failed — nothing ran |
| 2 | the run is valid but at least one ref exported nothing. **The window is in the point record; re-export with `export_metrics.py` before retention drops it.** |
| 3 | ran, but validity is in doubt: a guard breached, or a node was lost while it held work |
| 4 | the window never closed inside the timeout — nothing exported, because an unclosed window has no end |

## Resetting between points

Not a separate script: `./jobs_point.py --reset-only` wipes the S3 prefix,
purges the queues, clears the sink and waits for the system to read idle.
It lives in the runner because it needs exactly the runner's constants —
a second file with its own copy of `QUEUES` and `SHARED_TIERS` is a second
file to keep in sync. `--reset-after` does it once a point's files are
written; `--dry-run` prints what it would touch.

Run it between points of a jobs sweep. Waiting for organic drain costs
about an hour per point.

## The tools — run as-is, nothing to edit

Subcommands of the same CLI; `report-kit <tool> --help` for the options.

- **`report-kit export-metrics`** — re-export a window by hand. The case that
  matters: the run finished, the export didn't, and the window is sitting
  in the point record with retention counting down. A window can be
  re-exported but never re-measured. It is the one command built to work when
  the rest of the package cannot load.
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
  Provisional by construction: reconcile against CUR before the figure
  reaches a report.
- **`report-kit selftest`** — runs both runner templates end to end against a
  faked cluster, no cluster or AWS needed. Run it after editing a runner. It
  is also the worked example for testing your own: about sixty lines of
  fakes, patching only `report_kit.shell.sh` / `sh_json` / `http_json`.

## Traps these encode

Each of these cost someone a wasted run:

- **A condition that is true right now is not a condition that has held.** A
  queue reads zero while messages are still in flight; a deployment touches
  its floor between two scaling decisions. Closing on the instantaneous
  reading records a point that measures half a run.
- **The producer runs alongside the watch, never before it.** Filling the
  queue first measures a system draining a backlog that already exists —
  a different experiment, and the arrival pattern is gone from the data.
- **An idle system satisfies the close condition.** Empty queues, a pool at
  zero and every tier at its floor is also exactly what a system that has not
  started yet looks like. A producer slower to start than `HOLD_SECONDS` — an
  upload, a seeding pass, an image pull — closes a zero-length window over a
  system that never did any work, and the point reads clean. `jobs_point.py`
  will not begin the hold until it has seen the system busy at least once.
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
  validate, and passes quietly. Both runners pass `at=` for this reason.
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
