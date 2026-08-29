# posts-api-concurrency

- **Why this execution exists** — find the concurrency at which a single-replica JSON API
  stops gaining throughput, and whether the p95 SLO breaks before or after that point
- **Produces** — the sweet spot and knee on the concurrency axis, the proven Tier 1
  constraint, and a per-replica concurrency guardrail
- **Expected** — recorded 2026-08-25, before the first run: throughput plateaus near
  1,000 req/s when container CPU reaches its 2-vCPU limit; p95 crosses 100 ms after the
  plateau, so the binding constraint is hardware, not the SLO
- **Status** — closed
- **Givens frozen** — 2026-08-24 · commit `a3f19c2`
- **Plan frozen** — 2026-08-25 · commit `7b04e88`

---

## 1 · Givens

### System under test

- **Build** — `posts-api` @ `a3f19c2` · 2026-08-24 — `json-server` 1.0.0-beta.3 on Node 22,
  serving a local copy of the JSONPlaceholder dataset
- **Topology** — one pod, one replica, no cache, no database; Cilium Gateway API in front,
  load generator on a separate node in the same AZ
- **Deployed by** — `deploy/posts-api.yaml` · applied by ArgoCD, sync disabled during runs

| Parameter | Value | Where it is set | Why frozen |
| :--- | :--- | :--- | :--- |
| replicas | 1 | `deploy/posts-api.yaml` | the axis is concurrency, not width |
| cpu limit | 2 | `deploy/posts-api.yaml` | one node class for every point |
| memory limit | 1Gi | `deploy/posts-api.yaml` | never approached; excluded from the axis |
| node type | c6i.large | `terraform/nodegroup.tf` | 2 vCPU / 4 GiB, one pod per node |
| NODE_ENV | production | `deploy/posts-api.yaml` | dev mode adds per-request logging |
| dataset | 100 posts · 500 comments | `data/db.json` | fits in memory at every point |

### Workload — the denominator → report §2

- **Unit of work** — one HTTP response with a 2xx status, fully written to the socket.
  A timeout or a 5xx is not a unit and is not priced.
- **Fixture** — 90 % `GET /posts/{id}` over ids 1–100 uniformly · 10 % `GET /posts`
- **Exact unit count** — not fixed: this is a serving path, so the count is an output of
  each run, not an input. Per-run counts in `./data/run-⟨#⟩-⟨point⟩.json`.
- **Distribution** — response body median 292 B · p95 1.1 kB · `GET /posts` 27 kB
- **Arrival pattern** — closed loop, k6 constant-VU, no think time
- **Frozen** — 2026-08-24 · `./data/posts-mix-profile.txt`

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | successful responses per second | `http_reqs` rate, k6 JSON summary, `status<400` | confirmed 2026-08-24 | steady-state window only |
| M2 | client-observed latency p95 | `http_req_duration` p(95), k6 JSON summary | confirmed 2026-08-24 | includes gateway hop |
| M3 | share of non-units | `http_req_failed` rate, k6 JSON summary | confirmed 2026-08-24 | timeouts and 5xx |
| M4 | container CPU against its limit | `rate(container_cpu_usage_seconds_total{pod=~"posts-api-.*",container="api"}[1m])` | confirmed 2026-08-24 | name differs from cAdvisor docs |
| M5 | Node event loop lag p95 | `nodejs_eventloop_lag_p95_seconds{job="posts-api"}` | confirmed 2026-08-24 | prom-client, already in the build |
| M6 | GC pause time | — | dropped 2026-08-25 | M5 answered it; number not reused |
| R7 | which component sat at its ceiling | hand-recorded at the end of each steady state · M. S. | active | carried in the ledger `Signal` column |
| D8 | cost per 1M units | `node $/hr ÷ (M1 × 3600) × 1e6` | active | |
| E9 | cost of relieving Tier 1 | one more c6i.large at list rate | active | vs current $78/month single node |

- **Retention** — Prometheus 3 d · campaign length 2 d

### Price basis → report §4

- **File** — `./data/price-2026-08-24.json`
- **Rate type** — On-Demand list
- **Region · currency** — `eu-central-1` · USD
- **Covers** — c6i.large compute only. Gateway, EBS and inter-AZ transfer are floor lines
  and are excluded from every marginal figure here.

### Envelope → report §2

- **Platform** — EKS 1.30, x86_64, c6i.large, single AZ. Re-measure on: node family change,
  ARM64, or a minor Node runtime bump
- **Scale range** — 10 to 400 concurrent connections against one replica.
  Re-measure on: more than one replica, or any cache in front
- **Input** — the frozen 90/10 mix over a 100-post dataset. Re-measure on: write traffic,
  a larger dataset, or a payload above ~30 kB
- **Commercial** — On-Demand list, 2026-08-24. Re-measure on: rate card update or a
  Savings Plan covering this family

### Preflight

- [x] Every `M` ref confirmed on the live endpoint, not from chart docs — gates every figure
- [x] Every confirmed ref returns data with non-empty label dimensions under its selector — gates every figure
- [x] Cost attribution active in IaC; controller-created resources carry the tag — gates every $ figure
- [x] Retention compared against campaign length; export after every point if shorter — gates every point
- [x] Load generator and system on separate hosts; generator not the bottleneck — gates every throughput figure
- [x] Run script dry run clean — gates comparability

---

## 2 · Plan

### Axis

- **Varied parameter** — k6 constant virtual users, `--vus`, in `scripts/load.js`
- **Candidate grid** — 10 · 50 · 100 · 200 · 400
- **Sweep order** — 10, 400, 100, then refinement by the shape
- **Held constant** — replica count, request mix, node type, ArgoCD sync disabled,
  no other workload scheduled on the node

### Window

- **Warm-up** — 60 s, discarded from every figure
- **Steady state** — 5 min held per point
- **Opens** — first request after warm-up ends · recorded by the run script
- **Closes** — last response of the steady state · recorded by the run script

### Safeguards

- **Estimated cost / duration** — ~50 min of node time across the grid, under $1 ᴱ
- **Abort condition** — error rate above 5 %, or the generator's own CPU above 70 %

---

## 3 · Journal

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | vu-10 | 09:12 → 09:17 ᴿ | `a3f19c2` | ok | headroom — CPU 14 % of limit, lag 3 ms ᴿ | ✓ |
| 02 | vu-400 | 09:31 → 09:36 ᴿ | `a3f19c2` | ok | event loop saturated, CPU 54 % of limit ᴿ | ✓ |
| 03 | vu-100 | 09:48 → 09:53 ᴿ | `a3f19c2` | ok | event loop at its knee, CPU 51 % ᴿ | ✓ |
| 04 | vu-50 | 10:06 → 10:11 ᴿ | `a3f19c2` | ok | event loop climbing, CPU 47 % ᴿ | ✓ |
| 05 | vu-200 | 10:24 → 10:29 ᴿ | `a3f19c2` | invalid, node shared mid-window | — | — |
| 06 | vu-200 | 11:02 → 11:07 ᴿ | `a3f19c2` | ok | event loop saturated, CPU 53 % ᴿ | ✓ |

### Notes

**#02** — run second by design, not by accident: the top of the grid was taken early to check
that the range was wide enough. It was — throughput had already stopped moving.

**#05** — a batch job was scheduled onto the same node four minutes in; p95 doubled against
#03 while CPU on the pod barely moved. Invalidated rather than annotated: the node was no
longer the frozen given. Node cordoned, point re-run as #06.

### Close

- [x] Saturation identified, or headroom confirmed at the top of the grid
- [x] Every figure in §4 marked (unmarked · ᴰ · ᴿ · ᴱ)
- [x] Outcome compared against Expected in Retro, inversion included

---

## 4 · Results

**Finding** — one replica serves ~1,180 req/s, but the 100 ms p95 SLO breaks at 100
concurrent connections, well before any hardware limit; width, not size, is the lever
→ report §3.5

### Matrix

| Run | VUs | Units/sec | p95 ms | Errors % | $/1M units | Signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 10 | 780 | 14 | 0.00 | 0.0380 ᴰ | headroom ᴿ |
| #04 | 50 | 1,120 | 47 | 0.00 | 0.0265 ᴰ | lag climbing ᴿ |
| #03 | 100 | 1,180 | 92 | 0.01 | 0.0251 ᴰ | lag knee ᴿ |
| #06 | 200 | 1,186 | 189 | 0.30 | 0.0250 ᴰ | lag saturated ᴿ |
| #02 | 400 | 1,168 | 402 | 1.40 | 0.0254 ᴰ | lag saturated ᴿ |

- **Cost formula** — `$0.1068/hr ÷ (units/sec × 3600) × 1e6`, from the price basis in §1
- **Reference value** — p95 SLO < 100 ms; throughput target 1,000 req/s per replica
- **Condition boundary** — one replica, 90/10 read mix, bodies under ~30 kB. A write path
  or a larger payload moves the ceiling and this matrix stops applying.
- **Raw data** — `./data/`

### Saturation

**Tier 1 — Node event loop at 100 VUs, run #03**

- **Evidence** — M5 rises from 3 ms at VU-10 to 41 ms at VU-100 and 214 ms at VU-400, while
  M1 stops moving after VU-100. M4 never exceeds 54 % of the 2-vCPU limit at any point,
  including the two saturated ones.
- **Relieved by** — a second replica on a second node, +$78/month ᴱ (E9). Raising the CPU
  limit relieves nothing: a single Node process cannot use the second core.

### Guardrails

- **`maxConcurrent = 60`** — from the VU-50 row in §4, which holds p95 at 47 ms while
  delivering 95 % of peak throughput · `deploy/posts-api.yaml` → report §5
- **`replicas = ceil(target_rps / 1100)`** — from the plateau in §4, sized at the sweet spot
  rather than the knee · `deploy/posts-api.yaml` → report §5

### Retro

- **Expectation** — inverted. CPU was expected to saturate at the 2-vCPU limit and to be the
  ceiling; it topped out at 54 % and stayed there through both saturated points. The real
  ceiling was one thread, visible only in M5. Had M5 not been in the register, the run would
  have concluded "plenty of CPU headroom" and the next step would have been a larger node,
  which buys nothing here.
- **Cost against estimate** — 62 min of node time against 50 estimated; the re-run of #05
  accounts for the difference. Under $1 either way.
- **What should have been caught in Preflight** — the noisy-neighbour case in #05. The
  checklist isolated the load generator but said nothing about the system's own node. One
  line, and #05 would not have been spent.
