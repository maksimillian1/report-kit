# mock-api-arrival-rate

> A worked execution, produced by running `scripts/` against a local cluster.
> Every number below came out of a run; the rows are the ledger the runner
> wrote. Reproduce it with `scripts/up.sh` and the six invocations of
> `scripts/point.py` in §3 — about fifteen minutes.

---

## 1 · Givens

### System under test

A single HTTP service on Kubernetes, autoscaled on CPU. Each request costs the
server about 40 ms of CPU, so throughput is bounded by CPU and the shape of the
curve is not an artifact of the client.

| | |
| :--- | :--- |
| Workload | `mock-api`, one container, Python `ThreadingHTTPServer` |
| Requests | `50m` CPU, `32Mi` memory · Limits `200m` / `128Mi` |
| Autoscaler | HPA on CPU utilisation, target 50 %, `minReplicas` 1, `maxReplicas` 4 |
| Scale-down | `stabilizationWindowSeconds: 15` — shortened from the 300 s default so a demo finishes |
| Cluster | kind, single node, on one laptop |
| Commit | working tree, uncommitted (`git_facts` recorded it as dirty) |

### Workload — the denominator → report §2

One unit is one `GET /` served with status 200. The client offers a **constant
arrival rate** — requests leave on schedule whether or not earlier ones have
come back. A closed model would have offered less load as the server slowed and
the saturation below would never have appeared.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | `http_reqs.rate`, k6 summary | confirmed 2026-09-05 | client-side; the denominator of D7 |
| M2 | client-observed latency p95 | `http_req_duration.p(95)`, k6 summary | confirmed 2026-09-05 | includes the port-forward hop |
| M3 | share of requests not served | `http_req_failed.value`, k6 summary | confirmed 2026-09-05 | timeouts at 10 s count here |
| M4 | serving instances | `count(up{job="mock-api"} == 1)` | confirmed 2026-09-05 | **scrape targets, not replicas** — a terminating pod and its replacement are both up for one interval, so this overshoots `maxReplicas` during rollover |
| M5 | server-side served rate | `sum(rate(mock_requests_total[30s]))` | confirmed 2026-09-05 | second opinion on M1 |
| M6 | server-side mean service time | `sum(rate(mock_request_duration_seconds_sum[30s])) / sum(rate(mock_requests_total[30s]))` | confirmed 2026-09-05 | excludes queueing, unlike M2 |
| R7 | which component sat at its ceiling | hand-recorded at the end of each run | active | carried in the ledger `Signal` column |
| D8 | offered load actually served | `M1 ÷ offered rate` | active | |

- **Retention** — Prometheus 1 h · campaign length 20 min

### Preflight

- [x] Metric names confirmed against the live endpoint — `series.txt` exports four refs, none empty
- [x] Guards frozen — `guards.txt`, checked at each point's close
- [x] Floor captured — 1 replica, no traffic
- [x] Expected line written before the first run (below)

---

## 2 · Plan

### Axis

- **Varied parameter** — offered arrival rate, `TARGET_RATE` in `scripts/load.js`
- **Candidate grid** — 4 · 12 · 24 · 32 · 40 req/s
- **Sweep order** — 4, 24, 12, then 40, then 32 — ends and middle first, the rest placed by the shape (`methodology.md` §7)
- **Held constant** — image, CPU limits, HPA bounds, node, 45 s of load per point, no other workload on the node

### Expected

*Written 2026-09-05, before the first run.* Four replicas at `200m` each is
0.8 cores; at ~40 ms of CPU per request that is **about 20 req/s**. Latency
should be flat below that and rise sharply above it, so the SLO-breaking rate
and the throughput ceiling should coincide near 20.

### Window

- **Opens** — when the generator process starts · recorded by the run script
- **Closes** — when every gated deployment has been back at its floor for 20 s · recorded by the run script
- Scale-in sits inside the window: it is caused by the load and is billed to the point that caused it

### Safeguards

- **Abort condition** — a guard breach, or the generator failing to run at all
- **Estimated duration** — ~2 min per point, ~15 min for the grid ᴱ

---

## 3 · Journal

### Run ledger

| # | Point | Window UTC | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | rate-04 | 18:57:41 → 18:59:23 | ok | headroom — served all 4/s at p95 98 ms ᴿ | ✓ |
| 02 | rate-24 | 19:06:32 → 19:07:55 | ok | at the knee — served all 24/s, but p95 already 412 ms ᴿ | ✓ |
| 03 | rate-12 | 19:08:48 → 19:10:11 | ok | headroom — p95 195 ms, no drops ᴿ | ✓ |
| 04 | rate-40 | 19:11:36 → 19:13:11 | ok | saturated — CPU-bound, 806 iterations never started ᴿ | ✓ |
| 05 | rate-32 | 19:14:24 → 19:15:16 | **invalid, ran against one replica** | — | ✓ |
| 06 | rate-32 | 19:16:38 → 19:17:56 | ok | past the knee — p95 3.8 s, throughput still climbing ᴿ | ✓ |

### Notes

**#04 before #05** — the first three points said the range was wrong rather than
that the curve had a minimum: throughput tracked the offered rate at all of
them and latency was still climbing at the top. `methodology.md` §7 calls that
"extend it", so 40 was run before the refinement point, and it was 40 that
produced the collapse.

**#05 — invalid, and the ledger says why.** The point ran while the deployment
was still at one replica: it started 70 s after #04 ended, and the autoscaler
had scaled down but not yet back up. Replica count is in *Held constant*, so a
point measured against one replica is not comparable with four, whatever its
numbers say. It served 26.35<!--FM4-->/s at p95 4,680<!--FM10--> ms — close enough to #06 to be
mistaken for a valid row, which is exactly why the check is mechanical
(`M4 = 1`) rather than a judgement about whether the number "looks right".

**#06 — the re-run.** Same Point identity, new row, because the ledger's `#` is
never reused. Four replicas this time: 29.46<!--FM5-->/s at p95 3,755<!--FM11--> ms.

**Between points the instrumentation needs a moment.** A pod that has just
scaled in is still a scrape target for an interval or two and reports `up == 0`,
which fails the next point's preflight. The runs above waited for `up == 0` to
return nothing before starting — 0–20 s in practice. Starting points
back-to-back fails preflight through no fault of the system.

**The generator's exit code is not always a malfunction.** #04 exited 99, which
is k6's code for a breached threshold — the system failed to serve 5 % of
requests, which is the finding, not a broken generator. The runner flags any
non-zero exit; deciding which kind it was is the author's.

### Close

- [x] Every row has a `Signal`
- [x] Every valid point exported before retention (1 h; campaign 20 min)
- [x] `#05` carried as invalid rather than deleted
- [x] Expected line compared against the result (below)

---

## 4 · Results

**Finding** — the service serves the offered rate up to **24<!--FR3--> req/s** at
p95 412<!--FM9--> ms. Between 24 and 32 the queue grows faster than it drains: throughput
still climbs to 29.5<!--FM5-->/s but p95 jumps nine-fold to 3,755<!--FM11--> ms. At
40<!--FR5--> req/s it breaks down — 19.7<!--FM6-->/s served, one request in five unanswered,
p95 pinned at the 10 s timeout. **Throughput peaks before the system stops keeping up, and latency
finds the ceiling first.**

**Against the Expected line** — the throughput ceiling landed near 29/s, not
20/s, so the CPU estimate was pessimistic by about half. But the *useful*
ceiling — the highest rate served at a latency anyone would accept — is 24/s,
close to the estimate. The expectation was right about where the system stops
being usable and wrong about where it stops working, and those are not the
same rate.

### Matrix

| Point | Offered | M1 served/s | D8 served share | M2 p95 | M3 unserved | M4 targets | Signal |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| rate-04 | 4<!--FR1--> | 4.01<!--FM1--> | 100<!--FD1--> % | 98<!--FM7--> ms | 0<!--FM13--> % | 4 | headroom |
| rate-12 | 12<!--FR2--> | 11.99<!--FM2--> | 100<!--FD2--> % | 195<!--FM8--> ms | 0<!--FM14--> % | 4 | headroom |
| rate-24 | 24<!--FR3--> | 23.97<!--FM3--> | 100<!--FD3--> % | 412<!--FM9--> ms | 0<!--FM15--> % | 4 | at the knee |
| rate-32 ᴱˣ | 32<!--FR4--> | 26.35<!--FM4--> | 82<!--FD4--> % | 4,680<!--FM10--> ms | 0.5<!--FM16--> % | 1 | — (invalid) |
| rate-32 | 32<!--FR4--> | 29.46<!--FM5--> | 92<!--FD5--> % | 3,755<!--FM11--> ms | 0.2<!--FM17--> % | 4 | past the knee |
| rate-40 | 40<!--FR5--> | 19.72<!--FM6--> | 49<!--FD6--> % | 10,001<!--FM12--> ms | 21.2<!--FM18--> % | 5 | saturated |

ᴱˣ — excluded from the curve fit: ran against one replica, see Journal #05.

### Saturation

**Tier 1 — CPU, between 24 and 32 req/s, runs #02 and #06.** Latency rises with
offered load from the very first point (98<!--FM7--> → 195<!--FM8--> → 412<!--FM9--> ms across 4<!--FR1--> → 12<!--FR2--> → 24<!--FR3-->),
which is queueing, not noise. Past 24 the four replicas are already the
autoscaler's maximum, so nothing more arrives to absorb the load and the queue
grows without bound. `M6` (server-side service time, which excludes queueing)
stays within a factor of two across the whole grid, so the request handler is
not itself slowing down — the wait is in front of it.

**No second tier is claimed.** The grid ends where the first tier breaks, and a
sweep that stops at the first ceiling cannot see what would bind after it.

### Guardrails

- **Do not read the 40 req/s row as capacity.** It is what breakdown looks
  like: throughput below the 32 row and one request in five lost.
- **The replica ceiling is part of the measurement.** Every valid point above
  4 req/s ran at `maxReplicas`, so this curve describes *this* HPA
  configuration, not the service. Raising `maxReplicas` moves the knee and the
  sweep would need repeating.
- **`M4` counts scrape targets.** During rollover a terminating pod and its
  replacement are both up, which is why the 40 req/s row shows 5 against a
  maximum of 4. It is not a replica count and should not be read as one.

### Retro

The shape only appeared after the range was extended: three points inside a
range that was too small showed a straight line and no ceiling. Taking the ends
first is what surfaced that on the fourth run rather than the ninth.

The invalid row cost one re-run and would have cost a wrong conclusion. It was
caught because replica count is checked as a number rather than eyeballed —
26.35<!--FM4-->/s at p95 4,680<!--FM10--> ms sits close enough to the valid row that no one would
have questioned it.

Back into the kit: nothing this time. The runner already refused to overwrite
the earlier export, flagged the generator's exit, and recorded the window from
the process rather than from a timestamp typed afterwards.
