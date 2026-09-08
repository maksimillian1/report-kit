# Executive Engineering Report — mock-api (example)

> **This is the kit's worked example, not a real report.** Every figure comes
> from a real run on a single-node local cluster — see `execution.md` and the
> files under `scripts/data/`. Nothing here is fabricated, which is why the
> cost sections are empty: a laptop has no price basis, and inventing one
> would teach exactly the wrong lesson.

Legend — ᴰ derived · ᴱ estimated · ᴿ recorded during the run · ᴱˣ excluded

---

## Coverage

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| Throughput and latency vs offered load | measured | `execution.md` §4 | — | v1 |
| Saturation mechanism | measured | `execution.md` §4 Saturation | — | v1 |
| Cost per unit | **declared, not measured** | — | no price basis exists for a local cluster; the whole of §4 below | v1 |
| Behaviour above `maxReplicas: 4` | **out of scope** | — | the curve describes one autoscaler configuration, not the service | v1 |
| Reliability under instance loss | **out of scope** | — | a single-node local cluster cannot lose a node | v1 |

---

## 1. BLUF

The service serves everything offered up to **24 req/s** at p95 412 ms. Above
that the queue grows faster than it drains: throughput still rises to a peak of
**29.5 req/s** while p95 reaches 3.8 s, and at 40 req/s the service breaks down
— 19.7 req/s served, one request in five unanswered.

**Throughput peaks after the system has already stopped being usable.** Sizing
on peak throughput would place the service at a rate where a fifth of callers
time out; the usable ceiling is the latency knee, not the throughput one.

---

## 2. Workload Contract & Envelope

One unit is one `GET /` answered with status 200. Load is offered at a
**constant arrival rate** — requests depart on schedule regardless of whether
earlier ones have returned, so the measurement reflects the server rather than
the client's willingness to wait.

| | |
| :--- | :--- |
| Envelope | 1–4 replicas, `200m` CPU each, HPA target 50 % utilisation |
| Unit cost of work | ~40 ms of server CPU per request |
| Measured range | 4 – 40 req/s offered, 45 s of load per point |
| Not covered | sustained load beyond 45 s, concurrent workloads, more than 4 replicas |

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| Offered req/s | M1 served/s | D8 served share | M2 p95 | M3 unserved | Saturation signal |
| ---: | ---: | ---: | ---: | ---: | :--- |
| 4 | 4.01 | 100 % | 98 ms | 0 % | headroom ᴿ |
| 12 | 11.99 | 100 % | 195 ms | 0 % | headroom ᴿ |
| 24 | 23.97 | 100 % | 412 ms | 0 % | at the knee ᴿ |
| 32 | 29.46 | 92 % | 3 755 ms | 0.2 % | past the knee ᴿ |
| 40 | 19.72 | 49 % | 10 001 ms | 21.2 % | saturated, CPU-bound ᴿ |

A sixth run at 32 req/s is excluded: it ran against one replica instead of
four, which is a *Held constant*. See `execution.md` §3 note #05.

### 3.2 Chart

Not rendered — the example has no charting step, and a chart of five points
adds nothing the table does not already show. In a real report this is where
the throughput plateau and the latency curve would be drawn together, because
the point of the finding is that they turn at different rates.

### 3.3 Knee · sweet spot · waste boundary

| | Rate | Read from |
| :--- | ---: | :--- |
| **Sweet spot** | 24 req/s | last rate served in full, p95 still under half a second |
| **Knee** | between 24 and 32 req/s | p95 jumps nine-fold across this interval |
| **Throughput peak** | ~29.5 req/s | and already unusable — p95 3.8 s |
| **Waste boundary** | above 32 req/s | throughput falls while cost stays |

### 3.4 Shape of the cost curve

Latency rises with offered load from the very first point — 98 → 195 → 412 ms
across 4 → 12 → 24 req/s — so there is no flat region: every increment is
already buying queueing. What changes past 24 is only the rate of increase,
which is what makes the "knee" a range rather than a value.

### 3.5 Constraint ladder

**Tier 1 — CPU at the replica ceiling, between 24 and 32 req/s.** Every valid
point above 4 req/s ran at `maxReplicas`, so past 24 no further capacity
arrives and the queue grows without bound. Server-side service time (M6, which
excludes queueing) varies by less than a factor of two across the whole grid:
the handler is not slowing down, the wait in front of it is growing.

**No second tier is claimed.** The sweep ends where the first tier breaks, and
it cannot see what would bind after it.

---

## 4. Cost Structure

**Not measured.** This example runs on a local single-node cluster, which has
no price basis and no attribution tags. A dated price snapshot is one of the
things `methodology.md` §6 calls unrecoverable, so the honest entry is an empty
section with a reason rather than a plausible-looking table.

In a real report, §3.1's throughput column would become $/1M units here, and
the sweet spot would be re-read against cost rather than against latency alone
— the two rarely name the same row.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Do not size on peak throughput | usable ceiling 24 req/s, not 29.5 | §3.3 | — |
| The curve describes one HPA configuration | `maxReplicas: 4` | §3.5 | `scripts/manifests/mock-api.yaml` |
| 40 req/s is breakdown, not capacity | 49 % served | §3.1 | — |
| `M4` counts scrape targets, not replicas | shows 5 against a max of 4 during rollover | `execution.md` §1 register | `scripts/series.txt` |

---

## 6. Reliability Economics

Out of scope. A single-node local cluster cannot lose a node, so nothing here
was exercised: no instance interruption, no replica loss under load, no
recovery time. The tooling has the mechanism for it — the jobs profile
distinguishes an involuntary node loss from ordinary consolidation — but this
example does not reach it, and a section claiming otherwise would be the kind
of silent omission §11 exists to prevent.

---

## 7. Levers Evaluated

| Lever | Effort | Δ Throughput | Δ Cost | Quality / risk price | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Raise `maxReplicas` past 4 | trivial | unknown — moves Tier 1 | more instances at peak | none identified | **not evaluated** — would need the sweep repeated |
| Reduce per-request CPU | unknown | proportional to the saving | none | correctness risk in the handler | **not evaluated** |

Both are named rather than measured. The grid answered where this
configuration stops; it does not say what the next configuration would do, and
the difference is a second execution, not an inference from this one.
