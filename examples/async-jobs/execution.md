# queue-drain-worker-ceiling

> A worked execution, produced by running `scripts/` against a local cluster.
> Every number below came out of a run; the rows are the ledger the runner
> wrote. Reproduce it with `scripts/up.sh` and the invocations in §3 — about
> half an hour, most of it the `n=1` points.

---

## 1 · Givens

### System under test

A queue, a worker pool that scales to zero, and one always-on tier the workers
depend on. Each unit costs real CPU in both places, so the curve is bounded by
the system rather than by the client.

| | |
| :--- | :--- |
| Queue | Redis 7.4, two lists — `jobs:work` and `jobs:retry`, no persistence |
| Workers | `worker`, Python 3.12, `BRPOP` over both lists, work queue first |
| Worker cost | 150 ms of CPU per unit, then one POST to the shared tier |
| Worker resources | Requests `200m` / `32Mi` · Limits `600m` / `128Mi` |
| Worker autoscaler | KEDA 2.16.1 `ScaledObject`, two Redis-list triggers, `minReplicaCount: 0`, `pollingInterval: 2`, `cooldownPeriod: 20` |
| Shared tier | `results`, 60 ms of CPU per call, Requests `300m` · Limits `500m` |
| Shared-tier autoscaler | HPA on CPU utilisation, target 70 %, `minReplicas` 1, `maxReplicas` 2 |
| Scale-down | HPA `stabilizationWindowSeconds: 15` — shortened from the 300 s default so a demo finishes |
| Cluster | kind, single node, 10 CPUs available to Docker, on one laptop |
| Commit | working tree, uncommitted |

### Workload — the denominator → report §2

One unit is one queue message. Draining it costs **150 ms of worker CPU, then
one POST to the shared tier costing 60<!--VR4--> ms of its CPU**. One unit in
twenty fails after the burn and is requeued exactly once, so 1,200<!--VR1-->
units are 1,260<!--VD30--> burns and 1,200<!--VR1--> ingests.

The failure is **deterministic** — unit `n` is retried when `n % 20 == 0`, not
at random. Every point on the grid therefore does exactly the same work; a
random failure share would put run-to-run noise on the axis and call it a
measurement.

Arrivals are a **constant offered rate** (40 units/s), open model: units are
enqueued on a schedule whether or not the workers are keeping up, and the
producer runs concurrently with the watch. A producer paced by the drain could
never build a backlog, and the backlog is what this execution measures.

### Metrics

<!-- report-kit metrics: generated from metrics.yaml, edit that file -->

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | work queue depth | `max(jobs_queue_depth{queue="work"})` | confirmed 2026-10-22 | published by the queue exporter, which never scales to zero |
| M2 | retry queue depth | `max(jobs_queue_depth{queue="retry"})` | confirmed 2026-10-22 | rises *after* M1 reads empty — the retries are produced by the work |
| M3 | units in flight | `max(jobs_inflight)` | confirmed 2026-10-22 | `enqueued − completed − M1 − M2`. A popped unit is in no queue and in no counter; this is the only place it appears |
| M4 | worker pods serving | `count(up{job="worker"} == 1)` | confirmed 2026-10-22 | **scrape targets, not replicas.** Has fewer samples than every other ref in every export here — the pool is absent at both ends of the window, which is the profile, not a gap |
| M5 | completion rate | `sum(rate(jobs_completed_total[30s]))` | confirmed 2026-10-22 | from a Redis counter, so it survives the pool going away |
| M6 | shared-tier pods | `count(up{job="results"} == 1)` | confirmed 2026-10-22 | |
| M7 | shared-tier concurrency | `sum(rate(results_seconds_total[30s]))` | confirmed 2026-10-22 | service-seconds per second = mean concurrency inside the handler. Wall time, so CPU throttling inflates it |
| D8 | drain duration | `drain_window.seconds`, point record | active | producer start to the first poll at which `outstanding` reads 0, as the runner timed it; ±1 poll (3 s) |
| D9 | sustained drain rate | `drained_per_second`, point record | active | the headline of a jobs point: units completed ÷ D8, divided by the runner before D8 was rounded |
| D10 | shared-tier mean service time | `mean of M7 per M5 where M5 > 1` | active | seconds; samples where M5 ≤ 1 are the tier idling, and dividing by them measures nothing |
| R11 | what the pool actually did | read off M4 per point | active | carried in the ledger's `Signal` column |
| R12 | worker pool ceiling, the swept axis | `n`, point record | active | maxReplicaCount on the ScaledObject, set by point.py before preflight |
| R13 | units enqueued per point | `count`, point record | active | |
| R14 | offered rate, units per second | `offered_rate`, point record | active | produce.py --rate, an open model |

<!-- /report-kit metrics -->

- **Retention** — Prometheus 2 h · campaign length ~37 min

### Preflight

- [x] Metric names confirmed against the live endpoints — `metrics.yaml` exports seven refs, none empty in any point
- [x] Guards frozen — `execution.yaml`, checked at each point's close
- [x] Floor captured — queues empty, pool at zero, shared tier at 1 replica
- [x] Expected line written before the first run (below)

---

## 2 · Plan

### Axis

- **Varied parameter** — the **worker pool ceiling**, `maxReplicaCount` on the ScaledObject, patched per point by `scripts/point.py`
- **Candidate grid** — 1 · 2 · 4 · 8
- **Sweep order** — 1, 8, then 2, then 4 — ends and middle first, the rest placed by the shape (`methodology.md` §6)
- **Held constant** — images, unit cost, retry share, offered rate, shared-tier HPA bounds, node, and **the unit count within a pass**

### Expected

*Written 2026-09-09, before the first run.* The shared tier is two replicas at
`500m`, which is one core; at 60<!--VR4--> ms of CPU per unit that is **about
16.7<!--VE1--> units/s, whatever the workers do**. One worker running
150<!--VR3--> ms + 60<!--VR4--> ms serially per unit is about
4.8<!--VE2--> units/s. So throughput should track the pool ceiling to
about n = 3 and then flatten near 16 units/s, with the shared tier as the
binding constraint from there on.

### Window

- **Opens** — when the producer process starts · recorded by the run script
- **Closes** — when both queues are empty, the worker pool is at zero, and the shared tier is back at its floor, all three held for 30 s · recorded by the run script
- Scale-in sits inside the window: it is caused by the load and is billed to the point that caused it. **D8, the drain, is reported separately** — a rate averaged over the whole window is averaged over the wind-down too

### Safeguards

- **Abort condition** — a guard breach, or the producer failing to enqueue what the point claims
- **Guards** — G1 conservation (`enqueued − completed = 0`), G2 the point enqueued what it says, G3 both queues empty at close, G4 the shared tier never fell below its floor
- **Estimated duration** — ~2 min per point at 400 units, ~6 min at 1200 for `n=1` ᴱ

---

## 3 · Journal

### Run ledger

Two passes. The first is carried in full because it is what showed the second
was needed.

| # | Point | Units | Window UTC | Outcome | Signal | Exported |
| :--- | :--- | ---: | :--- | :--- | :--- | :--- |
| 01 | n01 | 400 | 15:48:26 → 15:50:27 | ok | one worker, 4.00 units/s ᴿ | ✓ |
| 02 | n08 | 400 | 15:51:26 → 15:52:22 | ok | pool reached 8; 12.69 units/s ᴿ | ✓ |
| 03 | n02 | 400 | 15:53:11 → 15:54:39 | ok | 6.39 units/s — 1.6× #01 for twice the pool ᴿ | ✓ |
| 04 | n04 | 400 | 15:55:28 → 15:56:28 | ok | 10.63 units/s ᴿ | ✓ |
| 05 | n08-relief | 400 | 15:57:20 → 15:58:07 | ok, **but measures nothing about its treatment** | shared tier's ceiling raised to 4; 15.87 units/s ᴿ | ✓ |
| 06 | n01-long | 1200 | 16:08:10 → 16:13:23 | ok | 4.08 units/s ᴿ | ✓ |
| 07 | n08-long | 1200 | 16:14:17 → 16:15:45 | ok | 20.14 units/s — no plateau reached ᴿ | ✓ |
| 08 | n02-long | 1200 | 16:17:04 → 16:20:17 | ok | 7.54 units/s ᴿ | ✓ |
| 09 | n04-long | 1200 | 16:21:09 → 16:23:01 | ok | 13.71 units/s ᴿ | ✓ |
| 10 | n08-long-b | 1200 | 16:23:53 → 16:25:15 | ok | 22.46 units/s — the repeat of #07 ᴿ | ✓ |

Every point's guards were clean, `G1` included: every unit enqueued was
completed, 400 or 1200 of them, in all ten runs.

### Notes

**#05 looked like a 25 % improvement and was not one.** It re-ran #02 with the
shared tier's `maxReplicas` raised from 2 to 4, and drained in 25.2 s against
31.5 s — which reads as proof that the tier was the binding constraint.
`M6` says otherwise: **the tier ran at one replica for the whole of both
drains.** Its HPA reacts on a lag longer than a 30-second drain, so it had not
scaled at all by the time the work was finished, and the treatment never took
effect. What differed between the two runs was when KEDA got the pool to 8 —
about ten seconds, on a drain of about thirty.

That is the whole reason for the second pass. **At 400 units the points were
short enough that the autoscaler's ramp was most of the measurement**, and a
difference of ten seconds of ramp is indistinguishable from a difference in
capacity. It was caught by looking at the series that should have moved if
the treatment had worked, rather than at the headline that did move.

**Unit count is a *Held constant*, and it changed between passes — so the two
passes are not one grid.** #01–#05 are 400 units, #06–#10 are 1200. Rows from
the two are never compared in §4; the matrix is built from the second pass
alone, and the first is kept because deleting it would delete the reason the
second exists.

**#10 is a repeat, not a re-run.** #07 was valid; #10 exists to say how much
two identical points differ. They came out 20.14<!--VD9--> and 22.46<!--VD10--> units/s — about
10<!--VD28--> % apart — which is the resolution of every other comparison in this
execution. Nothing smaller than that is readable.

**The pool takes 15–30 s to reach its ceiling.** On the `n=1` points that is
5 % of the drain; on the `n=8` points it is a third to a half of it. That is
the known weakness of the top of this grid and it is not fixed by the second
pass, only reduced — see §4 Guardrails.

**Nothing needs resetting between points by hand.** The queues are empty
because the window cannot close otherwise, and the runner clears the counters
itself before each point — they are the point's accumulators, and `G1` and
`G2` are meaningless against a total carried over from the run before.
`./point.py --reset` exists for the other case: a point that never converged
and left work in the queue.

### Close

- [x] Every row has a `Signal`
- [x] Every point exported before retention (2 h; campaign ~37 min)
- [x] The first pass carried as rows rather than deleted
- [x] Expected line compared against the result (below) — it was wrong, and §4 says how

---

## 4 · Results

**Finding** — raising the worker pool ceiling from 1<!--VR5--> to 8<!--VR8-->
cuts the drain of 1,200<!--VR1--> units from **294<!--VD1--> s to
60<!--VD4--> s**, a 4.9<!--VD19-->× speed-up for 8<!--VR8-->× the workers.
**No ceiling was found.** Throughput is still climbing at the top of the grid,
and the shared tier — the component this execution was built expecting to be
the constraint — never became one.

**Against the Expected line** — wrong, and the way it was wrong is the useful
part. The prediction was ~16 units/s, from *two replicas at `500m` is one
core, at 60<!--VR4--> ms of CPU per unit that is 16.7<!--VE1--> units/s*.
Measured: 20.14<!--VD9--> units/s, with the tier at one replica for most of
that drain — half of the two the estimate assumed.

The arithmetic modelled the wrong resource. The tier's per-unit cost is 60 ms
of **wall time** — a busy-wait to a deadline — so under CPU contention it
consumes *less* CPU and still returns on schedule. A component like that has a
**latency, not a throughput ceiling**, and no amount of load will make it
saturate the way the estimate assumed. Two independent readings agree:

- `D10`, the tier's mean service time, rises **1<!--VD26--> %**
  (81.6<!--VD11--> → 82.6<!--VD15--> ms) while throughput rises
  **394<!--VD27--> %**. A saturating tier's service time climbs steeply;
  this one barely moves.
- `M6` shows the tier below its own replica ceiling (2, its `maxReplicas`)
  for part of every drain of the second pass, and for all of it at `n = 1` —
  short of its limit for much of the load, and still not binding.

### Matrix

Second pass only. Rows from the first pass are a different *Held constant*
(400 units) and are not comparable — see §3.

| Point | Pool ceiling | D8 drain | D9 units/s | Speed-up | Per-worker efficiency | M1 peak queue | M6 tier pods | D10 tier service | Signal |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| n01-long | 1<!--VR5--> | 294.1<!--VD1--> s | 4.08<!--VD6--> | 1.00<!--VD16-->× | 100<!--VD21--> % | 1,066<!--VM1--> | 1 | 81.6<!--VD11--> ms | baseline |
| n02-long | 2<!--VR6--> | 159.2<!--VD2--> s | 7.54<!--VD7--> | 1.85<!--VD17-->× | 92<!--VD22--> % | 1,006<!--VM2--> | 2 | 80.2<!--VD12--> ms | near-linear |
| n04-long | 4<!--VR7--> | 87.5<!--VD3--> s | 13.71<!--VD8--> | 3.36<!--VD18-->× | 84<!--VD23--> % | 814<!--VM3--> | 2 | 75.5<!--VD13--> ms | efficiency decaying |
| n08-long | 8<!--VR8--> | 59.6<!--VD4--> s | 20.14<!--VD9--> | 4.94<!--VD19-->× | 62<!--VD24--> % | 773<!--VM4--> | 2 | 82.5<!--VD14--> ms | still climbing |
| n08-long-b | 8<!--VR8--> | 53.4<!--VD5--> s | 22.46<!--VD10--> | 5.50<!--VD20-->× | 69<!--VD25--> % | 616<!--VM5--> | 2 | 82.6<!--VD15--> ms | the repeat |

Every point: 1,200<!--VR1--> units offered at a constant 40<!--VR2--> units/s,
60<!--VD29--> of them retried once, `G1`–`G4` clean.

### Saturation

**No tier is claimed, and that is the result.** `methodology.md` §6's reading
of three points is explicit: *still falling at the top → the range was wrong,
extend it*. Efficiency is decaying (100<!--VD21--> → 92<!--VD22--> →
84<!--VD23--> → 62<!--VD24--> %) but capacity is still rising, so this grid ends
before the system does.

**The range is not extended, and the reason is the rig rather than the
system.** At `n = 8` the workers already request 1.6 cores and are limited to
4.8, on a 10-CPU laptop that is also running the api example's cluster.
`n = 16` would measure the laptop, and a row that reports the measuring
instrument as a property of the system under test is worse than a missing row.

**Where the missing 38 % goes is not resolved.** Two candidates — the
autoscaler's ramp (the pool takes 15–30 s to reach 8, a third to a half of a
60 s drain) and real CPU contention — and this grid cannot separate them,
because at `n = 8` the drain is no longer long enough to *contain* a plateau:
`rate(jobs_completed_total[30s])` never settles inside it. Distinguishing them
needs the unit count scaled with `n` so that every point's drain holds a
comparable steady segment, which is a different execution.

### Guardrails

- **Do not read `D9` at `n = 8` as a capacity value.** Two identical points
  came out 10<!--VD28--> % apart, and the drain is ramp-dominated. Anything
  below about 10<!--VD28--> % is noise in this rig.
- **Nothing here is a CPU cost.** Both `burn()` implementations spin to a
  wall-clock deadline, so every "per-unit cost" in §1 is a *latency*. Capacity
  arithmetic built on those numbers — as the Expected line was — describes a
  resource this system does not have.
- **The retry share is deterministic** (unit `n` retries when `n % 20 == 0`).
  That is what makes points comparable, and it is also why nothing here says
  anything about a system whose failure rate varies with load.
- **`M4` counts scrape targets, not replicas**, and has fewer samples than
  every other ref in every export — the pool is genuinely absent at both ends
  of the window. Reading that as an export gap would be reading the profile as
  a fault.
- **The measured window is not the drain.** The window includes scale-in,
  which is caused by the load and billed to the point; `D8` is the drain
  alone. At `n = 8` the window is 88 s against a 60 s drain, so a rate
  computed over the window would report 13.7 units/s instead of 20.1 — a 32 %
  understatement, from averaging over the wind-down as well as the work.

### Retro

The first pass produced a clean-looking curve, clean guards on every point,
and a headline number that was mostly the autoscaler's start-up. Nothing in
the point records said so. What said so was checking the series that the
`n08-relief` treatment *should* have moved — and finding it flat.

The second pass fixed the symptom by making the drains longer, not the cause.
The cause is that a jobs point's headline is a duration, and a duration
contains every fixed cost of getting started. Holding the unit count constant
across the grid keeps the work identical and lets the drain shrink until the
ramp dominates it; scaling the count with `n` would keep the drain comparable
and change the work. Both are defensible, neither is free, and the choice
belongs in the Plan rather than in the analysis afterwards. This execution
made the first choice and the top row pays for it.

**Back into the kit — two fixes, both from building this example:**

- **`jobs_point.py` could close a zero-length window.** Empty queues, a pool
  at zero and every tier at its floor is also exactly what a system that has
  not started yet looks like, so a producer slower to start than
  `HOLD_SECONDS` closed a window over a system that had done no work, and the
  point read clean. The watch loop now refuses to begin the hold until it has
  seen the system busy once.
- **`report-kit selftest` was passing on precisely that bug.** Its fake never
  entered its busy phase — preflight's reads spent a poll budget that was
  counted from zero — so both runners watched a system that was idle from the
  first poll, and the assertion was `window >= 0`. The fake now counts from
  the poll the load started on, and the assertion is `> 0`. Both profiles now
  exercise the scale-out → scale-in transition they were supposed to.
