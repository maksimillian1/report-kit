# async-jobs/scripts — the machinery behind `../execution.md`

A queue, a worker pool that scales to **zero**, a shared tier that does not,
and a producer that runs *while* the system drains. Running the grid below is
what produced every number in `../execution.md` and `../report.md`.

```bash
./up.sh                                              # kind + KEDA + workload (~3 min)
./point.py --run n01-long --n 1 --count 1200         # ends first,
./point.py --run n08-long --n 8 --count 1200         #   methodology.md §7
./point.py --run n02-long --n 2 --count 1200         # then the middle
./point.py --run n04-long --n 4 --count 1200         # then place the rest by the shape
./point.py --run n08-long-b --n 8 --count 1200       # a repeat, to size the noise
./down.sh                                            # delete the cluster
```

`--n` is the **worker pool ceiling** — the axis. `point.py` patches it into
the ScaledObject at the start of each point, so the run and the record cannot
disagree about what was measured.

The `-long` in the names is not decoration. An earlier pass ran the same grid
at 400 units and its drains were short enough that the autoscaler's ramp was
most of the measurement — `../execution.md` §3 note #05 is that story, and it
is the most useful thing in this example. Those runs are still in `data/`
under the bare names.

**Leave a gap between points.** A worker pod that has just scaled in is still
a scrape target for an interval or two and reports `up == 0`, which fails the
next point's preflight. The hold at the end of a point usually covers it.

## Why this is a second example and not a second grid

The api example measures a system answering. This one measures a system
*catching up*, and four things about that are different enough to need their
own runner, their own inputs, and their own document:

| | api — `simple-api/` | jobs — here |
| :--- | :--- | :--- |
| The load | runs to completion, then you look | runs **concurrently with the watch** |
| The window closes when | one deployment is back at its floor | queues empty **and** pool at zero **and** tier at floor |
| The headline | what the caller saw, per request | how long the backlog took to clear |
| The measurement dies with the pods | no — the service is always up | **yes** — the pool scales to zero and takes `/metrics` with it |

The last row is the one that bites. See *Counters that outlive the pods*.

## Files

| | |
| :--- | :--- |
| `point.py` | the runner: preflight → arm → producer+watch → export → guards → record |
| `produce.py` | the producer: enqueues at a constant offered rate, in the background |
| `resp.py` | the ten lines of the Redis wire protocol both sides need |
| `cluster/` | what runs *in* the cluster: `worker.py`, `results.py`, `exporter.py` |
| `env.yaml` | addresses, queue keys, counter keys, and the producer command |
| `series.txt` | the Prometheus refs (M1–M7) |
| `guards.txt` | what makes a point invalid — conservation, above all |
| `manifests/` | redis + exporter, the worker deployment, the shared tier and its HPA, Prometheus |
| `keda/` | the ScaledObject — separate because it needs CRDs `up.sh` installs first |
| `data/` | what the runs wrote — the evidence `../execution.md` cites |

`cluster/*.py` are real files, mounted through a ConfigMap that `up.sh` builds
from this directory rather than pasted into YAML. `resp.py` goes into the same
ConfigMap, so the host and the pods speak to the queue through one file
instead of two copies that drift.

`point.py` is deliberately smaller than the `jobs_point.py` template: no image
freeze, git facts, node-loss tracking, cost pass or exit-code contract. Read
this one to see the shape; run `report-kit new-point --profile jobs` to get
the real one.

It imports `report_kit` like any other package — this example is an ordinary
consumer of the installed kit, which is why a green run here also proves the
install is sound.

## The three things this profile is actually about

### 1 · The producer runs while the watch loop watches

Not before it. Filling the queue first and then starting to watch measures a
system draining a backlog that already exists — a different experiment with a
different answer, and the arrival pattern that built the backlog is gone from
the data. `report_kit.proc.Background` is that shape, and `point.py` uses it
in four lines.

### 2 · The window closes on three conditions, held

Queues empty, worker pool at zero, shared tier back at its floor. Any one of
them alone reads "done" while work is still in flight somewhere else:

- **Queues empty** is false the moment a worker pops the last unit and starts
  working on it. `BRPOP` is destructive; nothing in Redis knows that unit
  exists. The exporter publishes `jobs_inflight` precisely so this is visible
  rather than a matter of trust.
- **Pool at zero** is false while a retried unit is still waiting: the retry
  queue refills *after* the work queue has already read empty, which is why
  the ScaledObject has a second trigger on it.
- **Tier at floor** is the slowest of the three here — the shared tier's HPA
  reacts on a lag and often scales *up* after the drain has finished.

`poll.wait_until_stable` requires all three to hold for `HOLD_SECONDS` (30 s),
which has to sit above the ScaledObject's `cooldownPeriod` (20 s) or the hold
completes while the pool is still winding down.

### 3 · Counters that outlive the pods

The worker pool scales to zero at the end of every point and takes its
`/metrics` endpoint with it. A counter exported by the workers therefore has
**no series at all** at the instant the window closes — and guards are checked
at the window's close, where `check_guards` correctly reports NO DATA and
fails the point.

So the counters that decide validity live in Redis, and the exporter — which
never scales to zero — republishes them. That is what makes `G1` possible:

```
G1|max 0|max(jobs_enqueued_total) - max(jobs_completed_total)
```

Every unit enqueued is completed exactly once. Anything left over was dropped
by a worker that went away holding it, and the drain time the point reports is
then a time to do *less work than it claims*. Nothing else in the record would
say so.

Same reason `series.txt` reads queue depth from the exporter rather than from
the workers: `M4` (`count(up{job="worker"} == 1)`) is the one worker-side ref,
and it has fewer samples than every other ref in every export here — which is
the pool being absent at both ends of the window, not a gap.

## What the run shows

Verified output, not an illustration:

```
[  ok  ] queues empty — retry=0 work=0
[  ok  ] worker pool at zero — 0 pod(s)
[  ok  ] results at floor — 1 replica(s), floor 1
[  ok  ] prometheus targets up
-> arming counters
[  ok  ] cleared 3 key(s): jobs:work, jobs:retry, jobs:enqueued, jobs:done, jobs:retried

-> producer (background) · python3 produce.py ... --count 1200 --rate 40

-> watching the drain — hold 30s, poll 3.0s, timeout 0h15m00s
    q[retry=0 work=0]     workers=0  results=1 outstanding=0    producer=running
    q[retry=0 work=120]   workers=1  results=1 outstanding=121  producer=running
    q[retry=9 work=676]   workers=1  results=1 outstanding=686  producer=running   ← arrivals outrun the drain
    q[retry=17 work=1068] workers=1  results=1 outstanding=1086 producer=done
      … 76 polls …
    q[retry=48 work=0]    workers=1  results=2 outstanding=49   producer=done      ← work queue empty, 48 retries left
    q[retry=6 work=0]     workers=1  results=2 outstanding=7    producer=done
    q[retry=0 work=0]     workers=1  results=2 outstanding=0    producer=done      ← every queue empty; still not done
    q[retry=0 work=0]     workers=0  results=2 outstanding=0    producer=done      ← pool gone; tier still above floor
    q[retry=0 work=0]     workers=0  results=1 outstanding=0    producer=done · held 0s/30s
      … 9 polls …
    q[retry=0 work=0]     workers=0  results=1 outstanding=0    producer=done · held 31s/30s

[  ok  ] window 2026-09-09T15:46:23Z .. 2026-09-09T15:51:28Z (0h05m05s)
-> exporting 7 ref(s) · 2026-09-09T15:46:23Z .. 2026-09-09T15:51:28Z · step 5s
[  ok  ] M1 — 1 series, 62 points          … M2 … M7
[  ok  ] data/n01-long.jsonl · 7 series · 431 points

[  ok  ] guard G1 = 0     [max 0]          ← 1200 enqueued, 1200 completed
[  ok  ] guard G2 = 1200  [min 1200]
[  ok  ] guard G3 = 0     [max 0]
[  ok  ] guard G4 = 2     [min 1]
```

Three details there matter more than the rest.

**The three close conditions come true at three different times, in that
order.** The work queue empties with 48 retried units still waiting. Both
queues then read empty while a worker is still holding one. The pool reaches
zero while the shared tier is still at 2 replicas, because its HPA scaled it
*up* after the drain had already ended. Only on the next poll does the hold
begin — and a runner closing on any single one of those readings would have
recorded a shorter window than the run.

**`outstanding` is the number no queue can give you.** `BRPOP` is destructive,
so a popped unit exists in no queue and in no counter; `enqueued - completed`
is the only place it shows up. It is what makes `q[retry=0 work=0] …
outstanding=0` a claim rather than a hope — and `G1` is that same arithmetic
checked at the window's close.

**The retry queue refills after the work queue reads empty**, in every run
here — the retries are produced by the work, so they cannot all exist before
the work is done. That is why the ScaledObject carries a second trigger on
`jobs:retry`. With only the `jobs:work` trigger the pool's cooldown starts the
moment the work queue drains, and whether the point survives becomes a race
between that cooldown and the retry backlog: the workers pop from both queues,
so a small backlog clears in time and a large one does not. A close condition
should not be decided by which of two timers wins.

## What a local cluster can and cannot test

| Part | In kind | Why |
| :--- | :--- | :--- |
| The whole async lifecycle | **yes** | this example, end to end |
| A producer running concurrently with the watch (`proc.Background`) | **yes** | a real subprocess, killed by process group on exit |
| The three-part close condition, held (`poll.wait_until_stable`) | **yes** | all three conditions are real and reached at different times |
| Scale-to-**zero** as the close condition | **yes, with KEDA** | `up.sh` installs it; this is the local stand-in for a node pool draining |
| A retry queue refilling after the work queue reads empty | **yes** | deterministic, one unit in twenty |
| Counters surviving a pool that scaled to zero | **yes** | the reason they live in Redis |
| Conservation as a guard (`G1`) | **yes** | and it is a real check, not a tautology — a short grace period breaks it |
| `prometheus` — query, range, export, guards at `at=` | **yes** | a real Prometheus, real scrape intervals |
| `portforward`, `cluster.pods_by_node`, `deployment_replicas` | **yes** | plain kubectl reads against a real API server |
| Queue depth via `cloud.aws.sqs_depth` | **no** | this example speaks Redis; SQS via LocalStack is still unverified |
| **Node** autoscaling — `nodes_by_selector` reaching zero | **no** | kind nodes are fixed containers; nothing creates or removes them |
| **Interruptions** — `interrupt_events`, `FORCED_REASONS` | **no** | needs Karpenter and real EC2 reclaiming instances |
| **Cost** — `ondemand_hourly`, `spot_hourly`, `node_cost` | **no** | real AWS Pricing and spot-history APIs |
| Real capacity figures | **no** | one laptop, one node, throttled CPU |

The pool reaching zero is the substitution that makes this example worth
having: it is the same question the real profile asks of a node pool —
*is anything still allocated to this work?* — one layer down, where a laptop
can answer it. What stays untested is everything **downstream** of that
answer: what the allocation cost, and whether it was taken away involuntarily.

A green run here means the async measurement loop is correct. It never means
the cost or interruption logic is.

## Notes

- `up.sh` installs metrics-server with `--kubelet-insecure-tls`; kind's kubelet
  serving certificates are self-signed and the shared tier's HPA needs metrics.
- **`cooldownPeriod` and `HOLD_SECONDS` are one decision made in two files.**
  `keda/scaledobject.yaml` cuts the cooldown to 20 s and `point.py` holds for
  30 s. Raise the cooldown without raising the hold and the window closes
  while the pool is still winding down.
- The shared tier's HPA `scaleDown.stabilizationWindowSeconds` is cut to 15 s
  for the same reason the api example cuts it. Kubernetes defaults to 300 s;
  in a real sweep leave the default and set the hold above it.
- **The worker's grace period is load-bearing.** `terminationGracePeriodSeconds:
  30` against units of ~0.25 s is what makes scale-in safe: SIGTERM sets a
  flag, the unit in hand finishes and is counted, then the process exits. Cut
  it below a unit's duration and `G1` starts firing — which is the guard
  working, not the example being flaky.
- The retry rate is deterministic (unit `n` retries when `n % 20 == 0`), so
  every point on the grid does exactly the same work. A random failure rate
  would put run-to-run noise on the axis and call it a measurement.
- The cluster keeps running after a point. `./down.sh` removes it entirely.
- Both example clusters can be up at once — this one's port-forwards are on
  9092 and 6380, the api example's on 9091 and 8081.
