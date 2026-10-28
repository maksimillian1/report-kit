# mock-api-priced-per-request

> A worked execution, produced by running `scripts/` against a local cluster.
> Every number below came out of a run — **except the rates, which are
> invented**: a local cluster is billed by no one, so OpenCost prices it at the
> round numbers in `scripts/manifests/opencost.yaml`. What is real is
> everything between those rates and a cost per point: the replicas, the
> requests, the windows, OpenCost's own arithmetic and the kit's. Reproduce it
> with `scripts/up.sh` and the three invocations in `scripts/README.md`.

---

## 1 · Givens

### System under test

`simple-api`'s service, priced. The same CPU-bound handler and autoscaler,
with a volume and a load balancer added so that every line OpenCost prices has
something in it.

| | |
| :--- | :--- |
| Workload | `mock-api`, one container, Python `ThreadingHTTPServer`, alone in namespace `report-kit-priced` |
| Requests | `50m` CPU, `32Mi` memory per replica · Limits `200m` / `128Mi` |
| Autoscaler | HPA on CPU utilisation, target 50 %, `minReplicas` 1, `maxReplicas` 4 |
| Volume | one 2 GiB `PersistentVolumeClaim`, mounted and unused |
| Load balancer | the Service is `type: LoadBalancer`, given the node's address by k3s's servicelb |
| Pricing | OpenCost 1.115, kube-state-metrics 2.13 and cAdvisor, in `report-kit-priced-monitoring`, all scraped by one Prometheus |
| Cluster | k3s v1.31, one node, labelled `karpenter.sh/nodepool=apps` by `up.sh` |
| Commit | `d0944b2`; #02 and #03 ran with documentation edits uncommitted, the runner, register and `execution.yaml` unchanged |

### Price basis

OpenCost's custom provider, at the rates its ConfigMap sets. **Invented on
2026-10-24**, for this example, and nobody's prices:

| | |
| :--- | :--- |
| vCPU-hour | $0.03<!--VR1--> |
| GiB-hour of memory | $0.004<!--VR2--> |
| GiB-hour of storage | $0.00012<!--VR3--> |
| load balancer hour | $0.025<!--VR4--> |
| control plane | none — k3s has no fee, and OpenCost's custom provider publishes 0 |

### Workload — the denominator → report §2

One unit is one `GET /` served with status 200, offered at a constant arrival
rate. A point's cost per unit is its own cost over its window — scale-in
included, which the load caused — over the requests served in it.

### Metrics

<!-- report-kit metrics: generated from metrics.yaml, edit that file -->

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | `observations.client.served_per_second`, point record | confirmed 2026-10-24 | client-side, k6 summary `http_reqs.rate` |
| M2 | client-observed latency p95 | `observations.client.p95_ms`, point record | confirmed 2026-10-24 | k6 summary `http_req_duration.p(95)`; includes the port-forward hop |
| M3 | share of requests not served | `observations.client.failed_share`, point record | confirmed 2026-10-24 | k6 summary `http_req_failed.value` |
| M4 | serving instances | `count(up{job="mock-api"} == 1)` | confirmed 2026-10-24 | **scrape targets, not replicas**; guarded by G1 |
| R5 | requests served in the point | `observations.client.requests`, point record | active | k6 summary `http_reqs.count` — the denominator of D20 |
| M6 | price of the apps pool's nodes, USD/h | `sum(max by (node) (node_total_hourly_cost) * on (node) group_left () max by (node) (kube_node_labels{label_karpenter_sh_nodepool="apps"}))` | confirmed 2026-10-24 | every node the label names, whoever runs on it. No `or vector(0)`, because this pool never empties — one that can would add it and turn that gap into a zero |
| M7 | price of the service's CPU and memory requests, USD/h | `sum(kube_pod_container_resource_requests{job="kube-state-metrics", namespace="report-kit-priced", resource="cpu"} * on (node) group_left () max by (node) (node_cpu_hourly_cost)) + sum(kube_pod_container_resource_requests{job="kube-state-metrics", namespace="report-kit-priced", resource="memory"} / 1073741824 * on (node) group_left () max by (node) (node_ram_hourly_cost))` | confirmed 2026-10-24 | requests from kube-state-metrics at OpenCost's node rates, so it follows the replicas at scrape resolution. **`job=` is required**: OpenCost republishes these requests under its own job, and without it every request counts twice |
| M8 | OpenCost's allocation of the same, USD/h | `sum(container_cpu_allocation{namespace="report-kit-priced"} * on (node) group_left () max by (node) (node_cpu_hourly_cost)) + sum(container_memory_allocation_bytes{namespace="report-kit-priced"} / 1073741824 * on (node) group_left () max by (node) (node_ram_hourly_cost))` | confirmed 2026-10-24 | second opinion on M7 — the larger of request and use, but recomputed once a minute, so it runs up to a minute behind the replicas; see the Journal |
| M9 | price of the service's volumes, USD/h | `sum(max by (persistentvolume) (pv_hourly_cost) * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_capacity_bytes{job="kube-state-metrics"}) / 1073741824 * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_claim_ref{job="kube-state-metrics", claim_namespace="report-kit-priced"}))` | confirmed 2026-10-24 | `pv_hourly_cost` is per GiB, so times the size; billed whether or not the volume is used |
| M10 | price of the service's load balancers, USD/h | `sum(max by (service_name) (kubecost_load_balancer_cost{namespace="report-kit-priced"}))` | confirmed 2026-10-24 | one per Service of type LoadBalancer; OpenCost prices no ingress |
| M11 | control-plane fee, USD/h | `max(kubecost_cluster_management_cost)` | confirmed 2026-10-24 | **0 here, and 0 is right**: k3s charges no fee. On EKS OpenCost publishes $0.10 only while some node is in a managed node group — see runners.md |
| D12 | mean pool price over the window, USD/h | `mean of M6` | active | |
| D13 | mean price of the service's requests, USD/h | `mean of M7` | active | rises with replicas — the part of B the load causes |
| D14 | mean of OpenCost's allocation, USD/h | `mean of M8` | active | |
| D15 | mean price of the service's volumes, USD/h | `mean of M9` | active | |
| D16 | mean price of the service's load balancers, USD/h | `mean of M10` | active | |
| D17 | mean control-plane fee over the window, USD/h | `mean of M11` | active | |
| D18 | the service's own cost over the window, USD | `(D13 + D15 + D16) * window.seconds / 3600` | active | B in methodology.md §8 — what would go if the service did |
| D19 | shared cost over the window, USD | `(D12 - D13 + D17) * window.seconds / 3600` | active | A — the pool's price less what the service requested, plus the control plane. Not divided among tenants |
| D20 | the service's own cost per thousand requests, USD | `D18 / R5 * 1000` | active | over the whole window, scale-in included, which the load caused |
| R21 | offered rate, the swept axis | `settings.rate`, point record | active | TARGET_RATE in scripts/load.js, passed by api_point.py --rate |

<!-- /report-kit metrics -->

- **Retention** — Prometheus 6 h · campaign length 20 min

### Preflight

- [x] Metric names confirmed against the live endpoint — every exported ref evaluated against Prometheus before the first run
- [x] Guards frozen — `execution.yaml`, read as of each point's load end
- [x] Image frozen — `scripts/image-freeze.json`, checked in every preflight
- [x] Price basis recorded — above, and in `report-values.yaml` as VR1–VR4
- [ ] Floor captured — **not done**; see Close

---

## 2 · Plan

### Axis

- **Varied parameter** — offered arrival rate, the `rate` setting in `execution.yaml`
- **Grid** — 2 · 8 · 16 req/s, run 2, 16, then 8: ends and middle first
- **Held constant** — image, requests and limits, HPA bounds, the node, the rates, 45 s of load per point

### Expected

**Not written before the first run.** This example was built while the price
wiring it shows was being built, and no line was dated ahead of #01. It is
carried as an open item in Close rather than written now, which would be the
failure `methodology.md` §5 names.

### Window

- **Opens** — when the generator process starts
- **Closes** — when `mock-api` has been back at one replica for 20 s
- The prices are exported over the same window as everything else, at the same 15 s step

---

## 3 · Journal

### Run ledger

| # | Point | Window UTC | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | rate-02 | 09:21:05 → 09:22:34 | ok | headroom — two replicas, p95 46<!--VM2--> ms ᴿ | ✓ |
| 02 | rate-16 | 09:28:59 → 09:30:49 | ok | at the replica ceiling — four, p95 250<!--VM4--> ms ᴿ | ✓ |
| 03 | rate-08 | 09:37:15 → 09:38:34 | ok | at the replica ceiling — four, p95 102<!--VM6--> ms ᴿ | ✓ |

### Notes

**OpenCost's allocation runs a minute behind.** M7 prices the service's
requests as kube-state-metrics reports them; M8 is OpenCost's own allocation of
the same containers, at the same rates. Over these windows M8 came out lower at
every point — $0.00190<!--VD2-->/h against $0.00244<!--VD1-->/h at #01,
$0.00221<!--VD12-->/h against $0.00379<!--VD11-->/h at #03,
$0.00308<!--VD7-->/h against $0.00447<!--VD6-->/h at #02 — though an
allocation is the *larger* of request and use, and at #02 and #03 a replica
used up to four times its request. The raw samples say why: OpenCost
recomputes once a minute, from the two minutes of Prometheus data before it, so
a replica entered M8 up to a minute after kube-state-metrics first reported
it, and left up to a minute after it was gone. Replicas that lived about a
minute appeared in one sample. M7 is therefore the price, and M8 is kept as the second opinion
that shows the gap.

**A trial point ran at 09:16, before #01, and is in no row.** It is where the
gap above was first seen. Its extra replicas had left OpenCost's allocation by
09:19:20, before #01 started, so #01 carries none of them. The six minutes left
between points were set against that and turned out to be more than needed.

**OpenCost republishes kube-state-metrics' series.**
`kube_pod_container_resource_requests` and the volume series arrived twice,
once under each job, so a sum over them without a `job` filter counts every
request twice. M7 and M9 name `job="kube-state-metrics"`.

**The load balancer is most of what the service costs.** At every point M10
is $0.025<!--VR4-->/h against less than a cent an hour for four replicas'
requests, so B barely moves with the load and the cost per request falls almost
as fast as the rate rises. That is these invented rates speaking — a real
load balancer is priced per hour and per LCU, and a real replica's request is
a larger share of a real node — and the arithmetic, not the proportion, is
what the example is for.

### Close

- [x] Every row has a `Signal`
- [x] Every point exported before retention (6 h; campaign 20 min)
- [ ] Expected line compared against the result — none was written; see Plan
- [ ] Floor captured — no idle window was recorded, so §8's floor is not split here; report §3 carries it as declared, not measured
- [x] `prices_match_aws` left off, and why — the node is not an EC2 instance and the rates are invented, so every price would be in doubt

---

## 4 · Results

**Finding** — at these rates the service's own cost per thousand requests
falls from $0.0075<!--VD5--> at 2<!--VR5--> req/s to $0.0018<!--VD15--> at
8<!--VR9--> and $0.0013<!--VD10--> at 16<!--VR7-->, because most of it is a
load balancer that costs the same at any load. The shared pool behind it costs
several times more per window than the service does, and is not the
service's to divide.

### Matrix

| Point | Offered | M1 served/s | R5 requests | D13 requests $/h | D14 OpenCost's $/h | D18 own $ | D19 shared $ | D20 own $ per 1k |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rate-02 | 2<!--VR5--> | 2.02<!--VM1--> | 91<!--VR6--> | 0.00244<!--VD1--> | 0.00190<!--VD2--> | 0.000678<!--VD3--> | 0.00442<!--VD4--> | 0.0075<!--VD5--> |
| rate-08 | 8<!--VR9--> | 8.00<!--VM5--> | 360<!--VR10--> | 0.00379<!--VD11--> | 0.00221<!--VD12--> | 0.000638<!--VD13--> | 0.00393<!--VD14--> | 0.0018<!--VD15--> |
| rate-16 | 16<!--VR7--> | 15.99<!--VM3--> | 720<!--VR8--> | 0.00447<!--VD6--> | 0.00308<!--VD7--> | 0.000906<!--VD8--> | 0.00544<!--VD9--> | 0.0013<!--VD10--> |

Dollars at invented rates. D18 is B — requests, volume and load balancer;
D19 is A — the pool's price less the service's requests, plus a control-plane
fee of 0.

### Guardrails

- **Price the service by its requests, not by OpenCost's allocation, over a
  window of minutes.** M8 trailed M7 by a fifth to two fifths here.
- **Filter kube-state-metrics' series by `job`** wherever OpenCost runs beside
  it.
- **Read no proportion off these rates.** Which line dominates is a property of
  the invented ConfigMap, not of the service.
