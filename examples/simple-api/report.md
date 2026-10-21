# Executive Engineering Report — mock-api (example)

> **This is the kit's worked example, not a real report.** Every value comes
> from a real run on a single-node local cluster — see `execution.md` and the
> files under `scripts/data/`. Nothing here is fabricated, which is why the
> cost sections are empty: a laptop has no price basis, and inventing one
> would teach exactly the wrong lesson.

Legend — ᴰ derived · ᴱ estimated · ᴿ recorded during the run · ᴱˣ excluded

---

## Coverage

| Area | Status | Evidence |
| :--- | :--- | :--- |
| Throughput and latency vs offered load | measured | `execution.md` §4 |
| Saturation mechanism | measured | `execution.md` §4 Saturation |
| Cost per unit | **declared, not measured** | No price basis exists for a local cluster; the whole of §4 below |
| Behaviour above `maxReplicas: 4` | **out of scope** | The curve describes one autoscaler configuration, not the service |
| Reliability under instance loss | **out of scope** | A single-node local cluster cannot lose a node |

---

## 1. BLUF

The service serves everything offered up to **24<!--VR3--> req/s** at p95
304<!--VM9--> ms. Above that the queue grows faster than it drains: throughput
still rises to a peak of **31.3<!--VM5--> req/s** while p95 reaches
1,261<!--VM11--> ms, and at 40<!--VR5--> req/s the service breaks down —
22.9<!--VM6--> req/s served, about one request in seven unanswered.

**Throughput peaks after the system has already stopped being usable.** Sizing
on peak throughput would place the service at a rate where p95 is already over
a second; the usable ceiling is the latency knee, not the throughput one.

---

## 2. Test Setup & Scope

One unit is one `GET /` answered with status 200. Load is offered at a
**constant arrival rate** — requests depart on schedule regardless of whether
earlier ones have returned, so the measurement reflects the server rather than
the client's willingness to wait.

| | |
| :--- | :--- |
| Scope | 1–4 replicas, `200m` CPU each, HPA target 50 % utilisation |
| Unit cost of work | ~40 ms of server CPU per request |
| Measured range | 4<!--VR1--> – 40<!--VR5--> req/s offered, 45 s of load per point |
| Not covered | sustained load beyond 45 s, concurrent workloads, more than 4 replicas |

---

## 3. Efficiency Frontier

### 3.1 Run matrix

| Offered req/s | M1 served/s | D8 served share | M2 p95 | M3 unserved | Saturation signal |
| ---: | ---: | ---: | ---: | ---: | :--- |
| 4<!--VR1--> | 4.00<!--VM1--> | 100<!--VD1--> % | 103<!--VM7--> ms | 0<!--VM13--> % | headroom ᴿ |
| 12<!--VR2--> | 11.99<!--VM2--> | 100<!--VD2--> % | 188<!--VM8--> ms | 0<!--VM14--> % | headroom ᴿ |
| 24<!--VR3--> | 23.97<!--VM3--> | 100<!--VD3--> % | 304<!--VM9--> ms | 0<!--VM15--> % | at the knee ᴿ |
| 32<!--VR4--> | 31.33<!--VM5--> | 98<!--VD5--> % | 1,261<!--VM11--> ms | 0<!--VM17--> % | past the knee ᴿ |
| 40<!--VR5--> | 22.92<!--VM6--> | 57<!--VD6--> % | 10,001<!--VM12--> ms | 15.0<!--VM18--> % | saturated, CPU-bound ᴿ |

A sixth run at 32<!--VR4--> req/s is excluded: it ran against one replica instead of
four, which is a *Held constant*. See `execution.md` §3 note #05.

### 3.2 Chart

`charts/latency.svg` — `report-kit charts --all`, kind `line` in `charts/charts.yaml`, from a
CSV that transcribes §3.1 above and nothing else.

Two panels, because `ms` and `req/s` are different units and the renderer never
puts two scales on one frame. `M4` is absent on purpose: it counts scrape
targets rather than replicas and overshoots during rollover (`execution.md` §2),
so charting it would assert something the run did not measure. The `$/1k` column
is absent for the reason §4 is — there is no price basis.

The invalid run is absent too. A chart CSV holds only what is drawn, and the
ledger is where a point that ran is recorded whether or not it is read.

### 3.3 Knee · sweet spot · waste boundary

| | Rate | Read from |
| :--- | ---: | :--- |
| **Sweet spot** | 24<!--VR3--> req/s | last rate served in full, p95 still under half a second |
| **Knee** | between 24<!--VR3--> and 32<!--VR4--> req/s | p95 jumps four-fold across this interval |
| **Throughput peak** | ~31.3<!--VM5--> req/s | and already unusable — p95 1,261<!--VM11--> ms |
| **Waste boundary** | above 32<!--VR4--> req/s | throughput falls while cost stays |

### 3.4 Shape of the cost curve

Latency rises with offered load from the very first point — 103<!--VM7--> →
188<!--VM8--> → 304<!--VM9--> ms across 4<!--VR1--> → 12<!--VR2--> →
24<!--VR3--> req/s — so there is no flat region: every increment is
already costing latency. What changes past 24<!--VR3--> is only the rate of increase,
which is what makes the "knee" a range rather than a value.

### 3.5 Constraint ladder

**Tier 1 — CPU at the replica ceiling, between 24<!--VR3--> and 32<!--VR4--> req/s.** Every valid
point above 4<!--VR1--> req/s ran at `maxReplicas`, so past 24<!--VR3--> no further capacity
arrives and the queue grows without bound. Server-side service time (M6, which
excludes queueing) is flat between 12 and 24 and little more than doubles from
24 to 32 while p95 quadruples: the handler slows down under load, and the wait
in front of it grows faster still.

**No second tier is claimed.** The sweep ends where the first tier breaks, and
it cannot see what would bind after it.

---

## 4. Cost Structure

**Not measured.** This example runs on a local single-node cluster, which has
no price basis and no attribution tags. A dated price snapshot is one of the
things `methodology.md` §5 calls unrecoverable, so the honest entry is an empty
section with a reason rather than a plausible-looking table.

In a real report, §3.1's throughput column would become $/1M units here, and
the sweet spot would be re-read against cost rather than against latency alone
— the two rarely name the same row.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Do not size on peak throughput | usable ceiling 24<!--VR3--> req/s, not 31.3<!--VM5--> | §3.3 | — |
| The curve describes one HPA configuration | `maxReplicas: 4` | §3.5 | `scripts/manifests/mock-api.yaml` |
| 40<!--VR5--> req/s is breakdown, not capacity | 57<!--VD6--> % served | §3.1 | — |
| `M4` counts scrape targets, not replicas | can read above the max of 4 during rollover; no row here did | `execution.md` §1 register | `metrics.yaml` |

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
