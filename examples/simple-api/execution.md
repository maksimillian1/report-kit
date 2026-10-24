# mock-api-arrival-rate

> A worked execution, produced by running `scripts/` against a local cluster.
> Every number below came out of a run; the rows are the ledger the runner
> wrote, and every ref of the register was worked out of a point's record by
> `report-kit point finish`. Reproduce it with `scripts/up.sh` and the six
> invocations of `scripts/api_point.py` in `scripts/README.md` — about twenty
> minutes.

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
| Commit | working tree, uncommitted |

### Workload — the denominator → report §2

One unit is one `GET /` served with status 200. The client offers a **constant
arrival rate** — requests leave on schedule whether or not earlier ones have
come back. A closed model would have offered less load as the server slowed and
the saturation below would never have appeared.

### Metrics

<!-- report-kit metrics: generated from metrics.yaml, edit that file -->

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | `observations.client.served_per_second`, point record | confirmed 2026-10-22 | client-side, k6 summary `http_reqs.rate`; the numerator of D8 |
| M2 | client-observed latency p95 | `observations.client.p95_ms`, point record | confirmed 2026-10-22 | k6 summary `http_req_duration.p(95)`; includes the port-forward hop |
| M3 | share of requests not served | `observations.client.failed_share`, point record | confirmed 2026-10-22 | k6 summary `http_req_failed.value`; timeouts at 10 s count here |
| M4 | serving instances | `count(up{job="mock-api"} == 1)` | confirmed 2026-10-22 | **scrape targets, not replicas** — a terminating pod and its replacement are both up for one interval, so this overshoots `maxReplicas` during rollover |
| M5 | server-side served rate | `sum(rate(mock_requests_total[30s]))` | confirmed 2026-10-22 | second opinion on M1 |
| M6 | server-side mean service time | `sum(rate(mock_request_duration_seconds_sum[30s])) / sum(rate(mock_requests_total[30s]))` | confirmed 2026-10-22 | excludes queueing, unlike M2 |
| R7 | which component sat at its ceiling | hand-recorded at the end of each run | active | carried in the ledger `Signal` column |
| D8 | offered load actually served | `M1 / R9` | active | a share; the report prints it as a percent |
| R9 | offered rate, the swept axis | `settings.rate`, point record | active | TARGET_RATE in scripts/load.js, passed by api_point.py --rate |

<!-- /report-kit metrics -->

- **Retention** — Prometheus 1 h · campaign length 20 min

### Preflight

- [x] Metric names confirmed against the live endpoint — `metrics.yaml` exports three refs, none empty
- [x] Guards frozen — `execution.yaml`, read as of each point's load end
- [x] Image frozen — `scripts/image-freeze.json`, checked in every preflight
- [x] Floor captured — 1 replica, no traffic
- [x] Expected line written before the first run (below)

---

## 2 · Plan

### Axis

- **Varied parameter** — offered arrival rate, `TARGET_RATE` in `scripts/load.js`, the `rate` setting in `execution.yaml`
- **Candidate grid** — 4 · 12 · 24 · 32 · 40 req/s
- **Sweep order** — 4, 24, 12, then 40, then 32 — ends and middle first, the rest placed by the shape (`methodology.md` §6)
- **Held constant** — image, CPU limits, HPA bounds, node, 45 s of load per point, no other workload on the node

### Expected

*Written 2026-09-05, before the first run.* Four replicas at `200m` each is
0.8 cores; at ~40 ms of CPU per request that is **about 20 req/s**. Latency
should be flat below that and rise sharply above it, so the SLO-breaking rate
and the throughput ceiling should coincide near 20.

### Window

- **Opens** — when the generator process starts · recorded by the run script
- **Closes** — when every gated deployment has been back at its floor for 20 s · recorded by the run script, in `events`
- Scale-in sits inside the window: it is caused by the load and is billed to the point that caused it

### Safeguards

- **Abort condition** — a guard breach, or the generator failing to run at all
- **Estimated duration** — ~2 min per point, ~15 min for the grid ᴱ

---

## 3 · Journal

### Run ledger

| # | Point | Window UTC | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | rate-04 | 15:12:18 → 15:13:40 | ok | headroom — served all 4/s at p95 95 ms ᴿ | ✓ |
| 02 | rate-24 | 15:14:10 → 15:15:39 | ok | at the knee — served all 24/s, but p95 already 386 ms ᴿ | ✓ |
| 03 | rate-12 | 15:16:09 → 15:17:41 | ok | headroom — p95 241 ms, no drops ᴿ | ✓ |
| 04 | rate-40 | 15:18:11 → 15:19:55 | ok | saturated — CPU-bound, 315 iterations never started ᴿ | ✓ |
| 05 | rate-32 | 15:28:54 → 15:29:40 | **invalid, ran against one replica** | — | ✓ |
| 06 | rate-32b | 15:30:40 → 15:32:09 | ok | past the knee — p95 0.8 s, throughput still climbing ᴿ | ✓ |

### Notes

**#04 before #05** — the first three points said the range was wrong rather than
that the curve had a minimum: throughput tracked the offered rate at all of
them and latency was still climbing at the top. `methodology.md` §6 calls that
"extend it", so 40 was run before the refinement point, and it was 40 that
produced the collapse.

**#05 — invalid, and the ledger says why.** The point ran while the deployment
was held at one replica: the autoscaler's `maxReplicas` was lowered to 1 to
stand in for one that has scaled down and not yet back up, and restored
before #06. Replica count is in *Held constant*, so a
point measured against one replica is not comparable with four, whatever its
numbers say. It served 31.72<!--VM4-->/s at p95 941<!--VM10--> ms — close enough to #06 to be
mistaken for a valid row, which is exactly why the check is mechanical
(`M4 = 1`, and a record whose `ceilings_reached` is empty where every other
row's names `mock-api`) rather than a judgement about whether the number
"looks right".

**#06 — the re-run.** Same rate, new row, because the ledger's `#` is never
reused, and a new run id, because the record is named by it. Four replicas
this time: 31.75<!--VM5-->/s at p95 813<!--VM11--> ms.

**Between points the instrumentation needs a moment.** A pod that has just
scaled in is still a scrape target for an interval or two and reports `up == 0`,
which fails the next point's preflight. The runs above waited for
`--preflight-only` to pass before starting — 0–20 s in practice — and twice a
point still failed preflight because a pod scaled in between that check and
the run. Nothing was measured on either attempt; the run was started again.

**The generator's exit code is not always a malfunction, and not a guard
either.** k6 exits 99 when a threshold is breached; `load.js` sets one at 5 %
failed. #04 left 4.9<!--VM18--> % unanswered and exited 0 — just under it — where
an earlier pass of the same grid crossed it and exited 99. The copy of the
runner reads 99 as the finding rather than a doubt about the load; either way
the share itself is M3, and that is what the matrix prints.

### Close

- [x] Every row has a `Signal`
- [x] Every valid point exported before retention (1 h; campaign 20 min)
- [x] `#05` carried as invalid rather than deleted
- [x] Expected line compared against the result (below)

---

## 4 · Results

**Finding** — the service serves the offered rate up to **24<!--VR3--> req/s** at
p95 386<!--VM9--> ms. Between 24 and 32 the queue grows faster than it drains: throughput
still climbs to 31.75<!--VM5-->/s but p95 more than doubles to 813<!--VM11--> ms. At
40<!--VR5--> req/s it breaks down — 27.30<!--VM6-->/s served, fewer than at 32, about one
request in twenty unanswered and p95 pressed against the 10 s timeout. **Throughput peaks before the system stops keeping up, and latency
finds the ceiling first.**

**Against the Expected line** — the throughput ceiling landed near 32/s, not
20/s, so the CPU estimate was pessimistic by about half. But the *useful*
ceiling — the highest rate served at a latency anyone would accept — is 24/s,
close to the estimate. The expectation was right about where the system stops
being usable and wrong about where it stops working, and those are not the
same rate.

### Matrix

| Point | Offered | M1 served/s | D8 served share | M2 p95 | M3 unserved | M4 targets | Signal |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| rate-04 | 4<!--VR1--> | 4.00<!--VM1--> | 100<!--VD1--> % | 95<!--VM7--> ms | 0<!--VM13--> % | 4 | headroom |
| rate-12 | 12<!--VR2--> | 12.00<!--VM2--> | 100<!--VD2--> % | 241<!--VM8--> ms | 0<!--VM14--> % | 4 | headroom |
| rate-24 | 24<!--VR3--> | 23.95<!--VM3--> | 100<!--VD3--> % | 386<!--VM9--> ms | 0<!--VM15--> % | 4 | at the knee |
| rate-32 ᴱˣ | 32<!--VR4--> | 31.72<!--VM4--> | 99<!--VD4--> % | 941<!--VM10--> ms | 0<!--VM16--> % | 1 | — (invalid) |
| rate-32b | 32<!--VR4--> | 31.75<!--VM5--> | 99<!--VD5--> % | 813<!--VM11--> ms | 0<!--VM17--> % | 4 | past the knee |
| rate-40 | 40<!--VR5--> | 27.30<!--VM6--> | 68<!--VD6--> % | 9,840<!--VM12--> ms | 4.9<!--VM18--> % | 4 | saturated |

ᴱˣ — excluded from the curve fit: ran against one replica, see Journal #05.

### Saturation

**Tier 1 — CPU, between 24 and 32 req/s, runs #02 and #06.** Latency rises with
offered load from the very first point (95<!--VM7--> → 241<!--VM8--> → 386<!--VM9--> ms across 4<!--VR1--> → 12<!--VR2--> → 24<!--VR3-->),
which is not noise. Past 24 the four replicas are already the
autoscaler's maximum, so nothing more arrives to absorb the load and the queue
grows without bound. `M6` (server-side service time, which excludes queueing)
rises too, but more slowly: by about a sixth between 12 and 24, and by about
two fifths from 24 to 32 while p95 more than doubles, so the request handler
slows down under load and the wait in front of it grows faster still.

**No second tier is claimed.** The grid ends where the first tier breaks, and a
sweep that stops at the first ceiling cannot see what would bind after it.

### Guardrails

- **Do not read the 40 req/s row as capacity.** It is what breakdown looks
  like: throughput below the 32 row and about one request in seven lost.
- **The replica ceiling is part of the measurement.** Every valid point ran at
  `maxReplicas` — each record's `ceilings_reached` names `mock-api`, and the
  runner warns that such a point measures that limit — so this curve describes
  *this* HPA configuration, not the service. Raising `maxReplicas` moves the knee and the
  sweep would need repeating.
- **`M4` counts scrape targets.** During rollover a terminating pod and its
  replacement are both up, so it can read above the maximum of 4, although no
  row of this sweep did. It is not a replica count and should not be read as one.

### Retro

The shape only appeared after the range was extended: three points inside a
range that was too small showed a straight line and no ceiling. Taking the ends
first is what surfaced that on the fourth run rather than the ninth.

The invalid row cost one re-run and would have cost a wrong conclusion. It was
caught because replica count is checked as a number rather than eyeballed —
31.72<!--VM4-->/s at p95 941<!--VM10--> ms sits close enough to the valid row that no one would
have questioned it.

Back into the kit: nothing measured differently, but the pass was re-run on a
runner from `report-kit new-point`, whose record keeps k6's summary unrounded
and whose register refs — D8 among them — are worked out by `point finish`
rather than by the script. A runner killed by a signal left its two
port-forwards running, and the next point's forward died on the port they
held; nothing in the record was affected, but the ports had to be freed by
hand.
